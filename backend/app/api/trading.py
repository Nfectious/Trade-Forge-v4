"""
Trading API routes
Portfolio viewing, order placement, and trade history.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from decimal import Decimal
import json
import logging

from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.redis import get_redis_client
from app.core.security import limiter
from app.models.user import User
from app.models.trade import (
    TradingPair, Trade,
    OrderCreate, OrderResponse,
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
    """Place a buy or sell market order."""
    if order.side not in ("buy", "sell"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Side must be 'buy' or 'sell'",
        )

    symbol = order.symbol.upper()

    # TradeExecutor requires the TradingPair to already exist in the database.
    # Create it on the fly if this is the first trade for this symbol so that
    # new pairs discovered from live price feeds don't require manual seeding.
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

    return OrderResponse(
        success=True,
        message=(
            f"{order.side.capitalize()} {order.quantity} {symbol} "
            f"at ${trade_result['price']:,.2f}"
        ),
        trade_id=trade_result["trade_id"],
    )


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
