"""DCA (Dollar Cost Averaging) schedule management endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from bot.db.repository import DCAScheduleRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/dca",
    tags=["dca"],
    dependencies=[Depends(get_current_user)],
)

FREQ_MAP = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": timedelta(days=30),
}


# ── Request models ────────────────────────────────────

class DCACreate(BaseModel):
    pair: str
    amount_usd: float
    frequency: str  # daily / weekly / biweekly / monthly


# ── Endpoints ─────────────────────────────────────────

@router.get("/")
async def list_schedules(user_id: int = Depends(get_user_id)):
    """List all DCA schedules for the current user."""
    async with get_session() as session:
        repo = DCAScheduleRepository(session, user_id=user_id)
        schedules = await repo.get_all()
    return [
        {
            "id": s.id,
            "pair": s.pair,
            "amount_usd": s.amount_usd,
            "frequency": s.frequency,
            "active": s.active,
            "next_run": s.next_run.isoformat() if s.next_run else None,
            "last_run": s.last_run.isoformat() if s.last_run else None,
            "total_invested": s.total_invested or 0.0,
            "total_bought": s.total_bought or 0.0,
            "executions": s.executions or 0,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in schedules
    ]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_schedule(body: DCACreate, user_id: int = Depends(get_user_id)):
    """Create a new DCA schedule."""
    if body.frequency not in FREQ_MAP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"frequency must be one of: {', '.join(FREQ_MAP.keys())}",
        )
    if body.amount_usd <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="amount_usd must be positive",
        )

    now = datetime.now(timezone.utc)
    next_run = now + FREQ_MAP[body.frequency]

    async with get_session() as session:
        repo = DCAScheduleRepository(session, user_id=user_id)
        sched = await repo.create(
            pair=body.pair,
            amount_usd=body.amount_usd,
            frequency=body.frequency,
            next_run=next_run,
        )
        return {
            "id": sched.id,
            "pair": sched.pair,
            "amount_usd": sched.amount_usd,
            "frequency": sched.frequency,
            "active": sched.active,
            "next_run": next_run.isoformat(),
        }


@router.put("/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: int, user_id: int = Depends(get_user_id)):
    """Toggle a DCA schedule active/inactive."""
    async with get_session() as session:
        repo = DCAScheduleRepository(session, user_id=user_id)
        schedules = await repo.get_all()
        sched = next((s for s in schedules if s.id == schedule_id), None)
        if sched is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Schedule not found",
            )
        new_active = not sched.active
        await repo.toggle(schedule_id, active=new_active)
    return {"message": "Schedule toggled", "active": new_active}


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int, user_id: int = Depends(get_user_id)):
    """Delete a DCA schedule."""
    async with get_session() as session:
        repo = DCAScheduleRepository(session, user_id=user_id)
        deleted = await repo.delete(schedule_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        )
    return {"message": "Schedule deleted"}
