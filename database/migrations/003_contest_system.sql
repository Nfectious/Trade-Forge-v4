-- ============================================================================
-- Migration 003: Contest System
-- Adds contest portfolio isolation, entries, and contest trading tables.
-- Expands the contests table with prize, visibility, and lifecycle columns.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Expand contests table
-- ----------------------------------------------------------------------------

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'public';

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS invite_code VARCHAR(20);

-- Prize pool in cents (BIGINT). Display value = prize_pool / 100.
ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS prize_pool BIGINT DEFAULT 0;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS registration_deadline TIMESTAMPTZ;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS min_participants INTEGER DEFAULT 2;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS prize_distributed BOOLEAN DEFAULT false;

ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS winner_id UUID REFERENCES users(id);

-- Platform takes a configurable cut before distributing prizes.
ALTER TABLE contests
    ADD COLUMN IF NOT EXISTS platform_commission_percent DECIMAL(5,2) DEFAULT 10.0;

-- ----------------------------------------------------------------------------
-- 2. Contest portfolios (isolated from each user's main portfolio)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS contest_portfolios (
    id           UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    contest_id   UUID    NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    user_id      UUID    NOT NULL REFERENCES users(id),
    cash_balance BIGINT  NOT NULL,           -- cents
    total_value  BIGINT  NOT NULL,           -- cents; recalculated by scheduler
    unrealized_pnl BIGINT DEFAULT 0,         -- cents
    realized_pnl   BIGINT DEFAULT 0,         -- cents
    total_trades   INTEGER DEFAULT 0,
    rank           INTEGER,
    last_calculated TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(contest_id, user_id)
);

-- ----------------------------------------------------------------------------
-- 3. Contest entries (user ↔ contest enrollment record)
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS contest_entries (
    id                     UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    contest_id             UUID    NOT NULL REFERENCES contests(id) ON DELETE CASCADE,
    user_id                UUID    NOT NULL REFERENCES users(id),
    contest_portfolio_id   UUID    REFERENCES contest_portfolios(id),
    status                 VARCHAR(20) DEFAULT 'active',
    final_rank             INTEGER,
    final_value            BIGINT,            -- cents
    final_pnl              BIGINT,            -- cents
    final_pnl_percent      DECIMAL(10,4),
    payment_status         VARCHAR(20) DEFAULT 'free',
    stripe_payment_intent_id VARCHAR(100),
    joined_at              TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(contest_id, user_id)
);

-- ----------------------------------------------------------------------------
-- 4. Contest trades (isolated from main trade history)
--    price and total_value are stored in cents (BIGINT).
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS contest_trades (
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    contest_id           UUID        NOT NULL REFERENCES contests(id),
    user_id              UUID        NOT NULL REFERENCES users(id),
    contest_portfolio_id UUID        NOT NULL REFERENCES contest_portfolios(id),
    symbol               VARCHAR(20) NOT NULL,
    side                 VARCHAR(10) NOT NULL,       -- 'buy' | 'sell'
    quantity             DECIMAL(20,8) NOT NULL,
    price                BIGINT      NOT NULL,        -- cents per unit
    total_value          BIGINT      NOT NULL,        -- cents
    fee                  BIGINT      DEFAULT 0,
    stop_loss_price      BIGINT,                      -- cents, optional
    take_profit_price    BIGINT,                      -- cents, optional
    executed_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 5. Performance indexes
-- ----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_contest_entries_contest
    ON contest_entries(contest_id);

CREATE INDEX IF NOT EXISTS idx_contest_entries_user
    ON contest_entries(user_id);

CREATE INDEX IF NOT EXISTS idx_contest_portfolios_contest
    ON contest_portfolios(contest_id);

CREATE INDEX IF NOT EXISTS idx_contest_portfolios_rank
    ON contest_portfolios(contest_id, rank);

CREATE INDEX IF NOT EXISTS idx_contest_trades_contest
    ON contest_trades(contest_id);

CREATE INDEX IF NOT EXISTS idx_contest_trades_portfolio
    ON contest_trades(contest_portfolio_id, executed_at DESC);
