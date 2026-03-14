"""Telegram notification service."""

from __future__ import annotations

import httpx
import structlog

from bot.config import settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


async def send_telegram(message: str) -> bool:
    """Send a message via Telegram bot. Returns True on success."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id

    if not token or not chat_id:
        return False

    url = TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("telegram_error", error=str(exc))
        return False


async def notify_trade_opened(
    pair: str, direction: str, size: float, price: float, strategy: str
) -> None:
    msg = (
        f"🟢 <b>Trade Opened</b>\n"
        f"Pair: <code>{pair}</code>\n"
        f"Direction: <code>{direction.upper()}</code>\n"
        f"Size: <code>{size}</code>\n"
        f"Price: <code>{price:.4f}</code>\n"
        f"Strategy: <code>{strategy}</code>"
    )
    await send_telegram(msg)


async def notify_trade_closed(
    pair: str, profit: float, entry: float, exit_price: float
) -> None:
    emoji = "🟢" if profit >= 0 else "🔴"
    msg = (
        f"{emoji} <b>Trade Closed</b>\n"
        f"Pair: <code>{pair}</code>\n"
        f"Entry: <code>{entry:.4f}</code>\n"
        f"Exit: <code>{exit_price:.4f}</code>\n"
        f"P&L: <code>{profit:+.2f} USD</code>"
    )
    await send_telegram(msg)


async def notify_error(error: str) -> None:
    msg = f"⚠️ <b>Bot Error</b>\n<code>{error[:500]}</code>"
    await send_telegram(msg)


async def notify_bot_status(status: str) -> None:
    msg = f"ℹ️ <b>Bot Status</b>\n{status}"
    await send_telegram(msg)
