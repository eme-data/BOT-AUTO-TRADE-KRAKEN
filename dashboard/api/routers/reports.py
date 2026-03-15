"""Automatic reports endpoints – daily and weekly trading reports."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from bot.db.repository import TradeRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/reports",
    tags=["reports"],
    dependencies=[Depends(get_current_user)],
)


# ── helpers ───────────────────────────────────────────────────────


def _build_report(trades) -> dict:
    """Build a report summary from a list of trade objects."""
    closed = [t for t in trades if t.status == "CLOSED" and t.profit is not None]
    total = len(closed)
    if total == 0:
        return {
            "total_trades": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "winning": 0,
            "losing": 0,
            "best_trade": None,
            "worst_trade": None,
            "total_fees": 0.0,
        }

    winning = [t for t in closed if t.profit > 0]
    losing = [t for t in closed if t.profit <= 0]
    total_pnl = sum(t.profit for t in closed)
    total_fees = sum(t.fee or 0 for t in closed)
    win_rate = (len(winning) / total * 100) if total > 0 else 0.0

    best = max(closed, key=lambda t: t.profit)
    worst = min(closed, key=lambda t: t.profit)

    return {
        "total_trades": total,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 1),
        "winning": len(winning),
        "losing": len(losing),
        "best_trade": {
            "pair": best.pair,
            "profit": round(best.profit, 2),
            "direction": best.direction,
            "opened_at": best.opened_at.isoformat() if best.opened_at else None,
        },
        "worst_trade": {
            "pair": worst.pair,
            "profit": round(worst.profit, 2),
            "direction": worst.direction,
            "opened_at": worst.opened_at.isoformat() if worst.opened_at else None,
        },
        "total_fees": round(total_fees, 2),
    }


# ── endpoints ─────────────────────────────────────────────────────


@router.get("/daily")
async def daily_report(user_id: int = Depends(get_user_id)):
    """Generate a daily report for the current user."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_trades_since(start_of_day)

    report = _build_report(trades)
    report["period"] = "daily"
    report["date"] = start_of_day.strftime("%Y-%m-%d")
    return report


@router.get("/weekly")
async def weekly_report(user_id: int = Depends(get_user_id)):
    """Generate a weekly report with day-by-day breakdown."""
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    start = seven_days_ago.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_trades_since(start)

    # Overall summary
    report = _build_report(trades)
    report["period"] = "weekly"
    report["from"] = start.strftime("%Y-%m-%d")
    report["to"] = now.strftime("%Y-%m-%d")

    # Day-by-day breakdown
    closed = [t for t in trades if t.status == "CLOSED" and t.profit is not None]
    by_day: dict[str, list] = defaultdict(list)
    for t in closed:
        day_key = (t.closed_at or t.opened_at).strftime("%Y-%m-%d") if (t.closed_at or t.opened_at) else "unknown"
        by_day[day_key].append(t)

    daily_breakdown = []
    for i in range(7):
        day = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        day_trades = by_day.get(day, [])
        day_pnl = sum(t.profit for t in day_trades)
        day_wins = sum(1 for t in day_trades if t.profit > 0)
        daily_breakdown.append({
            "date": day,
            "pnl": round(day_pnl, 2),
            "trades": len(day_trades),
            "wins": day_wins,
        })

    report["daily_breakdown"] = daily_breakdown
    return report


@router.post("/send-now")
async def send_report_now(user_id: int = Depends(get_user_id)):
    """Trigger immediate daily report push notification."""
    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_trades_since(start_of_day)

    report = _build_report(trades)

    # Format notification body
    pnl = report["total_pnl"]
    pnl_sign = "+" if pnl >= 0 else ""
    body = (
        f"P&L: {pnl_sign}{pnl:.2f} USD | "
        f"Trades: {report['total_trades']} | "
        f"Win rate: {report['win_rate']:.0f}%"
    )

    from bot.notifications_push import send_push_to_user
    sent = await send_push_to_user(
        user_id,
        "Rapport quotidien",
        body,
        url="/reports",
        tag="daily-report",
    )

    return {"sent": sent, "report": report}
