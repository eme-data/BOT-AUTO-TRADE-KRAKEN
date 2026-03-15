"""Price alerts CRUD endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from bot.db.repository import PriceAlertRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/alerts",
    tags=["alerts"],
    dependencies=[Depends(get_current_user)],
)


# ── Request / response models ────────────────────────

class AlertCreate(BaseModel):
    pair: str
    condition: str  # "above" or "below"
    target_price: float
    note: str | None = None


class AlertOut(BaseModel):
    id: int
    pair: str
    condition: str
    target_price: float
    note: str | None
    active: bool
    triggered: bool
    triggered_at: str | None
    created_at: str


# ── Endpoints ─────────────────────────────────────────

@router.get("/")
async def list_alerts(user_id: int = Depends(get_user_id)):
    """List all alerts for the current user (active + triggered)."""
    async with get_session() as session:
        repo = PriceAlertRepository(session, user_id=user_id)
        alerts = await repo.get_all()
    return [
        {
            "id": a.id,
            "pair": a.pair,
            "condition": a.condition,
            "target_price": a.target_price,
            "note": a.note,
            "active": a.active,
            "triggered": a.triggered,
            "triggered_at": a.triggered_at.isoformat() if a.triggered_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_alert(body: AlertCreate, user_id: int = Depends(get_user_id)):
    """Create a new price alert."""
    if body.condition not in ("above", "below"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="condition must be 'above' or 'below'",
        )
    if body.target_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_price must be positive",
        )
    async with get_session() as session:
        repo = PriceAlertRepository(session, user_id=user_id)
        alert = await repo.create(
            pair=body.pair,
            condition=body.condition,
            target_price=body.target_price,
            note=body.note,
        )
        return {
            "id": alert.id,
            "pair": alert.pair,
            "condition": alert.condition,
            "target_price": alert.target_price,
            "note": alert.note,
            "active": alert.active,
            "triggered": alert.triggered,
        }


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int, user_id: int = Depends(get_user_id)):
    """Delete a price alert."""
    async with get_session() as session:
        repo = PriceAlertRepository(session, user_id=user_id)
        deleted = await repo.delete(alert_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return {"message": "Alert deleted"}


@router.put("/{alert_id}/toggle")
async def toggle_alert(alert_id: int, user_id: int = Depends(get_user_id)):
    """Toggle an alert active/inactive."""
    async with get_session() as session:
        repo = PriceAlertRepository(session, user_id=user_id)
        # Fetch current state to flip it
        alerts = await repo.get_all()
        alert = next((a for a in alerts if a.id == alert_id), None)
        if alert is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Alert not found",
            )
        new_active = not alert.active
        await repo.toggle(alert_id, active=new_active)
    return {"message": "Alert toggled", "active": new_active}
