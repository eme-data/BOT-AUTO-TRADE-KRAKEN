"""Simple trend-following strategy — buys when price is above rising EMA20."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class TrendFollowerStrategy(AbstractStrategy):
    name = "trend_follower"
    min_bars = 25

    def __init__(
        self,
        stop_pct: float = 6.0,
        limit_pct: float = 8.0,
    ) -> None:
        self.stop_pct = stop_pct
        self.limit_pct = limit_pct

    def on_tick(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        if len(df) < self.min_bars:
            return None

        cur = df.iloc[-1]
        prev = df.iloc[-2]
        close = cur.get("close", 0)

        if close == 0 or pd.isna(close):
            return None

        ema20 = cur.get("ema_20")
        prev_ema20 = prev.get("ema_20")
        ema200 = cur.get("ema_200")
        rsi = cur.get("rsi_14") or cur.get("rsi")

        if any(v is None or pd.isna(v) for v in [ema20, prev_ema20]):
            return None

        ema_rising = ema20 > prev_ema20
        price_above_ema = close > ema20
        price_below_ema = close < ema20

        # Major trend filter: don't buy below EMA200 (bearish territory)
        in_uptrend = ema200 is None or pd.isna(ema200) or close > ema200

        # Avoid overbought/oversold extremes
        rsi_ok_buy = rsi is None or pd.isna(rsi) or rsi < 72
        rsi_ok_sell = rsi is None or pd.isna(rsi) or rsi > 28

        # BUY: price above rising EMA20 + above EMA200 + not overbought
        if price_above_ema and ema_rising and rsi_ok_buy and in_uptrend:
            # Check that price just crossed above or is near EMA (within 1%)
            dist_pct = (close - ema20) / ema20
            if dist_pct < 0.01:  # Within 1% of EMA — fresh crossover only
                return Signal(
                    signal_type=SignalType.BUY,
                    pair=pair,
                    direction=Direction.BUY,
                    confidence=min(0.5 + dist_pct * 10, 0.8),
                    strategy_name=self.name,
                    stop_loss_pct=self.stop_pct,
                    take_profit_pct=self.limit_pct,
                    metadata={"trigger": "trend_follow_buy", "ema20": ema20, "dist_pct": dist_pct, "close": close},
                )

        # SELL signal — only if we own the asset (handled by _process_signal)
        if price_below_ema and not ema_rising and rsi_ok_sell:
            dist_pct = (ema20 - close) / ema20
            if dist_pct < 0.015:
                return Signal(
                    signal_type=SignalType.SELL,
                    pair=pair,
                    direction=Direction.SELL,
                    confidence=min(0.5 + dist_pct * 10, 0.8),
                    strategy_name=self.name,
                    stop_loss_pct=self.stop_pct,
                    take_profit_pct=self.limit_pct,
                    metadata={"trigger": "trend_follow_sell", "ema20": ema20, "dist_pct": dist_pct, "close": close},
                )

        return None

    def on_bar_mtf(self, pair, df_primary, df_higher) -> Signal | None:
        return self.on_bar(pair, df_primary)

    def get_config(self) -> dict[str, Any]:
        return {
            "stop_pct": self.stop_pct,
            "limit_pct": self.limit_pct,
        }
