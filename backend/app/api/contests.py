"""
Contest API routes
Public browsing, user enrollment, contest trading, and admin management.

Two routers exported:
  router       — mounted at /contests (public + authenticated user endpoints)
  admin_router — mounted at /admin/contests (admin-only management endpoints)
"""

import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_admin,
)
from app.core.redis import get_redis_client
from app.core.security import limiter
from app.models.contest import (
    Contest,
    ContestCreate,
    ContestEntry,
    ContestPortfolio,
    ContestTrade,
    ContestTradeCreate,
    ContestUpdate,
    JoinPrivateRequest,
)
from app.models.user import User, UserProfile
from app.services.contest_engine import (
    calculate_contest_rankings,
    cancel_contest,
    finalize_contest,
)

logger = logging.getLogger(__name__)

router = APIRouter()
admin_router = APIRouter(prefix="/admin/contests", tags=["Admin - Contests"])


# ============================================================================
# PRICE HELPER (local; same pattern as trading.py)
# ============================================================================

async def _get_price(symbol: str) -> Optional[Decimal]:
    """Get current price from Redis. Returns None if unavailable."""
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
            logger.debug("Price fetch failed %s: %s", key, exc)
    return None


# ============================================================================
# PUBLIC ENDPOINTS
# ============================================================================

@router.get("")
@limiter.limit("120/minute")
async def list_contests(
    request: Request,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    status_filter: str = Query(default="active", alias="status"),
    type_filter: str = Query(default="all", alias="type"),
    session: AsyncSession = Depends(get_session),
):
    """List public contests with pagination.

    Query params:
      status: upcoming | active | completed | all
      type:   free | paid | all
    """
    stmt = select(Contest).where(Contest.visibility == "public")

    if status_filter != "all":
        stmt = stmt.where(Contest.status == status_filter)

    if type_filter != "all":
        stmt = stmt.where(Contest.type == type_filter)

    stmt = stmt.order_by(Contest.start_time.asc())

    # Count total for pagination metadata
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar() or 0

    offset = (page - 1) * limit
    paginated_stmt = stmt.offset(offset).limit(limit)
    contests_result = await session.execute(paginated_stmt)
    contests = contests_result.scalars().all()

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit if limit > 0 else 0,
        "contests": [
            {
                "id": str(c.id),
                "name": c.name,
                "description": c.description,
                "type": c.type,
                "status": c.status,
                "entry_fee": c.entry_fee,
                "prize_pool": c.prize_pool / 100,      # cents → dollars
                "starting_balance": c.starting_balance / 100,
                "start_time": c.start_time.isoformat(),
                "end_time": c.end_time.isoformat(),
                "registration_deadline": (
                    c.registration_deadline.isoformat()
                    if c.registration_deadline else None
                ),
                "current_participants": c.current_participants,
                "max_participants": c.max_participants,
                "visibility": c.visibility,
            }
            for c in contests
        ],
    }


