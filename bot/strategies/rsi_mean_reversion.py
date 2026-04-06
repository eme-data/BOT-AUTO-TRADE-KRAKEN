"""RSI mean-reversion strategy with EMA trend filter."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class RSIMeanReversionStrategy(AbstractStrategy):
    name = "rsi_mean_reversion"
    min_bars = 30

    def __init__(
        self,
        rsi_oversold: float = 28.0,
        rsi_overbought: float = 72.0,
        stop_pct: float = 6.0,
        limit_pct: float = 12.0,
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

        # Major trend filter: don't buy below EMA200
        in_uptrend = close > ema200

        # BUY: RSI below oversold threshold and bouncing up (only in uptrend)
        if rsi_now <= self.rsi_oversold and rsi_now > rsi_prev and in_uptrend:
            confidence = min((self.rsi_oversold - rsi_now) / 20 + 0.4, 1.0)
            signal = Signal(
                signal_type=SignalType.BUY,
                pair=pair,
                direction=Direction.BUY,
                confidence=max(confidence, 0.3),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct,
                take_profit_pct=self.limit_pct,
                metadata={"rsi": rsi_now, "ema_200": ema200, "close": close, "trigger": "rsi_oversold"},
            )

        # SELL: RSI above overbought threshold and turning down
        elif rsi_now >= self.rsi_overbought and rsi_now < rsi_prev:
            confidence = min((rsi_now - self.rsi_overbought) / 20 + 0.4, 1.0)
            signal = Signal(
                signal_type=SignalType.SELL,
                pair=pair,
                direction=Direction.SELL,
                confidence=max(confidence, 0.3),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct,
                take_profit_pct=self.limit_pct,
                metadata={"rsi": rsi_now, "ema_200": ema200, "close": close, "trigger": "rsi_overbought"},
            )

        # BUY: RSI crossing up from extreme oversold (< 25)
        elif rsi_prev < 25 and rsi_now >= 25:
            signal = Signal(
                signal_type=SignalType.BUY,
                pair=pair,
                direction=Direction.BUY,
                confidence=0.7,
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct,
                take_profit_pct=self.limit_pct,
                metadata={"rsi": rsi_now, "ema_200": ema200, "close": close, "trigger": "rsi_extreme_bounce"},
            )

        self._prev_rsi = rsi_now
        return signal

    # ── Multi-timeframe confirmation ─────────────────

    def on_bar_mtf(
        self, pair: str, df_primary: pd.DataFrame, df_higher: pd.DataFrame
    ) -> Signal | None:
        """RSI mean-reversion on H1 confirmed by D1 context.

        Higher-timeframe checks (D1):
        - D1 RSI should be in the 35-65 range (room for mean reversion).
        - Reject BUY if D1 RSI is already deeply oversold (< 25) – double-bottom risk.
        - Reject SELL if D1 RSI is already deeply overbought (> 75) – could still rally.
        - Bollinger Band proximity: favour BUY near lower band, SELL near upper band.
        """
        # Get primary-timeframe signal via existing logic
        signal = self.on_bar(pair, df_primary)
        if signal is None:
            return None

        # Validate higher-timeframe DataFrame
        htf_required = {"rsi", "close"}
        if not htf_required.issubset(df_higher.columns) or df_higher.empty:
            return signal

        htf = df_higher.iloc[-1]
        d1_rsi = htf["rsi"]
        d1_close = htf["close"]

        if pd.isna(d1_rsi) or pd.isna(d1_close):
            return signal

        # ── RSI-based rejection ──
        # Reject BUY when D1 RSI is extremely oversold (double-bottom risk)
        if signal.signal_type == SignalType.BUY and d1_rsi < 25:
            return None
        # Reject SELL when D1 RSI is extremely overbought
        if signal.signal_type == SignalType.SELL and d1_rsi > 75:
            return None

        # ── D1 RSI "room to revert" check ──
        d1_rsi_has_room = 35 <= d1_rsi <= 65

        # ── Bollinger Band proximity (optional columns) ──
        bb_columns = {"bb_upper", "bb_lower"}
        bb_available = bb_columns.issubset(df_higher.columns)
        near_lower_band = False
        near_upper_band = False

        if bb_available:
            bb_upper = htf["bb_upper"]
            bb_lower = htf["bb_lower"]
            if not (pd.isna(bb_upper) or pd.isna(bb_lower)):
                bb_width = bb_upper - bb_lower
                if bb_width > 0:
                    position_in_band = (d1_close - bb_lower) / bb_width
                    near_lower_band = position_in_band < 0.3
                    near_upper_band = position_in_band > 0.7
                    signal.metadata["d1_bb_position"] = round(float(position_in_band), 4)

        # Boost confidence when D1 conditions are favourable
        confidence_boost = 0.0
        if d1_rsi_has_room:
            confidence_boost += 0.10
        if signal.signal_type == SignalType.BUY and near_lower_band:
            confidence_boost += 0.10
        elif signal.signal_type == SignalType.SELL and near_upper_band:
            confidence_boost += 0.10

        signal.confidence = min(signal.confidence + confidence_boost, 1.0)

        # Attach D1 metadata
        signal.metadata["d1_rsi"] = float(d1_rsi)
        signal.metadata["d1_rsi_has_room"] = d1_rsi_has_room
        if bb_available:
            signal.metadata["d1_near_lower_band"] = near_lower_band
            signal.metadata["d1_near_upper_band"] = near_upper_band

        return signal

    def get_config(self) -> dict[str, Any]:
        return {
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "stop_pct": self.stop_pct,
            "limit_pct": self.limit_pct,
        }
