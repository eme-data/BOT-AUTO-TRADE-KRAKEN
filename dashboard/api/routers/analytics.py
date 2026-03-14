"""Performance analytics endpoints for the trading dashboard."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from bot.db.models import Trade
from bot.db.repository import TradeRepository
from bot.db.session import get_session
from dashboard.api.deps import get_current_user, get_user_id

router = APIRouter(
    prefix="/api/analytics",
    tags=["analytics"],
    dependencies=[Depends(get_current_user)],
)


# ── helpers ──────────────────────────────────────────────────────────


async def _fetch_closed_trades(user_id: int, days: int) -> list[Trade]:
    """Fetch closed trades within the given window."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async with get_session() as session:
        repo = TradeRepository(session, user_id=user_id)
        trades = await repo.get_trades_since(since)
        return [t for t in trades if t.status == "CLOSED" and t.profit is not None]


def _group_by_date(trades: list[Trade]) -> dict[str, list[Trade]]:
    """Group trades by their close date (YYYY-MM-DD)."""
    groups: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        if t.closed_at:
            day = t.closed_at.strftime("%Y-%m-%d")
        elif t.opened_at:
            day = t.opened_at.strftime("%Y-%m-%d")
        else:
            continue
        groups[day].append(t)
    return dict(sorted(groups.items()))


def _build_equity_curve(trades: list[Trade]) -> list[dict[str, Any]]:
    """Build daily equity data points from closed trades."""
    by_day = _group_by_date(trades)
    cumulative_pnl = 0.0
    balance = 0.0
    curve: list[dict[str, Any]] = []
    for date, day_trades in by_day.items():
        day_pnl = sum(t.profit for t in day_trades)
        cumulative_pnl += day_pnl
        balance = cumulative_pnl  # equity = cumulative realised P&L
        curve.append({
            "date": date,
            "balance": round(balance, 2),
            "pnl": round(day_pnl, 2),
            "cumulative_pnl": round(cumulative_pnl, 2),
        })
    return curve


def _win_rate(trades: list[Trade]) -> float:
    if not trades:
        return 0.0
    wins = sum(1 for t in trades if t.profit and t.profit > 0)
    return round(wins / len(trades) * 100, 2)


# ── endpoints ────────────────────────────────────────────────────────


@router.get("/equity-curve")
async def equity_curve(
    days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(get_user_id),
):
    """Daily equity data points computed from closed trades."""
    trades = await _fetch_closed_trades(user_id, days)
    return _build_equity_curve(trades)


@router.get("/drawdown")
async def drawdown(
    days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(get_user_id),
):
    """Drawdown series derived from the equity curve."""
    trades = await _fetch_closed_trades(user_id, days)
    curve = _build_equity_curve(trades)

    peak = 0.0
    result: list[dict[str, Any]] = []
    for point in curve:
        balance = point["cumulative_pnl"]
        if balance > peak:
            peak = balance
        dd_abs = peak - balance
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0.0
        result.append({
            "date": point["date"],
            "drawdown_pct": round(dd_pct, 2),
            "max_balance": round(peak, 2),
        })
    return result


@router.get("/pnl-breakdown")
async def pnl_breakdown(
    days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(get_user_id),
):
    """P&L grouped by day, strategy, and pair."""
    trades = await _fetch_closed_trades(user_id, days)

    # ── by day ───────────────────────────────────
    by_day_map = _group_by_date(trades)
    by_day = [
        {
            "date": date,
            "pnl": round(sum(t.profit for t in ts), 2),
            "trades": len(ts),
        }
        for date, ts in by_day_map.items()
    ]

    # ── by strategy ──────────────────────────────
    strat_map: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        strat_map[t.strategy or "unknown"].append(t)
    by_strategy = [
        {
            "strategy": name,
            "pnl": round(sum(t.profit for t in ts), 2),
            "trades": len(ts),
            "win_rate": _win_rate(ts),
        }
        for name, ts in sorted(strat_map.items())
    ]

    # ── by pair ──────────────────────────────────
    pair_map: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        pair_map[t.pair].append(t)
    by_pair = [
        {
            "pair": pair,
            "pnl": round(sum(t.profit for t in ts), 2),
            "trades": len(ts),
            "win_rate": _win_rate(ts),
        }
        for pair, ts in sorted(pair_map.items())
    ]

    return {
        "by_day": by_day,
        "by_strategy": by_strategy,
        "by_pair": by_pair,
    }


@router.get("/strategy-comparison")
async def strategy_comparison(
    days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(get_user_id),
):
    """Per-strategy detailed metrics for side-by-side comparison."""
    trades = await _fetch_closed_trades(user_id, days)

    strat_map: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        strat_map[t.strategy or "unknown"].append(t)

    result: list[dict[str, Any]] = []
    for name, ts in sorted(strat_map.items()):
        wins = [t for t in ts if t.profit and t.profit > 0]
        losses = [t for t in ts if t.profit is not None and t.profit <= 0]

        total_pnl = sum(t.profit for t in ts)
        win_count = len(wins)
        loss_count = len(losses)
        win_rate = round(win_count / len(ts) * 100, 2) if ts else 0.0

        avg_profit = round(total_pnl / len(ts), 2) if ts else 0.0
        max_win = round(max((t.profit for t in wins), default=0.0), 2)
        max_loss = round(min((t.profit for t in losses), default=0.0), 2)

        gross_wins = sum(t.profit for t in wins)
        gross_losses = abs(sum(t.profit for t in losses))
        if gross_losses > 0:
            profit_factor = round(gross_wins / gross_losses, 4)
        elif gross_wins > 0:
            profit_factor = None  # infinite
        else:
            profit_factor = None

        # Average holding time in hours
        holding_times: list[float] = []
        for t in ts:
            if t.opened_at and t.closed_at:
                delta = (t.closed_at - t.opened_at).total_seconds() / 3600
                holding_times.append(delta)
        avg_holding_hours = round(
            sum(holding_times) / len(holding_times), 2
        ) if holding_times else None

        result.append({
            "strategy": name,
            "total_trades": len(ts),
            "win_count": win_count,
            "loss_count": loss_count,
            "win_rate": win_rate,
            "total_pnl": round(total_pnl, 2),
            "avg_profit": avg_profit,
            "max_win": max_win,
            "max_loss": max_loss,
            "profit_factor": profit_factor,
            "avg_holding_hours": avg_holding_hours,
        })

    return result


@router.get("/performance-summary")
async def performance_summary(
    days: int = Query(30, ge=1, le=365),
    user_id: int = Depends(get_user_id),
):
    """Key performance metrics over the requested window."""
    trades = await _fetch_closed_trades(user_id, days)

    if not trades:
        return {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "profit_factor": None,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": None,
            "best_day": 0.0,
            "worst_day": 0.0,
            "avg_trades_per_day": 0.0,
        }

    # Basic buckets
    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit <= 0]

    total_pnl = sum(t.profit for t in trades)
    win_rate = len(wins) / len(trades) * 100 if trades else 0.0

    gross_wins = sum(t.profit for t in wins)
    gross_losses = abs(sum(t.profit for t in losses))
    if gross_losses > 0:
        profit_factor = round(gross_wins / gross_losses, 4)
    elif gross_wins > 0:
        profit_factor = None  # infinite
    else:
        profit_factor = None

    avg_win = (gross_wins / len(wins)) if wins else 0.0
    avg_loss = (sum(t.profit for t in losses) / len(losses)) if losses else 0.0

    # Daily P&L for drawdown, best/worst day, Sharpe
    by_day = _group_by_date(trades)
    daily_pnls = [sum(t.profit for t in ts) for ts in by_day.values()]

    best_day = max(daily_pnls) if daily_pnls else 0.0
    worst_day = min(daily_pnls) if daily_pnls else 0.0

    # Max drawdown from equity curve
    curve = _build_equity_curve(trades)
    peak = 0.0
    max_dd = 0.0
    for pt in curve:
        bal = pt["cumulative_pnl"]
        if bal > peak:
            peak = bal
        dd_pct = ((peak - bal) / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd:
            max_dd = dd_pct

    # Sharpe ratio (annualised, using daily returns)
    sharpe_ratio: float | None = None
    if len(daily_pnls) >= 2:
        mean_daily = sum(daily_pnls) / len(daily_pnls)
        variance = sum((p - mean_daily) ** 2 for p in daily_pnls) / (len(daily_pnls) - 1)
        std_daily = math.sqrt(variance) if variance > 0 else 0.0
        if std_daily > 0:
            sharpe_ratio = round((mean_daily / std_daily) * math.sqrt(252), 4)

    # Average trades per day (calendar days in window)
    num_days = max(len(by_day), 1)
    avg_trades_per_day = len(trades) / num_days

    return {
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(win_rate, 2),
        "profit_factor": profit_factor,
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "max_drawdown": round(max_dd, 2),
        "sharpe_ratio": sharpe_ratio,
        "best_day": round(best_day, 2),
        "worst_day": round(worst_day, 2),
        "avg_trades_per_day": round(avg_trades_per_day, 2),
    }