@router.get("/my")
@limiter.limit("60/minute")
async def get_my_contests(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """List all contests the current user is enrolled in, with rank and P&L."""
    entries_result = await session.execute(
        select(ContestEntry, Contest)
        .join(Contest, ContestEntry.contest_id == Contest.id)
        .where(
            ContestEntry.user_id == current_user.id,
            ContestEntry.status == "active",
        )
        .order_by(ContestEntry.joined_at.desc())
    )
    rows = entries_result.all()

    output = []
    for entry, contest in rows:
        portfolio_result = await session.execute(
            select(ContestPortfolio).where(
                ContestPortfolio.id == entry.contest_portfolio_id
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()

        output.append(
            {
                "contest_id": str(contest.id),
                "contest_name": contest.name,
                "status": contest.status,
                "joined_at": entry.joined_at.isoformat(),
                "rank": portfolio.rank if portfolio else None,
                "total_value": portfolio.total_value / 100 if portfolio else None,
                "unrealized_pnl": portfolio.unrealized_pnl / 100 if portfolio else None,
                "total_trades": portfolio.total_trades if portfolio else 0,
                "start_time": contest.start_time.isoformat(),
                "end_time": contest.end_time.isoformat(),
                "final_rank": entry.final_rank,
                "final_pnl": entry.final_pnl / 100 if entry.final_pnl else None,
                "final_pnl_percent": entry.final_pnl_percent,
            }
        )

    return output


# IMPORTANT: /my must be defined BEFORE /{contest_id} so FastAPI matches the
# literal path first.

@router.get("/{contest_id}")
@limiter.limit("120/minute")
async def get_contest(
    request: Request,
    contest_id: UUID,
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_session),
):
    """Full contest details. Includes top-5 leaderboard preview and
    whether the requesting user is enrolled."""
    contest_result = await session.execute(
        select(Contest).where(
            Contest.id == contest_id,
            Contest.visibility == "public",
        )
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

    # Check user enrollment
    is_enrolled = False
    user_rank: Optional[int] = None
    if current_user:
        entry_result = await session.execute(
            select(ContestEntry).where(
                ContestEntry.contest_id == contest_id,
                ContestEntry.user_id == current_user.id,
                ContestEntry.status == "active",
            )
        )
        entry = entry_result.scalar_one_or_none()
        if entry and entry.contest_portfolio_id:
            is_enrolled = True
            portfolio_result = await session.execute(
                select(ContestPortfolio).where(
                    ContestPortfolio.id == entry.contest_portfolio_id
                )
            )
            portfolio = portfolio_result.scalar_one_or_none()
            user_rank = portfolio.rank if portfolio else None

    # Top-5 leaderboard preview (active or completed contests)
    leaderboard_preview = []
    if contest.status in ("active", "completed"):
        top_result = await session.execute(
            select(ContestPortfolio, UserProfile.nickname)
            .join(
                UserProfile,
                ContestPortfolio.user_id == UserProfile.user_id,
                isouter=True,
            )
            .where(ContestPortfolio.contest_id == contest_id)
            .order_by(ContestPortfolio.total_value.desc())
            .limit(5)
        )
        for portfolio, nickname in top_result.all():
            leaderboard_preview.append(
                {
                    "rank": portfolio.rank,
                    "nickname": nickname or "Anonymous",
                    "total_value": portfolio.total_value / 100,
                    "unrealized_pnl": portfolio.unrealized_pnl / 100,
                }
            )

    return {
        "id": str(contest.id),
        "name": contest.name,
        "description": contest.description,
        "type": contest.type,
        "status": contest.status,
        "visibility": contest.visibility,
        "entry_fee": contest.entry_fee,
        "prize_pool": contest.prize_pool / 100,
        "starting_balance": contest.starting_balance / 100,
        "start_time": contest.start_time.isoformat(),
        "end_time": contest.end_time.isoformat(),
        "registration_deadline": (
            contest.registration_deadline.isoformat()
            if contest.registration_deadline else None
        ),
        "current_participants": contest.current_participants,
        "max_participants": contest.max_participants,
        "min_participants": contest.min_participants,
        "allowed_assets": contest.allowed_assets,
        "max_trades_per_day": contest.max_trades_per_day,
        "is_enrolled": is_enrolled,
        "user_rank": user_rank,
        "winner_id": str(contest.winner_id) if contest.winner_id else None,
        "leaderboard_preview": leaderboard_preview,
    }


# ============================================================================
# AUTHENTICATED USER ENDPOINTS
# ============================================================================

async def _join_contest_logic(
    contest: Contest,
    current_user: User,
    session: AsyncSession,
) -> dict:
    """Shared enrollment logic used by both join and join-private."""
    now = datetime.now(timezone.utc)

    if contest.status != "upcoming":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Contest is not open for registration (status: {contest.status})",
        )

    if contest.registration_deadline and now > contest.registration_deadline.replace(
        tzinfo=timezone.utc
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration deadline has passed",
        )

    if (
        contest.max_participants is not None
        and contest.current_participants >= contest.max_participants
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Contest is full",
        )

    # Check not already enrolled
    existing_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest.id,
            ContestEntry.user_id == current_user.id,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already enrolled in this contest",
        )

    if contest.type == "paid":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Paid contests require a Stripe payment flow (available soon)",
        )

    # Create contest portfolio with contest's starting balance
    portfolio = ContestPortfolio(
        contest_id=contest.id,
        user_id=current_user.id,
        cash_balance=contest.starting_balance,
        total_value=contest.starting_balance,
    )
    session.add(portfolio)
    await session.flush()  # populate portfolio.id

    # Create contest entry linking user, contest, and portfolio
    entry = ContestEntry(
        contest_id=contest.id,
        user_id=current_user.id,
        contest_portfolio_id=portfolio.id,
        payment_status="free",
    )
    session.add(entry)

    # Increment participant count
    contest.current_participants += 1
    contest.updated_at = now

    # get_session commits on successful response

    return {
        "contest_id": str(contest.id),
        "contest_name": contest.name,
        "entry_id": str(entry.id),
        "portfolio": {
            "id": str(portfolio.id),
            "cash_balance": portfolio.cash_balance / 100,
            "total_value": portfolio.total_value / 100,
        },
        "message": f"Successfully joined '{contest.name}'",
    }


