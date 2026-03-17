"""MACD trend-following strategy for crypto."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class MACDTrendStrategy(AbstractStrategy):
    name = "macd_trend"
    min_bars = 30

    def __init__(
        self,
        atr_stop_multiplier: float = 1.5,
        risk_reward_ratio: float = 2.0,
    ) -> None:
        self.atr_stop_multiplier = atr_stop_multiplier
        self.risk_reward_ratio = risk_reward_ratio
        self._last_histogram: float | None = None

    def on_tick(self, tick: Tick) -> Signal | None:
        return None

    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        required = {"macd", "macd_signal", "macd_histogram", "atr", "close"}
        if not required.issubset(df.columns):
            return None
        if len(df) < self.min_bars:
            return None

        cur = df.iloc[-1]
        prev = df.iloc[-2]
        prev2 = df.iloc[-3] if len(df) >= 3 else prev

        macd_now = cur["macd_histogram"]
        macd_prev = prev["macd_histogram"]
        macd_prev2 = prev2["macd_histogram"]

        if pd.isna(macd_now) or pd.isna(macd_prev):
            return None

        atr = cur["atr"]
        close = cur["close"]

        if pd.isna(atr) or atr == 0 or close == 0:
            return None

        stop_pct = (atr * self.atr_stop_multiplier / close) * 100
        limit_pct = stop_pct * self.risk_reward_ratio
        confidence = min(abs(macd_now) / atr, 1.0)

        signal: Signal | None = None

        # --- Signal 1: Classic crossover (histogram changes sign) ---
        if macd_prev < 0 and macd_now >= 0:
            signal = self._make_signal(pair, SignalType.BUY, Direction.BUY,
                                       confidence, stop_pct, limit_pct, macd_now, atr, close, "crossover")
        elif macd_prev > 0 and macd_now <= 0:
            signal = self._make_signal(pair, SignalType.SELL, Direction.SELL,
                                       confidence, stop_pct, limit_pct, macd_now, atr, close, "crossover")

        # --- Signal 2: Momentum acceleration (histogram expanding in same direction) ---
        if signal is None and not pd.isna(macd_prev2):
            # Bullish momentum: histogram negative but accelerating upward (3 bars)
            if macd_now < 0 and macd_now > macd_prev > macd_prev2:
                confidence_mom = min(abs(macd_now - macd_prev) / atr, 0.8)
                if confidence_mom >= 0.2:
                    signal = self._make_signal(pair, SignalType.BUY, Direction.BUY,
                                               confidence_mom, stop_pct, limit_pct, macd_now, atr, close, "momentum")
            # Bearish momentum: histogram positive but decelerating downward
            elif macd_now > 0 and macd_now < macd_prev < macd_prev2:
                confidence_mom = min(abs(macd_prev - macd_now) / atr, 0.8)
                if confidence_mom >= 0.2:
                    signal = self._make_signal(pair, SignalType.SELL, Direction.SELL,
                                               confidence_mom, stop_pct, limit_pct, macd_now, atr, close, "momentum")

        # --- Signal 3: Strong MACD divergence from signal line ---
        if signal is None:
            macd_line = cur["macd"]
            macd_signal_line = cur["macd_signal"]
            if not pd.isna(macd_line) and not pd.isna(macd_signal_line):
                divergence = abs(macd_line - macd_signal_line) / atr
                if divergence > 0.5:
                    if macd_line > macd_signal_line and macd_now > 0:
                        signal = self._make_signal(pair, SignalType.BUY, Direction.BUY,
                                                   min(divergence, 1.0), stop_pct, limit_pct, macd_now, atr, close, "divergence")
                    elif macd_line < macd_signal_line and macd_now < 0:
                        signal = self._make_signal(pair, SignalType.SELL, Direction.SELL,
                                                   min(divergence, 1.0), stop_pct, limit_pct, macd_now, atr, close, "divergence")

        self._last_histogram = macd_now
        return signal

    def _make_signal(self, pair, signal_type, direction, confidence, stop_pct, limit_pct,
                     macd_hist, atr, close, trigger):
        return Signal(
            signal_type=signal_type,
            pair=pair,
            direction=direction,
            confidence=confidence,
            strategy_name=self.name,
            stop_loss_pct=stop_pct,
            take_profit_pct=limit_pct,
            metadata={"macd_histogram": macd_hist, "atr": atr, "close": close, "trigger": trigger},
        )

    # ── Multi-timeframe confirmation ─────────────────

    def on_bar_mtf(
        self, pair: str, df_primary: pd.DataFrame, df_higher: pd.DataFrame
    ) -> Signal | None:
        """MACD crossover on H1 confirmed by D1 trend direction.

        Higher-timeframe checks (D1):
        - EMA alignment: ema_20 vs ema_50 determines trend direction.
        - ADX filter: ADX > 20 indicates a trending market.
        - BUY signals require D1 bullish (ema_20 > ema_50 OR close > ema_50).
        - SELL signals require D1 bearish (ema_20 < ema_50 OR close < ema_50).
        - Confidence boosted by 0.15 when D1 trend agrees.
        """
        # Get primary-timeframe signal via existing logic
        signal = self.on_bar(pair, df_primary)
        if signal is None:
            return None

        # Validate higher-timeframe DataFrame
        htf_required = {"close", "ema_20", "ema_50"}
        if not htf_required.issubset(df_higher.columns) or df_higher.empty:
            # Cannot confirm – return primary signal as-is
            return signal

        htf = df_higher.iloc[-1]
        htf_close = htf["close"]
        htf_ema20 = htf.get("ema_20")
        htf_ema50 = htf.get("ema_50")

        if pd.isna(htf_ema20) or pd.isna(htf_ema50) or pd.isna(htf_close):
            return signal

        d1_bullish = htf_ema20 > htf_ema50 or htf_close > htf_ema50
        d1_bearish = htf_ema20 < htf_ema50 or htf_close < htf_ema50

        # Filter: reject signals that conflict with higher-timeframe trend
        if signal.signal_type == SignalType.BUY and not d1_bullish:
            return None
        if signal.signal_type == SignalType.SELL and not d1_bearish:
            return None

        # Boost confidence when D1 trend agrees
        boosted = min(signal.confidence + 0.15, 1.0)

        # Check ADX for trend strength (optional column)
        htf_adx = htf.get("adx") if "adx" in df_higher.columns else None
        d1_trending = htf_adx is not None and not pd.isna(htf_adx) and htf_adx > 20

        signal.confidence = boosted
        signal.metadata["d1_ema20"] = float(htf_ema20)
        signal.metadata["d1_ema50"] = float(htf_ema50)
        signal.metadata["d1_close"] = float(htf_close)
        signal.metadata["d1_bullish"] = d1_bullish
        signal.metadata["d1_bearish"] = d1_bearish
        if htf_adx is not None and not pd.isna(htf_adx):
            signal.metadata["d1_adx"] = float(htf_adx)
            signal.metadata["d1_trending"] = d1_trending

        return signal

    def get_config(self) -> dict[str, Any]:
        return {
            "atr_stop_multiplier": self.atr_stop_multiplier,
            "risk_reward_ratio": self.risk_reward_ratio,
        }
