"""
Leaderboard Service
Calculates and caches per-user trading stats and global rankings.

Convention:
  - All monetary values are BIGINT cents internally.
  - Display values (dollars) are computed at the API layer.
  - Starting balance baseline: settings.TIER_FREE_BALANCE (consistent across tiers).
"""

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import case, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.redis import get_redis_client
from app.models.leaderboard import LeaderboardWeekly, UserStatsCache
from app.models.portfolio import Portfolio
from app.models.trade import Trade
from app.models.user import User, UserProfile

logger = logging.getLogger(__name__)

# Redis TTL for cached leaderboard data (seconds)
LEADERBOARD_CACHE_TTL = 60


# ============================================================================
# WEEK HELPERS
# ============================================================================

def get_current_week_start() -> date:
    """Return the Monday of the current ISO week (UTC)."""
    today = datetime.now(timezone.utc).date()
    return today - timedelta(days=today.weekday())


def get_current_week_end() -> date:
    return get_current_week_start() + timedelta(days=6)


# ============================================================================
# STEP 1: PER-USER STAT RECALCULATION
# ============================================================================

async def recalculate_user_stats(user_id: UUID, session: AsyncSession) -> None:
    """Rebuild UserStatsCache for a single user from their trade history.

    Aggregates:
      - total_realized_pnl  — sum of trade.pnl (sell trades only)
      - total_pnl_percent   — pnl vs TIER_FREE_BALANCE baseline
      - total_trades        — count of all trades
      - winning_trades      — count where pnl > 0
      - win_rate            — winning_trades / total_trades * 100
      - total_volume        — sum of trade.total_value (all trades)
      - best/worst_trade_pnl_percent
      - current_win_streak  — consecutive wins from most recent trade backwards
      - longest_win_streak  — historical maximum consecutive wins

    Also syncs portfolios.total_trades and portfolios.winning_trades.
    """
    # ---- Aggregate stats in one DB round-trip ----
    agg_result = await session.execute(
        select(
            func.count(Trade.id).label("total_trades"),
            func.coalesce(func.sum(Trade.total_value), 0).label("total_volume"),
            func.coalesce(
                func.sum(case((Trade.pnl.isnot(None), Trade.pnl), else_=0)), 0
            ).label("total_realized_pnl"),
            func.sum(
                case((Trade.pnl > 0, 1), else_=0)
            ).label("winning_trades"),
            func.max(Trade.pnl_percent).label("best_pnl_percent"),
            func.min(Trade.pnl_percent).label("worst_pnl_percent"),
        ).where(Trade.user_id == user_id)
    )
    agg = agg_result.one()

    total_trades: int = agg.total_trades or 0
    total_volume: int = agg.total_volume or 0
    total_realized_pnl: int = agg.total_realized_pnl or 0
    winning_trades: int = agg.winning_trades or 0
    best_pnl_pct: float = float(agg.best_pnl_percent or 0.0)
    worst_pnl_pct: float = float(agg.worst_pnl_percent or 0.0)

    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0

    starting_value = settings.TIER_FREE_BALANCE  # 1 000 000 cents = $10 000 baseline
    total_pnl_percent = (
        float(total_realized_pnl / starting_value * 100)
        if starting_value > 0
        else 0.0
    )

    # ---- Win-streak calculation (requires ordered trade rows) ----
    streak_result = await session.execute(
        select(Trade.pnl)
        .where(Trade.user_id == user_id)
        .order_by(Trade.executed_at.asc())
    )
    pnl_series = [row[0] for row in streak_result.all()]

    # Longest historical streak (forward pass)
    longest_streak = 0
    cur = 0
    for pnl in pnl_series:
        if pnl is not None and pnl > 0:
            cur += 1
            longest_streak = max(longest_streak, cur)
        else:
            cur = 0

    # Current streak (backward pass from most recent)
    current_streak = 0
    for pnl in reversed(pnl_series):
        if pnl is not None and pnl > 0:
            current_streak += 1
        else:
            break

    # ---- Upsert into user_stats_cache ----
    stats_result = await session.execute(
        select(UserStatsCache).where(UserStatsCache.user_id == user_id)
    )
    stats = stats_result.scalar_one_or_none()

    if stats is None:
        stats = UserStatsCache(user_id=user_id)
        session.add(stats)

    stats.total_realized_pnl = total_realized_pnl
    stats.total_pnl_percent = round(total_pnl_percent, 4)
    stats.total_trades = total_trades
    stats.winning_trades = winning_trades
    stats.win_rate = round(win_rate, 2)
    stats.total_volume = total_volume
    stats.best_trade_pnl_percent = round(best_pnl_pct, 4)
    stats.worst_trade_pnl_percent = round(worst_pnl_pct, 4)
    stats.current_win_streak = current_streak
    stats.longest_win_streak = longest_streak
    stats.last_updated = datetime.now(timezone.utc)

    # ---- Sync portfolio summary counters ----
    portfolio_result = await session.execute(
        select(Portfolio).where(Portfolio.user_id == user_id)
    )
    portfolio = portfolio_result.scalar_one_or_none()
    if portfolio:
        portfolio.total_trades = total_trades
        portfolio.winning_trades = winning_trades

    await session.commit()

    logger.debug(
        "Stats recalculated: user=%s trades=%d win_rate=%.1f%% pnl_pct=%.2f%%",
        user_id, total_trades, win_rate, total_pnl_percent,
    )


