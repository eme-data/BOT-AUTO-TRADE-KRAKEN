"""Telegram webhook handler for interactive button callbacks."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Request

from bot.config import settings
from bot.notifications import send_telegram_interactive

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["telegram"])


async def _answer_callback(callback_query_id: str, text: str) -> None:
    """Answer a Telegram callback query to dismiss the loading indicator."""
    token = settings.telegram_bot_token
    if not token:
        return

    import aiohttp

    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text,
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except Exception:
        logger.warning("telegram_answer_callback_failed")


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """Handle Telegram callback queries (button presses)."""
    data = await request.json()

    callback = data.get("callback_query")
    if not callback:
        return {"ok": True}

    callback_data = callback.get("data", "")
    callback_id = callback.get("id", "")

    if callback_data.startswith("close:"):
        order_id = callback_data.split(":")[1]
        logger.info("telegram_close_requested", order_id=order_id)

        # Acknowledge the callback
        await _answer_callback(callback_id, f"Fermeture du trade {order_id} demandee")

        # Send confirmation message
        chat_id = str(callback.get("message", {}).get("chat", {}).get("id", ""))
        if chat_id:
            from bot.notifications import send_telegram

            await send_telegram(
                f"\u2705 <b>Trade close demande</b>\n"
                f"Order ID: <code>{order_id}</code>\n"
                f"La demande de fermeture a ete envoyee au bot."
            )

    return {"ok": True}
