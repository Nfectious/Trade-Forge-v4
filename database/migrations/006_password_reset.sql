-- ============================================================================
-- Migration 006: Password Reset Tokens
-- Separate table for password reset tokens (distinct from email verification).
-- Tokens are stored as SHA-256 hex digests; raw tokens are only in emails.
-- ============================================================================

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(64) NOT NULL UNIQUE,  -- sha256(raw_token).hexdigest()
    expires_at  TIMESTAMPTZ NOT NULL,
    used        BOOLEAN     DEFAULT false,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prt_token_hash ON password_reset_tokens(token_hash);
CREATE INDEX IF NOT EXISTS idx_prt_user_id    ON password_reset_tokens(user_id);