# ============================================================================
# STEP 2: GLOBAL RANKING RECALCULATION + REDIS CACHING
# ============================================================================

async def recalculate_all_rankings(session: AsyncSession) -> None:
    """Assign all_time_rank and weekly_rank to every user in user_stats_cache.
    Caches the top-100 for each leaderboard type in Redis (60-second TTL).
    """
    # ---- All-time ranking by total_pnl_percent DESC ----
    alltime_result = await session.execute(
        select(UserStatsCache, UserProfile.nickname, User.tier, UserProfile.level)
        .join(UserProfile, UserStatsCache.user_id == UserProfile.user_id, isouter=True)
        .join(User, UserStatsCache.user_id == User.id)
        .order_by(UserStatsCache.total_pnl_percent.desc())
    )
    alltime_rows = alltime_result.all()

    alltime_top100 = []
    for rank, (stats, nickname, tier, level) in enumerate(alltime_rows, start=1):
        stats.all_time_rank = rank
        if rank <= 100:
            alltime_top100.append({
                "rank": rank,
                "user_id": str(stats.user_id),
                "nickname": nickname or "Anonymous",
                "tier": tier if isinstance(tier, str) else (tier.value if tier else "free"),
                "level": level or 1,
                "total_pnl_percent": float(stats.total_pnl_percent),
                "total_trades": stats.total_trades,
                "win_rate": float(stats.win_rate),
                "total_volume_usd": stats.total_volume / 100,
            })

    # ---- Volume ranking by total_volume DESC ----
    volume_result = await session.execute(
        select(UserStatsCache, UserProfile.nickname, User.tier, UserProfile.level)
        .join(UserProfile, UserStatsCache.user_id == UserProfile.user_id, isouter=True)
        .join(User, UserStatsCache.user_id == User.id)
        .order_by(UserStatsCache.total_volume.desc())
    )
    volume_rows = volume_result.all()

    volume_top100 = []
    for rank, (stats, nickname, tier, level) in enumerate(volume_rows, start=1):
        if rank <= 100:
            volume_top100.append({
                "rank": rank,
                "user_id": str(stats.user_id),
                "nickname": nickname or "Anonymous",
                "tier": tier if isinstance(tier, str) else (tier.value if tier else "free"),
                "level": level or 1,
                "total_pnl_percent": float(stats.total_pnl_percent),
                "total_trades": stats.total_trades,
                "win_rate": float(stats.win_rate),
                "total_volume_usd": stats.total_volume / 100,
            })

    # ---- Weekly ranking by pnl_percent DESC (current week only) ----
    week_start = get_current_week_start()
    weekly_result = await session.execute(
        select(LeaderboardWeekly, UserProfile.nickname, User.tier, UserProfile.level)
        .join(UserProfile, LeaderboardWeekly.user_id == UserProfile.user_id, isouter=True)
        .join(User, LeaderboardWeekly.user_id == User.id)
        .where(LeaderboardWeekly.week_start == week_start)
        .order_by(LeaderboardWeekly.pnl_percent.desc())
    )
    weekly_rows = weekly_result.all()

    weekly_top100 = []
    for rank, (weekly, nickname, tier, level) in enumerate(weekly_rows, start=1):
        weekly.rank = rank
        # Write weekly_rank back to user_stats_cache
        cache_result = await session.execute(
            select(UserStatsCache).where(UserStatsCache.user_id == weekly.user_id)
        )
        cache_row = cache_result.scalar_one_or_none()
        if cache_row:
            cache_row.weekly_rank = rank

        if rank <= 100:
            weekly_top100.append({
                "rank": rank,
                "user_id": str(weekly.user_id),
                "nickname": nickname or "Anonymous",
                "tier": tier if isinstance(tier, str) else (tier.value if tier else "free"),
                "level": level or 1,
                "total_pnl_percent": float(weekly.pnl_percent),
                "total_trades": weekly.trades_this_week,
                "win_rate": None,
                "total_volume_usd": None,
            })

    await session.commit()

    # ---- Cache top-100 in Redis ----
    redis = get_redis_client()
    if redis:
        cache_pairs = [
            ("leaderboard:alltime:top100", alltime_top100),
            ("leaderboard:volume:top100", volume_top100),
            ("leaderboard:weekly:top100", weekly_top100),
        ]
        for key, data in cache_pairs:
            try:
                await redis.set(key, json.dumps(data), ex=LEADERBOARD_CACHE_TTL)
            except Exception as exc:
                logger.warning("Failed to cache %s: %s", key, exc)

    logger.info(
        "Rankings recalculated: alltime=%d weekly=%d volume=%d",
        len(alltime_rows), len(weekly_rows), len(volume_rows),
    )


