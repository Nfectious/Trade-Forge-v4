"""
Contest & Leaderboard Scheduler Service
Four background asyncio tasks.

Contest tasks:
  Task 1 — Rankings (every 5 minutes):
    Recalculates portfolio values and rankings for all active contests.
    Redis lock: "contest_scheduler:rankings:lock" (4-minute TTL).

  Task 2 — Lifecycle (every 1 minute):
    Transitions upcoming → active when start_time is reached and minimum
    participants are enrolled. Transitions active → completed (finalized)
    when end_time is reached.
    Redis lock: "contest_scheduler:lifecycle:lock" (55-second TTL).

Leaderboard tasks:
  Task 3 — Hourly stats (every hour):
    Recalculates UserStatsCache for users who traded in the last hour,
    then re-ranks everyone.
    Redis lock: "leaderboard:stats:lock" (3500-second TTL).

  Task 4 — Weekly snapshots (every 5 minutes, time-gated):
    Monday 00:05–00:10 UTC: snapshot_weekly_start() — captures starting values.
    Sunday 23:55–24:00 UTC: snapshot_weekly_end() — finalizes weekly P&L.
    Redis one-shot flags prevent double execution within the same week.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.core.database import async_session
from app.core.redis import get_redis_client
from app.models.contest import Contest
from app.models.trade import Trade
from app.services.contest_engine import (
    calculate_contest_rankings,
    finalize_contest,
)
from app.services.leaderboard_service import (
    recalculate_all_rankings,
    recalculate_user_stats,
    snapshot_weekly_end,
    snapshot_weekly_start,
)

logger = logging.getLogger(__name__)

# ---- Contest scheduler constants ----
RANKINGS_LOCK_KEY = "contest_scheduler:rankings:lock"
RANKINGS_LOCK_TTL = 240    # 4 minutes
RANKINGS_INTERVAL = 300    # 5 minutes

LIFECYCLE_LOCK_KEY = "contest_scheduler:lifecycle:lock"
LIFECYCLE_LOCK_TTL = 55    # 55 seconds
LIFECYCLE_INTERVAL = 60    # 1 minute

# ---- Leaderboard scheduler constants ----
LEADERBOARD_STATS_LOCK_KEY = "leaderboard:stats:lock"
LEADERBOARD_STATS_LOCK_TTL = 3500  # just under 1 hour
LEADERBOARD_STATS_INTERVAL = 3600  # 1 hour

WEEKLY_SNAPSHOT_INTERVAL = 300     # 5 minutes; logic is time-gated internally


# ============================================================================
# TASK 1 — CONTEST RANKINGS
# ============================================================================

async def run_rankings_cycle() -> None:
    """Recalculate rankings for all active contests (single cycle)."""
    redis = get_redis_client()
    if not redis:
        logger.warning("Contest rankings: Redis unavailable, skipping cycle")
        return

    acquired = await redis.set(RANKINGS_LOCK_KEY, "1", nx=True, ex=RANKINGS_LOCK_TTL)
    if not acquired:
        logger.debug("Contest rankings: lock held by another instance, skipping")
        return

    async with async_session() as session:
        try:
            result = await session.execute(
                select(Contest).where(Contest.status == "active")
            )
            active_contests = result.scalars().all()
        except Exception as exc:
            logger.error("Rankings cycle: failed to fetch active contests: %s", exc)
            return

    logger.debug("Rankings cycle: updating %d active contest(s)", len(active_contests))

    for contest in active_contests:
        try:
            async with async_session() as session:
                await calculate_contest_rankings(contest.id, session)
        except Exception as exc:
            logger.error(
                "Rankings cycle: failed for contest %s: %s",
                contest.id, exc,
                exc_info=True,
            )
            continue


async def _start_rankings_loop() -> None:
    """Infinite loop running the rankings cycle every 5 minutes."""
    logger.info("Contest rankings scheduler started (5-minute interval)")
    while True:
        try:
            await run_rankings_cycle()
        except Exception as exc:
            logger.error("Rankings loop error: %s", exc, exc_info=True)
        await asyncio.sleep(RANKINGS_INTERVAL)


# ============================================================================
# TASK 2 — CONTEST LIFECYCLE
# ============================================================================

async def run_lifecycle_cycle() -> None:
    """Transition contests between upcoming → active → completed (single cycle)."""
    redis = get_redis_client()
    if not redis:
        logger.warning("Contest lifecycle: Redis unavailable, skipping cycle")
        return

    acquired = await redis.set(LIFECYCLE_LOCK_KEY, "1", nx=True, ex=LIFECYCLE_LOCK_TTL)
    if not acquired:
        logger.debug("Contest lifecycle: lock held by another instance, skipping")
        return

    now = datetime.now(timezone.utc)

    # ---- Upcoming → Active ----
    async with async_session() as session:
        try:
            upcoming_result = await session.execute(
                select(Contest).where(
                    Contest.status == "upcoming",
                    Contest.start_time <= now,
                )
            )
            upcoming = upcoming_result.scalars().all()
        except Exception as exc:
            logger.error("Lifecycle cycle: failed to fetch upcoming contests: %s", exc)
            upcoming = []

    for contest in upcoming:
        if contest.current_participants < contest.min_participants:
            logger.debug(
                "Contest %s not started: participants=%d < min=%d",
                contest.id, contest.current_participants, contest.min_participants,
            )
            continue

        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Contest).where(Contest.id == contest.id)
                )
                db_contest = result.scalar_one_or_none()
                if db_contest and db_contest.status == "upcoming":
                    db_contest.status = "active"
                    db_contest.updated_at = now
                    await session.commit()
                    logger.info(
                        "Contest activated: id=%s name=%s", db_contest.id, db_contest.name
                    )
        except Exception as exc:
            logger.error(
                "Lifecycle cycle: failed to activate contest %s: %s",
                contest.id, exc,
                exc_info=True,
            )
            continue

    # ---- Active → Completed ----
    async with async_session() as session:
        try:
            active_result = await session.execute(
                select(Contest).where(
                    Contest.status == "active",
                    Contest.end_time <= now,
                )
            )
            ended = active_result.scalars().all()
        except Exception as exc:
            logger.error("Lifecycle cycle: failed to fetch ended contests: %s", exc)
            ended = []

    for contest in ended:
        try:
            async with async_session() as session:
                await finalize_contest(contest.id, session)
                logger.info("Contest finalized by scheduler: id=%s", contest.id)
        except ValueError as exc:
            logger.debug("Lifecycle cycle: contest %s skipped: %s", contest.id, exc)
        except Exception as exc:
            logger.error(
                "Lifecycle cycle: failed to finalize contest %s: %s",
                contest.id, exc,
                exc_info=True,
            )
            continue


async def _start_lifecycle_loop() -> None:
    """Infinite loop running the lifecycle cycle every 1 minute."""
    logger.info("Contest lifecycle scheduler started (1-minute interval)")
    while True:
        try:
            await run_lifecycle_cycle()
        except Exception as exc:
            logger.error("Lifecycle loop error: %s", exc, exc_info=True)
        await asyncio.sleep(LIFECYCLE_INTERVAL)


# ============================================================================
# TASK 3 — LEADERBOARD HOURLY STATS
# ============================================================================

async def run_leaderboard_stats_cycle() -> None:
    """Recalculate stats for users who traded in the last hour, then re-rank all."""
    redis = get_redis_client()
    if not redis:
        logger.warning("Leaderboard stats: Redis unavailable, skipping cycle")
        return

    acquired = await redis.set(
        LEADERBOARD_STATS_LOCK_KEY, "1", nx=True, ex=LEADERBOARD_STATS_LOCK_TTL
    )
    if not acquired:
        logger.debug("Leaderboard stats: lock held by another instance, skipping")
        return

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    async with async_session() as session:
        try:
            result = await session.execute(
                select(Trade.user_id)
                .where(Trade.executed_at >= one_hour_ago)
                .distinct()
            )
            user_ids = result.scalars().all()
        except Exception as exc:
            logger.error("Leaderboard stats: failed to fetch active traders: %s", exc)
            return

    logger.debug("Leaderboard stats: recalculating for %d user(s)", len(user_ids))

    for user_id in user_ids:
        try:
            async with async_session() as session:
                await recalculate_user_stats(user_id, session)
        except Exception as exc:
            logger.error(
                "Leaderboard stats: failed for user %s: %s", user_id, exc
            )
            continue

    if user_ids:
        try:
            async with async_session() as session:
                await recalculate_all_rankings(session)
        except Exception as exc:
            logger.error("Leaderboard stats: ranking recalculation failed: %s", exc)


async def _start_leaderboard_hourly_loop() -> None:
    """Infinite loop running the leaderboard stats cycle every hour."""
    logger.info("Leaderboard stats scheduler started (1-hour interval)")
    while True:
        try:
            await run_leaderboard_stats_cycle()
        except Exception as exc:
            logger.error("Leaderboard stats loop error: %s", exc, exc_info=True)
        await asyncio.sleep(LEADERBOARD_STATS_INTERVAL)


# ============================================================================
# TASK 4 — WEEKLY LEADERBOARD SNAPSHOTS
# ============================================================================

async def run_weekly_snapshot_check() -> None:
    """Time-gated weekly snapshot logic (runs every 5 minutes).

    Monday 00:05–00:10 UTC → snapshot_weekly_start()
    Sunday 23:55–24:00 UTC → snapshot_weekly_end()

    Redis one-shot flags (keyed by ISO week) prevent double execution.
    """
    redis = get_redis_client()
    if not redis:
        logger.warning("Weekly snapshot: Redis unavailable, skipping check")
        return

    now = datetime.now(timezone.utc)
    weekday = now.weekday()   # 0 = Monday, 6 = Sunday
    hour = now.hour
    minute = now.minute
    week_str = now.strftime("%Y-%W")  # e.g. "2025-17"

    # ---- Monday 00:05–00:10: weekly start snapshot ----
    if weekday == 0 and hour == 0 and 5 <= minute < 10:
        flag_key = f"leaderboard:weekly_start:{week_str}"
        acquired = await redis.set(flag_key, "1", nx=True, ex=86400 * 7)
        if acquired:
            try:
                async with async_session() as session:
                    await snapshot_weekly_start(session)
                logger.info("Weekly start snapshot taken: week=%s", week_str)
            except Exception as exc:
                logger.error("Weekly start snapshot failed: %s", exc, exc_info=True)

    # ---- Sunday 23:55–24:00: weekly end snapshot ----
    if weekday == 6 and hour == 23 and 55 <= minute < 60:
        flag_key = f"leaderboard:weekly_end:{week_str}"
        acquired = await redis.set(flag_key, "1", nx=True, ex=86400 * 7)
        if acquired:
            try:
                async with async_session() as session:
                    await snapshot_weekly_end(session)
                logger.info("Weekly end snapshot taken: week=%s", week_str)
            except Exception as exc:
                logger.error("Weekly end snapshot failed: %s", exc, exc_info=True)


async def _start_weekly_snapshot_loop() -> None:
    """Infinite loop checking weekly snapshot conditions every 5 minutes."""
    logger.info("Weekly snapshot scheduler started (5-minute check interval)")
    while True:
        try:
            await run_weekly_snapshot_check()
        except Exception as exc:
            logger.error("Weekly snapshot loop error: %s", exc, exc_info=True)
        await asyncio.sleep(WEEKLY_SNAPSHOT_INTERVAL)


# ============================================================================
# ENTRY POINT
# ============================================================================

async def start_contest_scheduler() -> None:
    """Launch all four scheduler loops concurrently.
    This coroutine runs forever (all inner tasks are infinite loops).
    """
    logger.info("Contest + leaderboard scheduler starting four background tasks")
    await asyncio.gather(
        _start_rankings_loop(),
        _start_lifecycle_loop(),
        _start_leaderboard_hourly_loop(),
        _start_weekly_snapshot_loop(),
    )
