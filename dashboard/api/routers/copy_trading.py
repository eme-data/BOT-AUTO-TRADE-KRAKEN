"""Copy trading endpoints – follow leaders and manage copy links."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.db.repository import CopyTradingRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/copy-trading",
    tags=["copy-trading"],
    dependencies=[Depends(get_current_user)],
)


# ── request / response schemas ────────────────────────────────────


class FollowRequest(BaseModel):
    leader_id: int
    multiplier: float = Field(1.0, gt=0, le=10.0)
    max_per_trade: float | None = Field(None, gt=0)


# ── helpers ───────────────────────────────────────────────────────


def _link_dict(link) -> dict:
    return {
        "id": link.id,
        "follower_id": link.follower_id,
        "leader_id": link.leader_id,
        "active": link.active,
        "multiplier": link.multiplier,
        "max_per_trade": link.max_per_trade,
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


# ── endpoints ─────────────────────────────────────────────────────


@router.get("/leaders")
async def list_leaders(user_id: int = Depends(get_user_id)):
    """List potential leaders with their performance stats."""
    async with get_session() as session:
        repo = CopyTradingRepository(session, user_id=user_id)
        stats = await repo.get_leaders_stats()
        return stats


@router.get("/links")
async def get_my_links(user_id: int = Depends(get_user_id)):
    """Get current user's copy trading links."""
    async with get_session() as session:
        repo = CopyTradingRepository(session, user_id=user_id)
        links = await repo.get_my_links()
        return [_link_dict(link) for link in links]


@router.post("/follow", status_code=201)
async def follow_leader(body: FollowRequest, user_id: int = Depends(get_user_id)):
    """Create a copy trading link to follow a leader."""
    if body.leader_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot follow yourself")
    async with get_session() as session:
        repo = CopyTradingRepository(session, user_id=user_id)
        # Check if already following
        existing = await repo.get_my_links()
        for link in existing:
            if link.leader_id == body.leader_id and link.active:
                raise HTTPException(
                    status_code=409, detail="Already following this leader"
                )
        link = await repo.create_link(
            leader_id=body.leader_id,
            multiplier=body.multiplier,
            max_per_trade=body.max_per_trade,
        )
        await session.commit()
        return _link_dict(link)


@router.put("/{link_id}/toggle")
async def toggle_link(link_id: int, user_id: int = Depends(get_user_id)):
    """Toggle a copy trading link active/inactive."""
    async with get_session() as session:
        repo = CopyTradingRepository(session, user_id=user_id)
        # Find current state
        links = await repo.get_my_links()
        current = next((l for l in links if l.id == link_id), None)
        if current is None:
            raise HTTPException(status_code=404, detail="Link not found")
        new_active = not current.active
        await repo.toggle(link_id, active=new_active)
        await session.commit()
        return {"id": link_id, "active": new_active}


@router.delete("/{link_id}", status_code=204)
async def delete_link(link_id: int, user_id: int = Depends(get_user_id)):
    """Remove a copy trading link."""
    async with get_session() as session:
        repo = CopyTradingRepository(session, user_id=user_id)
        deleted = await repo.delete(link_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Link not found")
        await session.commit()
