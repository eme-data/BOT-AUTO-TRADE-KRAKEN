"""Fee tracking and analysis endpoints."""
from __future__ import annotations
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select, func, cast, Date
from dashboard.api.deps import get_current_user, get_user_id
from bot.db.session import get_session
from bot.db.models import Trade

router = APIRouter(prefix="/api/fees", tags=["fees"], dependencies=[Depends(get_current_user)])


@router.get("/summary")
async def fee_summary(days: int = 30, user_id: int = Depends(get_user_id)):
    """Get fee summary over a period."""
    async with get_session() as session:
        since = datetime.utcnow() - timedelta(days=days)
        base = select(Trade).where(Trade.status == "closed", Trade.closed_at >= since)
        if user_id:
            base = base.where(Trade.user_id == user_id)

        # Total fees
        stmt = select(
            func.coalesce(func.sum(Trade.fee), 0).label("total_fees"),
            func.coalesce(func.sum(Trade.profit), 0).label("total_pnl"),
            func.count(Trade.id).label("total_trades"),
        ).where(Trade.status == "closed", Trade.closed_at >= since)
        if user_id:
            stmt = stmt.where(Trade.user_id == user_id)
        result = await session.execute(stmt)
        row = result.one()

        total_fees = float(row.total_fees)
        total_pnl = float(row.total_pnl)
        total_trades = int(row.total_trades)

        # Fees by day
        stmt_daily = select(
            cast(Trade.closed_at, Date).label("date"),
            func.sum(Trade.fee).label("fees"),
            func.sum(Trade.profit).label("pnl"),
            func.count(Trade.id).label("trades"),
        ).where(
            Trade.status == "closed", Trade.closed_at >= since
        ).group_by(cast(Trade.closed_at, Date)).order_by(cast(Trade.closed_at, Date))
        if user_id:
            stmt_daily = stmt_daily.where(Trade.user_id == user_id)
        result = await session.execute(stmt_daily)
        daily = [
            {
                "date": str(r.date),
                "fees": round(float(r.fees or 0), 4),
                "pnl": round(float(r.pnl or 0), 2),
                "trades": int(r.trades),
                "fee_pct_of_pnl": round(abs(float(r.fees or 0)) / abs(float(r.pnl)) * 100, 1) if float(r.pnl or 0) != 0 else 0,
            }
            for r in result.all()
        ]

        # Fees by pair
        stmt_pair = select(
            Trade.pair,
            func.sum(Trade.fee).label("fees"),
            func.sum(Trade.profit).label("pnl"),
            func.count(Trade.id).label("trades"),
        ).where(
            Trade.status == "closed", Trade.closed_at >= since
        ).group_by(Trade.pair).order_by(func.sum(Trade.fee).desc())
        if user_id:
            stmt_pair = stmt_pair.where(Trade.user_id == user_id)
        result = await session.execute(stmt_pair)
        by_pair = [
            {
                "pair": r.pair,
                "fees": round(float(r.fees or 0), 4),
                "pnl": round(float(r.pnl or 0), 2),
                "trades": int(r.trades),
                "avg_fee": round(float(r.fees or 0) / int(r.trades), 4) if int(r.trades) > 0 else 0,
            }
            for r in result.all()
        ]

        return {
            "period_days": days,
            "total_fees": round(total_fees, 4),
            "total_pnl": round(total_pnl, 2),
            "net_pnl": round(total_pnl - total_fees, 2),
            "fee_pct_of_pnl": round(abs(total_fees) / abs(total_pnl) * 100, 1) if total_pnl != 0 else 0,
            "total_trades": total_trades,
            "avg_fee_per_trade": round(total_fees / total_trades, 4) if total_trades > 0 else 0,
            "daily": daily,
            "by_pair": by_pair,
        }
