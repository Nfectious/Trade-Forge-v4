"""
Users API routes
Handles user profile management and user-related operations
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.dependencies import get_current_active_user
from app.models.user import User, UserProfile, UserProfileResponse

router = APIRouter()


@router.get("/me/profile", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
    session: AsyncSession = Depends(get_session),
):
    """Get current user's profile"""
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return UserProfileResponse(
        user_id=profile.user_id,
        nickname=profile.nickname,
        display_name=profile.display_name,
        avatar_url=profile.avatar_url,
        bio=profile.bio,
        trader_type=profile.trader_type,
        trading_goal=profile.trading_goal,
        experience_level=profile.experience_level,
        xp_points=profile.xp_points,
        level=profile.level,
        profile_public=profile.profile_public,
    )