@router.post("/{contest_id}/join")
@limiter.limit("10/minute")
async def join_contest(
    request: Request,
    contest_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Enroll in a free public contest.
    Paid contests require a separate Stripe payment flow."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    if contest.visibility == "private":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This is a private contest. Use the join-private endpoint with an invite code.",
        )

    return await _join_contest_logic(contest, current_user, session)


@router.post("/{contest_id}/join-private")
@limiter.limit("10/minute")
async def join_private_contest(
    request: Request,
    contest_id: UUID,
    body: JoinPrivateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Enroll in a private contest by providing the invite code."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contest not found")

    if contest.invite_code != body.invite_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid invite code",
        )

    return await _join_contest_logic(contest, current_user, session)


@router.get("/{contest_id}/my-portfolio")
@limiter.limit("60/minute")
async def get_my_contest_portfolio(
    request: Request,
    contest_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """User's contest portfolio: cash, holdings, P&L, rank."""
    entry_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest_id,
            ContestEntry.user_id == current_user.id,
            ContestEntry.status == "active",
        )
    )
    entry = entry_result.scalar_one_or_none()
    if not entry or not entry.contest_portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="You are not enrolled in this contest",
        )

    portfolio_result = await session.execute(
        select(ContestPortfolio).where(
            ContestPortfolio.id == entry.contest_portfolio_id
        )
    )
    portfolio = portfolio_result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portfolio not found",
        )

    # Aggregate net holdings from contest trades
    trades_result = await session.execute(
        select(ContestTrade)
        .where(ContestTrade.contest_portfolio_id == portfolio.id)
        .order_by(ContestTrade.executed_at.asc())
    )
    all_trades = trades_result.scalars().all()

    # Compute: net quantity and weighted avg entry price per symbol
    buy_qty: dict[str, Decimal] = {}
    buy_cost: dict[str, Decimal] = {}   # cents
    sell_qty: dict[str, Decimal] = {}

    for trade in all_trades:
        sym = trade.symbol.upper()
        qty = Decimal(str(trade.quantity))
        # trade.price is in cents (BIGINT)
        cost_cents = qty * Decimal(str(trade.price))

        if trade.side == "buy":
            buy_qty[sym] = buy_qty.get(sym, Decimal("0")) + qty
            buy_cost[sym] = buy_cost.get(sym, Decimal("0")) + cost_cents
        elif trade.side == "sell":
            sell_qty[sym] = sell_qty.get(sym, Decimal("0")) + qty

    holdings_out = []
    holdings_value_cents = 0

    for symbol in buy_qty:
        net_qty = buy_qty[symbol] - sell_qty.get(symbol, Decimal("0"))
        if net_qty <= Decimal("0.00000001"):
            continue

        total_buy_qty = buy_qty[symbol]
        avg_entry_price_cents = (
            buy_cost[symbol] / total_buy_qty if total_buy_qty > 0 else Decimal("0")
        )
        avg_entry_price_dollars = float(avg_entry_price_cents / 100)

        current_price = await _get_price(symbol)
        current_price_f = float(current_price) if current_price is not None else avg_entry_price_dollars

        current_value_cents = int(net_qty * Decimal(str(current_price_f)) * 100)
        holdings_value_cents += current_value_cents

        entry_value_cents = int(net_qty * avg_entry_price_cents)
        unrealized_pnl_cents = current_value_cents - entry_value_cents
        pnl_pct = (
            float(unrealized_pnl_cents / entry_value_cents * 100)
            if entry_value_cents > 0 else 0.0
        )

        holdings_out.append(
            {
                "symbol": symbol,
                "quantity": float(net_qty),
                "avg_entry_price": avg_entry_price_dollars,
                "current_price": current_price_f,
                "current_value": current_value_cents / 100,
                "unrealized_pnl": unrealized_pnl_cents / 100,
                "unrealized_pnl_percent": round(pnl_pct, 4),
            }
        )

    total_value_cents = portfolio.cash_balance + holdings_value_cents
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    starting_balance = contest.starting_balance if contest else portfolio.total_value
    overall_pnl_cents = total_value_cents - starting_balance

    return {
        "contest_id": str(contest_id),
        "portfolio_id": str(portfolio.id),
        "rank": portfolio.rank,
        "cash_balance": portfolio.cash_balance / 100,
        "holdings": holdings_out,
        "holdings_value": holdings_value_cents / 100,
        "total_value": total_value_cents / 100,
        "unrealized_pnl": overall_pnl_cents / 100,
        "unrealized_pnl_percent": (
            round(float(overall_pnl_cents / starting_balance * 100), 4)
            if starting_balance > 0 else 0.0
        ),
        "total_trades": portfolio.total_trades,
    }


