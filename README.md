# Trading Forge

Paper trade crypto with real-time prices. Compete in contests. Track your performance.

Trading Forge is a full-stack crypto paper trading platform with live WebSocket price feeds, portfolio management, a contest system, and an admin panel. Built for learning crypto trading without risking real money.

**Works on any domain, any server — zero code changes required. Configure with `.env.production` only.**

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | FastAPI 0.115, Python 3.12, Gunicorn + Uvicorn |
| Database | PostgreSQL 16 (UUID PKs, triggers, indexes) |
| Cache | Redis 7 (price cache, rate limiting, sessions) |
| Auth | JWT (memory) + httpOnly refresh cookies, Argon2id |
| Prices | WebSocket feeds — Binance, Bybit, Kraken |
| Payments | Stripe (subscriptions + contest entry fees) |
| Proxy | Nginx (HTTPS, security headers, rate limiting) |
| Infra | Docker Compose, multi-stage builds, non-root containers |

---

## Prerequisites

- **Docker** ≥ 24 and **Docker Compose** v2
- A server with ports **80** and **443** open (production) or **8000/3001** (local)
- A domain name pointed at your server (production) — or just `localhost` for local dev
- `openssl` and `curl` installed on the host

---

## Quick Start (Local Development)

```bash
git clone https://github.com/Nfectious/Trade-Forge-v4.git
cd Trade-Forge-v4

# Auto-generate secrets and start everything
sudo ./deploy.sh
# When prompted for domain, press Enter to use localhost
```

Services will be available at:

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3001 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| Health Check | http://localhost:8000/health |

---

## Production Deployment

### Step 1 — Clone the repo

```bash
git clone https://github.com/Nfectious/Trade-Forge-v4.git
cd Trade-Forge-v4
```

### Step 2 — Configure environment

```bash
cp .env.example .env.production
```

Edit `.env.production` and fill in **every required value**:

```bash
# Required — generate with: openssl rand -base64 32 | tr -d "=+/" | cut -c1-32
DB_PASSWORD=<strong-random-password>
REDIS_PASSWORD=<strong-random-password>

# Required — generate with: openssl rand -hex 64
JWT_SECRET_KEY=<64-hex-chars>

# Required — your domain (no trailing slash, no path)
FRONTEND_URL=https://yourdomain.com
BACKEND_URL=https://yourdomain.com/api
BACKEND_WS_URL=wss://yourdomain.com/market/ws/prices

# Update the connection strings with your generated passwords
DATABASE_URL=postgresql+asyncpg://crypto_admin:YOUR_DB_PASSWORD@postgres:5432/crypto_platform
REDIS_URL=redis://:YOUR_REDIS_PASSWORD@redis:6379/0
```

See [`.env.example`](.env.example) for the complete list with explanations.

### Step 3 — Build and start

```bash
# One command — prompts for domain, generates secrets, builds, and starts
sudo ./deploy.sh

# Or, if you already have .env.production configured:
docker compose -f docker-compose.prod.yml up -d --build
```

### Step 4 — Verify

```bash
curl https://yourdomain.com/health
# Expected: {"status":"healthy","services":{"database":"up","redis":"up",...}}
```

### Step 5 — SSL / HTTPS

If not using Cloudflare's edge SSL, install a certificate with Certbot:

```bash
apt install certbot python3-certbot-nginx
certbot --nginx -d yourdomain.com
```

Place the cert files at:
- `/etc/nginx/ssl/fullchain.pem`
- `/etc/nginx/ssl/privkey.pem`

Or mount them into the nginx container via `docker-compose.yml`.

### Step 6 — Configure Stripe webhook (if using payments)

