"""User management endpoints – admin only."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from bot.db.models import AdminUser
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, require_admin

router = APIRouter(prefix="/api/users", tags=["users"])


# ── Schemas ───────────────────────────────────────────

class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime | None = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"


class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None


# ── Helpers ───────────────────────────────────────────

def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


# ── Endpoints ─────────────────────────────────────────

@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """Return current user info from token."""
    return {
        "username": user.get("sub"),
        "role": user.get("role", "viewer"),
        "user_id": user.get("user_id"),
    }


@router.get("/", response_model=list[UserOut], dependencies=[Depends(require_admin)])
async def list_users():
    """List all users."""
    async with get_session() as session:
        result = await session.execute(select(AdminUser).order_by(AdminUser.id))
        users = result.scalars().all()
    return [
        UserOut(id=u.id, username=u.username, role=u.role, created_at=u.created_at)
        for u in users
    ]


@router.post("/", response_model=UserOut, status_code=201, dependencies=[Depends(require_admin)])
async def create_user(body: UserCreate):
    """Create a new user."""
    if body.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be admin, editor, or viewer.")

    async with get_session() as session:
        existing = await session.execute(
            select(AdminUser).where(AdminUser.username == body.username)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Username already exists")

        user = AdminUser(
            username=body.username,
            hashed_password=_hash_password(body.password),
            role=body.role,
        )
        session.add(user)
        await session.flush()
        return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.put("/{user_id}", response_model=UserOut, dependencies=[Depends(require_admin)])
async def update_user(user_id: int, body: UserUpdate):
    """Update user role and/or password."""
    if body.role is not None and body.role not in ("admin", "editor", "viewer"):
        raise HTTPException(status_code=400, detail="Invalid role. Must be admin, editor, or viewer.")

    async with get_session() as session:
        result = await session.execute(select(AdminUser).where(AdminUser.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if body.role is not None:
            user.role = body.role
        if body.password is not None:
            user.hashed_password = _hash_password(body.password)

        await session.flush()
        return UserOut(id=user.id, username=user.username, role=user.role, created_at=user.created_at)


@router.delete("/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a user. Cannot delete yourself."""
    async with get_session() as session:
        result = await session.execute(select(AdminUser).where(AdminUser.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")

        if user.username == current_user.get("sub"):
            raise HTTPException(status_code=400, detail="Cannot delete your own account")

        await session.delete(user)

    return {"message": f"User '{user.username}' deleted"}
