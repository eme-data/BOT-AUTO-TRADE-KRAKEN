"""Telegram & Discord notification service."""

from __future__ import annotations

import asyncio

import httpx
import structlog

from bot.config import settings

logger = structlog.get_logger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


# ── Telegram ──────────────────────────────────────────

async def send_telegram_interactive(
    text: str,
    buttons: list[list[dict]],
    chat_id: str | None = None,
) -> None:
    """Send a Telegram message with inline keyboard buttons."""
    token = settings.telegram_bot_token
    target = chat_id or settings.telegram_chat_id
    if not token or not target:
        return

    import aiohttp

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {"inline_keyboard": buttons},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                pass
    except Exception:
        pass


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


# ── Discord ───────────────────────────────────────────

async def send_discord(message: str, embed: dict | None = None) -> bool:
    """Send a message via Discord webhook. Returns True on success."""
    if not settings.discord_enabled or not settings.discord_webhook_url:
        return False

    payload: dict = {}
    if message:
        payload["content"] = message
    if embed is not None:
        payload["embeds"] = [embed]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.discord_webhook_url, json=payload)
            resp.raise_for_status()
            return True
    except Exception as exc:
        logger.error("discord_error", error=str(exc))
        return False


# ── Helpers ───────────────────────────────────────────

async def _send_all(telegram_msg: str, discord_msg: str, embed: dict | None = None) -> None:
    """Send notification to both Telegram and Discord concurrently."""
    tasks = [send_telegram(telegram_msg)]
    if settings.discord_enabled:
        tasks.append(send_discord(discord_msg, embed=embed))
    await asyncio.gather(*tasks, return_exceptions=True)


# ── Notification functions ────────────────────────────

async def notify_trade_opened(
    pair: str,
    direction: str,
    size: float,
    price: float,
    strategy: str,
    order_id: str | None = None,
) -> None:
    telegram_msg = (
        f"\U0001f7e2 <b>Trade Opened</b>\n"
        f"Pair: <code>{pair}</code>\n"
        f"Direction: <code>{direction.upper()}</code>\n"
        f"Size: <code>{size}</code>\n"
        f"Price: <code>{price:.4f}</code>\n"
        f"Strategy: <code>{strategy}</code>"
    )

    discord_embed = {
        "title": "Trade Opened",
        "color": 0x2ECC71,  # green
        "fields": [
            {"name": "Pair", "value": pair, "inline": True},
            {"name": "Direction", "value": direction.upper(), "inline": True},
            {"name": "Size", "value": str(size), "inline": True},
            {"name": "Price", "value": f"{price:.4f}", "inline": True},
            {"name": "Strategy", "value": strategy, "inline": True},
        ],
    }

    # Send interactive Telegram message with close button if order_id is available
    if order_id and settings.telegram_bot_token and settings.telegram_chat_id:
        buttons = [
            [{"text": "\u274c Fermer", "callback_data": f"close:{order_id}"}]
        ]
        await send_telegram_interactive(telegram_msg, buttons)
        # Send Discord separately (no interactive buttons for Discord)
        if settings.discord_enabled:
            await send_discord("", embed=discord_embed)
    else:
        await _send_all(telegram_msg, "", embed=discord_embed)


async def notify_trade_closed(
    pair: str, profit: float, entry: float, exit_price: float
) -> None:
    emoji = "\U0001f7e2" if profit >= 0 else "\U0001f534"
    telegram_msg = (
        f"{emoji} <b>Trade Closed</b>\n"
        f"Pair: <code>{pair}</code>\n"
        f"Entry: <code>{entry:.4f}</code>\n"
        f"Exit: <code>{exit_price:.4f}</code>\n"
        f"P&L: <code>{profit:+.2f} USD</code>"
    )

    color = 0x2ECC71 if profit >= 0 else 0xE74C3C  # green or red
    discord_embed = {
        "title": "Trade Closed",
        "color": color,
        "fields": [
            {"name": "Pair", "value": pair, "inline": True},
            {"name": "Entry", "value": f"{entry:.4f}", "inline": True},
            {"name": "Exit", "value": f"{exit_price:.4f}", "inline": True},
            {"name": "P&L", "value": f"{profit:+.2f} USD", "inline": True},
        ],
    }

    await _send_all(telegram_msg, "", embed=discord_embed)


async def notify_error(error: str) -> None:
    telegram_msg = f"\u26a0\ufe0f <b>Bot Error</b>\n<code>{error[:500]}</code>"

    discord_embed = {
        "title": "Bot Error",
        "color": 0xE74C3C,  # red
        "description": f"```\n{error[:1000]}\n```",
    }

    await _send_all(telegram_msg, "", embed=discord_embed)


async def notify_bot_status(status_msg: str) -> None:
    telegram_msg = f"\u2139\ufe0f <b>Bot Status</b>\n{status_msg}"

    discord_embed = {
        "title": "Bot Status",
        "color": 0x3498DB,  # blue
        "description": status_msg,
    }

    await _send_all(telegram_msg, "", embed=discord_embed)