@router.post("/{contest_id}/trade")
@limiter.limit("30/minute")
async def place_contest_trade(
    request: Request,
    contest_id: UUID,
    order: ContestTradeCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Place a trade within the contest using contest portfolio funds.
    Does NOT touch the user's main wallet.
    """
    if order.side not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'buy' or 'sell'",
        )

    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

    if contest.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Contest is not active (status: {contest.status})",
        )

    symbol = order.symbol.upper()

    # Validate allowed assets
    if contest.allowed_assets:
        allowed = [s.strip().upper() for s in contest.allowed_assets.split(",")]
        if symbol not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{symbol} is not allowed in this contest. Allowed: {', '.join(allowed)}",
            )

    # Verify enrollment
    entry_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest_id,
            ContestEntry.user_id == current_user.id,
            ContestEntry.status == "active",
        )
    )
    entry = entry_result.scalar_one_or_none()
    if not entry or not entry.contest_portfolio_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not enrolled in this contest",
        )

    portfolio_result = await session.execute(
        select(ContestPortfolio).where(
            ContestPortfolio.id == entry.contest_portfolio_id
        )
    )
    portfolio = portfolio_result.scalar_one_or_none()
    if not portfolio:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest portfolio not found",
        )

    # Check max_trades_per_day
    if contest.max_trades_per_day is not None:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        count_result = await session.execute(
            select(func.count()).select_from(ContestTrade).where(
                ContestTrade.contest_portfolio_id == portfolio.id,
                ContestTrade.executed_at >= today_start,
            )
        )
        trades_today = count_result.scalar() or 0
        if trades_today >= contest.max_trades_per_day:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Daily trade limit of {contest.max_trades_per_day} reached",
            )

    # Get current market price
    current_price = await _get_price(symbol)
    if current_price is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market price for {symbol} is currently unavailable",
        )

    price_cents = int(current_price * 100)
    quantity = Decimal(str(order.quantity))
    total_value_cents = int(quantity * Decimal(str(price_cents)))

    if order.side == "buy":
        if portfolio.cash_balance < total_value_cents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient contest balance. "
                    f"Required: ${total_value_cents / 100:,.2f}, "
                    f"Available: ${portfolio.cash_balance / 100:,.2f}"
                ),
            )
        portfolio.cash_balance -= total_value_cents

    elif order.side == "sell":
        # Verify sufficient net holdings
        trades_result = await session.execute(
            select(ContestTrade).where(
                ContestTrade.contest_portfolio_id == portfolio.id,
                ContestTrade.symbol == symbol,
            )
        )
        past_trades = trades_result.scalars().all()

        net_qty = Decimal("0")
        for trade in past_trades:
            if trade.side == "buy":
                net_qty += Decimal(str(trade.quantity))
            elif trade.side == "sell":
                net_qty -= Decimal(str(trade.quantity))

        if net_qty < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient {symbol} holdings. "
                    f"Required: {float(quantity):.8f}, "
                    f"Available: {float(net_qty):.8f}"
                ),
            )
        portfolio.cash_balance += total_value_cents

    # Create contest trade record
    stop_loss_cents = (
        int(order.stop_loss_price * 100) if order.stop_loss_price else None
    )
    take_profit_cents = (
        int(order.take_profit_price * 100) if order.take_profit_price else None
    )

    trade = ContestTrade(
        contest_id=contest_id,
        user_id=current_user.id,
        contest_portfolio_id=portfolio.id,
        symbol=symbol,
        side=order.side,
        quantity=float(quantity),
        price=price_cents,
        total_value=total_value_cents,
        stop_loss_price=stop_loss_cents,
        take_profit_price=take_profit_cents,
        executed_at=datetime.now(timezone.utc),
    )
    session.add(trade)

    portfolio.total_trades += 1

    # get_session commits on response

    return {
        "success": True,
        "symbol": symbol,
        "side": order.side,
        "quantity": float(quantity),
        "price": float(current_price),
        "total_value": total_value_cents / 100,
        "cash_balance_remaining": portfolio.cash_balance / 100,
        "message": (
            f"{order.side.capitalize()} {float(quantity):.8f} {symbol} "
            f"at ${float(current_price):,.2f}"
        ),
    }


@router.get("/{contest_id}/leaderboard")
@limiter.limit("60/minute")
async def get_leaderboard(
    request: Request,
    contest_id: UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Ranked participant list with P&L and trade counts."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

    offset = (page - 1) * limit

    rows_result = await session.execute(
        select(ContestPortfolio, UserProfile.nickname)
        .join(
            UserProfile,
            ContestPortfolio.user_id == UserProfile.user_id,
            isouter=True,
        )
        .where(ContestPortfolio.contest_id == contest_id)
        .order_by(ContestPortfolio.total_value.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = rows_result.all()

    # Total participants for pagination
    count_result = await session.execute(
        select(func.count()).select_from(ContestPortfolio).where(
            ContestPortfolio.contest_id == contest_id
        )
    )
    total = count_result.scalar() or 0

    starting_balance = contest.starting_balance

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "contest_status": contest.status,
        "entries": [
            {
                "rank": portfolio.rank or (offset + idx + 1),
                "nickname": nickname or "Anonymous",
                "total_value": portfolio.total_value / 100,
                "pnl": portfolio.unrealized_pnl / 100,
                "pnl_percent": (
                    round(
                        float(portfolio.unrealized_pnl / starting_balance * 100),
                        4,
                    )
                    if starting_balance > 0 else 0.0
                ),
                "trades": portfolio.total_trades,
                "last_updated": portfolio.last_calculated.isoformat(),
            }
            for idx, (portfolio, nickname) in enumerate(rows)
        ],
    }


@router.delete("/{contest_id}/withdraw")
@limiter.limit("10/minute")
async def withdraw_from_contest(
    request: Request,
    contest_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Withdraw from a contest. Only allowed while contest is 'upcoming'."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

    if contest.status != "upcoming":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Withdrawal is only allowed before the contest starts "
                f"(current status: {contest.status})"
            ),
        )

    entry_result = await session.execute(
        select(ContestEntry).where(
            ContestEntry.contest_id == contest_id,
            ContestEntry.user_id == current_user.id,
            ContestEntry.status == "active",
        )
    )
    entry = entry_result.scalar_one_or_none()
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not enrolled in this contest",
        )

    refund_info = None
    if entry.payment_status == "paid" and entry.stripe_payment_intent_id:
        refund_info = {
            "stripe_payment_intent_id": entry.stripe_payment_intent_id,
            "refund_status": "pending",
            "note": "Your refund will be processed within 5-10 business days",
        }
        entry.payment_status = "refunded"

    # Remove portfolio
    if entry.contest_portfolio_id:
        portfolio_result = await session.execute(
            select(ContestPortfolio).where(
                ContestPortfolio.id == entry.contest_portfolio_id
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()
        if portfolio:
            await session.delete(portfolio)

    await session.delete(entry)

    contest.current_participants = max(0, contest.current_participants - 1)
    contest.updated_at = datetime.now(timezone.utc)

    return {
        "message": f"Successfully withdrew from '{contest.name}'",
        "refund": refund_info,
    }


# ============================================================================
# ADMIN ENDPOINTS
# ============================================================================

@admin_router.post("")
async def admin_create_contest(
    contest_data: ContestCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Create a new contest with full configuration."""
    now = datetime.now(timezone.utc)

    # Validate time ordering
    if contest_data.end_time <= contest_data.start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="end_time must be after start_time",
        )

    if (
        contest_data.registration_deadline
        and contest_data.registration_deadline >= contest_data.start_time
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="registration_deadline must be before start_time",
        )

    # Auto-generate invite code for private contests if not provided
    invite_code = contest_data.invite_code
    if contest_data.visibility == "private" and not invite_code:
        invite_code = secrets.token_urlsafe(12)[:16]

    contest = Contest(
        name=contest_data.name,
        description=contest_data.description,
        type=contest_data.type,
        status="upcoming",
        visibility=contest_data.visibility,
        invite_code=invite_code,
        entry_fee=contest_data.entry_fee,
        prize_pool=contest_data.prize_pool,
        starting_balance=contest_data.starting_balance,
        max_participants=contest_data.max_participants,
        min_participants=contest_data.min_participants,
        start_time=contest_data.start_time,
        end_time=contest_data.end_time,
        registration_deadline=contest_data.registration_deadline,
        allowed_assets=contest_data.allowed_assets,
        max_trades_per_day=contest_data.max_trades_per_day,
        platform_commission_percent=contest_data.platform_commission_percent,
        created_by=admin.id,
        created_at=now,
        updated_at=now,
    )
    session.add(contest)
    await session.flush()

    return {
        "id": str(contest.id),
        "name": contest.name,
        "type": contest.type,
        "visibility": contest.visibility,
        "invite_code": contest.invite_code,
        "status": contest.status,
        "entry_fee": contest.entry_fee,
        "prize_pool": contest.prize_pool / 100,
        "starting_balance": contest.starting_balance / 100,
        "start_time": contest.start_time.isoformat(),
        "end_time": contest.end_time.isoformat(),
        "created_by": str(admin.id),
    }


