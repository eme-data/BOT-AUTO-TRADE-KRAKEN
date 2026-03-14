"""Authentication endpoints."""

from __future__ import annotations

import bcrypt
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from bot.config import settings
from bot.db.models import AdminUser
from bot.db.repository import AuditLogRepository
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
async def login(body: LoginRequest, request: Request):
    async with get_session() as session:
        # Try DB-based users first
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
            token = create_access_token({
                "sub": user.username,
                "role": user.role,
                "user_id": user.id,
            })
            # Audit log
            ip = request.client.host if request.client else None
            audit = AuditLogRepository(session, user_id=user.id)
            await audit.log(
                action="login",
                resource="user",
                resource_id=str(user.id),
                details={"username": user.username},
                ip_address=ip,
            )
            return TokenResponse(access_token=token)

        # Fallback: legacy env-based admin credentials
        if (
            body.username == settings.dashboard_admin_user
            and body.password == settings.dashboard_admin_password
        ):
            # Ensure legacy admin exists in DB so they have a user_id
            hashed = bcrypt.hashpw(
                body.password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            legacy = AdminUser(
                username=body.username, hashed_password=hashed, role="admin"
            )
            session.add(legacy)
            await session.flush()
            token = create_access_token({
                "sub": body.username,
                "role": "admin",
                "user_id": legacy.id,
            })
            # Audit log
            ip = request.client.host if request.client else None
            audit = AuditLogRepository(session, user_id=legacy.id)
            await audit.log(
                action="login",
                resource="user",
                resource_id=str(legacy.id),
                details={"username": body.username, "legacy_login": True},
                ip_address=ip,
            )
            return TokenResponse(access_token=token)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )
