"""Backtesting endpoints – run strategies against historical data."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from bot.broker.kraken_rest import KrakenRestClient
from bot.broker.models import Direction
from bot.config import settings
from bot.data.historical import HistoricalDataManager
from bot.data.indicators import add_all_indicators
from bot.strategies.base import SignalType
from bot.strategies.registry import STRATEGY_CLASSES
from dashboard.api.deps import get_current_user, get_user_id

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/backtest",
    tags=["backtest"],
    dependencies=[Depends(get_current_user)],
)


# ── Request / Response schemas ───────────────────────────────────────


class BacktestRequest(BaseModel):
    pair: str
    strategy: str
    days: int = Field(default=90, ge=1, le=730)
    initial_capital: float = Field(default=10000.0, gt=0)


class BacktestTrade(BaseModel):
    date: str
    pair: str
    direction: str
    entry_price: float
    exit_price: float
    profit: float
    duration_hours: float


class BacktestSummary(BaseModel):
    total_pnl: float
    win_rate: float
    profit_factor: float | None
    max_drawdown: float
    sharpe_ratio: float | None
    total_trades: int
    avg_profit: float


class EquityPoint(BaseModel):
    date: str
    equity: float


class BacktestResult(BaseModel):
    equity_curve: list[EquityPoint]
    trades: list[BacktestTrade]
    summary: BacktestSummary


# ── Helpers ──────────────────────────────────────────────────────────


def _compute_summary(
    trades: list[BacktestTrade],
    equity_curve: list[EquityPoint],
    initial_capital: float,
) -> BacktestSummary:
    """Derive performance metrics from simulated trades."""
    if not trades:
        return BacktestSummary(
            total_pnl=0.0,
            win_rate=0.0,
            profit_factor=None,
            max_drawdown=0.0,
            sharpe_ratio=None,
            total_trades=0,
            avg_profit=0.0,
        )

    profits = [t.profit for t in trades]
    total_pnl = sum(profits)
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    win_rate = (len(wins) / len(profits) * 100) if profits else 0.0

    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    if gross_losses > 0:
        profit_factor: float | None = round(gross_wins / gross_losses, 4)
    elif gross_wins > 0:
        profit_factor = None  # infinite
    else:
        profit_factor = None

    avg_profit = total_pnl / len(profits) if profits else 0.0

    # Max drawdown from equity curve
    peak = 0.0
    max_dd = 0.0
    for pt in equity_curve:
        if pt.equity > peak:
            peak = pt.equity
        dd_pct = ((peak - pt.equity) / peak * 100) if peak > 0 else 0.0
        if dd_pct > max_dd:
            max_dd = dd_pct

    # Sharpe ratio (annualised from daily returns)
    sharpe_ratio: float | None = None
    if len(equity_curve) >= 2:
        equities = [pt.equity for pt in equity_curve]
        daily_returns = [
            (equities[i] - equities[i - 1]) / equities[i - 1]
            for i in range(1, len(equities))
            if equities[i - 1] != 0
        ]
        if len(daily_returns) >= 2:
            mean_r = sum(daily_returns) / len(daily_returns)
            var_r = sum((r - mean_r) ** 2 for r in daily_returns) / (
                len(daily_returns) - 1
            )
            std_r = math.sqrt(var_r) if var_r > 0 else 0.0
            if std_r > 0:
                sharpe_ratio = round((mean_r / std_r) * math.sqrt(252), 4)

    return BacktestSummary(
        total_pnl=round(total_pnl, 2),
        win_rate=round(win_rate, 2),
        profit_factor=profit_factor,
        max_drawdown=round(max_dd, 2),
        sharpe_ratio=sharpe_ratio,
        total_trades=len(trades),
        avg_profit=round(avg_profit, 2),
    )


async def _fetch_historical_bars(
    pair: str, days: int
) -> pd.DataFrame:
    """Fetch historical OHLCV bars from Kraken via the REST client."""
    client = KrakenRestClient(
        api_key=settings.kraken_api_key,
        api_secret=settings.kraken_api_secret,
    )
    try:
        await client.connect()
        hdm = HistoricalDataManager(client)

        # Kraken limits per-request candle count, so we paginate hourly bars.
        # Each request returns up to 720 bars (30 days of hourly data).
        total_bars = days * 24
        interval_minutes = 60

        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        since_ms = int(since_dt.timestamp() * 1000)

        all_candles = []
        fetched = 0
        current_since = since_ms

        while fetched < total_bars:
            batch_limit = min(720, total_bars - fetched)
            candles = await client.get_historical_prices(
                pair=pair,
                interval_minutes=interval_minutes,
                since=current_since,
                limit=batch_limit,
            )
            if not candles:
                break
            all_candles.extend(candles)
            fetched += len(candles)
            # Move the cursor forward past the last candle
            last_ts = candles[-1].timestamp
            current_since = int(last_ts.timestamp() * 1000) + 1
            if len(candles) < batch_limit:
                break

        if not all_candles:
            return pd.DataFrame()

        df = HistoricalDataManager._candles_to_df(all_candles)
        # Remove duplicate indices from overlapping pagination
        df = df[~df.index.duplicated(keep="first")]
        df.sort_index(inplace=True)
        return df
    finally:
        await client.disconnect()


def _run_backtest_simulation(
    df: pd.DataFrame,
    strategy_name: str,
    pair: str,
    initial_capital: float,
) -> BacktestResult:
    """Run a simplified backtest: iterate bars, collect signals, simulate trades."""

    # Create strategy instance
    cls = STRATEGY_CLASSES.get(strategy_name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {strategy_name}")
    strategy = cls()

    # Add indicators
    df = add_all_indicators(df.copy())

    trades: list[BacktestTrade] = []
    equity_curve: list[EquityPoint] = []

    capital = initial_capital
    position_open = False
    entry_price = 0.0
    entry_time: datetime | None = None
    position_direction: str = "buy"

    min_bars = max(strategy.min_bars, 50)

    for i in range(min_bars, len(df)):
        # Build a window up to bar i (inclusive)
        window = df.iloc[: i + 1]
        current_bar = df.iloc[i]
        bar_time = current_bar.name  # timestamp index
        close_price = current_bar["close"]

        # Get signal from strategy
        try:
            signal = strategy.on_bar(pair, window)
        except Exception:
            signal = None

        if not position_open:
            # Look for entry signal
            if signal and signal.signal_type in (SignalType.BUY, SignalType.SELL):
                position_open = True
                entry_price = close_price
                entry_time = bar_time
                position_direction = signal.direction.value
        else:
            # Check for exit: opposite signal or stop-loss/take-profit hit
            should_exit = False
            exit_price = close_price

            if signal:
                if position_direction == "buy" and signal.signal_type == SignalType.SELL:
                    should_exit = True
                elif position_direction == "sell" and signal.signal_type == SignalType.BUY:
                    should_exit = True

            # Simple stop-loss / take-profit simulation (using strategy defaults)
            if not should_exit and entry_price > 0:
                if position_direction == "buy":
                    pnl_pct = ((close_price - entry_price) / entry_price) * 100
                else:
                    pnl_pct = ((entry_price - close_price) / entry_price) * 100

                # Use 5% stop-loss and 10% take-profit as defaults
                stop_pct = getattr(strategy, "stop_pct", 5.0) or 5.0
                tp_pct = getattr(strategy, "limit_pct", 10.0) or 10.0

                if pnl_pct <= -stop_pct:
                    should_exit = True
                elif pnl_pct >= tp_pct:
                    should_exit = True

            if should_exit:
                # Calculate P&L
                if position_direction == "buy":
                    profit = exit_price - entry_price
                else:
                    profit = entry_price - exit_price

                # Scale profit by position size (use fraction of capital)
                position_size = capital * 0.1 / entry_price if entry_price > 0 else 0
                dollar_profit = profit * position_size

                duration_hours = 0.0
                if entry_time is not None:
                    delta = bar_time - entry_time
                    if hasattr(delta, "total_seconds"):
                        duration_hours = delta.total_seconds() / 3600
                    else:
                        duration_hours = 0.0

                trades.append(
                    BacktestTrade(
                        date=str(bar_time)[:19],
                        pair=pair,
                        direction=position_direction,
                        entry_price=round(entry_price, 6),
                        exit_price=round(exit_price, 6),
                        profit=round(dollar_profit, 2),
                        duration_hours=round(duration_hours, 2),
                    )
                )

                capital += dollar_profit
                position_open = False
                entry_price = 0.0
                entry_time = None

        # Record equity at each bar (daily granularity for the curve)
        date_str = str(bar_time)[:10]
        if not equity_curve or equity_curve[-1].date != date_str:
            equity_curve.append(
                EquityPoint(date=date_str, equity=round(capital, 2))
            )
        else:
            equity_curve[-1].equity = round(capital, 2)

    summary = _compute_summary(trades, equity_curve, initial_capital)

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        summary=summary,
    )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post("/run", response_model=BacktestResult)
async def run_backtest(
    body: BacktestRequest,
    user_id: int = Depends(get_user_id),
):
    """Run a backtest for the given strategy on historical data."""
    if body.strategy not in STRATEGY_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown strategy '{body.strategy}'. "
            f"Available: {list(STRATEGY_CLASSES.keys())}",
        )

    logger.info(
        "backtest_start",
        pair=body.pair,
        strategy=body.strategy,
        days=body.days,
        capital=body.initial_capital,
        user_id=user_id,
    )

    try:
        df = await _fetch_historical_bars(body.pair, body.days)
    except Exception as exc:
        logger.error("backtest_fetch_error", error=str(exc))
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch historical data: {exc}",
        )

    if df.empty or len(df) < 50:
        raise HTTPException(
            status_code=422,
            detail=f"Insufficient historical data for {body.pair} "
            f"({len(df)} bars fetched, need at least 50).",
        )

    try:
        result = _run_backtest_simulation(
            df=df,
            strategy_name=body.strategy,
            pair=body.pair,
            initial_capital=body.initial_capital,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("backtest_simulation_error", error=str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Backtest simulation failed: {exc}",
        )

    logger.info(
        "backtest_complete",
        pair=body.pair,
        strategy=body.strategy,
        total_trades=result.summary.total_trades,
        total_pnl=result.summary.total_pnl,
        user_id=user_id,
    )

    return result


@router.get("/strategies")
async def list_strategies(
    user_id: int = Depends(get_user_id),
) -> list[dict[str, Any]]:
    """List available strategies for backtesting."""
    strategies = []
    for name, cls in STRATEGY_CLASSES.items():
        instance = cls()
        strategies.append(
            {
                "name": name,
                "display_name": name.replace("_", " ").title(),
                "min_bars": instance.min_bars,
                "config": instance.get_config(),
            }
        )
    return strategies
