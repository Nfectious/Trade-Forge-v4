"""
Trading models: TradingPair, Order, Trade
Maps to: trading_pairs, orders, trades tables in init.sql
"""

from sqlmodel import SQLModel, Field
from typing import Literal, Optional
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum


# ============================================================================
# ENUMS (match DB custom types)
# ============================================================================

class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT = "take_profit"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# Aliases used by trade_executor.py
TradeSide = OrderSide
TradeStatus = OrderStatus


# ============================================================================
# TRADING PAIR MODEL
# ============================================================================

class TradingPair(SQLModel, table=True):
    """Supported trading pairs (e.g., BTCUSDT)"""
    __tablename__ = "trading_pairs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    symbol: str = Field(unique=True, max_length=20)
    base_asset: str = Field(max_length=10)
    quote_asset: str = Field(max_length=10)
    name: str = Field(max_length=100)
    is_active: bool = Field(default=True)
    min_order_size: Optional[float] = None
    max_order_size: Optional[float] = None
    price_decimals: int = Field(default=2)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# ORDER MODEL
# ============================================================================

class Order(SQLModel, table=True):
    """Trade orders"""
    __tablename__ = "orders"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")
    trading_pair_id: UUID = Field(foreign_key="trading_pairs.id")

    order_type: str = Field(default="market", max_length=20)
    side: str = Field(max_length=10)
    status: str = Field(default="pending", max_length=20)

    quantity: float
    price: Optional[float] = None           # execution/display price
    filled_quantity: float = Field(default=0)
    filled_avg_price: Optional[float] = None

    total_cost: Optional[int] = None        # BIGINT (cents)
    fee: int = Field(default=0)

    # Existing risk-management prices (display prices, stored as DECIMAL in DB)
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None

    # ---- New columns added by migration 002 ----

    # Trailing-stop distance as a percentage (e.g. 2.5 = 2.5 %)
    trailing_stop_percent: Optional[float] = Field(default=None)

    # Highest price seen while position is open, in cents (BIGINT)
    trailing_stop_peak_price: Optional[int] = Field(default=None)

    # Limit trigger price in cents (BIGINT); display price = limit_price / 100
    limit_price: Optional[int] = Field(default=None)

    # True when the position monitor auto-executed this order
    auto_executed: bool = Field(default=False)

    # Reason recorded by the monitor on auto-execution
    auto_execute_reason: Optional[str] = Field(default=None)

    # Expiry timestamp for pending limit orders
    expires_at: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


# ============================================================================
# TRADE MODEL (executed trades)
# ============================================================================

class Trade(SQLModel, table=True):
    """Executed trade records"""
    __tablename__ = "trades"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    order_id: UUID = Field(foreign_key="orders.id")
    user_id: UUID = Field(foreign_key="users.id")
    trading_pair_id: UUID = Field(foreign_key="trading_pairs.id")

    side: str = Field(max_length=10)
    quantity: float
    price: float
    total_value: int  # BIGINT (cents)
    fee: int = Field(default=0)

    pnl: Optional[int] = None          # BIGINT (cents)
    pnl_percent: Optional[float] = None

    executed_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# REQUEST / RESPONSE MODELS (Pydantic, not DB tables)
# ============================================================================

class OrderCreate(SQLModel):
    """Order placement request."""

    symbol: str = Field(max_length=20)
    side: str = Field(max_length=10)        # "buy" or "sell"
    quantity: float = Field(gt=0)

    order_type: Literal["market", "limit", "stop_limit", "take_profit"] = "market"

    # Required for limit / stop_limit / take_profit orders (display price in $)
    limit_price: Optional[float] = None

    # Optional risk management (display prices in $); attached to any order
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None

    # Optional trailing stop expressed as a percentage (0.1 – 50.0)
    trailing_stop_percent: Optional[float] = None

    # How long a pending limit order stays active before the monitor expires it
    expires_in_hours: Optional[int] = 24


class OrderModifyRequest(SQLModel):
    """Body for PUT /trading/orders/{order_id} — modify risk-management prices."""
    stop_loss_price: Optional[float] = None    # display price in $
    take_profit_price: Optional[float] = None  # display price in $


class OrderResponse(SQLModel):
    """Order placement response."""
    success: bool
    message: str
    order_id: Optional[str] = None   # always set
    trade_id: Optional[str] = None   # set only for immediately executed orders


class TradeHistoryItem(SQLModel):
    """Single trade in history response."""
    id: UUID
    symbol: str
    side: str
    quantity: float
    price: float
    total_value: float
    executed_at: datetime
