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
