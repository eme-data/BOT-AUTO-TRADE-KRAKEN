"""Per-user strategy customization endpoints.

Users can list available strategies, toggle them on/off, and adjust
their parameters.  State is stored in the ``strategy_state`` table,
scoped by ``user_id``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from bot.db.repository import AuditLogRepository, StrategyRepository
from bot.db.session import get_session
from bot.strategies.registry import STRATEGY_CLASSES
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(get_current_user)],
)


# ── Models ─────────────────────────────────────────────

class StrategyUpdate(BaseModel):
    enabled: bool
    config: dict[str, Any] | None = None


# ── Available strategy names ───────────────────────────

@router.get("/available")
async def list_available():
    """Return all registered strategy names with their default configs."""
    result: list[dict[str, Any]] = []
    for name, cls in STRATEGY_CLASSES.items():
        instance = cls()
        result.append({
            "name": name,
            "default_config": instance.get_config(),
        })
    return result


# ── List strategies with user state ────────────────────

@router.get("/")
async def list_strategies(user_id: int = Depends(get_user_id)):
    """List all strategies with their current enabled/config state for the user."""
    async with get_session() as session:
        repo = StrategyRepository(session, user_id=user_id)

        # Build a dict of user's saved strategy states
        all_states = await _get_all_states(repo)

    result: list[dict[str, Any]] = []
    for name, cls in STRATEGY_CLASSES.items():
        instance = cls()
        default_config = instance.get_config()

        saved = all_states.get(name)
        result.append({
            "name": name,
            "enabled": saved["enabled"] if saved else False,
            "config": saved["config"] if saved and saved["config"] else default_config,
            "default_config": default_config,
        })

    return result


# ── Update a strategy ─────────────────────────────────

@router.put("/{name}")
async def update_strategy(
    name: str,
    body: StrategyUpdate,
    request: Request,
    user_id: int = Depends(get_user_id),
):
    """Update a strategy's enabled status and config for the user."""
    if name not in STRATEGY_CLASSES:
        return {"error": f"Unknown strategy: {name}"}

    async with get_session() as session:
        repo = StrategyRepository(session, user_id=user_id)
        await repo.save_state(
            name=name,
            enabled=body.enabled,
            config=body.config,
            state=None,
        )

        # Audit log
        ip = request.client.host if request.client else None
        audit = AuditLogRepository(session, user_id=user_id)
        await audit.log(
            action="strategy_update",
            resource="strategy",
            resource_id=name,
            details={"enabled": body.enabled, "config": body.config},
            ip_address=ip,
        )

    return {"message": f"Strategy '{name}' updated", "name": name, "enabled": body.enabled}


# ── Helpers ────────────────────────────────────────────

async def _get_all_states(repo: StrategyRepository) -> dict[str, dict[str, Any]]:
    """Fetch all strategy states for the user (enabled or not)."""
    from sqlalchemy import select
    from bot.db.models import StrategyState

    stmt = select(StrategyState)
    if repo.user_id is not None:
        stmt = stmt.where(StrategyState.user_id == repo.user_id)
    result = await repo.session.execute(stmt)
    rows = result.scalars().all()
    return {
        row.name: {
            "enabled": row.enabled,
            "config": row.config,
            "state": row.state,
        }
        for row in rows
    }
