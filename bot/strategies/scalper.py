"""Aggressive scalping strategy — short-term momentum + volatility breakouts."""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick
from bot.strategies.base import AbstractStrategy, Signal, SignalType


class ScalperStrategy(AbstractStrategy):
    name = "scalper"
    min_bars = 20

    def __init__(
        self,
        bb_squeeze_threshold: float = 0.02,
        volume_spike_mult: float = 1.5,
        stop_pct: float = 4.0,
        limit_pct: float = 5.0,
    ) -> None:
        self.bb_squeeze_threshold = bb_squeeze_threshold
        self.volume_spike_mult = volume_spike_mult
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

        # Trend context
        ema200 = cur.get("ema_200")
        in_uptrend = ema200 is None or pd.isna(ema200) or close > ema200
        rsi = cur.get("rsi_14") or cur.get("rsi")
        is_oversold = rsi is not None and not pd.isna(rsi) and rsi < 30

        signal: Signal | None = None

        # --- Signal 1: Bollinger Band bounce (works in any trend for oversold) ---
        if in_uptrend or is_oversold:
            signal = signal or self._bb_breakout(pair, df, cur, prev, close)

        # --- Signal 2: EMA fast cross (5/13) — only in uptrend ---
        if in_uptrend:
            signal = signal or self._ema_cross(pair, df, cur, prev, close)

        # --- Signal 3: Volume spike + momentum ---
        if in_uptrend or is_oversold:
            signal = signal or self._volume_momentum(pair, df, cur, prev, close)

        # --- Signal 4: Consecutive candles in same direction ---
        if in_uptrend:
            signal = signal or self._candle_streak(pair, df, close)

        # --- Signal 5: RSI extreme oversold bounce (any trend) ---
        if is_oversold and signal is None:
            signal = self._rsi_bounce(pair, df, cur, prev, close, rsi)

        return signal

    def _bb_breakout(self, pair, df, cur, prev, close) -> Signal | None:
        """Buy when price breaks above upper BB, sell below lower BB."""
        bb_upper = cur.get("bb_upper")
        bb_lower = cur.get("bb_lower")
        bb_mid = cur.get("bb_middle") or cur.get("sma_20")

        if bb_upper is None or bb_lower is None or pd.isna(bb_upper) or pd.isna(bb_lower):
            return None

        bb_width = (bb_upper - bb_lower) / close if close > 0 else 0

        # Breakout from squeeze (narrow bands)
        if bb_width < self.bb_squeeze_threshold:
            return None  # Wait for breakout

        if close > bb_upper:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=min(0.5 + bb_width * 10, 0.9),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "bb_breakout_up", "bb_width": bb_width, "close": close},
            )
        elif close < bb_lower:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=min(0.5 + bb_width * 10, 0.9),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "bb_bounce_lower", "bb_width": bb_width, "close": close},
            )
        return None

    def _ema_cross(self, pair, df, cur, prev, close) -> Signal | None:
        """Fast EMA crossover (5 over 13)."""
        ema5 = cur.get("ema_5")
        ema13 = cur.get("ema_13")
        prev_ema5 = prev.get("ema_5")
        prev_ema13 = prev.get("ema_13")

        if any(v is None or pd.isna(v) for v in [ema5, ema13, prev_ema5, prev_ema13]):
            return None

        # Bullish cross: EMA5 crosses above EMA13
        if prev_ema5 <= prev_ema13 and ema5 > ema13:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=0.6,
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "ema_cross_bull", "ema5": ema5, "ema13": ema13, "close": close},
            )
        # Bearish cross
        elif prev_ema5 >= prev_ema13 and ema5 < ema13:
            return Signal(
                signal_type=SignalType.SELL, pair=pair, direction=Direction.SELL,
                confidence=0.6,
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "ema_cross_bear", "ema5": ema5, "ema13": ema13, "close": close},
            )
        return None

    def _volume_momentum(self, pair, df, cur, prev, close) -> Signal | None:
        """Volume spike + price momentum."""
        vol = cur.get("volume")
        if vol is None or pd.isna(vol) or len(df) < 20:
            return None

        avg_vol = df["volume"].iloc[-21:-1].mean()
        if avg_vol == 0 or pd.isna(avg_vol):
            return None

        vol_ratio = vol / avg_vol
        if vol_ratio < self.volume_spike_mult:
            return None

        prev_close = prev.get("close", 0)
        if prev_close == 0:
            return None

        change_pct = (close - prev_close) / prev_close

        if change_pct > 0.005 and vol_ratio >= self.volume_spike_mult:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=min(0.4 + vol_ratio * 0.1, 0.9),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "volume_momentum_up", "vol_ratio": vol_ratio, "change_pct": change_pct, "close": close},
            )
        elif change_pct < -0.005 and vol_ratio >= self.volume_spike_mult:
            return Signal(
                signal_type=SignalType.SELL, pair=pair, direction=Direction.SELL,
                confidence=min(0.4 + vol_ratio * 0.1, 0.9),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "volume_momentum_down", "vol_ratio": vol_ratio, "change_pct": change_pct, "close": close},
            )
        return None

    def _candle_streak(self, pair, df, close) -> Signal | None:
        """3 consecutive bullish/bearish candles = momentum trade."""
        if len(df) < 4:
            return None

        last3 = df.iloc[-3:]
        bullish = all(last3["close"].values[i] > last3["open"].values[i] for i in range(3))
        bearish = all(last3["close"].values[i] < last3["open"].values[i] for i in range(3))

        if not bullish and not bearish:
            return None

        # Check streak strength (total % move)
        streak_pct = abs(last3["close"].iloc[-1] - last3["open"].iloc[0]) / last3["open"].iloc[0]
        if streak_pct < 0.003:  # At least 0.3% move
            return None

        if bullish:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=min(0.5 + streak_pct * 20, 0.85),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "candle_streak_bull", "streak_pct": streak_pct, "close": close},
            )
        else:
            return Signal(
                signal_type=SignalType.SELL, pair=pair, direction=Direction.SELL,
                confidence=min(0.5 + streak_pct * 20, 0.85),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "candle_streak_bear", "streak_pct": streak_pct, "close": close},
            )

    def _rsi_bounce(self, pair, df, cur, prev, close, rsi) -> Signal | None:
        """Buy on RSI extreme oversold bounce — works in any market regime."""
        prev_rsi = prev.get("rsi_14") or prev.get("rsi")
        if prev_rsi is None or pd.isna(prev_rsi):
            return None
        # RSI was below 30 and is now bouncing up
        if rsi > prev_rsi and rsi < 35:
            return Signal(
                signal_type=SignalType.BUY, pair=pair, direction=Direction.BUY,
                confidence=min(0.5 + (30 - rsi) * 0.05, 0.85),
                strategy_name=self.name,
                stop_loss_pct=self.stop_pct, take_profit_pct=self.limit_pct,
                metadata={"trigger": "rsi_oversold_bounce", "rsi": rsi, "close": close},
            )
        return None

    def on_bar_mtf(self, pair, df_primary, df_higher) -> Signal | None:
        # Scalper doesn't use higher timeframe — speed is key
        return self.on_bar(pair, df_primary)

    def get_config(self) -> dict[str, Any]:
        return {
            "bb_squeeze_threshold": self.bb_squeeze_threshold,
            "volume_spike_mult": self.volume_spike_mult,
            "stop_pct": self.stop_pct,
            "limit_pct": self.limit_pct,
        }
