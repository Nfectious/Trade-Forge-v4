#!/bin/bash
# =============================================================================
# GENERATE SECURE .env FILE
# Run this to create a .env file with auto-generated secure passwords.
# Edit the output file to fill in your domain, SMTP, and Stripe values.
# Usage: bash generate-env_v2.sh
# =============================================================================

set -e

echo "🔐 Generating secure .env file..."

# Generate secure values
DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
JWT_SECRET=$(openssl rand -hex 64)

# Create .env file
cat > .env << EOF
# =============================================================================
# TRADING FORGE - ENVIRONMENT CONFIGURATION
# Auto-generated on $(date)
# Edit this file and set your domain, email, and Stripe values.
# =============================================================================

# =============================================================================
# DATABASE
# =============================================================================
DB_USER=crypto_admin
DB_PASSWORD=${DB_PASSWORD}
DATABASE_URL=postgresql+asyncpg://crypto_admin:${DB_PASSWORD}@postgres:5432/crypto_platform
POSTGRES_USER=crypto_admin
POSTGRES_PASSWORD=${DB_PASSWORD}
POSTGRES_DB=crypto_platform

# =============================================================================
# REDIS
# =============================================================================
REDIS_PASSWORD=${REDIS_PASSWORD}
REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0

# =============================================================================
# JWT / AUTH
# =============================================================================
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7

# =============================================================================
# EMAIL (UPDATE with your provider credentials)
# Free option: https://resend.com — 3,000 emails/month free tier
# =============================================================================
SMTP_HOST=smtp.resend.com
SMTP_PORT=587
SMTP_USER=resend
SMTP_PASSWORD=                        # Your Resend API key (re_...)
SMTP_FROM=noreply@yourdomain.com      # Replace with your verified sender domain

# =============================================================================
# APPLICATION URLS (UPDATE with your domain)
# Development defaults — change for production
# =============================================================================
FRONTEND_URL=http://localhost:3001
BACKEND_URL=http://localhost:8000
BACKEND_WS_URL=ws://localhost:8000/market/ws/prices

# =============================================================================
# ENVIRONMENT
# =============================================================================
ENVIRONMENT=development
DEBUG=true

# =============================================================================
# RATE LIMITING
# =============================================================================
RATE_LIMIT_SIGNUP=5/hour
RATE_LIMIT_LOGIN=10/15minutes

# =============================================================================
# CORS (optional — defaults to FRONTEND_URL only)
# Comma-separated list of allowed origins
# =============================================================================
ALLOWED_ORIGINS=

# =============================================================================
# EXCHANGE API KEYS (optional — app falls back to cached prices without these)
# =============================================================================
KRAKEN_API_KEY=
KRAKEN_API_SECRET=
COINGECKO_API_KEY=
OPENROUTER_API_KEY=

# =============================================================================
# STRIPE PAYMENTS (optional — required for paid tiers)
# Get keys from https://dashboard.stripe.com/apikeys
# =============================================================================
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRICE_ID_PRO=
STRIPE_PRICE_ID_ELITE=
STRIPE_PRICE_ID_VALKYRIE=

# =============================================================================
# TIER STARTING BALANCES (in cents — $10k, $25k, $100k, $500k)
# =============================================================================
TIER_FREE_BALANCE=1000000
TIER_PRO_BALANCE=2500000
TIER_ELITE_BALANCE=10000000
TIER_VALKYRIE_BALANCE=50000000
EOF

echo "✅ .env file created!"
echo ""
echo "📝 Auto-generated secure values:"
echo "   DB_PASSWORD:    ${DB_PASSWORD}"
echo "   REDIS_PASSWORD: ${REDIS_PASSWORD}"
echo "   JWT_SECRET_KEY: ${JWT_SECRET:0:20}... (truncated)"
echo ""
echo "⚠️  Required manual edits in .env:"
echo "   - FRONTEND_URL / BACKEND_URL / BACKEND_WS_URL  (your domain)"
echo "   - SMTP_PASSWORD  (get from https://resend.com/api-keys)"
echo "   - STRIPE_*  (if using paid tiers)"
echo ""
echo "💾 Keep this file secure — never commit it to version control!"
