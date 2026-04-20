"""Funding-rate divergence contrarian strategy.

Thesis: extremely negative Binance perpetual funding = crowded shorts paying
longs on leverage = fragile positioning that unwinds into spot rallies.
We fade the crowd by going long spot when funding hits its recent extreme.

Signal logic (long-only, spot):
  - current funding_rate < 0 (shorts are paying)
  - current funding_rate is at or below the lookback_window percentile
    of the last ``lookback_bars`` bars
  - confidence scales with how far below the percentile the current rate sits

Exit is handled by the outer engine via stop-loss / take-profit. We choose
stops wider than our TP because funding reversals can take 12-48 h and the
initial dip often overshoots before reversing.

Inputs: the DataFrame passed to ``on_bar`` must contain a ``funding_rate``
column. The backtest harness merges Binance funding history onto the price
bars before running; live mode relies on a periodic fetch loop in
``UserBotContext`` (see the runtime integration TODO).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class FundingDivergenceStrategy(AbstractStrategy):
    name = "funding_divergence"
    min_bars = 90  # need enough history to compute a stable percentile

    def __init__(
        self,
        lookback_bars: int = 60 * 24,  # 60 days on 1h bars
        percentile: float = 0.20,  # bottom 20% — extreme-ish negative funding
        abs_threshold: float = -3e-5,  # per-8h rate (~-3.3% annualized) minimum
        stop_loss_pct: float = 7.0,
        take_profit_pct: float = 5.0,
        min_confirm_bars: int = 1,  # single-bar trigger (funding updates every 8h)
    ) -> None:
        self.lookback_bars = lookback_bars
        self.percentile = percentile
        self.abs_threshold = abs_threshold
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.min_confirm_bars = min_confirm_bars
        self._last_signal_bar: dict[str, int] = {}  # pair -> last signaled index

    def on_tick(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_bars:
            return None
        if "funding_rate" not in df.columns:
            return None

        cur = df.iloc[-1]
        current_funding = cur.get("funding_rate")
        close = cur.get("close", 0)
        if current_funding is None or pd.isna(current_funding) or close <= 0:
            return None

        # Must be genuinely negative and below the absolute floor
        if current_funding >= self.abs_threshold:
            return None

        # Compute percentile over the lookback window
        lookback = df["funding_rate"].dropna().tail(self.lookback_bars)
        if len(lookback) < max(30, self.min_bars // 2):
            return None
        threshold = lookback.quantile(self.percentile)
        if pd.isna(threshold):
            return None
        if current_funding > threshold:
            return None  # not extreme enough vs recent history

        # Confirmation: funding must have stayed in the extreme zone
        recent = df["funding_rate"].tail(self.min_confirm_bars).dropna()
        if len(recent) < self.min_confirm_bars:
            return None
        if not (recent <= threshold).all():
            return None

        # Debounce: don't re-enter on consecutive bars
        last_idx = self._last_signal_bar.get(pair, -(10**9))
        current_idx = len(df) - 1
        if current_idx - last_idx < 8:  # minimum 8 bars between signals
            return None

        # Confidence scales with depth below percentile (capped)
        denom = abs(threshold) if threshold else 1e-6
        depth_ratio = min((threshold - current_funding) / max(denom, 1e-6), 3.0)
        confidence = float(min(0.55 + 0.10 * depth_ratio, 0.90))

        self._last_signal_bar[pair] = current_idx

        return Signal(
            signal_type=SignalType.BUY,
            pair=pair,
            direction=Direction.BUY,
            confidence=confidence,
            strategy_name=self.name,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pct=self.take_profit_pct,
            metadata={
                "trigger": "funding_extreme_negative",
                "funding_rate": float(current_funding),
                "percentile_threshold": float(threshold),
                "lookback_bars": int(len(lookback)),
                "close": float(close),
            },
        )

    def on_bar_mtf(
        self, pair: str, df_primary: pd.DataFrame, df_higher: pd.DataFrame
    ) -> Signal | None:
        return self.on_bar(pair, df_primary)

    def get_config(self) -> dict[str, Any]:
        return {
            "lookback_bars": self.lookback_bars,
            "percentile": self.percentile,
            "abs_threshold": self.abs_threshold,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "min_confirm_bars": self.min_confirm_bars,
        }

    def reset(self) -> None:
        self._last_signal_bar.clear()
