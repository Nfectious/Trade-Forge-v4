"""
Contest Engine Service
Handles rankings calculation, contest finalization, and cancellation.
All functions accept an AsyncSession and operate atomically.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.redis import get_redis_client
from app.models.contest import Contest, ContestEntry, ContestPortfolio, ContestTrade
from app.models.wallet import VirtualWallet, WalletTransaction

logger = logging.getLogger(__name__)


# ============================================================================
# PRICE HELPER
# ============================================================================

async def _get_price(symbol: str) -> Optional[Decimal]:
    """Fetch current price from Redis.
    Tries binance → bybit → kraken; returns None if all miss.
    Redis stores JSON: {"exchange": "binance", "price": 65000.0, ...}
    """
    redis = get_redis_client()
    if not redis:
        return None

    for exchange in ("binance", "bybit", "kraken"):
        key = f"price:{exchange}:{symbol.upper()}"
        try:
            data = await redis.get(key)
            if data:
                parsed = json.loads(data)
                price = parsed.get("price") or parsed.get("p")
                if price is not None:
                    return Decimal(str(price))
        except Exception as exc:
            logger.debug("Price lookup failed for %s: %s", key, exc)

    return None


# ============================================================================
# RANKING CALCULATION
# ============================================================================

async def calculate_contest_rankings(
    contest_id: UUID,
    session: AsyncSession,
) -> None:
    """Recalculate portfolio values and ranking for all participants.

    Steps:
      1. Load all ContestPortfolios for this contest.
      2. For each portfolio, aggregate net holdings from ContestTrades.
      3. Price each holding via Redis.
      4. Update total_value = cash_balance + holdings_value_cents.
      5. Rank portfolios by total_value descending.
      6. If contest is 'completed', flush results into ContestEntry final stats.
    """
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        logger.warning("calculate_contest_rankings: contest %s not found", contest_id)
        return

    portfolios_result = await session.execute(
        select(ContestPortfolio).where(ContestPortfolio.contest_id == contest_id)
    )
    portfolios = list(portfolios_result.scalars().all())

    if not portfolios:
        return

    for portfolio in portfolios:
        # Aggregate net holdings from trades (buy qty - sell qty per symbol)
        trades_result = await session.execute(
            select(ContestTrade).where(
                ContestTrade.contest_portfolio_id == portfolio.id
            )
        )
        trades = trades_result.scalars().all()

        # holdings[symbol] = net quantity (Decimal)
        holdings: dict[str, Decimal] = {}
        for trade in trades:
            sym = trade.symbol.upper()
            if sym not in holdings:
                holdings[sym] = Decimal("0")
            qty = Decimal(str(trade.quantity))
            if trade.side == "buy":
                holdings[sym] += qty
            elif trade.side == "sell":
                holdings[sym] -= qty

        # Value holdings at current market prices
        holdings_value_cents = 0
        for symbol, net_qty in holdings.items():
            if net_qty <= Decimal("0.00000001"):
                continue
            price = await _get_price(symbol)
            if price is not None:
                holdings_value_cents += int(net_qty * price * 100)
            else:
                logger.debug(
                    "No Redis price for %s during ranking (contest %s)",
                    symbol, contest_id,
                )

        total_value = portfolio.cash_balance + holdings_value_cents
        portfolio.total_value = total_value
        portfolio.unrealized_pnl = total_value - contest.starting_balance
        portfolio.last_calculated = datetime.now(timezone.utc)

    await session.flush()

    # Rank by total_value descending
    portfolios.sort(key=lambda p: p.total_value, reverse=True)
    for rank, portfolio in enumerate(portfolios, start=1):
        portfolio.rank = rank

    await session.flush()

    # When contest is completed, write final stats into ContestEntry rows
    if contest.status == "completed":
        for portfolio in portfolios:
            entry_result = await session.execute(
                select(ContestEntry).where(
                    ContestEntry.contest_id == contest_id,
                    ContestEntry.user_id == portfolio.user_id,
                )
            )
            entry = entry_result.scalar_one_or_none()
            if entry:
                entry.final_rank = portfolio.rank
                entry.final_value = portfolio.total_value
                entry.final_pnl = portfolio.unrealized_pnl
                entry.final_pnl_percent = (
                    round(
                        float(portfolio.unrealized_pnl / contest.starting_balance * 100),
                        4,
                    )
                    if contest.starting_balance > 0
                    else 0.0
                )

    await session.commit()

    logger.info(
        "Rankings calculated: contest=%s participants=%d", contest_id, len(portfolios)
    )


# ============================================================================
# CONTEST FINALIZATION
# ============================================================================

async def finalize_contest(
    contest_id: UUID,
    session: AsyncSession,
) -> dict:
    """Close a contest, determine the winner, and distribute prizes.

    Steps:
      1. Set contest.status = 'completed'.
      2. Run final rankings.
      3. Identify rank-1 winner.
      4. Award prize_pool (minus platform commission) to winner's VirtualWallet.
      5. Create WalletTransaction record.
      6. Set contest.winner_id and contest.prize_distributed.

    Returns a summary dict with winner info and prize details.
    """
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise ValueError(f"Contest {contest_id} not found")

    if contest.status == "completed":
        raise ValueError(f"Contest {contest_id} is already completed")

    contest.status = "completed"
    contest.updated_at = datetime.now(timezone.utc)
    await session.flush()

    # Final ranking calculation (also writes ContestEntry final stats)
    await calculate_contest_rankings(contest_id, session)

    # Determine winner (rank 1)
    winner_portfolio_result = await session.execute(
        select(ContestPortfolio)
        .where(ContestPortfolio.contest_id == contest_id)
        .order_by(ContestPortfolio.total_value.desc())
        .limit(1)
    )
    winner_portfolio = winner_portfolio_result.scalar_one_or_none()

    prize_awarded_cents = 0
    winner_user_id: Optional[UUID] = None

    if winner_portfolio:
        winner_user_id = winner_portfolio.user_id
        contest.winner_id = winner_user_id

        if contest.prize_pool > 0 and not contest.prize_distributed:
            # Deduct platform commission
            commission_cents = int(
                contest.prize_pool * (contest.platform_commission_percent / 100)
            )
            prize_awarded_cents = contest.prize_pool - commission_cents

            # Fetch winner wallet
            wallet_result = await session.execute(
                select(VirtualWallet).where(VirtualWallet.user_id == winner_user_id)
            )
            wallet = wallet_result.scalar_one_or_none()

            if wallet:
                balance_after = wallet.balance + prize_awarded_cents
                wallet.balance = balance_after

                session.add(
                    WalletTransaction(
                        user_id=winner_user_id,
                        type="contest_prize",
                        amount=prize_awarded_cents,
                        balance_after=balance_after,
                        reference_id=contest_id,
                        description=(
                            f"Contest prize: {contest.name} — "
                            f"1st place (after {contest.platform_commission_percent:.1f}% commission)"
                        ),
                    )
                )
                contest.prize_distributed = True
                logger.info(
                    "Prize awarded: contest=%s winner=%s amount_cents=%d",
                    contest_id, winner_user_id, prize_awarded_cents,
                )
            else:
                logger.error(
                    "finalize_contest: wallet not found for winner %s", winner_user_id
                )

    contest.updated_at = datetime.now(timezone.utc)
    await session.commit()

    logger.info(
        "Contest finalized: id=%s winner=%s prize_awarded_cents=%d",
        contest_id, winner_user_id, prize_awarded_cents,
    )

    return {
        "contest_id": str(contest_id),
        "status": "completed",
        "winner_user_id": str(winner_user_id) if winner_user_id else None,
        "prize_awarded_cents": prize_awarded_cents,
        "prize_awarded_dollars": prize_awarded_cents / 100,
    }


# ============================================================================
# CONTEST CANCELLATION
# ============================================================================

async def _issue_stripe_refund(stripe_payment_intent_id: str, user_id: UUID) -> dict:
    """Placeholder for Stripe refund logic (implemented in Phase 5).
    Returns a refund status dict for the caller to include in the response.
    """
    logger.info(
        "Stripe refund queued (placeholder): pi=%s user=%s",
        stripe_payment_intent_id, user_id,
    )
    return {
        "stripe_payment_intent_id": stripe_payment_intent_id,
        "user_id": str(user_id),
        "refund_status": "queued",
        "note": "Stripe refund will be processed when payment integration is complete",
    }


async def cancel_contest(
    contest_id: UUID,
    session: AsyncSession,
) -> dict:
    """Cancel a contest and initiate refunds for all paid entries.

    Steps:
      1. Set contest.status = 'cancelled'.
      2. For each paid entry: queue Stripe refund.
      3. Set all ContestEntry.status = 'cancelled'.

    Returns a summary dict with refund statuses.
    """
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise ValueError(f"Contest {contest_id} not found")

    if contest.status in ("completed", "cancelled"):
        raise ValueError(f"Contest {contest_id} is already {contest.status}")

    contest.status = "cancelled"
    contest.updated_at = datetime.now(timezone.utc)
    await session.flush()

    entries_result = await session.execute(
        select(ContestEntry).where(ContestEntry.contest_id == contest_id)
    )
    entries = entries_result.scalars().all()

    refund_statuses = []
    for entry in entries:
        entry.status = "cancelled"

        if (
            entry.payment_status == "paid"
            and entry.stripe_payment_intent_id
        ):
            refund_info = await _issue_stripe_refund(
                entry.stripe_payment_intent_id, entry.user_id
            )
            entry.payment_status = "refunded"
            refund_statuses.append(refund_info)

    await session.commit()

    logger.info(
        "Contest cancelled: id=%s entries_cancelled=%d refunds_queued=%d",
        contest_id, len(entries), len(refund_statuses),
    )

    return {
        "contest_id": str(contest_id),
        "status": "cancelled",
        "entries_cancelled": len(entries),
        "refunds": refund_statuses,
    }
