"""Trade history and open positions endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from bot.db.repository import TradeRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user

router = APIRouter(
    prefix="/api/trades",
    tags=["trades"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/")
async def list_trades(limit: int = 50):
    async with get_session() as session:
        repo = TradeRepository(session)
        trades = await repo.get_recent_trades(limit=limit)
        return [
            {
                "id": t.id,
                "order_id": t.order_id,
                "pair": t.pair,
                "direction": t.direction,
                "size": t.size,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "profit": t.profit,
                "fee": t.fee,
                "status": t.status,
                "strategy": t.strategy,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            }
            for t in trades
        ]


@router.get("/open")
async def open_trades():
    async with get_session() as session:
        repo = TradeRepository(session)
        trades = await repo.get_open_trades()
        return [
            {
                "id": t.id,
                "order_id": t.order_id,
                "pair": t.pair,
                "direction": t.direction,
                "size": t.size,
                "entry_price": t.entry_price,
                "strategy": t.strategy,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            }
            for t in trades
        ]
