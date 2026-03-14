"""Abstract base class for all trading strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd

from bot.broker.models import Direction, Tick


class SignalType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Signal:
    signal_type: SignalType
    pair: str
    direction: Direction
    confidence: float  # 0.0 – 1.0
    strategy_name: str
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    size: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class AbstractStrategy(ABC):
    """All strategies must implement on_tick and on_bar."""

    name: str = "base"
    min_bars: int = 50

    @abstractmethod
    def on_tick(self, tick: Tick) -> Signal | None:
        """React to a real-time price tick."""

    @abstractmethod
    def on_bar(self, pair: str, df: pd.DataFrame) -> Signal | None:
        """React to a new completed bar with indicators."""

    @abstractmethod
    def get_config(self) -> dict[str, Any]:
        """Return current strategy parameters."""

    def reset(self) -> None:
        """Reset internal state (e.g. between pairs)."""
