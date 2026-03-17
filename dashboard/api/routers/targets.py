"""Daily/weekly profit target tracking with notifications."""
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from dashboard.api.deps import get_current_user, get_user_id
from bot.db.session import get_session
from bot.db.repository import TradeRepository, SettingsRepository

router = APIRouter(prefix="/api/targets", tags=["targets"], dependencies=[Depends(get_current_user)])


@router.get("/status")
async def get_target_status(user_id: int = Depends(get_user_id)):
    """Get current progress toward daily/weekly profit targets."""
    async with get_session() as session:
        trade_repo = TradeRepository(session, user_id=user_id)
        settings_repo = SettingsRepository(session, user_id=user_id)

        # Get targets from settings
        daily_target = float(await settings_repo.get("profit_target_daily") or "10.0")
        weekly_target = float(await settings_repo.get("profit_target_weekly") or "50.0")

        # Calculate daily P&L
        from sqlalchemy import select, func
        from bot.db.models import Trade
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today - timedelta(days=today.weekday())

        # Daily trades
        stmt_daily = select(func.coalesce(func.sum(Trade.profit), 0)).where(
            Trade.closed_at >= today,
            Trade.status == "closed",
        )
        if user_id:
            stmt_daily = stmt_daily.where(Trade.user_id == user_id)
        result = await session.execute(stmt_daily)
        daily_pnl = float(result.scalar() or 0)

        # Weekly trades
        stmt_weekly = select(func.coalesce(func.sum(Trade.profit), 0)).where(
            Trade.closed_at >= week_start,
            Trade.status == "closed",
        )
        if user_id:
            stmt_weekly = stmt_weekly.where(Trade.user_id == user_id)
        result = await session.execute(stmt_weekly)
        weekly_pnl = float(result.scalar() or 0)

        # Daily fee total
        stmt_fees_daily = select(func.coalesce(func.sum(Trade.fee), 0)).where(
            Trade.closed_at >= today,
            Trade.status == "closed",
        )
        if user_id:
            stmt_fees_daily = stmt_fees_daily.where(Trade.user_id == user_id)
        result = await session.execute(stmt_fees_daily)
        daily_fees = float(result.scalar() or 0)

        # Weekly fee total
        stmt_fees_weekly = select(func.coalesce(func.sum(Trade.fee), 0)).where(
            Trade.closed_at >= week_start,
            Trade.status == "closed",
        )
        if user_id:
            stmt_fees_weekly = stmt_fees_weekly.where(Trade.user_id == user_id)
        result = await session.execute(stmt_fees_weekly)
        weekly_fees = float(result.scalar() or 0)

        # Count trades
        stmt_count_daily = select(func.count(Trade.id)).where(
            Trade.closed_at >= today, Trade.status == "closed",
        )
        if user_id:
            stmt_count_daily = stmt_count_daily.where(Trade.user_id == user_id)
        result = await session.execute(stmt_count_daily)
        daily_trades = int(result.scalar() or 0)

        stmt_count_weekly = select(func.count(Trade.id)).where(
            Trade.closed_at >= week_start, Trade.status == "closed",
        )
        if user_id:
            stmt_count_weekly = stmt_count_weekly.where(Trade.user_id == user_id)
        result = await session.execute(stmt_count_weekly)
        weekly_trades = int(result.scalar() or 0)

        return {
            "daily": {
                "target": daily_target,
                "current": round(daily_pnl, 2),
                "progress_pct": round((daily_pnl / daily_target * 100) if daily_target else 0, 1),
                "reached": daily_pnl >= daily_target,
                "trades": daily_trades,
                "fees": round(daily_fees, 2),
                "net_pnl": round(daily_pnl - daily_fees, 2),
            },
            "weekly": {
                "target": weekly_target,
                "current": round(weekly_pnl, 2),
                "progress_pct": round((weekly_pnl / weekly_target * 100) if weekly_target else 0, 1),
                "reached": weekly_pnl >= weekly_target,
                "trades": weekly_trades,
                "fees": round(weekly_fees, 2),
                "net_pnl": round(weekly_pnl - weekly_fees, 2),
            },
        }


@router.put("/configure")
async def configure_targets(
    daily: float = 10.0,
    weekly: float = 50.0,
    user_id: int = Depends(get_user_id),
):
    """Set daily and weekly profit targets."""
    async with get_session() as session:
        repo = SettingsRepository(session, user_id=user_id)
        await repo.set("profit_target_daily", str(daily))
        await repo.set("profit_target_weekly", str(weekly))
        await session.commit()
    return {"daily": daily, "weekly": weekly}
