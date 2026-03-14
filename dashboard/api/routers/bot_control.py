"""Bot control endpoints – start/stop/status."""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends

from bot.config import settings
from dashboard.api.deps import get_current_user

router = APIRouter(prefix="/api/bot", tags=["bot"], dependencies=[Depends(get_current_user)])


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.redis_url)


@router.get("/status")
async def bot_status():
    try:
        r = await _get_redis()
        status_msg = await r.get("bot:last_status")
        await r.close()
        return {"status": "running", "details": status_msg.decode() if status_msg else "unknown"}
    except Exception:
        return {"status": "unknown", "details": "Redis unavailable"}


@router.post("/stop")
async def stop_bot():
    r = await _get_redis()
    await r.publish("bot:commands", "stop")
    await r.close()
    return {"message": "Stop command sent"}


@router.post("/autopilot/scan")
async def trigger_scan():
    r = await _get_redis()
    await r.publish("bot:commands", "autopilot_scan_now")
    await r.close()
    return {"message": "Scan triggered"}


@router.post("/daily-reset")
async def daily_reset():
    r = await _get_redis()
    await r.publish("bot:commands", "daily_reset")
    await r.close()
    return {"message": "Daily reset command sent"}
