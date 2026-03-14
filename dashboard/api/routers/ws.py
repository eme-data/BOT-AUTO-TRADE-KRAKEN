"""WebSocket endpoints for live bot logs and dashboard data."""

from __future__ import annotations

import asyncio
from typing import Optional

import redis.asyncio as aioredis
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from bot.config import settings
from dashboard.api.auth.jwt import verify_token

router = APIRouter()


def _authenticate_ws(token: str | None) -> int | None:
    """Verify JWT token from query param and return user_id."""
    if not token:
        return None
    payload = verify_token(token)
    if payload is None:
        return None
    return payload.get("user_id")


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, token: Optional[str] = Query(None)):
    await websocket.accept()

    user_id = _authenticate_ws(token)

    try:
        r = aioredis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        # Subscribe to user-specific and global channels
        channels = ["bot:logs"]
        if user_id:
            channels.append(f"bot:user:{user_id}:logs")
        await pubsub.subscribe(*channels)

        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if msg and msg["type"] == "message":
                await websocket.send_text(msg["data"].decode())
            else:
                # Send heartbeat
                try:
                    await websocket.send_text('{"type":"heartbeat"}')
                except Exception:
                    break
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            await r.close()
        except Exception:
            pass


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket, token: Optional[str] = Query(None)):
    """Stream live dashboard data (status updates and trade events)."""
    await websocket.accept()

    user_id = _authenticate_ws(token)

    r: aioredis.Redis | None = None
    pubsub = None
    channels = ["bot:status", "bot:trades"]
    if user_id:
        channels.extend([
            f"bot:user:{user_id}:status",
            f"bot:user:{user_id}:trades",
        ])

    try:
        r = aioredis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe(*channels)

        while True:
            msg = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=1.0
            )
            if msg and msg["type"] == "message":
                await websocket.send_text(msg["data"].decode())
            else:
                # Send heartbeat to keep connection alive
                try:
                    await websocket.send_text('{"type":"heartbeat"}')
                except Exception:
                    break
                await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            if pubsub:
                await pubsub.unsubscribe(*channels)
            if r:
                await r.close()
        except Exception:
            pass