# ============================================================================
# STEP 3: WEEKLY SNAPSHOTS
# ============================================================================

async def snapshot_weekly_start(session: AsyncSession) -> None:
    """Capture starting portfolio values for all users at the start of each week.
    Called Monday 00:05 UTC. Idempotent — skips users already snapshotted.
    """
    week_start = get_current_week_start()
    week_end = get_current_week_end()

    # All users who have a portfolio (i.e., are active participants)
    portfolios_result = await session.execute(select(Portfolio))
    portfolios = portfolios_result.scalars().all()

    created = 0
    for portfolio in portfolios:
        # Idempotency check
        existing_result = await session.execute(
            select(LeaderboardWeekly).where(
                LeaderboardWeekly.user_id == portfolio.user_id,
                LeaderboardWeekly.week_start == week_start,
            )
        )
        if existing_result.scalar_one_or_none():
            continue

        session.add(
            LeaderboardWeekly(
                user_id=portfolio.user_id,
                week_start=week_start,
                week_end=week_end,
                starting_value=portfolio.total_value,
            )
        )
        created += 1

    await session.commit()
    logger.info(
        "Weekly start snapshot: week=%s snapshots_created=%d", week_start, created
    )


async def snapshot_weekly_end(session: AsyncSession) -> None:
    """Capture ending portfolio values and compute week P&L for all users.
    Called Sunday 23:55 UTC. Only processes entries where ending_value is NULL.
    """
    week_start = get_current_week_start()

    # Only entries not yet finalized (ending_value is NULL)
    entries_result = await session.execute(
        select(LeaderboardWeekly).where(
            LeaderboardWeekly.week_start == week_start,
            LeaderboardWeekly.ending_value.is_(None),
        )
    )
    entries = entries_result.scalars().all()

    for entry in entries:
        portfolio_result = await session.execute(
            select(Portfolio).where(Portfolio.user_id == entry.user_id)
        )
        portfolio = portfolio_result.scalar_one_or_none()
        ending_value = portfolio.total_value if portfolio else (entry.starting_value or 0)

        entry.ending_value = ending_value

        if entry.starting_value and entry.starting_value > 0:
            entry.pnl = ending_value - entry.starting_value
            entry.pnl_percent = round(
                float(entry.pnl / entry.starting_value * 100), 4
            )
        else:
            entry.pnl = 0
            entry.pnl_percent = 0.0

        # Count trades made during this week
        week_start_dt = datetime(
            week_start.year, week_start.month, week_start.day,
            tzinfo=timezone.utc,
        )
        trades_count_result = await session.execute(
            select(func.count()).select_from(Trade).where(
                Trade.user_id == entry.user_id,
                Trade.executed_at >= week_start_dt,
            )
        )
        entry.trades_this_week = trades_count_result.scalar() or 0

    await session.commit()
    logger.info(
        "Weekly end snapshot: week=%s entries_finalized=%d", week_start, len(entries)
    )
