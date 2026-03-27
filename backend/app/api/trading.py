"""
Trading API routes
Portfolio viewing, order placement, order management, and trade history.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List
from uuid import UUID
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.redis import get_redis_client
from app.core.security import limiter
from app.models.user import User
from app.models.trade import (
    TradingPair, Order, Trade,
    OrderCreate, OrderModifyRequest, OrderResponse,
)
from app.services.trade_executor import (
    TradeExecutor,
    TradeExecutionError,
    InsufficientBalanceError,
    PriceUnavailableError,
)
from app.services.portfolio_calculator import PortfolioCalculator

logger = logging.getLogger(__name__)

router = APIRouter()

# Fallback prices used when the Redis cache is empty (WebSocket feed down).
# Passed to TradeExecutor and PortfolioCalculator so both degrade gracefully
# rather than hard-failing when live data is momentarily unavailable.
FALLBACK_PRICES: dict[str, Decimal] = {
    "BTCUSDT": Decimal("65000.00"),
    "ETHUSDT": Decimal("3200.00"),
    "SOLUSDT": Decimal("180.00"),
}


async def get_price(symbol: str) -> Decimal | None:
    """Get price from Redis cache, fall back to static prices.

    Redis stores JSON: {"exchange": "binance", "price": 65000.0, "volume": 1.23}
    Must json.loads() — never decode as raw float.
    """
    redis = get_redis_client()
    if redis:
        for exchange in ("binance", "bybit", "kraken"):
            key = f"price:{exchange}:{symbol}"
            try:
                data = await redis.get(key)
                if data:
                    parsed = json.loads(data)
                    price = parsed.get("price") or parsed.get("p")
                    if price:
                        return Decimal(str(price))
            except Exception as e:
                logger.debug("Redis price lookup failed for %s: %s", key, e)

    return FALLBACK_PRICES.get(symbol)


# ============================================================================
# PORTFOLIO
# ============================================================================

@router.get("/portfolio")
@limiter.limit("60/minute")
async def get_portfolio(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get user's portfolio with current holdings and P&L."""
    redis = get_redis_client()
    calculator = PortfolioCalculator(session, redis, fallback_prices=FALLBACK_PRICES)
    data = await calculator.get_current_value(current_user.id)

    # Map PortfolioCalculator's "holdings" / "average_price" keys to the API
    # shape the frontend expects: "assets" list with "avg_price" per entry.
    assets = [
        {
            "symbol": h["symbol"],
            "quantity": h["quantity"],
            "avg_price": h["average_price"],
            "current_price": h["current_price"],
            "current_value": h["current_value"],
            "pnl_percent": h["pnl_percent"],
        }
        for h in data.get("holdings", [])
    ]

    return {
        "cash_balance": data["cash_balance"],
        "assets": assets,
        "total_value": data["total_value"],
        "updated_at": data["updated_at"],
    }


# ============================================================================
# ORDER PLACEMENT
# ============================================================================