1. Go to [Stripe Webhooks Dashboard](https://dashboard.stripe.com/webhooks)
2. Add endpoint: `https://yourdomain.com/payments/webhook`
3. Select events: `customer.subscription.*`, `invoice.payment_*`, `payment_intent.*`
4. Copy the **Signing secret** → set `STRIPE_WEBHOOK_SECRET=whsec_...` in `.env.production`
5. Restart backend: `docker compose restart backend`

For local testing:
```bash
stripe listen --forward-to localhost:8000/payments/webhook
```

---

## Environment Variables Reference

All configuration lives in `.env.production`. See [`.env.example`](.env.example) for the complete template.

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL async connection string | `postgresql+asyncpg://user:pass@postgres:5432/db` |
| `REDIS_URL` | Redis connection string | `redis://:password@redis:6379/0` |
| `JWT_SECRET_KEY` | JWT signing secret (64+ hex chars) | `openssl rand -hex 64` |
| `FRONTEND_URL` | Your frontend URL — used for CORS | `https://yourdomain.com` |
| `DB_PASSWORD` | PostgreSQL password | strong random string |
| `REDIS_PASSWORD` | Redis password | strong random string |

### Optional — Email

| Variable | Description |
|----------|-------------|
| `SMTP_HOST` | SMTP server (e.g. `smtp.resend.com`) |
| `SMTP_PORT` | SMTP port (usually `587`) |
| `SMTP_USER` | SMTP username |
| `SMTP_PASSWORD` | SMTP password or API key |
| `SMTP_FROM` | Sender address (e.g. `noreply@yourdomain.com`) |

Email is optional — the app works without it, but email verification won't send.
[Resend](https://resend.com) offers 3,000 free emails/month.

### Optional — Stripe

| Variable | Description | Where to get it |
|----------|-------------|-----------------|
| `STRIPE_SECRET_KEY` | Stripe secret or restricted key | [dashboard.stripe.com/apikeys](https://dashboard.stripe.com/apikeys) |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key | Same page |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret | [dashboard.stripe.com/webhooks](https://dashboard.stripe.com/webhooks) |
| `STRIPE_PRICE_ID_PRO` | Stripe price ID for Pro tier | Stripe Products |
| `STRIPE_PRICE_ID_ELITE` | Stripe price ID for Elite tier | Stripe Products |
| `STRIPE_PRICE_ID_VALKYRIE` | Stripe price ID for Valkyrie tier | Stripe Products |

Stripe is optional — the platform works fully without it (all tiers are free).

### Optional — CORS / Networking

| Variable | Description |
|----------|-------------|
| `ALLOWED_ORIGINS` | Comma-separated CORS origins. Defaults to `FRONTEND_URL` only. |
| `BACKEND_WS_URL` | WebSocket URL used by the frontend |

### Optional — Exchange API Keys

| Variable | Description |
|----------|-------------|
| `KRAKEN_API_KEY` / `KRAKEN_API_SECRET` | Kraken private API access |
| `COINGECKO_API_KEY` | CoinGecko API key for additional data |
| `OPENROUTER_API_KEY` | AI trading features |

---

## Project Structure

```
Trade-Forge-v4/
├── deploy.sh                   # One-command deploy script
├── docker-compose.yml          # Development + basic production
├── docker-compose.prod.yml     # Production (resource limits, log rotation)
├── .env.example                # Complete environment template with comments
│
├── backend/
│   ├── Dockerfile              # Non-root, multi-stage Python 3.12
│   ├── requirements.txt
│   ├── gunicorn.conf.py
│   └── app/
│       ├── main.py             # FastAPI app, middleware, startup validation
│       ├── core/
│       │   ├── config.py       # Pydantic settings — all from env
│       │   ├── security.py     # JWT, Argon2id, rate limiting
│       │   ├── database.py     # Async SQLModel + PostgreSQL
│       │   ├── redis.py        # Shared Redis client
│       │   └── websocket_manager.py
│       ├── models/             # SQLModel table definitions
│       ├── api/                # Route handlers (auth, trading, admin, etc.)
│       └── services/           # Business logic
│
├── frontend/
│   ├── Dockerfile              # Multi-stage Node 18 Alpine
│   ├── package.json
│   ├── next.config.js
│   ├── lib/
│   │   ├── api.ts              # Axios client — token in memory, not localStorage
│   │   ├── auth.tsx            # Auth context with silent refresh
│   │   └── toast.tsx           # Toast notifications
│   ├── components/
│   └── app/                    # Next.js App Router pages
│
├── database/
│   ├── init.sql                # Full schema
│   ├── seed.sql                # Trading pairs, tiers, achievements
│   └── backups/
│
├── nginx/
│   └── nginx.conf              # HTTPS, security headers, rate limiting, WebSocket
│
└── scripts/
    ├── deploy.sh               # Production deploy with rollback
    ├── backup.sh               # DB + Redis + env backup
    └── status.sh               # System health dashboard
```

---

## API Reference

### Auth — `/auth/*`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Login — returns access token, sets httpOnly refresh cookie |
| POST | `/auth/refresh` | Rotate refresh token (reads cookie) |
| POST | `/auth/logout` | Revoke tokens, clear cookie |
| GET | `/auth/me` | Current user profile |
| POST | `/auth/forgot-password` | Send password reset email |
| POST | `/auth/reset-password` | Set new password with reset token |

### Trading — `/trading/*`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/trading/portfolio` | Portfolio with holdings and P&L |
| POST | `/trading/order` | Place market / limit / stop-limit order |
| GET | `/trading/orders/open` | Open positions with live P&L |
| GET | `/trading/orders/pending` | Pending limit orders |
| PUT | `/trading/orders/{id}` | Modify stop-loss / take-profit |
| DELETE | `/trading/orders/{id}` | Cancel pending order |
| GET | `/trading/trades/history` | Trade history |

### Market — `/market/*`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/market/prices` | Cached live prices |
| WS | `/market/ws/prices` | WebSocket price stream |

### Payments — `/payments/*`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/payments/subscribe` | Start Stripe Checkout |
| GET | `/payments/subscription` | Current subscription status |
| DELETE | `/payments/subscription` | Cancel at period end |
| GET | `/payments/billing-portal` | Stripe billing portal URL |
| POST | `/payments/webhook` | Stripe webhook receiver |

### System

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | DB + Redis + WebSocket status. 200 = healthy, 503 = degraded |

---

## Security Features

- **Passwords**: Argon2id hashing
- **JWT**: Access tokens stored in JS memory (not localStorage) — XSS-safe. Refresh token in httpOnly cookie.
- **Account lockout**: 5 failed logins → 15-minute lockout per email (Redis-backed)
- **Rate limiting**: slowapi + Nginx — per-IP and per-user
  - Register: 5/hour
  - Login: 10/15 minutes
  - Orders: 60/minute
  - Payments: 10/minute
  - Default: 100/minute
- **CORS**: Restricted to `FRONTEND_URL` / `ALLOWED_ORIGINS` — no wildcards
- **Security headers**: HSTS, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy
- **Stripe**: Webhook signature verification, server-side PaymentIntent confirmation
- **Database**: All ports bound to 127.0.0.1 — not exposed externally
- **Containers**: All run as non-root user
- **Startup validation**: App refuses to start if DATABASE_URL, REDIS_URL, or JWT secret are missing or contain placeholder values

---

## Deployment Scripts

### `deploy.sh` — One-command deploy

```bash
sudo ./deploy.sh              # First-time setup: prompts for domain, generates secrets
sudo ./deploy.sh --restart    # Rebuild and restart (uses existing .env.production)
sudo ./deploy.sh --reset      # ⚠️ Destroy data volumes and start fresh
```

### `scripts/deploy.sh` — Production deploy with rollback

```bash
sudo ./scripts/deploy.sh              # Full deploy (pull, build, health check)
sudo ./scripts/deploy.sh --no-pull    # Build from local code
sudo ./scripts/deploy.sh --no-cache   # Force full rebuild
sudo ./scripts/deploy.sh --rollback   # Roll back to previous version
```

### `scripts/backup.sh` — Database backup

```bash
sudo ./scripts/backup.sh
# Backs up PostgreSQL, Redis snapshot, and .env.production
# Deletes backups older than 7 days
```

Cron (daily at 3 AM):
```
0 3 * * * cd /opt/Trade-Forge-v4 && ./scripts/backup.sh >> logs/backup.log 2>&1
```

### `scripts/status.sh` — System health dashboard

```bash
./scripts/status.sh
# Container health, resource usage, DB connections, Redis memory, recent errors
```

---

## Troubleshooting

**Backend won't start:**
```bash
docker compose logs backend          # Check for startup errors
# Common causes: missing env vars, DB not ready yet
docker compose restart backend       # Retry after DB is healthy
```

**Health check failing:**
```bash
curl http://localhost:8000/health
# Returns {"status":"degraded",...} — check which service is down
docker compose ps                    # Check container states
```

**Database connection refused:**
```bash
docker compose ps postgres           # Is it running?
docker compose logs postgres         # Any init errors?
```

**Redis auth error (`NOAUTH`):**
```bash
grep REDIS_PASSWORD .env.production  # Confirm password is set
docker compose restart redis backend
```

**CORS errors in browser:**
```bash
grep FRONTEND_URL .env.production    # Must exactly match the browser's origin (no trailing slash)
grep ALLOWED_ORIGINS .env.production # Add extra origins here if needed
```

**Stripe webhooks not received:**
```bash
# Verify the webhook endpoint is accessible:
curl -X POST https://yourdomain.com/payments/webhook
# Should return 400 (signature check fails on empty body — that's correct)

# For local dev, use Stripe CLI:
stripe listen --forward-to localhost:8000/payments/webhook
```

---

## License

MIT License — use freely, attribution appreciated.
