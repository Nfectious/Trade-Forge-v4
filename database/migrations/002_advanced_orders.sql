-- ============================================================================
-- Migration 002: Advanced Order Management
-- Adds trailing stop, limit orders, auto-execution tracking, and 'open'
-- position status so the position monitor can watch active positions.
--
-- Run notes:
--   ALTER TYPE ... ADD VALUE cannot be used in a transaction that was
--   already started with BEGIN in PostgreSQL < 12.  Run this migration
--   with a tool that executes DDL outside an explicit transaction block,
--   or execute it in two phases:
--     Phase 1: the two ALTER TYPE statements
--     Phase 2: the rest
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Extend existing enums
-- ----------------------------------------------------------------------------

-- 'open' — an executed market order whose position is still active (has
-- stop-loss / take-profit / trailing-stop attached and monitored).
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'open';

-- 'stop_limit' — a pending limit order placed below current price on a buy
-- (or above on a sell) that triggers like a stop and fills like a limit.
ALTER TYPE order_type ADD VALUE IF NOT EXISTS 'stop_limit';

-- ----------------------------------------------------------------------------
-- 2. New columns on orders
-- ----------------------------------------------------------------------------

-- Trailing-stop distance expressed as a percentage (e.g. 2.50 = 2.5 %).
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS trailing_stop_percent DECIMAL(5,2);

-- Highest price seen since order opened, stored in cents (BIGINT).
-- Updated by the position monitor on each cycle.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS trailing_stop_peak_price BIGINT;

-- Limit trigger price in cents (BIGINT).  Display price = limit_price / 100.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS limit_price BIGINT;

-- The column below already exists as the 'order_type' enum column; the
-- IF NOT EXISTS guard makes this statement a safe no-op.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS order_type VARCHAR(20) NOT NULL DEFAULT 'market';

-- True when the position monitor auto-executed this order.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS auto_executed BOOLEAN DEFAULT false;

-- Human-readable reason set by the monitor: stop_loss_triggered,
-- take_profit_triggered, or trailing_stop_triggered.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS auto_execute_reason VARCHAR(50);

-- Optional expiry for pending limit orders.  Monitor cancels when exceeded.
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- ----------------------------------------------------------------------------
-- 3. Performance indexes for the position monitor
-- ----------------------------------------------------------------------------

-- Partial index: only rows the monitor actually cares about.
-- Requires 'open' to be a valid enum value (added above).
CREATE INDEX IF NOT EXISTS idx_orders_status_active
    ON orders(status)
    WHERE status IN ('pending', 'open');

-- Composite index used by monitor queries filtered by (user_id, status).
-- Note: init.sql already created idx_orders_user_status covering
-- (user_id, status, created_at DESC).  The IF NOT EXISTS below is a safe
-- no-op for that name; the existing index already serves these queries.
CREATE INDEX IF NOT EXISTS idx_orders_user_status
    ON orders(user_id, status);
