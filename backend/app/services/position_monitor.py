"""
Position Monitor Service
Operation Phoenix | Trading Forge

Background asyncio task that runs every 30 seconds.
Checks open positions for stop-loss / take-profit / trailing-stop triggers
and fills pending limit orders when price conditions are met.

Locking: a Redis SET NX with a 25-second TTL prevents two instances of the
server from running the cycle concurrently.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlmodel import select

from app.core.database import async_session
from app.core.redis import get_redis_client
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.trade import Order, Trade, TradingPair
from app.models.wallet import VirtualWallet, WalletTransaction

logger = logging.getLogger(__name__)

LOCK_KEY = "position_monitor:lock"
LOCK_TTL_SECONDS = 25


# ============================================================================
# REDIS PRICE HELPER
# ============================================================================

async def _get_price_from_redis(redis, symbol: str) -> Optional[Decimal]:
    """Fetch the latest price for *symbol* from Redis.

    Redis stores JSON objects: {"exchange": "binance", "price": 65000.0, ...}
    Tries exchanges in order: binance → bybit → kraken.
    Returns None if no valid price is found.
    """
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
            logger.debug("Redis price fetch failed for %s: %s", key, exc)
    return None


# ============================================================================
# AUTO-CLOSE (stop-loss / take-profit / trailing-stop triggered)
# ============================================================================

async def execute_auto_close(
    order: Order,
    symbol: str,
    current_price: Decimal,
    reason: str,
) -> None:
    """Close an open position by creating a sell Trade and updating all
    accounting tables in a single atomic transaction.

    Args:
        order:         The Order whose position is being closed.
        symbol:        Trading symbol (e.g. 'BTCUSDT') for logging.
        current_price: The price at which the position is closed.
        reason:        One of: stop_loss_triggered, take_profit_triggered,
                       trailing_stop_triggered.
    """
    quantity = Decimal(str(order.quantity))
    total_value_dollars = quantity * current_price
    total_value_cents = int(total_value_dollars * 100)

    entry_price = Decimal(str(order.filled_avg_price or 0))
    if entry_price > 0 and quantity > 0:
        pnl_dollars = (current_price - entry_price) * quantity
        pnl_cents = int(pnl_dollars * 100)
        pnl_percent = float((pnl_dollars / (entry_price * quantity)) * 100)
    else:
        pnl_cents = 0
        pnl_percent = 0.0

    async with async_session() as session:
        try:
            # Create the closing trade (always a sell for a long position)
            close_trade = Trade(
                order_id=order.id,
                user_id=order.user_id,
                trading_pair_id=order.trading_pair_id,
                side="sell",
                quantity=float(quantity),
                price=float(current_price),
                total_value=total_value_cents,
                pnl=pnl_cents,
                pnl_percent=round(pnl_percent, 4),
                executed_at=datetime.now(timezone.utc),
            )
            session.add(close_trade)
            await session.flush()  # populate close_trade.id for WalletTransaction

            # Mark the original order as filled / auto-executed
            order_result = await session.execute(
                select(Order).where(Order.id == order.id)
            )
            db_order = order_result.scalar_one_or_none()
            if db_order:
                db_order.status = "filled"
                db_order.auto_executed = True
                db_order.auto_execute_reason = reason
                db_order.filled_at = datetime.now(timezone.utc)

            # Reduce / remove the portfolio holding
            holding_result = await session.execute(
                select(PortfolioHolding).where(
                    PortfolioHolding.user_id == order.user_id,
                    PortfolioHolding.trading_pair_id == order.trading_pair_id,
                )
            )
            holding = holding_result.scalar_one_or_none()
            if holding:
                new_qty = Decimal(str(holding.quantity)) - quantity
                if new_qty <= Decimal("0.00000001"):
                    await session.delete(holding)
                else:
                    holding.quantity = float(new_qty)
                    holding.current_price = float(current_price)
                    holding.total_value = int(new_qty * current_price * 100)

            # Credit proceeds to portfolio cash balance (cents)
            portfolio_result = await session.execute(
                select(Portfolio).where(Portfolio.user_id == order.user_id)
            )
            portfolio = portfolio_result.scalar_one_or_none()
            if portfolio:
                portfolio.cash_balance += total_value_cents
                portfolio.realized_pnl += pnl_cents

            # Update virtual wallet
            wallet_result = await session.execute(
                select(VirtualWallet).where(VirtualWallet.user_id == order.user_id)
            )
            wallet = wallet_result.scalar_one_or_none()
            balance_after = (wallet.balance + total_value_cents) if wallet else total_value_cents

            wallet_tx = WalletTransaction(
                user_id=order.user_id,
                type="trade_profit" if pnl_cents >= 0 else "trade_loss",
                amount=total_value_cents,
                balance_after=balance_after,
                reference_id=close_trade.id,
                description=f"Auto-close {symbol}: {reason}",
            )
            session.add(wallet_tx)

            if wallet:
                wallet.balance = balance_after

            await session.commit()

            logger.info(
                "Auto-close executed | order_id=%s user_id=%s symbol=%s "
                "reason=%s price=%s pnl_cents=%s",
                order.id, order.user_id, symbol, reason, current_price, pnl_cents,
            )

        except Exception as exc:
            await session.rollback()
            logger.error(
                "execute_auto_close failed | order_id=%s symbol=%s reason=%s error=%s",
                order.id, symbol, reason, exc,
                exc_info=True,
            )
            raise


# ============================================================================
# LIMIT FILL (pending limit order's price condition met)
# ============================================================================

async def execute_limit_fill(
    order: Order,
    symbol: str,
    current_price: Decimal,
) -> None:
    """Fill a pending limit order at its limit_price when the market price
    crosses the threshold.  If the user no longer has sufficient funds /
    holdings the order is cancelled instead of raising an exception.

    Args:
        order:         The pending Order to fill.
        symbol:        Trading symbol for logging.
        current_price: Current market price (used only for logging; fill
                       executes at order.limit_price).
    """
    # Fill at the limit price, not the current market price
    fill_price = Decimal(str(order.limit_price)) / 100  # cents → dollars
    quantity = Decimal(str(order.quantity))
    total_value_dollars = quantity * fill_price
    total_value_cents = int(total_value_dollars * 100)

    async with async_session() as session:
        try:
            # Re-fetch order inside this session to get fresh state
            order_result = await session.execute(
                select(Order).where(Order.id == order.id)
            )
            db_order = order_result.scalar_one_or_none()
            if not db_order or db_order.status != "pending":
                return  # already processed

            # Fetch portfolio for balance check
            portfolio_result = await session.execute(
                select(Portfolio).where(Portfolio.user_id == db_order.user_id)
            )
            portfolio = portfolio_result.scalar_one_or_none()
            if not portfolio:
                db_order.status = "cancelled"
                db_order.cancelled_at = datetime.now(timezone.utc)
                await session.commit()
                return

            # Balance / holdings validation
            if db_order.side == "buy":
                if portfolio.cash_balance < total_value_cents:
                    db_order.status = "cancelled"
                    db_order.cancelled_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.warning(
                        "Limit order cancelled (insufficient balance) | "
                        "order_id=%s symbol=%s", db_order.id, symbol,
                    )
                    return

            elif db_order.side == "sell":
                holding_check_result = await session.execute(
                    select(PortfolioHolding).where(
                        PortfolioHolding.user_id == db_order.user_id,
                        PortfolioHolding.trading_pair_id == db_order.trading_pair_id,
                    )
                )
                existing_holding = holding_check_result.scalar_one_or_none()
                if (
                    not existing_holding
                    or Decimal(str(existing_holding.quantity)) < quantity
                ):
                    db_order.status = "cancelled"
                    db_order.cancelled_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.warning(
                        "Limit order cancelled (insufficient holdings) | "
                        "order_id=%s symbol=%s", db_order.id, symbol,
                    )
                    return

            # Create trade record
            fill_trade = Trade(
                order_id=db_order.id,
                user_id=db_order.user_id,
                trading_pair_id=db_order.trading_pair_id,
                side=db_order.side,
                quantity=float(quantity),
                price=float(fill_price),
                total_value=total_value_cents,
                executed_at=datetime.now(timezone.utc),
            )
            session.add(fill_trade)
            await session.flush()  # populate fill_trade.id

            # Determine new order status: 'open' if risk management is attached
            has_risk = any([
                db_order.stop_price is not None,
                db_order.take_profit_price is not None,
                db_order.trailing_stop_percent is not None,
            ])
            db_order.status = "open" if has_risk else "filled"
            db_order.filled_at = datetime.now(timezone.utc)
            db_order.filled_avg_price = float(fill_price)
            db_order.filled_quantity = float(quantity)
            db_order.total_cost = total_value_cents

            if db_order.trailing_stop_percent is not None:
                # Seed the trailing-stop peak at the fill price
                db_order.trailing_stop_peak_price = int(fill_price * 100)

            # Update portfolio holdings
            holding_result = await session.execute(
                select(PortfolioHolding).where(
                    PortfolioHolding.user_id == db_order.user_id,
                    PortfolioHolding.trading_pair_id == db_order.trading_pair_id,
                )
            )
            holding = holding_result.scalar_one_or_none()

            if db_order.side == "buy":
                if holding:
                    old_cost = (
                        Decimal(str(holding.quantity))
                        * Decimal(str(holding.avg_entry_price))
                    )
                    new_qty = Decimal(str(holding.quantity)) + quantity
                    holding.quantity = float(new_qty)
                    holding.avg_entry_price = float(
                        (old_cost + quantity * fill_price) / new_qty
                    )
                    holding.current_price = float(fill_price)
                    holding.total_value = int(new_qty * fill_price * 100)
                else:
                    session.add(
                        PortfolioHolding(
                            user_id=db_order.user_id,
                            trading_pair_id=db_order.trading_pair_id,
                            quantity=float(quantity),
                            avg_entry_price=float(fill_price),
                            current_price=float(fill_price),
                            total_value=total_value_cents,
                        )
                    )
                portfolio.cash_balance -= total_value_cents

            elif db_order.side == "sell":
                if holding:
                    new_qty = Decimal(str(holding.quantity)) - quantity
                    if new_qty <= Decimal("0.00000001"):
                        await session.delete(holding)
                    else:
                        holding.quantity = float(new_qty)
                        holding.current_price = float(fill_price)
                        holding.total_value = int(new_qty * fill_price * 100)
                portfolio.cash_balance += total_value_cents

            # Update virtual wallet
            wallet_result = await session.execute(
                select(VirtualWallet).where(VirtualWallet.user_id == db_order.user_id)
            )
            wallet = wallet_result.scalar_one_or_none()

            # Buys debit cash; sells credit cash
            tx_amount = (
                -total_value_cents if db_order.side == "buy" else total_value_cents
            )
            balance_after = (wallet.balance + tx_amount) if wallet else tx_amount

            session.add(
                WalletTransaction(
                    user_id=db_order.user_id,
                    type="trade_loss" if db_order.side == "buy" else "trade_profit",
                    amount=tx_amount,
                    balance_after=balance_after,
                    reference_id=fill_trade.id,
                    description=f"Limit fill {symbol} {db_order.side.upper()}",
                )
            )

            if wallet:
                wallet.balance = balance_after

            await session.commit()

            logger.info(
                "Limit order filled | order_id=%s user_id=%s symbol=%s "
                "side=%s fill_price=%s market_price=%s",
                db_order.id, db_order.user_id, symbol,
                db_order.side, fill_price, current_price,
            )

        except Exception as exc:
            await session.rollback()
            logger.error(
                "execute_limit_fill failed | order_id=%s symbol=%s error=%s",
                order.id, symbol, exc,
                exc_info=True,
            )
            raise


# ============================================================================
# MONITOR CYCLE
# ============================================================================

async def run_position_monitor_cycle() -> None:
    """Single monitoring cycle.

    1. Acquire a 25-second Redis distributed lock to prevent concurrent runs.
    2. Fetch all 'open' and 'pending' orders from the database.
    3. For each order, get the current market price and evaluate triggers.
    4. Exceptions per individual order are caught and logged; the cycle
       continues with the next order rather than aborting.
    """
    redis = get_redis_client()
    if not redis:
        logger.warning("Position monitor: Redis unavailable, skipping cycle")
        return

    # Distributed lock — prevents two app instances running the cycle at once
    acquired = await redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_SECONDS)
    if not acquired:
        logger.debug("Position monitor: lock held by another instance, skipping")
        return

    now_utc = datetime.now(timezone.utc)

    # Fetch all actionable orders in one query
    async with async_session() as session:
        try:
            result = await session.execute(
                select(Order, TradingPair.symbol)
                .join(TradingPair, Order.trading_pair_id == TradingPair.id)
                .where(Order.status.in_(["open", "pending"]))
            )
            orders_with_symbols = [(row[0], row[1]) for row in result.all()]
        except Exception as exc:
            logger.error("Position monitor: failed to fetch orders: %s", exc)
            return

    logger.debug("Position monitor: evaluating %d orders", len(orders_with_symbols))

    for order, symbol in orders_with_symbols:
        try:
            current_price = await _get_price_from_redis(redis, symbol)
            if current_price is None:
                logger.debug(
                    "Position monitor: no price for %s, skipping order %s",
                    symbol, order.id,
                )
                continue

            # ---- Open position: check stop-loss / take-profit / trailing stop ----
            if order.status == "open":
                await _evaluate_open_order(order, symbol, current_price)

            # ---- Pending limit order: check fill / expiry conditions ----
            elif order.status == "pending":
                await _evaluate_pending_order(order, symbol, current_price, now_utc)

        except Exception as exc:
            logger.error(
                "Position monitor: unhandled error for order %s (%s): %s",
                order.id, symbol, exc,
                exc_info=True,
            )
            continue  # never let one order crash the entire cycle


async def _evaluate_open_order(
    order: Order,
    symbol: str,
    current_price: Decimal,
) -> None:
    """Evaluate stop-loss, take-profit, and trailing-stop conditions for an
    open position.  Executes at most one action per call."""

    # ---- Trailing stop ----
    if order.trailing_stop_percent is not None:
        current_price_cents = int(current_price * 100)
        peak = order.trailing_stop_peak_price or 0

        # Update peak if price has risen
        if current_price_cents > peak:
            async with async_session() as session:
                try:
                    order_result = await session.execute(
                        select(Order).where(Order.id == order.id)
                    )
                    db_order = order_result.scalar_one_or_none()
                    if db_order and db_order.status == "open":
                        db_order.trailing_stop_peak_price = current_price_cents
                        await session.commit()
                        peak = current_price_cents
                except Exception as exc:
                    await session.rollback()
                    logger.error(
                        "Failed to update trailing_stop_peak_price for order %s: %s",
                        order.id, exc,
                    )

        trailing_stop_cents = int(peak * (1 - order.trailing_stop_percent / 100))
        if current_price_cents <= trailing_stop_cents:
            await execute_auto_close(
                order, symbol, current_price, "trailing_stop_triggered"
            )
            return

    # ---- Stop-loss ----
    if order.stop_price is not None:
        stop_price = Decimal(str(order.stop_price))
        if current_price <= stop_price:
            await execute_auto_close(
                order, symbol, current_price, "stop_loss_triggered"
            )
            return

    # ---- Take-profit ----
    if order.take_profit_price is not None:
        take_profit = Decimal(str(order.take_profit_price))
        if current_price >= take_profit:
            await execute_auto_close(
                order, symbol, current_price, "take_profit_triggered"
            )
            return


async def _evaluate_pending_order(
    order: Order,
    symbol: str,
    current_price: Decimal,
    now_utc: datetime,
) -> None:
    """Evaluate expiry and fill conditions for a pending limit order."""

    # ---- Check expiry first ----
    if order.expires_at is not None:
        expires_at = order.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if now_utc > expires_at:
            async with async_session() as session:
                try:
                    order_result = await session.execute(
                        select(Order).where(Order.id == order.id)
                    )
                    db_order = order_result.scalar_one_or_none()
                    if db_order and db_order.status == "pending":
                        db_order.status = "cancelled"
                        db_order.cancelled_at = now_utc
                        await session.commit()
                        logger.info(
                            "Limit order expired | order_id=%s user_id=%s symbol=%s",
                            db_order.id, db_order.user_id, symbol,
                        )
                except Exception as exc:
                    await session.rollback()
                    logger.error(
                        "Failed to expire order %s: %s", order.id, exc
                    )
            return

    # ---- Check limit fill condition ----
    if order.order_type not in ("limit", "stop_limit", "take_profit"):
        return
    if order.limit_price is None:
        return

    limit_price_dollars = Decimal(str(order.limit_price)) / 100

    should_fill = (
        (order.side == "buy" and current_price <= limit_price_dollars)
        or (order.side == "sell" and current_price >= limit_price_dollars)
    )

    if should_fill:
        await execute_limit_fill(order, symbol, current_price)


# ============================================================================
# ENTRY POINT (infinite loop)
# ============================================================================

async def start_position_monitor() -> None:
    """Infinite loop: run one monitoring cycle every 30 seconds.
    Exceptions in a full cycle are caught and logged without crashing the task.
    """
    logger.info("Position monitor started (30-second interval)")
    while True:
        try:
            await run_position_monitor_cycle()
        except Exception as exc:
            logger.error(
                "Position monitor cycle error: %s", exc, exc_info=True
            )
        await asyncio.sleep(30)
