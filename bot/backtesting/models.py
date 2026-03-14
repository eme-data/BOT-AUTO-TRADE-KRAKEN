"""Data models for backtesting results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BacktestTrade:
    """Record of a single simulated trade."""

    pair: str
    direction: str  # "buy" or "sell"
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    pnl_pct: float
    fee: float
    size: float


@dataclass
class BacktestResult:
    """Aggregated results from a backtest run."""

    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    equity_curve: list[float] = field(default_factory=list)
    trades: list[BacktestTrade] = field(default_factory=list)
