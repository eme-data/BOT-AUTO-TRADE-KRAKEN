"""Audit log endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from bot.db.repository import AuditLogRepository
from bot.db.session import get_session
from dashboard.api.deps import require_admin

router = APIRouter(
    prefix="/api/audit",
    tags=["audit"],
    dependencies=[Depends(require_admin)],
)


@router.get("/logs")
async def get_audit_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    action: str | None = Query(default=None),
):
    """Get audit logs (admin only - shows all users' logs)."""
    async with get_session() as session:
        repo = AuditLogRepository(session)  # No user_id filter - admin sees all
        if action:
            logs = await repo.get_by_action(action, limit=limit)
        else:
            logs = await repo.get_recent(limit=limit)

    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "resource": log.resource,
            "resource_id": log.resource_id,
            "details": log.details,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
