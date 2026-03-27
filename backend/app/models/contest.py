"""
Contest models: Contest, ContestPortfolio, ContestEntry, ContestTrade
Maps to: contests, contest_portfolios, contest_entries, contest_trades tables
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


# ============================================================================
# CONTEST MODEL
# ============================================================================

class Contest(SQLModel, table=True):
    """Trading contest / competition."""
    __tablename__ = "contests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, max_length=200)
    description: Optional[str] = Field(default=None)
    type: str = Field(max_length=50)             # free | paid | sponsored
    status: str = Field(default="upcoming", max_length=50)

    entry_fee: float = Field(default=0)           # DECIMAL(10,2) display dollars
    prize_pool: int = Field(default=0)            # BIGINT cents
    starting_balance: int = Field(default=10000000)  # BIGINT cents

    max_participants: Optional[int] = Field(default=None, ge=1)
    min_participants: int = Field(default=2)
    current_participants: int = Field(default=0, ge=0)

    start_time: datetime
    end_time: datetime
    registration_deadline: Optional[datetime] = Field(default=None)

    # Visibility: 'public' or 'private' (requires invite_code)
    visibility: str = Field(default="public", max_length=20)
    invite_code: Optional[str] = Field(default=None, max_length=20)

    allowed_assets: Optional[str] = None         # comma-separated symbols, NULL = all
    max_trades_per_day: Optional[int] = None

    prize_distributed: bool = Field(default=False)
    winner_id: Optional[UUID] = Field(default=None, foreign_key="users.id")
    platform_commission_percent: float = Field(default=10.0)

    created_by: Optional[UUID] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CONTEST PORTFOLIO MODEL
# ============================================================================

class ContestPortfolio(SQLModel, table=True):
    """Isolated portfolio for a user within a specific contest.
    Holdings are derived from ContestTrade records (event-sourced).
    total_value and rank are updated by the contest scheduler.
    """
    __tablename__ = "contest_portfolios"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    contest_id: UUID = Field(foreign_key="contests.id")
    user_id: UUID = Field(foreign_key="users.id")

    cash_balance: int         # BIGINT cents
    total_value: int          # BIGINT cents; scheduler-maintained
    unrealized_pnl: int = Field(default=0)   # BIGINT cents
    realized_pnl: int = Field(default=0)     # BIGINT cents
    total_trades: int = Field(default=0)
    rank: Optional[int] = Field(default=None)
    last_calculated: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CONTEST ENTRY MODEL
# ============================================================================

class ContestEntry(SQLModel, table=True):
    """Links a user to a contest and tracks their enrollment status and results."""
    __tablename__ = "contest_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    contest_id: UUID = Field(foreign_key="contests.id")
    user_id: UUID = Field(foreign_key="users.id")
    contest_portfolio_id: Optional[UUID] = Field(
        default=None, foreign_key="contest_portfolios.id"
    )

    status: str = Field(default="active", max_length=20)  # active | cancelled | disqualified
    final_rank: Optional[int] = Field(default=None)
    final_value: Optional[int] = Field(default=None)       # BIGINT cents
    final_pnl: Optional[int] = Field(default=None)         # BIGINT cents
    final_pnl_percent: Optional[float] = Field(default=None)

    payment_status: str = Field(default="free", max_length=20)  # free | paid | refunded
    stripe_payment_intent_id: Optional[str] = Field(default=None, max_length=100)

    joined_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CONTEST TRADE MODEL
# ============================================================================

class ContestTrade(SQLModel, table=True):
    """Trade executed within a contest using contest portfolio funds.
    price and total_value stored in cents (BIGINT).
    """
    __tablename__ = "contest_trades"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    contest_id: UUID = Field(foreign_key="contests.id")
    user_id: UUID = Field(foreign_key="users.id")
    contest_portfolio_id: UUID = Field(foreign_key="contest_portfolios.id")

    symbol: str = Field(max_length=20)
    side: str = Field(max_length=10)          # buy | sell
    quantity: float                            # DECIMAL(20,8)
    price: int                                 # BIGINT cents per unit
    total_value: int                           # BIGINT cents
    fee: int = Field(default=0)               # BIGINT cents

    stop_loss_price: Optional[int] = Field(default=None)   # BIGINT cents
    take_profit_price: Optional[int] = Field(default=None) # BIGINT cents

    executed_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# REQUEST / RESPONSE MODELS (Pydantic, not DB tables)
# ============================================================================

class ContestCreate(SQLModel):
    """Contest creation request (admin)."""
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    type: str = Field(max_length=50)          # free | paid

    visibility: str = Field(default="public", max_length=20)
    invite_code: Optional[str] = Field(default=None, max_length=20)

    entry_fee: float = Field(default=0, ge=0)  # dollars
    prize_pool: int = Field(default=0, ge=0)   # cents

    starting_balance: int = Field(default=10000000, ge=100)  # cents
    max_participants: Optional[int] = Field(default=None, ge=2)
    min_participants: int = Field(default=2, ge=2)

    start_time: datetime
    end_time: datetime
    registration_deadline: Optional[datetime] = Field(default=None)

    allowed_assets: Optional[str] = Field(default=None)  # comma-separated symbols
    max_trades_per_day: Optional[int] = Field(default=None, ge=1)

    platform_commission_percent: float = Field(default=10.0, ge=0, le=100)


class ContestUpdate(SQLModel):
    """Contest update request (admin). All fields optional."""
    name: Optional[str] = Field(default=None, max_length=200)
    description: Optional[str] = Field(default=None, max_length=1000)
    visibility: Optional[str] = Field(default=None, max_length=20)
    invite_code: Optional[str] = Field(default=None, max_length=20)
    entry_fee: Optional[float] = Field(default=None, ge=0)
    prize_pool: Optional[int] = Field(default=None, ge=0)
    max_participants: Optional[int] = Field(default=None, ge=2)
    min_participants: Optional[int] = Field(default=None, ge=2)
    registration_deadline: Optional[datetime] = Field(default=None)
    allowed_assets: Optional[str] = Field(default=None)
    max_trades_per_day: Optional[int] = Field(default=None, ge=1)
    platform_commission_percent: Optional[float] = Field(default=None, ge=0, le=100)


class ContestTradeCreate(SQLModel):
    """Contest trade placement request."""
    symbol: str = Field(max_length=20)
    side: str = Field(max_length=10)          # buy | sell
    quantity: float = Field(gt=0)
    stop_loss_price: Optional[float] = Field(default=None, gt=0)    # display dollars
    take_profit_price: Optional[float] = Field(default=None, gt=0)  # display dollars


class JoinPrivateRequest(SQLModel):
    """Body for POST /contests/{contest_id}/join-private."""
    invite_code: str


class ContestResponse(SQLModel):
    """Contest response model (used by admin.py and contest list)."""
    id: UUID
    name: str
    description: Optional[str] = None
    type: str
    status: str
    entry_fee: float
    prize_pool: int
    max_participants: Optional[int] = None
    current_participants: int
    start_time: datetime
    end_time: datetime
    starting_balance: int
    visibility: str
    created_at: datetime
    updated_at: datetime
