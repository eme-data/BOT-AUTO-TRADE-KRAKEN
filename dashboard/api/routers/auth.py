"""Authentication endpoints."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from bot.config import settings
from bot.db.models import AdminUser
from bot.db.session import get_session
from dashboard.api.auth.jwt import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    # First try DB-based users
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.username == body.username)
        )
        user = result.scalar_one_or_none()

    if user is not None:
        if not bcrypt.checkpw(
            body.password.encode("utf-8"),
            user.hashed_password.encode("utf-8"),
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )
        token = create_access_token({"sub": user.username, "role": user.role})
        return TokenResponse(access_token=token)

    # Fallback: legacy env-based admin credentials
    if (
        body.username == settings.dashboard_admin_user
        and body.password == settings.dashboard_admin_password
    ):
        token = create_access_token({"sub": body.username, "role": "admin"})
        return TokenResponse(access_token=token)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )
