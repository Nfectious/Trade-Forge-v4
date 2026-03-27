"""
Portfolio Calculator Service
Operation Phoenix | Trading Forge
For Madison

Calculates real-time portfolio value, P&L, and holdings breakdown
using current market prices from Redis.
"""

from decimal import Decimal, ROUND_DOWN
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.trade import TradingPair
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class PortfolioCalculator:
    """
    Real-time portfolio valuation engine.

    CRITICAL OPERATIONS:
    1. Fetch all user holdings from database
    2. Get current prices from Redis (WebSocket cache)
    3. Calculate real-time value and P&L
    4. Return comprehensive portfolio snapshot
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        fallback_prices: Optional[Dict[str, Decimal]] = None,
    ):
        self.db = db
        self.redis = redis
        self.fallback_prices: Dict[str, Decimal] = fallback_prices or {}

    async def get_current_value(self, user_id: UUID) -> Dict[str, Any]:
        portfolio = await self._get_portfolio(user_id)

        if not portfolio:
            return self._empty_portfolio_response()

        # Get all holdings with their trading pair symbols
        holdings_with_symbols = await self._get_holdings_with_symbols(user_id)

        # Calculate current value of holdings
        holdings_value = Decimal('0')
        total_invested = Decimal('0')
        holdings_breakdown = []

        for holding, symbol in holdings_with_symbols:
            if holding.quantity > 0:
                qty = Decimal(str(holding.quantity))
                entry_price = Decimal(str(holding.avg_entry_price))
                invested = qty * entry_price
                total_invested += invested

                current_price = await self._get_current_price(symbol)

                if current_price:
                    current_value = qty * current_price
                    unrealized_pnl = current_value - invested
                    pnl_percent = (
                        (unrealized_pnl / invested * 100)
                        if invested > 0 else Decimal('0')
                    )

                    holdings_value += current_value

                    holdings_breakdown.append({
                        "symbol": symbol,
                        "quantity": float(qty),
                        "average_price": float(entry_price),
                        "current_price": float(current_price),
                        "total_invested": float(invested),
                        "current_value": float(current_value),
                        "unrealized_pnl": float(unrealized_pnl),
                        "pnl_percent": float(pnl_percent.quantize(Decimal('0.01')))
                    })

        # cash_balance is in cents
        cash_balance = Decimal(portfolio.cash_balance) / 100
        total_value = cash_balance + holdings_value

        # Use 10000 USD as default starting balance (1000000 cents)
        starting_balance = Decimal('10000')
        total_pnl = total_value - starting_balance
        pnl_percent = (
            (total_pnl / starting_balance * 100)
            if starting_balance > 0 else Decimal('0')
        )

        return {
            "user_id": str(user_id),
            "total_value": float(total_value),
            "cash_balance": float(cash_balance),
            "holdings_value": float(holdings_value),
            "total_invested": float(total_invested),
            "starting_balance": float(starting_balance),
            "total_pnl": float(total_pnl),
            "pnl_percent": float(pnl_percent.quantize(Decimal('0.01'))),
            "holdings_count": len(holdings_breakdown),
            "holdings": holdings_breakdown,
            "updated_at": datetime.utcnow().isoformat()
        }

    async def get_holdings_breakdown(self, user_id: UUID) -> List[Dict[str, Any]]:
        portfolio = await self._get_portfolio(user_id)
        if not portfolio:
            return []

        holdings_with_symbols = await self._get_holdings_with_symbols(user_id)
        breakdown = []

        for holding, symbol in holdings_with_symbols:
            if holding.quantity > 0:
                qty = Decimal(str(holding.quantity))
                entry_price = Decimal(str(holding.avg_entry_price))
                invested = qty * entry_price

                current_price = await self._get_current_price(symbol)

                if current_price:
                    current_value = qty * current_price
                    unrealized_pnl = current_value - invested
                    pnl_percent = (
                        (unrealized_pnl / invested * 100)
                        if invested > 0 else Decimal('0')
                    )

                    breakdown.append({
                        "symbol": symbol,
                        "quantity": float(qty),
                        "average_price": float(entry_price),
                        "current_price": float(current_price),
                        "total_invested": float(invested),
                        "current_value": float(current_value),
                        "unrealized_pnl": float(unrealized_pnl),
                        "pnl_percent": float(pnl_percent.quantize(Decimal('0.01'))),
                        "allocation_percent": 0.0
                    })

        # Calculate allocation percentages
        if breakdown:
            total_holdings_value = sum(h["current_value"] for h in breakdown)
            if total_holdings_value > 0:
                for h in breakdown:
                    h["allocation_percent"] = round(
                        (h["current_value"] / total_holdings_value) * 100, 2
                    )

        breakdown.sort(key=lambda x: x["current_value"], reverse=True)
        return breakdown

    async def get_performance_metrics(self, user_id: UUID) -> Dict[str, Any]:
        portfolio_data = await self.get_current_value(user_id)
        return {
            "total_pnl": portfolio_data["total_pnl"],
            "pnl_percent": portfolio_data["pnl_percent"],
            "total_value": portfolio_data["total_value"],
            "starting_balance": portfolio_data["starting_balance"],
            "cash_balance": portfolio_data["cash_balance"],
            "holdings_value": portfolio_data["holdings_value"],
            "holdings_count": portfolio_data["holdings_count"],
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "best_trade_pnl": 0.0,
            "worst_trade_pnl": 0.0,
            "average_trade_pnl": 0.0
        }

    async def _get_portfolio(self, user_id: UUID) -> Optional[Portfolio]:
        stmt = select(Portfolio).where(Portfolio.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_holdings_with_symbols(
        self, user_id: UUID
    ) -> List[Tuple[PortfolioHolding, str]]:
        """Fetch holdings joined with TradingPair to get symbol"""
        stmt = (
            select(PortfolioHolding, TradingPair.symbol)
            .join(TradingPair, PortfolioHolding.trading_pair_id == TradingPair.id)
            .where(
                PortfolioHolding.user_id == user_id,
                PortfolioHolding.quantity > 0
            )
        )
        result = await self.db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def _get_current_price(self, symbol: str) -> Optional[Decimal]:
        """Get current price from Redis (WebSocket cache).

        Redis stores JSON objects: {"exchange": "binance", "price": 65000.0, "volume": 1.23}
        Must json.loads() first — never decode as raw float.
        Returns None if no valid price found (caller skips that holding).
        """
        for exchange in ("binance", "kraken", "bybit"):
            redis_key = f"price:{exchange}:{symbol.upper()}"
            price_bytes = await self.redis.get(redis_key)
            if price_bytes is None:
                continue
            try:
                data = json.loads(price_bytes.decode("utf-8"))
                price = data.get("price")
                if price is not None:
                    return Decimal(str(price))
                logger.warning(
                    "Redis key %s had no 'price' field: %s", redis_key, data
                )
            except (json.JSONDecodeError, ValueError, AttributeError) as e:
                logger.warning(
                    "Failed to parse Redis price for %s: %s — %s",
                    redis_key, price_bytes, e
                )
                continue

        fallback = self.fallback_prices.get(symbol.upper())
        if fallback is not None:
            logger.warning(
                "Using fallback price for %s: %s (Redis cache empty)", symbol, fallback
            )
            return fallback

        logger.warning("Price unavailable for %s in Redis across all exchanges", symbol)
        return None

    def _empty_portfolio_response(self) -> Dict[str, Any]:
        return {
            "total_value": 0.0,
            "cash_balance": 0.0,
            "holdings_value": 0.0,
            "total_invested": 0.0,
            "starting_balance": 0.0,
            "total_pnl": 0.0,
            "pnl_percent": 0.0,
            "holdings_count": 0,
            "holdings": [],
            "updated_at": datetime.utcnow().isoformat()
        }


# Dependency injection helper
async def get_portfolio_calculator(
    db: AsyncSession = None,
    redis: Redis = None
) -> PortfolioCalculator:
    if redis is None:
        redis = get_redis_client()
    return PortfolioCalculator(db, redis)
