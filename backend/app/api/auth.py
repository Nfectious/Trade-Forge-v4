"""
Authentication API routes
Registration, login, token management, email verification, and password reset.

Token security model:
  - Raw tokens (secrets.token_urlsafe(32)) are only ever sent in emails.
  - Only the SHA-256 hex digest is stored in the database.
  - Lookup always re-hashes the received raw token before querying.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, UTC

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.dependencies import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    rate_limit_auth,
    rate_limit_signup,
    validate_password_strength,
    verify_password,
)
from app.models.user import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshToken,
    TokenResponse,
    User,
    UserLogin,
    UserProfile,
    UserRegister,
    UserResponse,
)
from app.services.email_service import email_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def _sha256(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _get_nickname(user: User, profile: UserProfile | None) -> str:
    if profile and profile.nickname:
        return profile.nickname
    return user.email.split("@")[0]


# ---------------------------------------------------------------------------
# REQUEST BODIES
# ---------------------------------------------------------------------------

class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    pass  # auth only — no body needed


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


# ============================================================================
# REGISTER
# ============================================================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@rate_limit_signup
async def register(
    request: Request,
    user_data: UserRegister,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Register a new user. Sends a verification email in the background."""
    is_valid, error_message = validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

    result = await session.execute(select(User).where(User.email == user_data.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    if user_data.nickname:
        result = await session.execute(
            select(UserProfile).where(UserProfile.nickname == user_data.nickname)
        )
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nickname already taken",
            )

    new_user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    if user_data.nickname:
        profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == new_user.id)
        )
        profile = profile_result.scalar_one()
        profile.nickname = user_data.nickname
        await session.commit()

    # Generate verification token — store only the hash
    raw_token = secrets.token_urlsafe(32)
    token_record = EmailVerificationToken(
        user_id=new_user.id,
        token=_sha256(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(token_record)
    await session.commit()

    nickname = user_data.nickname or new_user.email.split("@")[0]
    background_tasks.add_task(
        email_service.send_verification_email,
        new_user.email,
        nickname,
        raw_token,
    )

    return new_user


# ============================================================================
# VERIFY EMAIL (POST — uses sha256-hashed token lookup)
# ============================================================================

@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    session: AsyncSession = Depends(get_session),
):
    """Verify email address using the token sent to the user's inbox."""
    token_hash = _sha256(body.token)

    result = await session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token == token_hash,
            EmailVerificationToken.used == False,
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record or token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link",
        )

    token_record.used = True

    user_result = await session.execute(select(User).where(User.id == token_record.user_id))
    user = user_result.scalar_one()
    user.status = "active"
    user.verified_at = datetime.now(UTC)

    await session.commit()
    return {"message": "Email verified successfully"}


# ============================================================================
# RESEND VERIFICATION
# ============================================================================

@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Resend the email verification link. Rate-limited to once per 5 minutes."""
    if current_user.status == "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your email is already verified",
        )

    # Rate-limit: reject if a token was issued less than 5 minutes ago
    recent_result = await session.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.user_id == current_user.id,
            EmailVerificationToken.used == False,
        )
        .order_by(EmailVerificationToken.created_at.desc())
        .limit(1)
    )
    recent = recent_result.scalar_one_or_none()

    if recent:
        age = datetime.now(UTC) - recent.created_at.replace(tzinfo=UTC)
        if age.total_seconds() < 300:  # 5 minutes
            remaining = int(300 - age.total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} seconds before requesting another verification email",
            )

        # Invalidate all existing unused tokens for this user
        all_result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.user_id == current_user.id,
                EmailVerificationToken.used == False,
            )
        )
        for old_token in all_result.scalars().all():
            old_token.used = True

    raw_token = secrets.token_urlsafe(32)
    token_record = EmailVerificationToken(
        user_id=current_user.id,
        token=_sha256(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(token_record)
    await session.commit()

    profile_result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = profile_result.scalar_one_or_none()
    nickname = _get_nickname(current_user, profile)

    background_tasks.add_task(
        email_service.send_verification_email,
        current_user.email,
        nickname,
        raw_token,
    )

    return {"message": "Verification email sent"}


# ============================================================================
# LOGIN
# ============================================================================

@router.post("/login", response_model=TokenResponse)
@rate_limit_auth
async def login(
    request: Request,
    credentials: UserLogin,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Login with email and password. Returns access token; sets refresh cookie."""
    result = await session.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if user.status == "banned":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is banned")

    if user.status == "suspended":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is suspended")

    user.last_login = datetime.now(UTC)
    await session.commit()

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session.add(RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires_at))
    await session.commit()

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============================================================================
# FORGOT PASSWORD
# ============================================================================

