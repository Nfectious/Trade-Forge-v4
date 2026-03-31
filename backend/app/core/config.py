"""
Application configuration management
Loads environment variables and provides type-safe configuration access
Supports both local .env files and cloud environment variables (e.g., Fly.io)
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


def get_env_file() -> str | None:
    """
    Determine which .env file to use (if any).
    Priority: .env.production > .env > None (cloud env vars only)
    """
    if Path(".env.production").exists():
        return ".env.production"
    elif Path(".env").exists():
        return ".env"
    return None


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    This configuration works in multiple contexts:
    - Local development: Reads from .env or .env.production
    - Cloud deployment (Fly.io): Reads from injected environment variables
    - Docker: Reads from environment variables passed to container
    """

    model_config = SettingsConfigDict(
        env_file=get_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # JWT Configuration - Support both JWT_SECRET and JWT_SECRET_KEY for backwards compatibility
    JWT_SECRET: str | None = None
    JWT_SECRET_KEY: str | None = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    @property
    def jwt_secret(self) -> str:
        """Get JWT secret from either JWT_SECRET or JWT_SECRET_KEY"""
        secret = self.JWT_SECRET or self.JWT_SECRET_KEY
        if not secret:
            raise ValueError("Either JWT_SECRET or JWT_SECRET_KEY must be set")
        return secret

    # Email Configuration (optional until email service is implemented)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM: str | None = None

    # Stripe Payments — supports both STRIPE_SECRET_KEY and legacy STRIPE_RESTRICTED_KEY
    STRIPE_SECRET_KEY: str | None = None       # preferred name
    STRIPE_RESTRICTED_KEY: str | None = None   # legacy alias
    STRIPE_PUBLISHABLE_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_PRICE_ID_PRO: str | None = None
    STRIPE_PRICE_ID_ELITE: str | None = None
    STRIPE_PRICE_ID_VALKYRIE: str | None = None

    @property
    def stripe_secret_key(self) -> str | None:
        """Return Stripe secret/restricted key, preferring STRIPE_SECRET_KEY."""
        return self.STRIPE_SECRET_KEY or self.STRIPE_RESTRICTED_KEY

    # Application URLs
    FRONTEND_URL: str
    BACKEND_URL: str | None = None

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production"] = "production"
    DEBUG: bool = False

    # CORS — comma-separated list overrides the default FRONTEND_URL-only behaviour
    ALLOWED_ORIGINS: str | None = None

    @property
    def CORS_ORIGINS(self) -> list[str]:
        """Get allowed CORS origins"""
        if self.ALLOWED_ORIGINS:
            return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]
        origins = [self.FRONTEND_URL]
        if self.ENVIRONMENT == "development":
            origins.extend([
                "http://localhost:3001",
                "http://localhost:8000"
            ])
        return origins

    # Rate Limiting
    RATE_LIMIT_SIGNUP: str = "5/hour"
    RATE_LIMIT_LOGIN: str = "10/15minutes"

    # Tier Balances (in cents)
    TIER_FREE_BALANCE: int = 1000000  # $10,000
    TIER_PRO_BALANCE: int = 2500000  # $25,000
    TIER_ELITE_BALANCE: int = 10000000  # $100,000
    TIER_VALKYRIE_BALANCE: int = 50000000  # $500,000

    # Exchange API Keys (Optional)
    KRAKEN_API_KEY: str | None = None
    KRAKEN_API_SECRET: str | None = None
    COINGECKO_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
   


# Global settings instance
settings = Settings()
