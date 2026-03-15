"""Web Push notification sender using VAPID."""

from __future__ import annotations

import json
import os

import structlog
from pywebpush import webpush, WebPushException

from bot.db.session import get_session
from bot.db.repository import PushSubscriptionRepository

logger = structlog.get_logger(__name__)

VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_CLAIMS = {"sub": "mailto:admin@altior-holding.fr"}


async def send_push_to_user(user_id: int, title: str, body: str, url: str = "/", tag: str = "trade") -> int:
    """Send a push notification to all subscriptions for a user. Returns count of successful sends."""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        logger.debug("push_skipped_no_vapid_keys")
        return 0

    async with get_session() as session:
        repo = PushSubscriptionRepository(session)
        subs = await repo.get_by_user(user_id)

    sent = 0
    for sub in subs:
        try:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            }
            payload = json.dumps({
                "title": title,
                "body": body,
                "url": url,
                "tag": tag,
            })
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS,
            )
            sent += 1
        except WebPushException as exc:
            resp = getattr(exc, "response", None)
            if resp and hasattr(resp, "status_code") and resp.status_code in (404, 410):
                logger.info("push_sub_expired", endpoint=sub.endpoint[:50])
                async with get_session() as session:
                    repo = PushSubscriptionRepository(session)
                    await repo.delete_by_endpoint(sub.endpoint)
                    await session.commit()
            else:
                logger.warning("push_send_error", error=str(exc))
        except Exception as exc:
            logger.warning("push_send_error", error=str(exc))

    return sent


async def notify_trade_push(user_id: int, trade_type: str, pair: str, direction: str,
                            price: float, size: float = 0, profit: float = 0,
                            strategy: str = "") -> int:
    """Send a push notification for a trade event."""
    if trade_type == "trade_opened":
        emoji = "\U0001f7e2" if direction.upper() == "BUY" else "\U0001f534"
        title = f"{emoji} {direction.upper()} {pair}"
        body = f"Prix: {price:.2f} | Taille: {size} | Strategie: {strategy}"
    elif trade_type == "trade_closed":
        emoji = "\u2705" if profit >= 0 else "\u274c"
        title = f"{emoji} Trade cloture {pair}"
        body = f"P&L: {profit:+.2f} USD | Prix: {price:.2f}"
    else:
        title = f"Trade {pair}"
        body = f"{direction} @ {price:.2f}"

    return await send_push_to_user(user_id, title, body, url="/", tag=f"trade-{pair}")