@admin_router.put("/{contest_id}")
async def admin_update_contest(
    contest_id: UUID,
    updates: ContestUpdate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Update contest fields. Cannot modify active or completed contests."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

    if contest.status in ("active", "completed"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify a {contest.status} contest",
        )

    if updates.name is not None:
        contest.name = updates.name
    if updates.description is not None:
        contest.description = updates.description
    if updates.visibility is not None:
        contest.visibility = updates.visibility
    if updates.invite_code is not None:
        contest.invite_code = updates.invite_code
    if updates.entry_fee is not None:
        contest.entry_fee = updates.entry_fee
    if updates.prize_pool is not None:
        contest.prize_pool = updates.prize_pool
    if updates.max_participants is not None:
        contest.max_participants = updates.max_participants
    if updates.min_participants is not None:
        contest.min_participants = updates.min_participants
    if updates.registration_deadline is not None:
        contest.registration_deadline = updates.registration_deadline
    if updates.allowed_assets is not None:
        contest.allowed_assets = updates.allowed_assets
    if updates.max_trades_per_day is not None:
        contest.max_trades_per_day = updates.max_trades_per_day
    if updates.platform_commission_percent is not None:
        contest.platform_commission_percent = updates.platform_commission_percent

    contest.updated_at = datetime.now(timezone.utc)

    return {"message": "Contest updated", "contest_id": str(contest_id)}


@admin_router.post("/{contest_id}/cancel")
async def admin_cancel_contest(
    contest_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Cancel a contest and initiate refunds for all paid entries."""
    try:
        result = await cancel_contest(contest_id, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return result


@admin_router.post("/{contest_id}/force-end")
async def admin_force_end_contest(
    contest_id: UUID,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Force-end a contest immediately, compute final rankings, and award prizes."""
    try:
        result = await finalize_contest(contest_id, session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    # Fetch final rankings to include in the response
    rankings_result = await session.execute(
        select(ContestPortfolio, UserProfile.nickname)
        .join(
            UserProfile,
            ContestPortfolio.user_id == UserProfile.user_id,
            isouter=True,
        )
        .where(ContestPortfolio.contest_id == contest_id)
        .order_by(ContestPortfolio.rank.asc())
        .limit(20)
    )

    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    starting_balance = contest.starting_balance if contest else 0

    final_rankings = [
        {
            "rank": portfolio.rank,
            "nickname": nickname or "Anonymous",
            "total_value": portfolio.total_value / 100,
            "pnl": portfolio.unrealized_pnl / 100,
            "pnl_percent": (
                round(
                    float(portfolio.unrealized_pnl / starting_balance * 100),
                    4,
                )
                if starting_balance > 0 else 0.0
            ),
        }
        for portfolio, nickname in rankings_result.all()
    ]

    result["final_rankings"] = final_rankings
    return result
