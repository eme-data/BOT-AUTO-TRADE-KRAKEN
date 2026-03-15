"""Push notification subscription endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from dashboard.api.deps import get_current_user, get_user_id
from bot.db.session import get_session
from bot.db.repository import PushSubscriptionRepository

router = APIRouter(prefix="/api/push", tags=["push"], dependencies=[Depends(get_current_user)])


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionRequest(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


class UnsubscribeRequest(BaseModel):
    endpoint: str


@router.get("/vapid-key")
async def get_vapid_public_key():
    """Return the VAPID public key for push subscription."""
    key = os.environ.get("VAPID_PUBLIC_KEY", "")
    return {"publicKey": key}


@router.post("/subscribe", status_code=201)
async def subscribe(body: SubscriptionRequest, user_id: int = Depends(get_user_id)):
    """Save a push subscription for the current user."""
    async with get_session() as session:
        repo = PushSubscriptionRepository(session, user_id=user_id)
        await repo.save(
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
        )
        await session.commit()
    return {"status": "subscribed"}


@router.post("/unsubscribe")
async def unsubscribe(body: UnsubscribeRequest):
    """Remove a push subscription."""
    async with get_session() as session:
        repo = PushSubscriptionRepository(session)
        await repo.delete_by_endpoint(body.endpoint)
        await session.commit()
    return {"status": "unsubscribed"}


@router.post("/test")
async def test_push(user_id: int = Depends(get_user_id)):
    """Send a test push notification."""
    from bot.notifications_push import send_push_to_user
    sent = await send_push_to_user(
        user_id, "\U0001f514 Test Notification",
        "Les notifications push fonctionnent !", url="/",
    )
    return {"sent": sent}
