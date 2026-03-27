"""
Trade Execution Service
Operation Phoenix | Trading Forge
For Madison

Handles all trade execution logic with atomic database transactions,
balance validation, and real-time price integration from Redis.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import json
import logging

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis

from app.models.trade import Trade, Order, OrderStatus, TradingPair
from app.models.portfolio import Portfolio, PortfolioHolding
from app.models.wallet import VirtualWallet, WalletTransaction
from app.core.config import settings
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)


class TradeExecutionError(Exception):
    """Base exception for trade execution failures"""
    pass


class InsufficientBalanceError(TradeExecutionError):
    """Raised when user lacks sufficient funds or holdings"""
    pass


class PriceUnavailableError(TradeExecutionError):
    """Raised when market price data is unavailable"""
    pass


class InvalidQuantityError(TradeExecutionError):
    """Raised for invalid trade quantities"""
    pass


class TradeExecutor:
    """
    Core trading engine for executing simulated trades.

    CRITICAL OPERATIONS:
    1. Fetch real-time price from Redis (WebSocket cache)
    2. Validate user balance/holdings
    3. Execute atomic database transaction
    4. Update portfolio state
    """

    def __init__(
        self,
        db: AsyncSession,
        redis: Redis,
        fallback_prices: Optional[Dict[str, Decimal]] = None,
    ):
        self.db = db
        self.redis = redis
        # Static prices used when Redis cache is empty (e.g. WebSocket feed down).
        # Caller passes FALLBACK_PRICES from the router so TradeExecutor degrades
        # gracefully instead of always raising PriceUnavailableError.
        self.fallback_prices: Dict[str, Decimal] = fallback_prices or {}

    async def execute_trade(
        self,
        user_id: UUID,
        symbol: str,
        side: str,
        quantity: Decimal,
        order_type: str = "market"
    ) -> Dict[str, Any]:
        # Validate inputs
        self._validate_trade_params(symbol, side, quantity, order_type)

        # Resolve trading pair from symbol string
        trading_pair = await self._get_trading_pair(symbol)

        # Get current market price from Redis
        current_price = await self._get_current_price(symbol)

        # Calculate trade value (in dollars)
        total_value = self._calculate_trade_value(quantity, current_price, side)

        # Get user's portfolio
        portfolio = await self._get_portfolio(user_id)

        # Validate sufficient balance/holdings
        await self._validate_balance(portfolio, trading_pair.id, side, quantity, total_value)

        # Execute trade within database transaction
        try:
            async with self.db.begin():
                # Create order first (trades reference orders via FK)
                order = Order(
                    user_id=user_id,
                    trading_pair_id=trading_pair.id,
                    order_type=order_type,
                    side=side,
                    status=OrderStatus.FILLED,
                    quantity=float(quantity),
                    price=float(current_price),
                    filled_quantity=float(quantity),
                    filled_avg_price=float(current_price),
                    total_cost=int(total_value * 100),
                    filled_at=datetime.now(timezone.utc)
                )
                self.db.add(order)
                await self.db.flush()

                # Create trade record referencing the order
                trade = Trade(
                    order_id=order.id,
                    user_id=user_id,
                    trading_pair_id=trading_pair.id,
                    side=side,
                    quantity=float(quantity),
                    price=float(current_price),
                    total_value=int(total_value * 100),
                    executed_at=datetime.now(timezone.utc)
                )
                self.db.add(trade)
                await self.db.flush()

                # Update wallet (cash balance)
                await self._update_wallet(user_id, side, total_value, trade.id)

                # Update portfolio cash balance
                await self._update_portfolio_cash(portfolio, side, total_value)

                # Update holdings (asset quantity)
                await self._update_holdings(
                    user_id, trading_pair.id, side, quantity, current_price
                )

                await self.db.commit()

            # Fetch updated portfolio state
            updated_portfolio = await self._get_portfolio(user_id)

            return {
                "trade_id": str(trade.id),
                "order_id": str(order.id),
                "symbol": symbol,
                "side": side,
                "quantity": float(quantity),
                "price": float(current_price),
                "total_value": float(total_value),
                "new_balance": float(updated_portfolio.cash_balance),
                "executed_at": trade.executed_at.isoformat(),
                "status": "success"
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Trade execution failed: {str(e)}")
            raise TradeExecutionError(f"Failed to execute trade: {str(e)}")

    def _validate_trade_params(
        self, symbol: str, side: str, quantity: Decimal, order_type: str
    ) -> None:
        if order_type != "market":
            raise TradeExecutionError("Only market orders are supported")
        if side not in ["buy", "sell"]:
            raise TradeExecutionError(f"Invalid side: {side}. Must be 'buy' or 'sell'")
        if quantity <= 0:
            raise InvalidQuantityError("Quantity must be greater than zero")
        if not symbol or len(symbol) < 3:
            raise TradeExecutionError(f"Invalid symbol: {symbol}")

    async def _get_trading_pair(self, symbol: str) -> TradingPair:
        """Look up TradingPair by symbol string"""
        stmt = select(TradingPair).where(TradingPair.symbol == symbol.upper())
        result = await self.db.execute(stmt)
        pair = result.scalar_one_or_none()
        if not pair:
            raise TradeExecutionError(f"Trading pair not found: {symbol}")
        return pair

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Fetch current price from Redis cache (populated by WebSocket).

        Redis stores JSON objects: {"exchange": "binance", "price": 65000.0, "volume": 1.23}
        Must json.loads() first — never decode as raw float.
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
                logger.error(
                    "Failed to parse Redis price for %s: %s — %s",
                    redis_key, price_bytes, e
                )
                continue

        # Try static fallback prices before giving up entirely
        fallback = self.fallback_prices.get(symbol.upper())
        if fallback is not None:
            logger.warning(
                "Using fallback price for %s: %s (Redis cache empty)", symbol, fallback
            )
            return fallback

        raise PriceUnavailableError(
            f"Market price for {symbol} is currently unavailable. "
            "No valid price found in Redis cache across all exchanges and no fallback "
            "configured. WebSocket feed may be disconnected."
        )

    def _calculate_trade_value(
        self, quantity: Decimal, price: Decimal, side: str
    ) -> Decimal:
        total = quantity * price
        return total.quantize(Decimal('0.01'), rounding=ROUND_DOWN)

    async def _get_portfolio(self, user_id: UUID) -> Portfolio:
        stmt = select(Portfolio).where(Portfolio.user_id == user_id)
        result = await self.db.execute(stmt)
        portfolio = result.scalar_one_or_none()
        if not portfolio:
            raise TradeExecutionError("Portfolio not found for user")
        return portfolio

    async def _validate_balance(
        self,
        portfolio: Portfolio,
        trading_pair_id: UUID,
        side: str,
        quantity: Decimal,
        total_value: Decimal
    ) -> None:
        if side == "buy":
            # cash_balance is in cents, total_value is dollars
            balance_dollars = Decimal(portfolio.cash_balance) / 100
            if balance_dollars < total_value:
                raise InsufficientBalanceError(
                    f"Insufficient balance. Required: ${total_value:.2f}, "
                    f"Available: ${balance_dollars:.2f}"
                )
        elif side == "sell":
            stmt = select(PortfolioHolding).where(
                PortfolioHolding.user_id == portfolio.user_id,
                PortfolioHolding.trading_pair_id == trading_pair_id
            )
            result = await self.db.execute(stmt)
            holding = result.scalar_one_or_none()
            if not holding or Decimal(str(holding.quantity)) < quantity:
                available = Decimal(str(holding.quantity)) if holding else Decimal('0')
                raise InsufficientBalanceError(
                    f"Insufficient holdings. Required: {quantity}, Available: {available}"
                )

    async def _update_wallet(
        self,
        user_id: UUID,
        side: str,
        total_value: Decimal,
        trade_id: UUID
    ) -> None:
        """Create wallet transaction and update wallet balance"""
        transaction_type = "trade_profit" if side == "sell" else "trade_loss"
        amount_cents = int(total_value * 100)
        amount = -amount_cents if side == "buy" else amount_cents

        # Get current wallet balance for balance_after (required NOT NULL)
        stmt = select(VirtualWallet).where(VirtualWallet.user_id == user_id)
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        balance_after = (wallet.balance + amount) if wallet else amount

        wallet_tx = WalletTransaction(
            user_id=user_id,
            type=transaction_type,
            amount=amount,
            balance_after=balance_after,
            reference_id=trade_id,
            description=f"Trade {side.upper()}: {trade_id}"
        )
        self.db.add(wallet_tx)

        if wallet:
            wallet.balance = balance_after

    async def _update_portfolio_cash(
        self, portfolio: Portfolio, side: str, total_value: Decimal
    ) -> None:
        """Update portfolio cash balance (stored in cents)"""
        amount_cents = int(total_value * 100)
        if side == "buy":
            portfolio.cash_balance -= amount_cents
        else:
            portfolio.cash_balance += amount_cents
        if portfolio.cash_balance < 0:
            raise TradeExecutionError("Negative balance detected")

    async def _update_holdings(
        self,
        user_id: UUID,
        trading_pair_id: UUID,
        side: str,
        quantity: Decimal,
        price: Decimal
    ) -> None:
        """Update or create portfolio holdings using user_id + trading_pair_id"""
        stmt = select(PortfolioHolding).where(
            PortfolioHolding.user_id == user_id,
            PortfolioHolding.trading_pair_id == trading_pair_id
        )
        result = await self.db.execute(stmt)
        holding = result.scalar_one_or_none()

        if side == "buy":
            if holding:
                old_cost = Decimal(str(holding.quantity)) * Decimal(str(holding.avg_entry_price))
                new_cost = quantity * price
                new_quantity = Decimal(str(holding.quantity)) + quantity
                holding.quantity = float(new_quantity)
                holding.avg_entry_price = float((old_cost + new_cost) / new_quantity)
                holding.current_price = float(price)
                holding.total_value = int(new_quantity * price * 100)
            else:
                holding = PortfolioHolding(
                    user_id=user_id,
                    trading_pair_id=trading_pair_id,
                    quantity=float(quantity),
                    avg_entry_price=float(price),
                    current_price=float(price),
                    total_value=int(quantity * price * 100)
                )
                self.db.add(holding)

        elif side == "sell":
            if not holding:
                raise TradeExecutionError("Cannot sell asset not owned")
            new_quantity = Decimal(str(holding.quantity)) - quantity
            holding.quantity = float(new_quantity)
            holding.current_price = float(price)
            holding.total_value = int(new_quantity * price * 100)
            if new_quantity <= Decimal('0.00000001'):
                await self.db.delete(holding)


# Dependency injection helper
async def get_trade_executor(
    db: AsyncSession = None,
    redis: Redis = None
) -> TradeExecutor:
    if redis is None:
        redis = get_redis_client()
    return TradeExecutor(db, redis)
