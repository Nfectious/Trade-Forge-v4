-- ============================================================================
-- Migration 005: Stripe Integration
-- Adds Stripe customer mapping, subscription tracking, and payment transaction
-- log tables. All monetary amounts stored as INTEGER cents.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Stripe customer mapping — one row per user who has interacted with Stripe
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stripe_customers (
    user_id             UUID        PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    stripe_customer_id  VARCHAR(100) UNIQUE NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 2. Subscriptions — tracks active/past Stripe subscriptions per user
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS subscriptions (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID        NOT NULL REFERENCES users(id),
    stripe_subscription_id  VARCHAR(100) UNIQUE,
    stripe_price_id         VARCHAR(100),
    tier                    VARCHAR(20) NOT NULL,
    status                  VARCHAR(20) NOT NULL,   -- active | trialing | past_due | cancelled | incomplete
    current_period_start    TIMESTAMPTZ,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    BOOLEAN     DEFAULT false,
    cancelled_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 3. Payment transactions — immutable log of all real-money events
--    transaction_type: subscription_created | subscription_renewal |
--                      subscription_failed | contest_entry | refund
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS payment_transactions (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID        NOT NULL REFERENCES users(id),
    stripe_payment_intent_id VARCHAR(100),
    stripe_charge_id        VARCHAR(100),
    transaction_type        VARCHAR(30) NOT NULL,
    amount_cents            INTEGER     NOT NULL,
    currency                VARCHAR(3)  DEFAULT 'usd',
    status                  VARCHAR(20) NOT NULL,   -- succeeded | failed | refunded
    contest_id              UUID        REFERENCES contests(id),
    description             TEXT,
    metadata                JSONB       DEFAULT '{}',
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 4. Indexes
-- ----------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_stripe_customers_stripe_id
    ON stripe_customers(stripe_customer_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user
    ON subscriptions(user_id);

CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_id
    ON subscriptions(stripe_subscription_id);

CREATE INDEX IF NOT EXISTS idx_transactions_user
    ON payment_transactions(user_id);

CREATE INDEX IF NOT EXISTS idx_transactions_intent
    ON payment_transactions(stripe_payment_intent_id);
