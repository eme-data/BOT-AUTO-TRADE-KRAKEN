"""Bot control endpoints – start/stop/status/balance."""

from __future__ import annotations

import json

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends

from bot.config import settings
from dashboard.api.deps import get_current_user, require_admin

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


@router.get("/balance")
async def bot_balance():
    """Get Kraken account balance (real or paper)."""
    from bot.crypto import decrypt
    from bot.db.repository import SettingsRepository
    from bot.db.session import get_session

    # Load fresh credentials from DB
    try:
        async with get_session() as session:
            repo = SettingsRepository(session)
            db_values = await repo.get_decrypted_values(decrypt)
    except Exception:
        db_values = {}

    api_key = db_values.get("kraken_api_key", settings.kraken_api_key)
    api_secret = db_values.get("kraken_api_secret", settings.kraken_api_secret)
    acc_type = db_values.get("kraken_acc_type", settings.kraken_acc_type)
    paper_trading = db_values.get("bot_paper_trading", str(settings.bot_paper_trading))
    is_paper = str(paper_trading).lower() in ("true", "1", "yes", "on")

    # In DEMO mode or paper trading, return the bot's paper balance from Redis
    if acc_type == "DEMO" or is_paper:
        try:
            r = await _get_redis()
            status_raw = await r.get("bot:last_balance")
            await r.close()
            if status_raw:
                data = json.loads(status_raw.decode())
                return data
        except Exception:
            pass
        # Fallback: return paper broker default
        return {
            "total_balance": 10000.0,
            "available_balance": 10000.0,
            "currency": "USD",
            "open_positions": 0,
            "positions": [],
            "mode": "DEMO / Paper Trading",
        }

    if not api_key or not api_secret:
        return {"error": "Kraken credentials not configured"}

    # LIVE mode: connect to real Kraken API
    from bot.broker.kraken_rest import KrakenRestClient

    old_key = settings.kraken_api_key
    old_secret = settings.kraken_api_secret
    old_acc = settings.kraken_acc_type
    object.__setattr__(settings, "kraken_api_key", api_key)
    object.__setattr__(settings, "kraken_api_secret", api_secret)
    object.__setattr__(settings, "kraken_acc_type", "LIVE")  # Force LIVE, never sandbox

    broker = KrakenRestClient()

    try:
        await broker.connect()
        balance = await broker.get_account_balance()

        # Also get open positions
        positions = await broker.get_open_positions()

        return {
            "total_balance": balance.total_balance,
            "available_balance": balance.available_balance,
            "currency": balance.currency,
            "open_positions": len(positions),
            "positions": [
                {
                    "pair": p.pair,
                    "direction": p.direction.value if hasattr(p.direction, 'value') else str(p.direction),
                    "size": p.size,
                    "entry_price": p.entry_price,
                    "unrealized_pnl": p.unrealized_pnl,
                }
                for p in positions
            ],
            "mode": "LIVE",
        }
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        await broker.disconnect()
        object.__setattr__(settings, "kraken_api_key", old_key)
        object.__setattr__(settings, "kraken_api_secret", old_secret)
        object.__setattr__(settings, "kraken_acc_type", old_acc)


@router.post("/stop", dependencies=[Depends(require_admin)])
async def stop_bot():
    r = await _get_redis()
    await r.publish("bot:commands", "stop")
    await r.close()
    return {"message": "Stop command sent"}


@router.post("/autopilot/scan", dependencies=[Depends(require_admin)])
async def trigger_scan():
    r = await _get_redis()
    await r.publish("bot:commands", "autopilot_scan_now")
    await r.close()
    return {"message": "Scan triggered"}


@router.get("/autopilot/scores")
async def autopilot_scores():
    """Get latest autopilot scan scores from Redis."""
    try:
        r = await _get_redis()
        raw = await r.get("bot:autopilot_scores")
        await r.close()
        if raw:
            return json.loads(raw.decode())
        return {"all_scores": [], "active_count": 0, "total_scanned": 0}
    except Exception:
        return {"all_scores": [], "active_count": 0, "total_scanned": 0}


@router.post("/daily-reset", dependencies=[Depends(require_admin)])
async def daily_reset():
    r = await _get_redis()
    await r.publish("bot:commands", "daily_reset")
    await r.close()
    return {"message": "Daily reset command sent"}


@router.get("/logs")
async def bot_logs(limit: int = 100):
    """Get recent bot logs from Redis list."""
    try:
        r = await _get_redis()
        raw = await r.lrange("bot:logs:history", 0, limit - 1)
        await r.close()
        logs = []
        for item in raw:
            try:
                logs.append(json.loads(item.decode()))
            except Exception:
                pass
        return logs
    except Exception:
        return []
