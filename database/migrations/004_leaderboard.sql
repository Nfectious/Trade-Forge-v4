-- ============================================================================
-- Migration 004: Leaderboard System
-- Adds user stats cache and weekly snapshot tables for fast ranking queries.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. User stats cache — one row per user, updated by the leaderboard scheduler
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_stats_cache (
    user_id             UUID    PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    total_realized_pnl  BIGINT  DEFAULT 0,          -- cents; sum of trades.pnl
    total_pnl_percent   DECIMAL(10,4) DEFAULT 0.0,  -- % vs tier starting balance
    total_trades        INTEGER DEFAULT 0,
    winning_trades      INTEGER DEFAULT 0,
    win_rate            DECIMAL(5,2) DEFAULT 0.0,   -- 0–100
    total_volume        BIGINT  DEFAULT 0,           -- cents; sum of trades.total_value
    best_trade_pnl_percent  DECIMAL(10,4) DEFAULT 0.0,
    worst_trade_pnl_percent DECIMAL(10,4) DEFAULT 0.0,
    current_win_streak  INTEGER DEFAULT 0,
    longest_win_streak  INTEGER DEFAULT 0,
    all_time_rank       INTEGER,                     -- updated by recalculate_all_rankings
    weekly_rank         INTEGER,                     -- rank within current week
    last_updated        TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 2. Weekly leaderboard snapshots
--    Starting value captured Monday 00:05 UTC.
--    Ending value captured Sunday 23:55 UTC.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS leaderboard_weekly (
    id              UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID    NOT NULL REFERENCES users(id),
    week_start      DATE    NOT NULL,   -- Monday of the week
    week_end        DATE    NOT NULL,   -- Sunday of the week
    starting_value  BIGINT,             -- portfolio value at week start (cents)
    ending_value    BIGINT,             -- portfolio value at week end (cents)
    pnl             BIGINT  DEFAULT 0,  -- ending_value - starting_value (cents)
    pnl_percent     DECIMAL(10,4) DEFAULT 0.0,
    trades_this_week INTEGER DEFAULT 0,
    rank            INTEGER,
    UNIQUE(user_id, week_start)
);

-- ----------------------------------------------------------------------------
-- 3. Indexes
-- ----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_stats_cache_alltime
    ON user_stats_cache(total_pnl_percent DESC);

CREATE INDEX IF NOT EXISTS idx_stats_cache_volume
    ON user_stats_cache(total_volume DESC);

CREATE INDEX IF NOT EXISTS idx_weekly_week
    ON leaderboard_weekly(week_start, pnl_percent DESC);

CREATE INDEX IF NOT EXISTS idx_weekly_user
    ON leaderboard_weekly(user_id, week_start DESC);
