"""MACD trend-following strategy for crypto."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class MACDTrendStrategy(AbstractStrategy):
    name = "macd_trend"
    min_bars = 100

    def __init__(
        self,
        atr_stop_multiplier: float = 2.0,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        self.atr_stop_multiplier = atr_stop_multiplier
        self.risk_reward_ratio = risk_reward_ratio
        self._last_histogram: float | None = None

    def on_tick(self, tick: Tick) -> Signal | None:
        # MACD is a bar-based strategy; ticks are ignored
        return None

    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        required = {"macd", "macd_signal", "macd_histogram", "atr", "close"}
        if not required.issubset(df.columns):
            return None
        if len(df) < self.min_bars:
            return None

        cur = df.iloc[-1]
        prev = df.iloc[-2]

        macd_now = cur["macd_histogram"]
        macd_prev = prev["macd_histogram"]

        if pd.isna(macd_now) or pd.isna(macd_prev):
            return None

        atr = cur["atr"]
        close = cur["close"]

        if pd.isna(atr) or atr == 0 or close == 0:
            return None

        stop_pct = (atr * self.atr_stop_multiplier / close) * 100
        limit_pct = stop_pct * self.risk_reward_ratio

        # Confidence: normalized histogram magnitude relative to ATR
        confidence = min(abs(macd_now) / atr, 1.0)

        signal: Signal | None = None

        # Bullish crossover: histogram goes from negative to positive
        if macd_prev < 0 and macd_now >= 0:
            signal = Signal(
                signal_type=SignalType.BUY,
                pair=pair,
                direction=Direction.BUY,
                confidence=confidence,
                strategy_name=self.name,
                stop_loss_pct=stop_pct,
                take_profit_pct=limit_pct,
                metadata={
                    "macd_histogram": macd_now,
                    "atr": atr,
                    "close": close,
                },
            )

        # Bearish crossover: histogram goes from positive to negative
        elif macd_prev > 0 and macd_now <= 0:
            signal = Signal(
                signal_type=SignalType.SELL,
                pair=pair,
                direction=Direction.SELL,
                confidence=confidence,
                strategy_name=self.name,
                stop_loss_pct=stop_pct,
                take_profit_pct=limit_pct,
                metadata={
                    "macd_histogram": macd_now,
                    "atr": atr,
                    "close": close,
                },
            )

        self._last_histogram = macd_now
        return signal

    def get_config(self) -> dict[str, Any]:
        return {
            "atr_stop_multiplier": self.atr_stop_multiplier,
            "risk_reward_ratio": self.risk_reward_ratio,
        }
