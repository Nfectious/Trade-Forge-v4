"""
User models: User, UserProfile, RefreshToken, EmailVerificationToken
"""

from sqlmodel import SQLModel, Field, Relationship
from typing import Optional
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum


# ============================================================================
# ENUMS
# ============================================================================

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    MODERATOR = "moderator"


class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    BANNED = "banned"
    PENDING_VERIFICATION = "pending_verification"


class TierLevel(str, Enum):
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"
    VALKYRIE = "valkyrie"


class TraderType(str, Enum):
    SCALPER = "scalper"
    DAY_TRADER = "day_trader"
    SWING_TRADER = "swing_trader"
    POSITION_TRADER = "position_trader"
    HODLER = "hodler"
    ALGORITHMIC = "algorithmic"


# ============================================================================
# USER MODEL
# ============================================================================

class User(SQLModel, table=True):
    """Main user authentication and account model"""
    
    __tablename__ = "users"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str = Field(max_length=255)
    
    role: UserRole = Field(default=UserRole.USER, sa_column_kwargs={"server_default": "user"})
    status: UserStatus = Field(
        default=UserStatus.PENDING_VERIFICATION,
        sa_column_kwargs={"server_default": "pending_verification"}
    )
    tier: TierLevel = Field(default=TierLevel.FREE, sa_column_kwargs={"server_default": "free"})
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    
    suspended_until: Optional[datetime] = None
    suspension_reason: Optional[str] = None
    
    discord_id: Optional[str] = Field(default=None, max_length=100)


# ============================================================================
# USER PROFILE MODEL
# ============================================================================

class UserProfile(SQLModel, table=True):
    """Extended user profile information"""
    
    __tablename__ = "user_profiles"
    
    user_id: UUID = Field(foreign_key="users.id", primary_key=True, ondelete="CASCADE")
    
    nickname: Optional[str] = Field(default=None, unique=True, max_length=50)
    display_name: Optional[str] = Field(default=None, max_length=100)
    avatar_url: Optional[str] = None
    bio: Optional[str] = Field(default=None, max_length=500)
    
    trader_type: Optional[TraderType] = None
    trading_goal: Optional[str] = None
    experience_level: Optional[str] = Field(default=None, max_length=50)
    
    twitter_handle: Optional[str] = Field(default=None, max_length=50)
    discord_username: Optional[str] = Field(default=None, max_length=50)
    telegram_handle: Optional[str] = Field(default=None, max_length=50)
    
    profile_public: bool = Field(default=True)
    show_stats: bool = Field(default=True)
    show_leaderboard: bool = Field(default=True)
    
    xp_points: int = Field(default=0)
    level: int = Field(default=1)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# REFRESH TOKEN MODEL
# ============================================================================

class RefreshToken(SQLModel, table=True):
    """JWT refresh tokens for session management"""
    
    __tablename__ = "refresh_tokens"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE")
    token: str = Field(unique=True, max_length=500)
    expires_at: datetime
    revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# EMAIL VERIFICATION TOKEN MODEL
# ============================================================================

class EmailVerificationToken(SQLModel, table=True):
    """Email verification tokens"""

    __tablename__ = "email_verification_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE")
    token: str = Field(unique=True, max_length=255)
    expires_at: datetime
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PasswordResetToken(SQLModel, table=True):
    """Password reset tokens — stored as SHA-256 hex digests (migration 006)."""

    __tablename__ = "password_reset_tokens"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", ondelete="CASCADE")
    token_hash: str = Field(unique=True, max_length=64)  # sha256 hex digest
    expires_at: datetime
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# REQUEST/RESPONSE MODELS (Pydantic)
# ============================================================================

class UserRegister(SQLModel):
    """User registration request"""
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=100)
    nickname: Optional[str] = Field(default=None, max_length=50)


class UserLogin(SQLModel):
    """User login request"""
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


class UserResponse(SQLModel):
    """User response (without sensitive data)"""
    id: UUID
    email: str
    role: UserRole
    status: UserStatus
    tier: TierLevel
    created_at: datetime
    verified_at: Optional[datetime]


class UserProfileUpdate(SQLModel):
    """User profile update request"""
    nickname: Optional[str] = Field(default=None, max_length=50)
    display_name: Optional[str] = Field(default=None, max_length=100)
    bio: Optional[str] = Field(default=None, max_length=500)
    trader_type: Optional[TraderType] = None
    trading_goal: Optional[str] = None
    experience_level: Optional[str] = None
    twitter_handle: Optional[str] = None
    discord_username: Optional[str] = None
    telegram_handle: Optional[str] = None
    profile_public: Optional[bool] = None
    show_stats: Optional[bool] = None
    show_leaderboard: Optional[bool] = None


class UserProfileResponse(SQLModel):
    """User profile response"""
    user_id: UUID
    nickname: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    bio: Optional[str]
    trader_type: Optional[TraderType]
    trading_goal: Optional[str]
    experience_level: Optional[str]
    xp_points: int
    level: int
    profile_public: bool


class TokenResponse(SQLModel):
    """JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
