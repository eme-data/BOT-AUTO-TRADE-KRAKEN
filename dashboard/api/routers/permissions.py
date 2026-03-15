"""Granular permissions router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from bot.db.models import AdminUser
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/api/permissions", tags=["permissions"])

# ── Role → permission mapping ────────────────────────

ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "admin": {
        "can_trade": True,
        "can_view_trades": True,
        "can_manage_settings": True,
        "can_manage_users": True,
        "can_backtest": True,
        "can_use_ai": True,
        "can_export": True,
    },
    "trader": {
        "can_trade": True,
        "can_view_trades": True,
        "can_manage_settings": False,
        "can_manage_users": False,
        "can_backtest": True,
        "can_use_ai": True,
        "can_export": True,
    },
    "analyst": {
        "can_trade": False,
        "can_view_trades": True,
        "can_manage_settings": False,
        "can_manage_users": False,
        "can_backtest": True,
        "can_use_ai": True,
        "can_export": True,
    },
    "viewer": {
        "can_trade": False,
        "can_view_trades": True,
        "can_manage_settings": False,
        "can_manage_users": False,
        "can_backtest": False,
        "can_use_ai": False,
        "can_export": False,
    },
}

VALID_ROLES = set(ROLE_PERMISSIONS.keys())


# ── Schemas ───────────────────────────────────────────

class RoleUpdate(BaseModel):
    role: str


# ── Endpoints ─────────────────────────────────────────

@router.get("/roles")
async def list_roles(_: dict = Depends(get_current_user)):
    """List available roles with their permissions."""
    return ROLE_PERMISSIONS


@router.get("/me")
async def my_permissions(user: dict = Depends(get_current_user)):
    """Get current user's permissions based on their role."""
    role = user.get("role", "viewer")
    permissions = ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["viewer"])
    return {
        "role": role,
        "permissions": permissions,
    }


@router.put("/user/{user_id}/role", dependencies=[Depends(require_admin)])
async def update_user_role(user_id: int, body: RoleUpdate):
    """Update a user's role (admin only)."""
    if body.role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role. Must be one of: {', '.join(sorted(VALID_ROLES))}",
        )

    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user.role = body.role
        await session.flush()

        return {
            "id": user.id,
            "username": user.username,
            "role": user.role,
        }
