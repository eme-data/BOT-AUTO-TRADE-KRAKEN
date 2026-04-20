"""Backtesting engine — simulates strategy execution on historical data."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from bot.broker.models import Direction
from bot.strategies.base import AbstractStrategy, SignalType
from bot.backtesting.models import BacktestResult, BacktestTrade


@dataclass
class _OpenPosition:
    """Internal tracker for an open simulated position."""

    pair: str
    direction: str  # "buy" or "sell"
    entry_price: float
    entry_time: pd.Timestamp
    size: float
    stop_loss: float | None
    take_profit: float | None
    entry_fee: float


class BacktestEngine:
    """Iterate bars, call strategy.on_bar(), and simulate entries/exits.

    Accounts for:
    - Maker/taker fees on entry and exit
    - Slippage (applied to both entry and exit prices)
    - ATR-based stop-loss and take-profit checked against bar high/low
    - Proper equity-curve and drawdown tracking
    """

    def __init__(
        self,
        strategy: AbstractStrategy,
        initial_balance: float = 10_000.0,
        maker_fee: float = 0.0016,
        taker_fee: float = 0.0026,
        slippage: float = 0.0005,
        position_size_pct: float = 0.15,
    ) -> None:
        self.strategy = strategy
        self.initial_balance = initial_balance
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage = slippage
        # Fraction of equity risked per trade — must mirror production sizing
        # (`risk_max_position_pct` in user config, default 0.15).
        self.position_size_pct = position_size_pct

    # ── public ──────────────────────────────────────────

    def run(self, df: pd.DataFrame, pair: str) -> BacktestResult:
        """Run backtest over a DataFrame with OHLCV + indicator columns.

        The DataFrame must have at least: open, high, low, close, volume
        and any columns that the strategy requires.
        """
        self.strategy.reset()

        balance = self.initial_balance
        position: Optional[_OpenPosition] = None
        trades: list[BacktestTrade] = []
        equity_curve: list[float] = []

        for i in range(self.strategy.min_bars, len(df)):
            bar = df.iloc[i]
            history = df.iloc[: i + 1]

            # ── Check stop-loss / take-profit on current bar ──
            if position is not None:
                closed, exit_price, exit_reason = self._check_sl_tp(
                    position, bar
                )
                if closed:
                    trade, balance = self._close_position(
                        position, exit_price, bar.name, balance
                    )
                    trades.append(trade)
                    position = None

            # ── Ask strategy for a signal ──
            signal = self.strategy.on_bar(pair, history)

            if signal is not None and signal.signal_type != SignalType.HOLD:
                # If we have a position in the opposite direction, close it
                if position is not None:
                    opposite = (
                        signal.direction.value != position.direction
                    )
                    if opposite:
                        exit_price = self._apply_slippage(
                            bar["close"], position.direction, closing=True
                        )
                        trade, balance = self._close_position(
                            position, exit_price, bar.name, balance
                        )
                        trades.append(trade)
                        position = None

                # Open new position if flat
                if position is None and signal.signal_type in (
                    SignalType.BUY,
                    SignalType.SELL,
                ):
                    position, balance = self._open_position(
                        signal, bar, pair, balance
                    )

            # ── Record equity (cash + mark-to-market position value) ──
            mark = bar["close"]
            if position is not None:
                equity = balance + position.size * mark
            else:
                equity = balance
            equity_curve.append(equity)

        # Close any remaining position at last bar's close
        if position is not None:
            last_bar = df.iloc[-1]
            exit_price = self._apply_slippage(
                last_bar["close"], position.direction, closing=True
            )
            trade, balance = self._close_position(
                position, exit_price, last_bar.name, balance
            )
            trades.append(trade)
            # Overwrite the last equity sample to reflect the realised close
            if equity_curve:
                equity_curve[-1] = balance

        return self._build_result(trades, equity_curve)

    # ── private helpers ──────────────────────────────────

    def _apply_slippage(
        self, price: float, direction: str, closing: bool = False
    ) -> float:
        """Apply slippage: worse price for the trader."""
        # When buying to open or buying to close a short, price goes up
        # When selling to open or selling to close a long, price goes down
        if (direction == "buy" and not closing) or (
            direction == "sell" and closing
        ):
            # Buying: price goes up
            return price * (1 + self.slippage)
        else:
            # Selling: price goes down
            return price * (1 - self.slippage)

    def _open_position(self, signal, bar, pair, balance):
        """Open a new position, deducting entry fee from balance."""
        # Guard against depleted balance — avoid compounding into negative equity.
        if balance <= 0:
            return None, balance

        entry_price = self._apply_slippage(
            bar["close"], signal.direction.value, closing=False
        )
        # Use taker fee for market entries
        fee_rate = self.taker_fee
        # Size: fraction of current equity (mirrors production sizing).
        notional = balance * self.position_size_pct
        if notional <= 0 or entry_price <= 0:
            return None, balance
        size = notional / (entry_price * (1 + fee_rate))
        entry_fee = size * entry_price * fee_rate

        # Compute stop/take-profit price levels
        stop_loss: float | None = None
        take_profit: float | None = None

        if signal.stop_loss_pct is not None:
            sl_pct = signal.stop_loss_pct / 100.0
            if signal.direction == Direction.BUY:
                stop_loss = entry_price * (1 - sl_pct)
            else:
                stop_loss = entry_price * (1 + sl_pct)

        if signal.take_profit_pct is not None:
            tp_pct = signal.take_profit_pct / 100.0
            if signal.direction == Direction.BUY:
                take_profit = entry_price * (1 + tp_pct)
            else:
                take_profit = entry_price * (1 - tp_pct)

        balance -= size * entry_price + entry_fee

        pos = _OpenPosition(
            pair=pair,
            direction=signal.direction.value,
            entry_price=entry_price,
            entry_time=bar.name,
            size=size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_fee=entry_fee,
        )
        return pos, balance

    def _close_position(
        self,
        position: _OpenPosition,
        exit_price: float,
        exit_time,
        balance: float,
    ) -> tuple[BacktestTrade, float]:
        """Close a position and return the trade record + updated balance."""
        exit_fee = position.size * exit_price * self.taker_fee
        total_fee = position.entry_fee + exit_fee

        if position.direction == "buy":
            pnl = (exit_price - position.entry_price) * position.size - total_fee
        else:
            pnl = (position.entry_price - exit_price) * position.size - total_fee

        pnl_pct = (
            pnl / (position.size * position.entry_price) * 100
            if position.entry_price
            else 0.0
        )

        # Return capital + pnl to balance
        balance += position.size * exit_price - exit_fee

        trade = BacktestTrade(
            pair=position.pair,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            entry_time=position.entry_time,
            exit_time=exit_time,
            pnl=pnl,
            pnl_pct=pnl_pct,
            fee=total_fee,
            size=position.size,
        )
        return trade, balance

    def _check_sl_tp(
        self, position: _OpenPosition, bar
    ) -> tuple[bool, float, str]:
        """Check if stop-loss or take-profit was hit on this bar.

        Uses the bar's high and low to determine if SL/TP was breached.
        Returns (closed, exit_price, reason).
        """
        high = bar["high"]
        low = bar["low"]

        if position.direction == "buy":
            # Stop-loss hit if low <= stop_loss
            if position.stop_loss is not None and low <= position.stop_loss:
                return True, position.stop_loss, "stop_loss"
            # Take-profit hit if high >= take_profit
            if position.take_profit is not None and high >= position.take_profit:
                return True, position.take_profit, "take_profit"
        else:  # sell / short
            # Stop-loss hit if high >= stop_loss
            if position.stop_loss is not None and high >= position.stop_loss:
                return True, position.stop_loss, "stop_loss"
            # Take-profit hit if low <= take_profit
            if position.take_profit is not None and low <= position.take_profit:
                return True, position.take_profit, "take_profit"

        return False, 0.0, ""

    def _unrealized_pnl(self, position: _OpenPosition, mark_price: float) -> float:
        """Calculate unrealized PnL for equity curve tracking."""
        if position.direction == "buy":
            return (mark_price - position.entry_price) * position.size
        else:
            return (position.entry_price - mark_price) * position.size

    def _build_result(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[float],
    ) -> BacktestResult:
        """Compute aggregate metrics from the trade list and equity curve."""
        total_trades = len(trades)

        if total_trades == 0:
            return BacktestResult(
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                avg_win=0.0,
                avg_loss=0.0,
                equity_curve=equity_curve,
                trades=trades,
            )

        winners = [t for t in trades if t.pnl > 0]
        losers = [t for t in trades if t.pnl <= 0]

        winning_trades = len(winners)
        losing_trades = len(losers)
        win_rate = winning_trades / total_trades if total_trades else 0.0

        gross_profit = sum(t.pnl for t in winners) if winners else 0.0
        gross_loss = abs(sum(t.pnl for t in losers)) if losers else 0.0
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        avg_win = gross_profit / winning_trades if winning_trades else 0.0
        avg_loss = gross_loss / losing_trades if losing_trades else 0.0

        # Total return
        final_equity = equity_curve[-1] if equity_curve else self.initial_balance
        total_return = (
            (final_equity - self.initial_balance) / self.initial_balance
        ) * 100

        # Max drawdown
        max_drawdown = self._compute_max_drawdown(equity_curve)

        # Sharpe ratio (annualized, assuming daily bars — adjustable)
        sharpe_ratio = self._compute_sharpe(equity_curve)

        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            avg_win=avg_win,
            avg_loss=avg_loss,
            equity_curve=equity_curve,
            trades=trades,
        )

    @staticmethod
    def _compute_max_drawdown(equity_curve: list[float]) -> float:
        """Maximum drawdown as a percentage."""
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak * 100 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @staticmethod
    def _compute_sharpe(
        equity_curve: list[float], periods_per_year: float = 252.0
    ) -> float:
        """Annualized Sharpe ratio from equity curve returns."""
        if len(equity_curve) < 2:
            return 0.0

        returns = []
        for i in range(1, len(equity_curve)):
            prev = equity_curve[i - 1]
            if prev == 0:
                continue
            returns.append((equity_curve[i] - prev) / prev)

        if not returns:
            return 0.0

        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        std_ret = math.sqrt(variance)

        if std_ret == 0:
            return 0.0

        return (mean_ret / std_ret) * math.sqrt(periods_per_year)