@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
):
    """Send a password reset email. Always returns 200 (don't reveal if email exists)."""
    user_result = await session.execute(select(User).where(User.email == body.email))
    user = user_result.scalar_one_or_none()

    if user:
        # Invalidate any existing unused reset tokens
        existing_result = await session.execute(
            select(PasswordResetToken).where(
                PasswordResetToken.user_id == user.id,
                PasswordResetToken.used == False,
            )
        )
        for old in existing_result.scalars().all():
            old.used = True

        raw_token = secrets.token_urlsafe(32)
        token_record = PasswordResetToken(
            user_id=user.id,
            token_hash=_sha256(raw_token),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(token_record)
        await session.commit()

        profile_result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )
        profile = profile_result.scalar_one_or_none()
        nickname = _get_nickname(user, profile)

        background_tasks.add_task(
            email_service.send_password_reset,
            user.email,
            nickname,
            raw_token,
        )

    return {"message": "If that email exists, a reset link has been sent"}


# ============================================================================
# RESET PASSWORD
# ============================================================================

@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
):
    """Set a new password using a valid reset token."""
    token_hash = _sha256(body.token)

    result = await session.execute(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash,
            PasswordResetToken.used == False,
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record or token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset link",
        )

    is_valid, error_message = validate_password_strength(body.new_password)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)

    user_result = await session.execute(select(User).where(User.id == token_record.user_id))
    user = user_result.scalar_one()

    user.password_hash = hash_password(body.new_password)
    user.updated_at = datetime.now(UTC)
    token_record.used = True

    # Revoke all refresh tokens — forces re-login on all devices
    refresh_result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user.id,
            RefreshToken.revoked == False,
        )
    )
    for rt in refresh_result.scalars().all():
        rt.revoked = True

    await session.commit()
    return {"message": "Password reset successfully"}


# ============================================================================
# REFRESH TOKEN
# ============================================================================

@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    """Rotate refresh token and issue a new access token (reads cookie)."""
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No refresh token provided",
        )

    try:
        payload = decode_token(refresh_token)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.revoked == False,
        )
    )
    token_record = result.scalar_one_or_none()

    if not token_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not found or revoked",
        )

    if token_record.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
        )

    user_id = payload.get("sub")
    new_access_token = create_access_token(data={"sub": user_id})
    new_refresh_token = create_refresh_token(data={"sub": user_id})

    token_record.revoked = True

    new_expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session.add(
        RefreshToken(
            user_id=token_record.user_id,
            token=new_refresh_token,
            expires_at=new_expires_at,
        )
    )
    await session.commit()

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.ENVIRONMENT == "production",
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=new_access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============================================================================
# LOGOUT
# ============================================================================

@router.post("/logout")
async def logout(
    response: Response,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Revoke all refresh tokens and clear the cookie."""
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == current_user.id,
            RefreshToken.revoked == False,
        )
    )
    for token in result.scalars().all():
        token.revoked = True

    await session.commit()
    response.delete_cookie("refresh_token")
    return {"message": "Logged out successfully"}


# ============================================================================
# ME
# ============================================================================

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Return the current authenticated user's profile."""
    return current_user
