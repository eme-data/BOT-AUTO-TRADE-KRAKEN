"""Settings management endpoints – structured by category.

All trading settings are stored in the DB (app_settings table).
Sensitive values (API keys, tokens) are encrypted at rest.
The bot reloads settings on demand via Redis command.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from bot.config import ALL_DB_KEYS, SENSITIVE_KEYS, SETTINGS_SCHEMA, settings
from bot.db.repository import AuditLogRepository, SettingsRepository
from bot.db.session import get_session
from bot.crypto import decrypt, encrypt
from dashboard.api.deps import get_current_user, get_user_id, require_admin

router = APIRouter(
    prefix="/api/settings",
    tags=["settings"],
    dependencies=[Depends(get_current_user)],
)


# ── Models ─────────────────────────────────────────────

class SettingUpdate(BaseModel):
    key: str
    value: str


class CategoryUpdate(BaseModel):
    values: dict[str, str]


class TestConnectionRequest(BaseModel):
    api_key: str
    api_secret: str
    acc_type: str = "DEMO"


# ── Schema (tells the frontend how to render forms) ────

@router.get("/schema")
async def get_settings_schema(user_id: int = Depends(get_user_id)):
    """Return the settings schema with field types, labels, and current values."""
    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        db_values = await repo.get_decrypted_values(decrypt)

    result: dict[str, dict] = {}
    for category, fields in SETTINGS_SCHEMA.items():
        cat_fields: dict[str, dict] = {}
        for key, meta in fields.items():
            current = db_values.get(key, "")
            is_sensitive = key in SENSITIVE_KEYS
            cat_fields[key] = {
                **meta,
                "value": "***" if (is_sensitive and current) else current,
                "has_value": bool(current),
                "sensitive": is_sensitive,
            }
        result[category] = cat_fields

    return result


# ── Get / Set by category ──────────────────────────────

@router.get("/category/{category}")
async def get_category(category: str, user_id: int = Depends(get_user_id)):
    """Get all settings for a category."""
    if category not in SETTINGS_SCHEMA:
        return {"error": f"Unknown category: {category}"}

    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        db_values = await repo.get_decrypted_values(decrypt)

    fields = SETTINGS_SCHEMA[category]
    result: dict[str, dict] = {}
    for key, meta in fields.items():
        current = db_values.get(key, "")
        is_sensitive = key in SENSITIVE_KEYS
        result[key] = {
            **meta,
            "value": "***" if (is_sensitive and current) else current,
            "has_value": bool(current),
        }
    return result


@router.put("/category/{category}", dependencies=[Depends(require_admin)])
async def update_category(
    category: str,
    body: CategoryUpdate,
    request: Request,
    user_id: int = Depends(get_user_id),
):
    """Update all settings for a category at once."""
    if category not in SETTINGS_SCHEMA:
        return {"error": f"Unknown category: {category}"}

    allowed_keys = set(SETTINGS_SCHEMA[category].keys())
    filtered = {k: v for k, v in body.values.items() if k in allowed_keys}

    # Don't overwrite secrets with the mask value
    to_save = {k: v for k, v in filtered.items() if v != "***"}

    if not to_save:
        return {"message": "No changes"}

    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        count = await repo.bulk_set(to_save, SENSITIVE_KEYS, encrypt)

        # Audit log
        ip = request.client.host if request.client else None
        audit = AuditLogRepository(session, user_id=user_id)
        await audit.log(
            action="settings_update",
            resource="settings",
            resource_id=category,
            details={"keys": list(to_save.keys()), "category": category},
            ip_address=ip,
        )

    # Tell the bot to reload
    await _notify_reload(user_id)

    return {"message": f"{count} setting(s) updated", "keys": list(to_save.keys())}


# ── Individual setting ─────────────────────────────────

@router.put("/", dependencies=[Depends(require_admin)])
async def update_setting(body: SettingUpdate, request: Request, user_id: int = Depends(get_user_id)):
    """Update a single setting."""
    if body.key not in ALL_DB_KEYS:
        return {"error": f"Unknown setting: {body.key}"}
    if body.value == "***":
        return {"message": "No change (masked value)"}

    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        is_sensitive = body.key in SENSITIVE_KEYS
        value = encrypt(body.value) if is_sensitive and body.value else body.value
        await repo.set(body.key, value, encrypted=is_sensitive)

        # Audit log
        ip = request.client.host if request.client else None
        audit = AuditLogRepository(session, user_id=user_id)
        await audit.log(
            action="settings_update",
            resource="settings",
            resource_id=body.key,
            details={"keys": [body.key]},
            ip_address=ip,
        )

    await _notify_reload(user_id)
    return {"message": f"Setting '{body.key}' updated"}


# ── All settings (flat view) ──────────────────────────

@router.get("/")
async def list_settings(user_id: int = Depends(get_user_id)):
    """List all settings with values (sensitive ones masked)."""
    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        all_settings = await repo.get_all()

    safe: dict[str, str] = {}
    for k, v in all_settings.items():
        if k in SENSITIVE_KEYS:
            safe[k] = "***" if v else ""
        else:
            safe[k] = v
    return safe


# ── Configuration status ──────────────────────────────

@router.get("/status")
async def settings_status(user_id: int = Depends(get_user_id)):
    """Check if the bot is properly configured."""
    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        db_values = await repo.get_decrypted_values(decrypt)

    has_api_key = bool(db_values.get("kraken_api_key"))
    has_api_secret = bool(db_values.get("kraken_api_secret"))
    has_telegram = bool(db_values.get("telegram_bot_token") and db_values.get("telegram_chat_id"))

    return {
        "configured": has_api_key and has_api_secret,
        "kraken_connected": has_api_key and has_api_secret,
        "telegram_configured": has_telegram,
        "acc_type": db_values.get("kraken_acc_type", "DEMO"),
        "categories": {
            cat: any(bool(db_values.get(k)) for k in fields)
            for cat, fields in SETTINGS_SCHEMA.items()
        },
    }


# ── Test Kraken connection ─────────────────────────────

@router.post("/test-connection", dependencies=[Depends(require_admin)])
async def test_kraken_connection(body: TestConnectionRequest):
    """Test Kraken API credentials without saving them."""
    import ccxt.async_support as ccxt

    # DEMO mode uses PaperBroker – no real connection needed
    if body.acc_type == "DEMO":
        return {"success": True, "balance_usd": 10000.0, "mode": "DEMO (Paper Trading)"}

    exchange = ccxt.kraken(
        {
            "apiKey": body.api_key,
            "secret": body.api_secret,
            "enableRateLimit": True,
        }
    )

    try:
        balance = await exchange.fetch_balance()
        await exchange.close()
        usd = float(balance.get("total", {}).get("USD", 0) or 0)
        return {"success": True, "balance_usd": usd}
    except Exception as exc:
        try:
            await exchange.close()
        except Exception:
            pass
        return {"success": False, "error": str(exc)}


# ── Reload bot settings ───────────────────────────────

@router.post("/reload", dependencies=[Depends(require_admin)])
async def reload_settings(user_id: int = Depends(get_user_id)):
    """Tell the bot to reload settings from DB."""
    await _notify_reload(user_id)
    return {"message": "Reload command sent"}


async def _notify_reload(user_id: int | None = None) -> None:
    """Send reload_settings command to bot via Redis."""
    try:
        r = aioredis.from_url(settings.redis_url)
        # Send on user-specific channel and global channel
        if user_id:
            await r.publish(f"bot:user:{user_id}:commands", "reload_settings")
        await r.publish("bot:commands", "reload_settings")
        await r.close()
    except Exception:
        pass  # bot may not be running yet
