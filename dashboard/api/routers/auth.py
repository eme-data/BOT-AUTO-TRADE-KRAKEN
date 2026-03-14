"""Authentication endpoints with optional TOTP 2FA."""

from __future__ import annotations

import base64
import io
from typing import Optional

import bcrypt
import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from bot.config import settings
from bot.db.models import AdminUser
from bot.db.repository import AuditLogRepository
from bot.db.session import get_session
from dashboard.api.auth.jwt import create_access_token
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    totp_code: Optional[str] = None  # Required only if 2FA is enabled


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TotpRequiredResponse(BaseModel):
    requires_totp: bool = True
    message: str = "2FA code required"


# ── Login ──────────────────────────────────────────────


@router.post("/login")
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

            # Check TOTP if enabled
            if user.totp_secret:
                if not body.totp_code:
                    return TotpRequiredResponse()
                totp = pyotp.TOTP(user.totp_secret)
                if not totp.verify(body.totp_code, valid_window=1):
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid 2FA code",
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


# ── 2FA Setup ──────────────────────────────────────────


class TotpSetupResponse(BaseModel):
    secret: str
    qr_code: str  # Base64-encoded PNG
    otpauth_uri: str


class TotpVerifyRequest(BaseModel):
    code: str


class TotpStatusResponse(BaseModel):
    enabled: bool


@router.get("/2fa/status", response_model=TotpStatusResponse)
async def totp_status(user_id: int = Depends(get_user_id)):
    """Check if 2FA is enabled for the current user."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return TotpStatusResponse(enabled=bool(user.totp_secret))


@router.post("/2fa/setup", response_model=TotpSetupResponse)
async def totp_setup(user_id: int = Depends(get_user_id)):
    """Generate a new TOTP secret and QR code. Does NOT enable 2FA yet."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(
            name=user.username,
            issuer_name="Altior Trading Bot",
        )

        # Generate QR code as base64 PNG
        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        qr_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        # Store the secret temporarily — it's only persisted after verify
        # We store it now but it won't be "active" until confirmed
        user.totp_secret = f"pending:{secret}"
        await session.flush()

        return TotpSetupResponse(
            secret=secret,
            qr_code=qr_b64,
            otpauth_uri=uri,
        )


@router.post("/2fa/verify")
async def totp_verify(
    body: TotpVerifyRequest,
    request: Request,
    user_id: int = Depends(get_user_id),
):
    """Verify a TOTP code to activate 2FA."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        stored = user.totp_secret or ""
        if stored.startswith("pending:"):
            secret = stored.replace("pending:", "")
        elif stored:
            # Already active — verify against current secret
            secret = stored
        else:
            raise HTTPException(status_code=400, detail="2FA setup not started")

        totp = pyotp.TOTP(secret)
        if not totp.verify(body.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")

        # Activate 2FA
        user.totp_secret = secret
        await session.flush()

        # Audit
        ip = request.client.host if request.client else None
        audit = AuditLogRepository(session, user_id=user_id)
        await audit.log(
            action="2fa_enabled",
            resource="user",
            resource_id=str(user_id),
            ip_address=ip,
        )

        return {"message": "2FA activated successfully"}


@router.post("/2fa/disable")
async def totp_disable(
    body: TotpVerifyRequest,
    request: Request,
    user_id: int = Depends(get_user_id),
):
    """Disable 2FA. Requires a valid TOTP code to confirm."""
    async with get_session() as session:
        result = await session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.totp_secret or user.totp_secret.startswith("pending:"):
            raise HTTPException(status_code=400, detail="2FA is not enabled")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(body.code, valid_window=1):
            raise HTTPException(status_code=400, detail="Invalid code")

        user.totp_secret = None
        await session.flush()

        # Audit
        ip = request.client.host if request.client else None
        audit = AuditLogRepository(session, user_id=user_id)
        await audit.log(
            action="2fa_disabled",
            resource="user",
            resource_id=str(user_id),
            ip_address=ip,
        )

        return {"message": "2FA disabled successfully"}