@router.post("/order", response_model=OrderResponse)
@limiter.limit("30/minute")
async def place_order(
    request: Request,
    order: OrderCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Place a market, limit, stop_limit, or take_profit order."""
    if order.side not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'buy' or 'sell'",
        )

    symbol = order.symbol.upper()

    # Ensure TradingPair exists — create on first trade for this symbol so live
    # pairs discovered from price feeds don't require manual seeding.
    pair_result = await session.execute(
        select(TradingPair).where(TradingPair.symbol == symbol)
    )
    trading_pair = pair_result.scalar_one_or_none()

    if not trading_pair:
        base = symbol.replace("USDT", "").replace("USD", "")
        trading_pair = TradingPair(
            symbol=symbol,
            base_asset=base,
            quote_asset="USDT",
            name=f"{base}/USDT",
        )
        session.add(trading_pair)
        await session.flush()

    # ---- Validate order parameters ----

    # trailing_stop_percent range check
    if order.trailing_stop_percent is not None:
        if not (0.1 <= order.trailing_stop_percent <= 50.0):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="trailing_stop_percent must be between 0.1 and 50.0",
            )

    # limit / stop_limit / take_profit orders require limit_price
    if order.order_type in ("limit", "stop_limit", "take_profit"):
        if order.limit_price is None or order.limit_price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"limit_price is required for {order.order_type} orders",
            )

    # Fetch current price for validation (stop_loss / take_profit sanity checks)
    current_price = await get_price(symbol)
    if current_price is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Market price for {symbol} is currently unavailable",
        )

    if order.stop_loss_price is not None:
        if order.side == "buy" and order.stop_loss_price >= float(current_price):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="stop_loss_price must be below the current market price for buy orders",
            )
        if order.side == "sell" and order.stop_loss_price <= float(current_price):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="stop_loss_price must be above the current market price for sell orders",
            )

    if order.take_profit_price is not None:
        if order.side == "buy" and order.take_profit_price <= float(current_price):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="take_profit_price must be above the current market price for buy orders",
            )
        if order.side == "sell" and order.take_profit_price >= float(current_price):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="take_profit_price must be below the current market price for sell orders",
            )

    # ---- Route by order type ----

    if order.order_type == "market":
        return await _place_market_order(
            order, symbol, trading_pair, current_user, session
        )
    else:
        return await _place_limit_order(
            order, symbol, trading_pair, current_user, session
        )


async def _place_market_order(
    order: OrderCreate,
    symbol: str,
    trading_pair: TradingPair,
    current_user: User,
    session: AsyncSession,
) -> OrderResponse:
    """Execute a market order immediately via TradeExecutor, then attach
    risk management fields and flip status to 'open' if any are set."""
    redis = get_redis_client()
    executor = TradeExecutor(session, redis, fallback_prices=FALLBACK_PRICES)

    try:
        trade_result = await executor.execute_trade(
            user_id=current_user.id,
            symbol=symbol,
            side=order.side,
            quantity=Decimal(str(order.quantity)),
            order_type="market",
        )
    except InsufficientBalanceError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except PriceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except TradeExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    has_risk_management = any([
        order.stop_loss_price,
        order.take_profit_price,
        order.trailing_stop_percent,
    ])

    if has_risk_management:
        # Fetch the order the executor just created so we can update it.
        order_db_result = await session.execute(
            select(Order).where(Order.id == UUID(trade_result["order_id"]))
        )
        db_order = order_db_result.scalar_one()

        # Status 'open' tells the position monitor to watch this order.
        db_order.status = "open"

        if order.stop_loss_price is not None:
            db_order.stop_price = order.stop_loss_price

        if order.take_profit_price is not None:
            db_order.take_profit_price = order.take_profit_price

        if order.trailing_stop_percent is not None:
            db_order.trailing_stop_percent = order.trailing_stop_percent
            # Seed peak price at the fill price (cents).
            db_order.trailing_stop_peak_price = int(trade_result["price"] * 100)

        # get_session dependency commits on response.

    return OrderResponse(
        success=True,
        message=(
            f"{order.side.capitalize()} {order.quantity} {symbol} "
            f"at ${trade_result['price']:,.2f}"
        ),
        order_id=trade_result["order_id"],
        trade_id=trade_result["trade_id"],
    )


async def _place_limit_order(
    order: OrderCreate,
    symbol: str,
    trading_pair: TradingPair,
    current_user: User,
    session: AsyncSession,
) -> OrderResponse:
    """Create a pending limit / stop_limit / take_profit order.
    Not executed immediately — the position monitor fills it when the
    price condition is met or expires it when expires_at is reached."""
    expires_at: datetime | None = None
    if order.expires_in_hours and order.expires_in_hours > 0:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=order.expires_in_hours)

    limit_price_cents = int(order.limit_price * 100)  # type: ignore[operator]  # validated above

    new_order = Order(
        user_id=current_user.id,
        trading_pair_id=trading_pair.id,
        order_type=order.order_type,
        side=order.side,
        status="pending",
        quantity=order.quantity,
        price=order.limit_price,            # display price (DECIMAL in DB)
        limit_price=limit_price_cents,      # BIGINT cents
        stop_price=order.stop_loss_price,
        take_profit_price=order.take_profit_price,
        trailing_stop_percent=order.trailing_stop_percent,
        expires_at=expires_at,
    )
    session.add(new_order)
    await session.flush()  # populates new_order.id; get_session commits on exit

    expiry_msg = f", expires in {order.expires_in_hours}h" if expires_at else ""
    return OrderResponse(
        success=True,
        message=(
            f"{order.order_type.replace('_', ' ').capitalize()} {order.side} "
            f"{order.quantity} {symbol} at ${order.limit_price:,.2f}{expiry_msg}"
        ),
        order_id=str(new_order.id),
    )


# ============================================================================
# OPEN ORDERS
# ============================================================================

@router.get("/orders/open")
@limiter.limit("60/minute")
async def get_open_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """All user orders with status 'open' — executed positions being monitored.
    Returns current unrealized P&L for each."""
    result = await session.execute(
        select(Order, TradingPair.symbol)
        .join(TradingPair, Order.trading_pair_id == TradingPair.id)
        .where(
            Order.user_id == current_user.id,
            Order.status == "open",
        )
        .order_by(Order.created_at.desc())
    )
    rows = result.all()

    orders_out = []
    for db_order, symbol in rows:
        current_price = await get_price(symbol)
        current_price_f = float(current_price) if current_price else None

        entry = float(db_order.filled_avg_price or 0)
        qty = float(db_order.quantity)

        unrealized_pnl: float | None = None
        unrealized_pnl_pct: float | None = None
        current_value: float | None = None

        if current_price_f is not None and entry > 0 and qty > 0:
            current_value = current_price_f * qty
            unrealized_pnl = (current_price_f - entry) * qty
            unrealized_pnl_pct = round((current_price_f - entry) / entry * 100, 4)

        # Compute trailing stop trigger price for display
        trailing_stop_trigger: float | None = None
        if (
            db_order.trailing_stop_percent is not None
            and db_order.trailing_stop_peak_price is not None
        ):
            trailing_stop_trigger = round(
                (db_order.trailing_stop_peak_price / 100)
                * (1 - db_order.trailing_stop_percent / 100),
                2,
            )

        orders_out.append({
            "order_id": str(db_order.id),
            "symbol": symbol,
            "side": db_order.side,
            "order_type": db_order.order_type,
            "quantity": qty,
            "entry_price": entry,
            "current_price": current_price_f,
            "current_value": current_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_percent": unrealized_pnl_pct,
            "stop_loss_price": db_order.stop_price,
            "take_profit_price": db_order.take_profit_price,
            "trailing_stop_percent": db_order.trailing_stop_percent,
            "trailing_stop_trigger": trailing_stop_trigger,
            "created_at": db_order.created_at.isoformat(),
            "filled_at": db_order.filled_at.isoformat() if db_order.filled_at else None,
        })

    return orders_out


# ============================================================================
# PENDING LIMIT ORDERS
# ============================================================================

@router.get("/orders/pending")
@limiter.limit("60/minute")
async def get_pending_orders(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """All user orders with status 'pending' — limit orders waiting to fill."""
    result = await session.execute(
        select(Order, TradingPair.symbol)
        .join(TradingPair, Order.trading_pair_id == TradingPair.id)
        .where(
            Order.user_id == current_user.id,
            Order.status == "pending",
        )
        .order_by(Order.created_at.desc())
    )
    rows = result.all()

    return [
        {
            "order_id": str(db_order.id),
            "symbol": symbol,
            "side": db_order.side,
            "order_type": db_order.order_type,
            "quantity": float(db_order.quantity),
            "limit_price": db_order.limit_price / 100 if db_order.limit_price else None,
            "stop_loss_price": db_order.stop_price,
            "take_profit_price": db_order.take_profit_price,
            "trailing_stop_percent": db_order.trailing_stop_percent,
            "expires_at": db_order.expires_at.isoformat() if db_order.expires_at else None,
            "created_at": db_order.created_at.isoformat(),
        }
        for db_order, symbol in rows
    ]


# ============================================================================
# MODIFY OPEN ORDER (stop-loss / take-profit only)
# ============================================================================

@router.put("/orders/{order_id}")
@limiter.limit("30/minute")
async def modify_order(
    request: Request,
    order_id: UUID,
    body: OrderModifyRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Modify stop_loss_price or take_profit_price on an open or pending order.
    Cannot change order_type, quantity, or symbol.
    Returns 400 if the order is already filled, cancelled, or rejected."""
    result = await session.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    db_order = result.scalar_one_or_none()

    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if db_order.status in ("filled", "cancelled", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot modify a {db_order.status} order",
        )

    if body.stop_loss_price is not None:
        db_order.stop_price = body.stop_loss_price

    if body.take_profit_price is not None:
        db_order.take_profit_price = body.take_profit_price

    # get_session dependency commits on successful response

    return {
        "order_id": str(db_order.id),
        "stop_loss_price": db_order.stop_price,
        "take_profit_price": db_order.take_profit_price,
        "message": "Order updated",
    }


# ============================================================================
# CANCEL PENDING LIMIT ORDER
# ============================================================================

@router.delete("/orders/{order_id}")
@limiter.limit("30/minute")
async def cancel_order(
    request: Request,
    order_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Cancel a pending limit order.  Only orders with status='pending' can be
    cancelled — returns 400 for already filled or cancelled orders."""
    result = await session.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.id,
        )
    )
    db_order = result.scalar_one_or_none()

    if not db_order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if db_order.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only pending orders can be cancelled; this order is '{db_order.status}'",
        )

    db_order.status = "cancelled"
    db_order.cancelled_at = datetime.now(timezone.utc)

    # get_session dependency commits on successful response

    return {"order_id": str(db_order.id), "status": "cancelled", "message": "Order cancelled"}


# ============================================================================
# TRADE HISTORY
# ============================================================================

@router.get("/trades/history")
@limiter.limit("60/minute")
async def get_trade_history(
    request: Request,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Get recent trades for the current user."""
    if limit > 100:
        limit = 100

    result = await session.execute(
        select(Trade, TradingPair.symbol)
        .join(TradingPair, Trade.trading_pair_id == TradingPair.id)
        .where(Trade.user_id == current_user.id)
        .order_by(Trade.executed_at.desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "id": str(t.id),
            "symbol": symbol,
            "side": t.side,
            "quantity": t.quantity,
            "price": t.price,
            "total_value": t.total_value / 100,  # cents → dollars
            "executed_at": t.executed_at.isoformat(),
        }
        for t, symbol in rows
    ]
