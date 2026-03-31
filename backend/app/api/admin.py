# backend/app/api/admin.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import require_admin
from app.models.contest import Contest, ContestEntry, ContestResponse
from app.models.payment import PaymentTransaction
from app.models.trade import Trade, TradingPair
from app.models.user import TierLevel, User, UserProfile, UserResponse

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _today_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _month_start_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


# ── Stats: Overview ───────────────────────────────────────────────────────────

@router.get("/stats/overview")
async def stats_overview(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Aggregated platform stats for the admin dashboard."""
    today = _today_utc()
    month_start = _month_start_utc()

    # Total users
    total_users_res = await session.execute(
        select(func.count()).select_from(User)
    )
    total_users: int = total_users_res.scalar() or 0

    # Active today (last_login >= today)
    active_today_res = await session.execute(
        select(func.count()).select_from(User).where(User.last_login >= today)
    )
    active_today: int = active_today_res.scalar() or 0

    # Trades today
    trades_today_res = await session.execute(
        select(func.count()).select_from(Trade).where(Trade.executed_at >= today)
    )
    trades_today: int = trades_today_res.scalar() or 0

    # Revenue this month (payment_transactions status='succeeded')
    revenue_res = await session.execute(
        select(func.coalesce(func.sum(PaymentTransaction.amount_cents), 0))
        .where(PaymentTransaction.status == "succeeded")
        .where(PaymentTransaction.created_at >= month_start)
    )
    revenue_cents: int = revenue_res.scalar() or 0

    # Contest counts by status
    contest_counts_res = await session.execute(
        select(Contest.status, func.count()).group_by(Contest.status)
    )
    contest_counts = {row[0]: row[1] for row in contest_counts_res.all()}

    # User tier distribution
    tier_dist_res = await session.execute(
        select(User.tier, func.count()).group_by(User.tier)
    )
    tier_distribution = {row[0]: row[1] for row in tier_dist_res.all()}

    # Total volume (all-time, sum of trade total_values in cents)
    volume_res = await session.execute(
        select(func.coalesce(func.sum(Trade.total_value), 0))
    )
    total_volume_cents: int = volume_res.scalar() or 0

    return {
        "total_users":        total_users,
        "active_today":       active_today,
        "trades_today":       trades_today,
        "revenue_month_cents": revenue_cents,
        "revenue_month_dollars": revenue_cents / 100,
        "total_volume_cents": total_volume_cents,
        "total_volume_dollars": total_volume_cents / 100,
        "contest_counts":     contest_counts,
        "tier_distribution":  tier_distribution,
    }


# ── Stats: Trading Activity ────────────────────────────────────────────────────

@router.get("/stats/trading-activity")
async def stats_trading_activity(
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Hourly trade count + volume for the last N days."""
    result = await session.execute(
        text("""
            SELECT
                date_trunc('hour', executed_at AT TIME ZONE 'UTC') AS hour,
                COUNT(*)::int                                       AS trade_count,
                COALESCE(SUM(total_value), 0)::bigint              AS volume_cents
            FROM trades
            WHERE executed_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY 1
            ORDER BY 1
        """),
        {"days": days},
    )
    rows = result.mappings().all()
    return [
        {
            "hour":        row["hour"].isoformat() if row["hour"] else None,
            "trade_count": row["trade_count"],
            "volume_cents": row["volume_cents"],
            "volume_dollars": row["volume_cents"] / 100,
        }
        for row in rows
    ]


# ── Stats: User Growth ────────────────────────────────────────────────────────

@router.get("/stats/user-growth")
async def stats_user_growth(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Daily new user registrations for the last N days."""
    result = await session.execute(
        text("""
            SELECT
                date_trunc('day', created_at AT TIME ZONE 'UTC') AS day,
                COUNT(*)::int AS registrations
            FROM users
            WHERE created_at >= NOW() - INTERVAL '1 day' * :days
            GROUP BY 1
            ORDER BY 1
        """),
        {"days": days},
    )
    rows = result.mappings().all()
    return [
        {
            "day":           row["day"].isoformat() if row["day"] else None,
            "registrations": row["registrations"],
        }
        for row in rows
    ]


# ── Users: Paginated list with search + tier filter ───────────────────────────

@router.get("/users")
async def list_users(
    search: Optional[str] = Query(None, max_length=100),
    tier:   Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page:   int = Query(1, ge=1),
    limit:  int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Paginated user list with optional search (email/nickname) and filters."""
    offset = (page - 1) * limit

    # Build user query with optional left join on user_profiles for nickname
    base = (
        select(
            User.id,
            User.email,
            User.role,
            User.status,
            User.tier,
            User.created_at,
            User.last_login,
            User.verified_at,
            UserProfile.nickname,
        )
        .outerjoin(UserProfile, UserProfile.user_id == User.id)
    )

    if search:
        pattern = f"%{search}%"
        base = base.where(
            (User.email.ilike(pattern)) | (UserProfile.nickname.ilike(pattern))
        )
    if tier:
        base = base.where(User.tier == tier)
    if status:
        base = base.where(User.status == status)

    # Count
    count_q = select(func.count()).select_from(
        base.subquery()
    )
    count_res = await session.execute(count_q)
    total: int = count_res.scalar() or 0

    # Paginated rows
    rows_res = await session.execute(
        base.order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    rows = rows_res.mappings().all()

    # Trade counts per user (batch via subquery for efficiency)
    user_ids = [row["id"] for row in rows]
    trade_counts: dict[UUID, int] = {}
    if user_ids:
        tc_res = await session.execute(
            select(Trade.user_id, func.count().label("cnt"))
            .where(Trade.user_id.in_(user_ids))
            .group_by(Trade.user_id)
        )
        trade_counts = {r.user_id: r.cnt for r in tc_res.all()}

    users_out = [
        {
            "id":         str(row["id"]),
            "email":      row["email"],
            "nickname":   row["nickname"],
            "role":       row["role"],
            "status":     row["status"],
            "tier":       row["tier"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "last_login": row["last_login"].isoformat() if row["last_login"] else None,
            "verified_at": row["verified_at"].isoformat() if row["verified_at"] else None,
            "total_trades": trade_counts.get(row["id"], 0),
        }
        for row in rows
    ]

    return {"users": users_out, "total": total, "page": page, "limit": limit}


# ── Users: Change Tier ────────────────────────────────────────────────────────

_VALID_TIERS = {t.value for t in TierLevel}


@router.put("/users/{user_id}/tier")
async def change_user_tier(
    user_id: str,
    body: dict,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Change a user's subscription tier (admin only)."""
    new_tier = (body.get("tier") or "").lower()
    if new_tier not in _VALID_TIERS:
        raise HTTPException(400, f"Invalid tier. Must be one of: {', '.join(sorted(_VALID_TIERS))}")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    old_tier = user.tier
    user.tier = TierLevel(new_tier)
    user.updated_at = datetime.now(timezone.utc)
    await session.commit()

    return {"message": f"User {user.email} tier changed from {old_tier} to {new_tier}"}


# ── Users: Ban / Unban ────────────────────────────────────────────────────────

@router.patch("/users/{user_id}/ban")
@router.put("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Ban a user (admin only)."""
    if str(admin.id) == user_id:
        admin_count = await session.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if admin_count.scalar() <= 1:
            raise HTTPException(400, "Cannot ban the last admin account")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.status = "banned"
    user.suspension_reason = "Banned via admin panel"
    await session.commit()
    return {"message": f"User {user.email} banned"}


@router.patch("/users/{user_id}/unban")
@router.put("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Unban a user (admin only)."""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.status = "active"
    user.suspension_reason = None
    await session.commit()
    return {"message": f"User {user.email} unbanned"}


# ── Contests: List all with participant counts ────────────────────────────────

@router.get("/contests")
async def list_contests(
    status: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """All contests with participant counts (admin only)."""
    q = select(Contest).order_by(Contest.created_at.desc())
    if status:
        q = q.where(Contest.status == status)

    result = await session.execute(q)
    contests = result.scalars().all()

    # Participant counts per contest
    contest_ids = [c.id for c in contests]
    part_counts: dict[UUID, int] = {}
    if contest_ids:
        pc_res = await session.execute(
            select(ContestEntry.contest_id, func.count().label("cnt"))
            .where(ContestEntry.contest_id.in_(contest_ids))
            .where(ContestEntry.status == "active")
            .group_by(ContestEntry.contest_id)
        )
        part_counts = {r.contest_id: r.cnt for r in pc_res.all()}

    return [
        {
            "id":                  str(c.id),
            "name":                c.name,
            "description":         c.description,
            "type":                c.type,
            "status":              c.status,
            "entry_fee":           c.entry_fee,
            "prize_pool":          c.prize_pool,
            "prize_pool_dollars":  c.prize_pool / 100,
            "max_participants":    c.max_participants,
            "current_participants": part_counts.get(c.id, c.current_participants),
            "start_time":          c.start_time.isoformat(),
            "end_time":            c.end_time.isoformat(),
            "starting_balance":    c.starting_balance,
            "prize_distributed":   c.prize_distributed,
            "created_at":          c.created_at.isoformat(),
        }
        for c in contests
    ]


# ── Trades: Recent platform-wide feed ────────────────────────────────────────

@router.get("/trades/recent")
async def recent_trades(
    limit:  int = Query(50, ge=1, le=200),
    symbol: Optional[str] = Query(None),
    side:   Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Most recent platform-wide trades for the admin trade monitor."""
    q = (
        select(
            Trade.id,
            Trade.user_id,
            TradingPair.symbol,
            Trade.side,
            Trade.quantity,
            Trade.price,
            Trade.total_value,
            Trade.pnl,
            Trade.executed_at,
            User.email.label("user_email"),
        )
        .join(TradingPair, TradingPair.id == Trade.trading_pair_id)
        .join(User, User.id == Trade.user_id)
    )
    if symbol:
        q = q.where(TradingPair.symbol == symbol.upper())
    if side:
        q = q.where(Trade.side == side.lower())
    q = q.order_by(Trade.executed_at.desc()).limit(limit)

    result = await session.execute(q)
    rows = result.mappings().all()
    return [
        {
            "id":                str(row["id"]),
            "user_id":           str(row["user_id"]),
            "user_email":        row["user_email"],
            "symbol":            row["symbol"],
            "side":              row["side"],
            "quantity":          row["quantity"],
            "price":             row["price"],
            "total_value_dollars": (row["total_value"] or 0) / 100,
            "pnl_dollars":       (row["pnl"] or 0) / 100 if row["pnl"] is not None else None,
            "executed_at":       row["executed_at"].isoformat() if row["executed_at"] else None,
        }
        for row in rows
    ]


# ── Admin: Detailed health check ─────────────────────────────────────────────

@router.get("/health")
async def admin_health(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Comprehensive platform health snapshot for the admin dashboard."""
    import json as _json
    import os
    import time

    from app.core.redis import get_redis_client

    result: dict = {}

    # ── Database ──────────────────────────────────────────────────────────────
    db_start = time.monotonic()
    try:
        await session.execute(text("SELECT 1"))
        result["database"] = {
            "status": "up",
            "latency_ms": round((time.monotonic() - db_start) * 1000, 1),
        }
    except Exception as exc:
        result["database"] = {"status": "down", "error": str(exc)}

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis = get_redis_client()
    if redis:
        try:
            r_start = time.monotonic()
            await redis.ping()
            info = await redis.info("memory")
            result["redis"] = {
                "status": "up",
                "latency_ms": round((time.monotonic() - r_start) * 1000, 1),
                "used_memory_mb": round(info.get("used_memory", 0) / 1_048_576, 1),
                "peak_memory_mb": round(info.get("used_memory_peak", 0) / 1_048_576, 1),
            }
        except Exception as exc:
            result["redis"] = {"status": "down", "error": str(exc)}
    else:
        result["redis"] = {"status": "down", "error": "client not initialised"}

    # ── Price feed ────────────────────────────────────────────────────────────
    if redis:
        try:
            symbols_live, latest_ts = 0, None
            for exchange in ("binance", "bybit", "kraken"):
                for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"):
                    raw = await redis.get(f"price:{exchange}:{sym}")
                    if not raw:
                        continue
                    symbols_live += 1
                    try:
                        parsed = _json.loads(raw)
                        ts = parsed.get("timestamp") or parsed.get("ts")
                        if ts and (latest_ts is None or str(ts) > str(latest_ts)):
                            latest_ts = ts
                    except Exception:
                        pass
            stale = True
            if latest_ts:
                try:
                    age_s = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(latest_ts).replace("Z", "+00:00"))
                    ).total_seconds()
                    stale = age_s > 60
                except Exception:
                    pass
            result["price_feed"] = {
                "status": "stale" if stale else "live",
                "symbols_live": symbols_live,
                "last_update": latest_ts,
            }
        except Exception as exc:
            result["price_feed"] = {"status": "unknown", "error": str(exc)}
    else:
        result["price_feed"] = {"status": "unknown"}

    # ── Scheduler heartbeat (stored by scheduler in Redis) ────────────────────
    scheduler_info: dict = {"status": "unknown"}
    if redis:
        try:
            hb = await redis.get("scheduler:heartbeat")
            if hb:
                hb_data = _json.loads(hb)
                last_ran = hb_data.get("last_ran")
                age_s = 0
                if last_ran:
                    age_s = (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(str(last_ran).replace("Z", "+00:00"))
                    ).total_seconds()
                scheduler_info = {
                    "status": "running" if age_s < 120 else "stale",
                    "last_ran": last_ran,
                    "next_run": hb_data.get("next_run"),
                    "age_seconds": round(age_s),
                }
            else:
                scheduler_info = {"status": "no_heartbeat"}
        except Exception as exc:
            scheduler_info = {"status": "unknown", "error": str(exc)}
    result["scheduler"] = scheduler_info

    # ── Server ────────────────────────────────────────────────────────────────
    result["server"] = {
        "pid": os.getpid(),
        "uptime_seconds": round(time.monotonic()),
    }

    return result


# ── Admin Logs ─────────────────────────────────────────────────────────────────

@router.get("/logs")
async def list_admin_logs(
    page:  int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    """Recent admin action log entries."""
    offset = (page - 1) * limit
    result = await session.execute(
        text("""
            SELECT
                al.id,
                al.action,
                al.details,
                al.created_at,
                a.email  AS admin_email,
                tu.email AS target_email
            FROM admin_logs al
            JOIN users a  ON a.id  = al.admin_id
            LEFT JOIN users tu ON tu.id = al.target_user_id
            ORDER BY al.created_at DESC
            LIMIT :limit OFFSET :offset
        """),
        {"limit": limit, "offset": offset},
    )
    rows = result.mappings().all()

    count_res = await session.execute(text("SELECT COUNT(*) FROM admin_logs"))
    total: int = count_res.scalar() or 0

    return {
        "logs": [
            {
                "id":           str(row["id"]),
                "action":       row["action"],
                "details":      row["details"],
                "created_at":   row["created_at"].isoformat() if row["created_at"] else None,
                "admin_email":  row["admin_email"],
                "target_email": row["target_email"],
            }
            for row in rows
        ],
        "total": total,
        "page": page,
        "limit": limit,
    }
