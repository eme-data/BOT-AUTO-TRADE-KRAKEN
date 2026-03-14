"""WebSocket endpoint for live bot logs."""

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
