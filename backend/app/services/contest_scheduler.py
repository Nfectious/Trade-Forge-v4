"""
Contest Scheduler Service
Two background asyncio tasks that manage contest lifecycles and rankings.

Task 1 — Rankings (every 5 minutes):
  Recalculates portfolio values and rankings for all active contests.
  Redis lock: "contest_scheduler:rankings:lock" (4-minute TTL).

Task 2 — Lifecycle (every 1 minute):
  Transitions upcoming → active when start_time is reached and minimum
  participants are enrolled. Transitions active → completed (finalized)
  when end_time is reached.
  Redis lock: "contest_scheduler:lifecycle:lock" (55-second TTL).
"""

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlmodel import select

from app.core.database import async_session
from app.core.redis import get_redis_client
from app.models.contest import Contest
from app.services.contest_engine import (
    calculate_contest_rankings,
    finalize_contest,
)

logger = logging.getLogger(__name__)

RANKINGS_LOCK_KEY = "contest_scheduler:rankings:lock"
RANKINGS_LOCK_TTL = 240   # 4 minutes (seconds)
RANKINGS_INTERVAL = 300   # 5 minutes (seconds)

LIFECYCLE_LOCK_KEY = "contest_scheduler:lifecycle:lock"
LIFECYCLE_LOCK_TTL = 55   # 55 seconds
LIFECYCLE_INTERVAL = 60   # 1 minute (seconds)


# ============================================================================
# TASK 1 — RANKINGS UPDATE
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
            continue  # never let one contest failure stop the rest


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
# TASK 2 — LIFECYCLE TRANSITIONS
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
    # Condition: start_time has passed AND participant count meets minimum
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
                "Contest %s not started yet: participants=%d < min=%d",
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
                    logger.info("Contest activated: id=%s name=%s", db_contest.id, db_contest.name)
        except Exception as exc:
            logger.error(
                "Lifecycle cycle: failed to activate contest %s: %s",
                contest.id, exc,
                exc_info=True,
            )
            continue

    # ---- Active → Completed ----
    # Condition: end_time has passed
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
            # Already completed or cancelled — not a scheduler error
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
# ENTRY POINT
# ============================================================================

async def start_contest_scheduler() -> None:
    """Launch both scheduler loops concurrently.
    This coroutine runs forever (both inner tasks are infinite loops).
    """
    logger.info("Contest scheduler starting two background tasks")
    await asyncio.gather(
        _start_rankings_loop(),
        _start_lifecycle_loop(),
    )
