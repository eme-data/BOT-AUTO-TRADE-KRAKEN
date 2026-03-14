"""Autopilot data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class MarketScore:
    pair: str
    trend_score: float = 0.0      # 0-1
    momentum_score: float = 0.0   # 0-1
    volatility_score: float = 0.0 # 0-1
    alignment_score: float = 0.0  # 0-1
    sentiment_score: float = 0.5  # 0-1 (Polymarket, 0.5 = neutral)
    composite: float = 0.0        # weighted average
    regime: str = "ranging"       # trending / ranging / volatile
    direction_bias: str = "neutral"  # bullish / bearish / neutral
    recommended_strategy: str = ""
    scored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ScanResult:
    pair: str
    base: str
    quote: str
    volume_24h: float = 0.0
    tradeable: bool = True
