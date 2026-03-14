"""WebSocket endpoints for live bot logs and dashboard data."""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from bot.config import settings

router = APIRouter()


@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await websocket.accept()

    try:
        r = aioredis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe("bot:logs")

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
            await pubsub.unsubscribe("bot:logs")
            await r.close()
        except Exception:
            pass


@router.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """Stream live dashboard data (status updates and trade events)."""
    await websocket.accept()

    r: aioredis.Redis | None = None
    pubsub = None

    try:
        r = aioredis.from_url(settings.redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe("bot:status", "bot:trades")

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
                await pubsub.unsubscribe("bot:status", "bot:trades")
            if r:
                await r.close()
        except Exception:
            pass
