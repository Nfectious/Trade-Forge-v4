"""
Leaderboard API routes
Global rankings (all-time, weekly, volume), personal rank lookup,
and contest-specific leaderboards.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_current_user, get_current_user_optional
from app.core.redis import get_redis_client
from app.core.security import limiter
from app.models.contest import Contest, ContestEntry, ContestPortfolio
from app.models.leaderboard import LeaderboardWeekly, UserStatsCache
from app.models.user import User, UserProfile
from app.services.leaderboard_service import get_current_week_start

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# HELPERS
# ============================================================================

def _tier_str(tier) -> str:
    """Normalize a TierLevel enum or string to a plain string."""
    if tier is None:
        return "free"
    return tier if isinstance(tier, str) else tier.value


# ============================================================================
# GET /leaderboard/global
# ============================================================================

@router.get("/global")
@limiter.limit("120/minute")
async def get_global_leaderboard(
    request: Request,
    type: str = Query(default="alltime", pattern="^(alltime|weekly|volume)$"),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Global leaderboard with pagination.

    type=alltime  — ordered by all-time realized P&L % (cached in Redis)
    type=weekly   — ordered by current-week P&L %
    type=volume   — ordered by cumulative trade volume
    """
    redis = get_redis_client()
    offset = (page - 1) * limit

    # ---- Try Redis cache for page 1 ----
    if page == 1 and redis:
        try:
            cached_raw = await redis.get(f"leaderboard:{type}:top100")
            if cached_raw:
                all_entries = json.loads(cached_raw)
                page_entries = all_entries[:limit]

                # Count from DB for correct pagination metadata
                if type == "weekly":
                    week_start = get_current_week_start()
                    count_result = await session.execute(
                        select(func.count()).select_from(LeaderboardWeekly).where(
                            LeaderboardWeekly.week_start == week_start
                        )
                    )
                else:
                    count_result = await session.execute(
                        select(func.count()).select_from(UserStatsCache)
                    )
                total = count_result.scalar() or 0

                return {
                    "type": type,
                    "total_entries": total,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "page": 1,
                    "total_pages": max(1, (total + limit - 1) // limit),
                    "from_cache": True,
                    "entries": page_entries,
                }
        except Exception as exc:
            logger.debug("Leaderboard cache miss (%s): %s", type, exc)

    # ---- DB query ----
    if type == "alltime":
        stmt = (
            select(UserStatsCache, UserProfile.nickname, User.tier, UserProfile.level)
            .join(UserProfile, UserStatsCache.user_id == UserProfile.user_id, isouter=True)
            .join(User, UserStatsCache.user_id == User.id)
            .order_by(UserStatsCache.total_pnl_percent.desc())
        )
        count_stmt = select(func.count()).select_from(UserStatsCache)

    elif type == "weekly":
        week_start = get_current_week_start()
        stmt = (
            select(LeaderboardWeekly, UserProfile.nickname, User.tier, UserProfile.level)
            .join(UserProfile, LeaderboardWeekly.user_id == UserProfile.user_id, isouter=True)
            .join(User, LeaderboardWeekly.user_id == User.id)
            .where(LeaderboardWeekly.week_start == week_start)
            .order_by(LeaderboardWeekly.pnl_percent.desc())
        )
        count_stmt = select(func.count()).select_from(LeaderboardWeekly).where(
            LeaderboardWeekly.week_start == week_start
        )

    else:  # volume
        stmt = (
            select(UserStatsCache, UserProfile.nickname, User.tier, UserProfile.level)
            .join(UserProfile, UserStatsCache.user_id == UserProfile.user_id, isouter=True)
            .join(User, UserStatsCache.user_id == User.id)
            .order_by(UserStatsCache.total_volume.desc())
        )
        count_stmt = select(func.count()).select_from(UserStatsCache)

    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    rows_result = await session.execute(stmt.offset(offset).limit(limit))
    rows = rows_result.all()

    entries = []
    for idx, row in enumerate(rows):
        if type == "weekly":
            weekly, nickname, tier, level = row
            entries.append({
                "rank": weekly.rank or (offset + idx + 1),
                "user_id": str(weekly.user_id),
                "nickname": nickname or "Anonymous",
                "tier": _tier_str(tier),
                "level": level or 1,
                "total_pnl_percent": float(weekly.pnl_percent),
                "total_trades": weekly.trades_this_week,
                "win_rate": None,
                "total_volume_usd": None,
            })
        else:
            stats, nickname, tier, level = row
            entries.append({
                "rank": (
                    stats.all_time_rank if type == "alltime" else (offset + idx + 1)
                ),
                "user_id": str(stats.user_id),
                "nickname": nickname or "Anonymous",
                "tier": _tier_str(tier),
                "level": level or 1,
                "total_pnl_percent": float(stats.total_pnl_percent),
                "total_trades": stats.total_trades,
                "win_rate": float(stats.win_rate),
                "total_volume_usd": stats.total_volume / 100,
            })

    return {
        "type": type,
        "total_entries": total,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "page": page,
        "total_pages": max(1, (total + limit - 1) // limit) if total else 1,
        "entries": entries,
    }


# ============================================================================
# GET /leaderboard/my-rank
# ============================================================================

@router.get("/my-rank")
@limiter.limit("60/minute")
async def get_my_rank(
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Current user's rank on all three leaderboards plus their full stats."""
    stats_result = await session.execute(
        select(UserStatsCache).where(UserStatsCache.user_id == current_user.id)
    )
    stats = stats_result.scalar_one_or_none()

    if not stats:
        return {
            "alltime_rank": None,
            "weekly_rank": None,
            "volume_rank": None,
            "stats": None,
            "message": "No trading history yet. Make your first trade to appear on the leaderboard.",
        }

    # Volume rank: count users with higher total_volume + 1
    volume_rank_result = await session.execute(
        select(func.count()).select_from(UserStatsCache).where(
            UserStatsCache.total_volume > stats.total_volume
        )
    )
    volume_rank = (volume_rank_result.scalar() or 0) + 1

    return {
        "alltime_rank": stats.all_time_rank,
        "weekly_rank": stats.weekly_rank,
        "volume_rank": volume_rank,
        "stats": {
            "total_realized_pnl": stats.total_realized_pnl / 100,
            "total_pnl_percent": float(stats.total_pnl_percent),
            "total_trades": stats.total_trades,
            "winning_trades": stats.winning_trades,
            "win_rate": float(stats.win_rate),
            "total_volume_usd": stats.total_volume / 100,
            "best_trade_pnl_percent": float(stats.best_trade_pnl_percent),
            "worst_trade_pnl_percent": float(stats.worst_trade_pnl_percent),
            "current_win_streak": stats.current_win_streak,
            "longest_win_streak": stats.longest_win_streak,
            "last_updated": stats.last_updated.isoformat(),
        },
    }


# ============================================================================
# GET /leaderboard/contest/{contest_id}
# ============================================================================

@router.get("/contest/{contest_id}")
@limiter.limit("60/minute")
async def get_contest_leaderboard(
    request: Request,
    contest_id: UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """Ranked participant list for a specific contest."""
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

    count_result = await session.execute(
        select(func.count()).select_from(ContestPortfolio).where(
            ContestPortfolio.contest_id == contest_id
        )
    )
    total = count_result.scalar() or 0

    rows_result = await session.execute(
        select(ContestPortfolio, UserProfile.nickname)
        .join(
            UserProfile,
            ContestPortfolio.user_id == UserProfile.user_id,
            isouter=True,
        )
        .where(ContestPortfolio.contest_id == contest_id)
        .order_by(ContestPortfolio.rank.asc().nulls_last(), ContestPortfolio.total_value.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = rows_result.all()

    starting_balance = contest.starting_balance

    return {
        "type": "contest",
        "contest_id": str(contest_id),
        "contest_name": contest.name,
        "contest_status": contest.status,
        "total_entries": total,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "page": page,
        "total_pages": max(1, (total + limit - 1) // limit) if total else 1,
        "entries": [
            {
                "rank": portfolio.rank or (offset + idx + 1),
                "user_id": str(portfolio.user_id),
                "nickname": nickname or "Anonymous",
                "total_value": portfolio.total_value / 100,
                "pnl": portfolio.unrealized_pnl / 100,
                "pnl_percent": (
                    round(
                        float(portfolio.unrealized_pnl / starting_balance * 100), 4
                    )
                    if starting_balance > 0 else 0.0
                ),
                "total_trades": portfolio.total_trades,
                "last_updated": portfolio.last_calculated.isoformat(),
            }
            for idx, (portfolio, nickname) in enumerate(rows)
        ],
    }


# ============================================================================
# GET /leaderboard/contest/{contest_id}/my-position
# ============================================================================

@router.get("/contest/{contest_id}/my-position")
@limiter.limit("60/minute")
async def get_my_contest_position(
    request: Request,
    contest_id: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Requesting user's rank, portfolio value, and P&L within a contest."""
    contest_result = await session.execute(
        select(Contest).where(Contest.id == contest_id)
    )
    contest = contest_result.scalar_one_or_none()
    if not contest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contest not found",
        )

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
            detail="Contest portfolio not found",
        )

    # Total participants for context
    count_result = await session.execute(
        select(func.count()).select_from(ContestPortfolio).where(
            ContestPortfolio.contest_id == contest_id
        )
    )
    total_participants = count_result.scalar() or 0

    starting_balance = contest.starting_balance

    return {
        "contest_id": str(contest_id),
        "contest_name": contest.name,
        "contest_status": contest.status,
        "rank": portfolio.rank,
        "total_participants": total_participants,
        "total_value": portfolio.total_value / 100,
        "cash_balance": portfolio.cash_balance / 100,
        "pnl": portfolio.unrealized_pnl / 100,
        "pnl_percent": (
            round(
                float(portfolio.unrealized_pnl / starting_balance * 100), 4
            )
            if starting_balance > 0 else 0.0
        ),
        "total_trades": portfolio.total_trades,
        "final_rank": entry.final_rank,
        "final_pnl": entry.final_pnl / 100 if entry.final_pnl is not None else None,
        "final_pnl_percent": entry.final_pnl_percent,
        "last_updated": portfolio.last_calculated.isoformat(),
    }
