"""Active session management endpoints."""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from dashboard.api.deps import get_current_user, get_user_id, require_admin
from bot.db.session import get_session
import redis.asyncio as redis
import json
import os

router = APIRouter(prefix="/api/sessions", tags=["sessions"], dependencies=[Depends(get_current_user)])

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")


async def _get_redis():
    return redis.from_url(REDIS_URL, decode_responses=True)


@router.post("/register")
async def register_session(request: Request, user_id: int = Depends(get_user_id)):
    """Register the current session (called on login/page load)."""
    r = await _get_redis()
    session_key = f"session:{user_id}:{request.client.host if request.client else 'unknown'}"
    session_data = {
        "user_id": user_id,
        "ip": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown")[:200],
        "last_seen": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }
    await r.setex(session_key, 86400, json.dumps(session_data))  # 24h TTL
    await r.close()
    return {"status": "registered"}


@router.get("/active")
async def list_active_sessions(user_id: int = Depends(get_user_id)):
    """List active sessions for the current user."""
    r = await _get_redis()
    keys = await r.keys(f"session:{user_id}:*")
    sessions = []
    for key in keys:
        data = await r.get(key)
        if data:
            session = json.loads(data)
            session["session_key"] = key
            sessions.append(session)
    await r.close()
    return {"sessions": sessions}


@router.get("/all")
async def list_all_sessions(_: dict = Depends(require_admin)):
    """List all active sessions (admin only)."""
    r = await _get_redis()
    keys = await r.keys("session:*")
    sessions = []
    for key in keys:
        data = await r.get(key)
        if data:
            session = json.loads(data)
            session["session_key"] = key
            sessions.append(session)
    await r.close()
    return {"sessions": sessions}


@router.delete("/revoke/{session_key:path}")
async def revoke_session(session_key: str, user_id: int = Depends(get_user_id)):
    """Revoke a specific session."""
    r = await _get_redis()
    # Users can only revoke their own sessions
    if not session_key.startswith(f"session:{user_id}:"):
        await r.close()
        return {"error": "Not authorized"}, 403
    await r.delete(session_key)
    await r.close()
    return {"status": "revoked"}


@router.delete("/revoke-all")
async def revoke_all_sessions(user_id: int = Depends(get_user_id)):
    """Revoke all sessions for the current user."""
    r = await _get_redis()
    keys = await r.keys(f"session:{user_id}:*")
    if keys:
        await r.delete(*keys)
    await r.close()
    return {"revoked": len(keys)}
