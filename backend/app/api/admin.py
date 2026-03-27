# backend/app/api/admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, func
from app.core.dependencies import require_admin
from app.core.database import get_session
from app.models.user import User, UserResponse
# Contest management is handled by app.api.contests (admin_router)
from datetime import datetime

router = APIRouter(prefix="/admin", tags=["Admin"])

@router.get("/users", response_model=list[UserResponse])
async def list_users(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin)
):
    """List all users (admin only)"""
    result = await session.execute(select(User))
    return result.scalars().all()

@router.patch("/users/{user_id}/ban")
async def ban_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin)
):
    """Ban a user (admin only)"""
    # Prevent banning the last admin
    if str(admin.id) == user_id:
        admin_count = await session.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if admin_count.scalar() <= 1:
            raise HTTPException(400, "Cannot ban the last admin account")

    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.status = "banned"
    user.suspension_reason = "Banned via admin panel"
    await session.commit()
    return {"message": f"User {user.email} banned"}

@router.patch("/users/{user_id}/unban")
async def unban_user(
    user_id: str,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin)
):
    """Unban a user (admin only)"""
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.status = "active"
    user.suspension_reason = None
    await session.commit()
    return {"message": f"User {user.email} unbanned"}

# Contest CRUD is handled by app.api.contests (admin_router at /admin/contests)
