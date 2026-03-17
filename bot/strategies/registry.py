"""Strategy registry – manages active strategies and dispatches ticks/bars."""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog

from bot.broker.models import Tick
from bot.strategies.base import AbstractStrategy, Signal
from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from bot.strategies.scalper import ScalperStrategy

logger = structlog.get_logger(__name__)

# Built-in strategy classes
STRATEGY_CLASSES: dict[str, type[AbstractStrategy]] = {
    "macd_trend": MACDTrendStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
    "scalper": ScalperStrategy,
}


class StrategyRegistry:
    """Holds enabled strategies and dispatches market events to them."""

    def __init__(self) -> None:
        self._strategies: dict[str, AbstractStrategy] = {}

    @property
    def strategies(self) -> dict[str, AbstractStrategy]:
        return dict(self._strategies)

    def register(self, key: str, strategy: AbstractStrategy) -> None:
        self._strategies[key] = strategy
        logger.info("strategy_registered", key=key, name=strategy.name)

    def unregister(self, key: str) -> None:
        if key in self._strategies:
            del self._strategies[key]
            logger.info("strategy_unregistered", key=key)

    def create_strategy(
        self, name: str, config: dict[str, Any] | None = None
    ) -> AbstractStrategy:
        cls = STRATEGY_CLASSES.get(name)
        if cls is None:
            raise ValueError(f"Unknown strategy: {name}")
        return cls(**(config or {}))

    def dispatch_tick(self, tick: Tick) -> list[Signal]:
        signals: list[Signal] = []
        for key, strategy in self._strategies.items():
            try:
                sig = strategy.on_tick(tick)
                if sig:
                    signals.append(sig)
            except Exception as exc:
                logger.error(
                    "strategy_tick_error", key=key, error=str(exc)
                )
        return signals

    def dispatch_bar(self, pair: str, df: pd.DataFrame) -> list[Signal]:
        signals: list[Signal] = []
        for key, strategy in self._strategies.items():
            try:
                sig = strategy.on_bar(pair, df)
                if sig:
                    signals.append(sig)
            except Exception as exc:
                logger.error(
                    "strategy_bar_error", key=key, error=str(exc)
                )
        return signals

    def dispatch_bar_mtf(
        self, pair: str, df_primary: pd.DataFrame, df_higher: pd.DataFrame
    ) -> list[Signal]:
        """Dispatch bars with multi-timeframe context to all strategies."""
        signals: list[Signal] = []
        for key, strategy in self._strategies.items():
            try:
                sig = strategy.on_bar_mtf(pair, df_primary, df_higher)
                if sig:
                    signals.append(sig)
            except Exception as exc:
                logger.error(
                    "strategy_bar_mtf_error", key=key, error=str(exc)
                )
        return signals

    def load_defaults(self) -> None:
        """Load default strategies with default config."""
        self.register("macd_trend", MACDTrendStrategy())
        self.register("rsi_mean_reversion", RSIMeanReversionStrategy())
        self.register("scalper", ScalperStrategy())
