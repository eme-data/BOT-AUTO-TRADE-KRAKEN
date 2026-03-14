"""Data models for AI analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AIVerdict(str, Enum):
    APPROVE = "APPROVE"       # signal confirmed – proceed
    REJECT = "REJECT"         # signal rejected – skip trade
    ADJUST = "ADJUST"         # signal OK but adjust parameters
    INSUFFICIENT = "INSUFFICIENT"  # not enough data to decide


class AnalysisMode(str, Enum):
    PRE_TRADE = "pre_trade"          # validate signal before execution
    MARKET_REVIEW = "market_review"  # periodic market overview
    SENTIMENT = "sentiment"          # news/sentiment analysis
    POST_TRADE = "post_trade"        # review after trade closed


@dataclass
class AIAnalysisRequest:
    mode: AnalysisMode
    pair: str
    signal_direction: str = ""
    signal_strategy: str = ""
    signal_confidence: float = 0.0
    indicators: dict[str, Any] = field(default_factory=dict)
    recent_bars: list[dict[str, float]] = field(default_factory=list)
    open_positions: list[dict[str, Any]] = field(default_factory=list)
    account_balance: float = 0.0
    extra_context: str = ""


@dataclass
class AIAnalysisResult:
    verdict: AIVerdict
    confidence: float  # 0.0 – 1.0
    reasoning: str     # Claude's explanation (shown in dashboard)
    suggested_adjustments: dict[str, Any] = field(default_factory=dict)
    market_summary: str = ""
    risk_warnings: list[str] = field(default_factory=list)
    model_used: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_response: str = ""
