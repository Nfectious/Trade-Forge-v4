"""
Main FastAPI application
Entry point for the Crypto Simulation Platform API
"""

import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.security import limiter, get_security_headers
from app.core.database import close_db
from app.core.redis import init_redis, get_redis_client, close_redis
from app.core.websocket_manager import WebSocketManager
from app.services.position_monitor import start_position_monitor

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBAL STATE (WebSocket Manager only — Redis is in app.core.redis)
# ============================================================================

ws_manager = None

# ============================================================================
# LIFESPAN CONTEXT MANAGER
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global ws_manager

    logger.info("Starting Crypto Platform API")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Debug mode: {settings.DEBUG}")

    # Initialize Redis via shared module
    try:
        await init_redis(settings.REDIS_URL)
        logger.info("Redis connected")
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")

    redis_client = get_redis_client()

    # Initialize WebSocket Manager (only if Redis is available)
    if redis_client:
        try:
            ws_manager = WebSocketManager(redis_client)

            # Start WS feeds in background
            asyncio.create_task(ws_manager.connect())

            # Subscribe to default trading pairs
            await ws_manager.subscribe("binance", "BTCUSDT")
            await ws_manager.subscribe("binance", "ETHUSDT")
            await ws_manager.subscribe("binance", "SOLUSDT")
            await ws_manager.subscribe("bybit", "BTCUSDT")
            await ws_manager.subscribe("kraken", "XBT/USD")
            await ws_manager.subscribe("kraken", "ETH/USD")

            logger.info("Live price feeds operational")

        except Exception as e:
            logger.error(f"WebSocket manager failed: {e}")
            ws_manager = None

    # Start position monitor (stop-loss / take-profit / trailing-stop / limit fills)
    asyncio.create_task(start_position_monitor())
    logger.info("Position monitor task started")

    logger.info("Application startup complete")

    yield  # Application runs here

    # ==================== SHUTDOWN ====================
    logger.info("Shutting down Crypto Platform API")

    if ws_manager:
        await ws_manager.disconnect()
        logger.info("WebSocket feeds closed")

    await close_redis()
    logger.info("Redis connection closed")

    await close_db()
    logger.info("Database connections closed")

    logger.info("Shutdown complete")

# ============================================================================
# CREATE FASTAPI APP
# ============================================================================

app = FastAPI(
    title="Crypto Simulation Platform API",
    description="Professional crypto trading simulation and education platform",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# Add rate limiter
app.state.limiter = limiter

# ============================================================================
# MIDDLEWARE
# ============================================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    for key, value in get_security_headers().items():
        response.headers[key] = value
    return response


# ============================================================================
# EXCEPTION HANDLERS
# ============================================================================

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": exc.retry_after
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    if settings.DEBUG:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error": str(exc),
                "type": type(exc).__name__
            }
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# ============================================================================
# ROOT ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "Crypto Simulation Platform API",
        "version": "1.0.0",
        "status": "operational",
        "websocket_status": "connected" if ws_manager and ws_manager.running else "disconnected",
        "redis_status": "connected" if get_redis_client() else "disconnected"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "services": {
            "redis": "up" if get_redis_client() else "down",
            "websocket_feeds": "up" if ws_manager and ws_manager.running else "down"
        }
    }

# ============================================================================
# API ROUTES
# ============================================================================

from app.api import auth, users, wallet, trading, admin, market

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(wallet.router, prefix="/wallet", tags=["Wallet"])
app.include_router(trading.router, prefix="/trading", tags=["Trading"])
app.include_router(market.router, prefix="/market", tags=["Market Data"])
app.include_router(admin.router)

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
