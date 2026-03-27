"""
Leaderboard models: UserStatsCache, LeaderboardWeekly
Maps to: user_stats_cache, leaderboard_weekly tables (migration 004)
"""

from datetime import date, datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class UserStatsCache(SQLModel, table=True):
    """Aggregated trading stats per user — rebuilt by the leaderboard scheduler.
    One row per user; upserted on each recalculation cycle.
    All monetary values in cents (BIGINT).
    """
    __tablename__ = "user_stats_cache"

    user_id: UUID = Field(foreign_key="users.id", primary_key=True)

    total_realized_pnl: int = Field(default=0)         # cents
    total_pnl_percent: float = Field(default=0.0)      # % vs tier starting balance

    total_trades: int = Field(default=0)
    winning_trades: int = Field(default=0)
    win_rate: float = Field(default=0.0)               # 0–100

    total_volume: int = Field(default=0)               # cents

    best_trade_pnl_percent: float = Field(default=0.0)
    worst_trade_pnl_percent: float = Field(default=0.0)

    current_win_streak: int = Field(default=0)
    longest_win_streak: int = Field(default=0)

    all_time_rank: Optional[int] = Field(default=None)
    weekly_rank: Optional[int] = Field(default=None)

    last_updated: datetime = Field(default_factory=datetime.utcnow)


class LeaderboardWeekly(SQLModel, table=True):
    """Weekly P&L snapshot for leaderboard tracking.
    Starting value captured Monday 00:05 UTC; ending value Sunday 23:55 UTC.
    """
    __tablename__ = "leaderboard_weekly"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id")

    week_start: date           # Monday (PostgreSQL DATE)
    week_end: date             # Sunday

    starting_value: Optional[int] = Field(default=None)   # cents
    ending_value: Optional[int] = Field(default=None)     # cents

    pnl: int = Field(default=0)            # cents
    pnl_percent: float = Field(default=0.0)

    trades_this_week: int = Field(default=0)
    rank: Optional[int] = Field(default=None)
