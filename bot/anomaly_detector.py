"""Market anomaly detector - flash crashes, volume spikes, spread anomalies."""

from __future__ import annotations

import structlog
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class Anomaly:
    type: str  # flash_crash, flash_pump, volume_spike, spread_warning
    pair: str
    severity: str  # low, medium, high, critical
    message: str
    value: float
    threshold: float


class AnomalyDetector:
    """Detects market anomalies from OHLCV data."""

    def __init__(
        self,
        flash_crash_pct: float = 0.05,
        volume_spike_mult: float = 5.0,
        spread_warn_pct: float = 0.02,
    ):
        self.flash_crash_pct = flash_crash_pct
        self.volume_spike_mult = volume_spike_mult
        self.spread_warn_pct = spread_warn_pct

    def check(self, pair: str, bars) -> list[Anomaly]:
        """Check latest bars for anomalies. bars is a DataFrame with OHLCV columns."""
        anomalies: list[Anomaly] = []
        if bars is None or len(bars) < 2:
            return anomalies

        latest = bars.iloc[-1]
        prev = bars.iloc[-2]

        # Flash crash / pump detection
        if prev["close"] > 0:
            change_pct = (latest["close"] - prev["close"]) / prev["close"]
            if abs(change_pct) >= self.flash_crash_pct:
                direction = "crash" if change_pct < 0 else "pump"
                severity = "critical" if abs(change_pct) >= self.flash_crash_pct * 2 else "high"
                anomalies.append(Anomaly(
                    type=f"flash_{direction}",
                    pair=pair,
                    severity=severity,
                    message=f"Flash {direction}: {change_pct:+.2%} in one bar",
                    value=abs(change_pct),
                    threshold=self.flash_crash_pct,
                ))

        # Volume spike detection
        if "volume" in bars.columns and len(bars) >= 20:
            avg_vol = bars["volume"].iloc[-21:-1].mean()
            if avg_vol > 0:
                vol_ratio = latest["volume"] / avg_vol
                if vol_ratio >= self.volume_spike_mult:
                    severity = "high" if vol_ratio >= self.volume_spike_mult * 2 else "medium"
                    anomalies.append(Anomaly(
                        type="volume_spike",
                        pair=pair,
                        severity=severity,
                        message=f"Volume spike: {vol_ratio:.1f}x average",
                        value=vol_ratio,
                        threshold=self.volume_spike_mult,
                    ))

        # Spread / wick detection
        if latest["high"] > 0:
            wick_pct = (latest["high"] - latest["low"]) / latest["high"]
            if wick_pct >= self.spread_warn_pct:
                severity = "medium" if wick_pct < self.spread_warn_pct * 2 else "high"
                anomalies.append(Anomaly(
                    type="spread_warning",
                    pair=pair,
                    severity=severity,
                    message=f"High volatility: {wick_pct:.2%} range",
                    value=wick_pct,
                    threshold=self.spread_warn_pct,
                ))

        return anomalies
