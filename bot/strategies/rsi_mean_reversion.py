"""RSI mean-reversion strategy with EMA trend filter."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class RSIMeanReversionStrategy(AbstractStrategy):
    name = "rsi_mean_reversion"
    min_bars = 250  # needs 200-EMA warmup

    def __init__(
        self,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        stop_pct: float = 2.5,
        limit_pct: float = 5.0,
    ) -> None:
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.stop_pct = stop_pct
        self.limit_pct = limit_pct
        self._prev_rsi: float | None = None

    def on_tick(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        required = {"rsi", "ema_200", "close"}
        if not required.issubset(df.columns):
            return None
        if len(df) < self.min_bars:
            return None

        cur = df.iloc[-1]
        prev = df.iloc[-2]

        rsi_now = cur["rsi"]
        rsi_prev = prev["rsi"]
        close = cur["close"]
        ema200 = cur["ema_200"]

        if pd.isna(rsi_now) or pd.isna(rsi_prev) or pd.isna(ema200):
            return None

        confidence = 0.0
        signal: Signal | None = None

        # BUY: RSI crosses UP through oversold, price above 200-EMA (trend filter)
        if rsi_prev <= self.rsi_oversold < rsi_now and close > ema200:
            confidence = min((self.rsi_oversold - rsi_prev) / self.rsi_oversold, 1.0)
            signal = Signal(
                signal_type=SignalType.BUY,
                pair=pair,
                direction=Direction.BUY,
                confidence=max(confidence, 0.3),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct,
                take_profit_pct=self.limit_pct,
                metadata={"rsi": rsi_now, "ema_200": ema200, "close": close},
            )

        # SELL: RSI crosses DOWN through overbought, price below 200-EMA
        elif rsi_prev >= self.rsi_overbought > rsi_now and close < ema200:
            confidence = min(
                (rsi_prev - self.rsi_overbought) / (100 - self.rsi_overbought), 1.0
            )
            signal = Signal(
                signal_type=SignalType.SELL,
                pair=pair,
                direction=Direction.SELL,
                confidence=max(confidence, 0.3),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct,
                take_profit_pct=self.limit_pct,
                metadata={"rsi": rsi_now, "ema_200": ema200, "close": close},
            )

        self._prev_rsi = rsi_now
        return signal

    def get_config(self) -> dict[str, Any]:
        return {
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "stop_pct": self.stop_pct,
            "limit_pct": self.limit_pct,
        }
