"""Fetch and cache historical OHLCV data."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import structlog

from bot.broker.kraken_rest import KrakenRestClient
from bot.broker.models import OHLCV

logger = structlog.get_logger(__name__)


class HistoricalDataManager:
    """Fetches and maintains rolling OHLCV windows per pair/timeframe."""

    def __init__(self, broker: KrakenRestClient) -> None:
        self._broker = broker
        # cache: (pair, interval_min) -> DataFrame
        self._cache: dict[tuple[str, int], pd.DataFrame] = {}

    async def get_bars(
        self,
        pair: str,
        interval_minutes: int = 60,
        count: int = 250,
    ) -> pd.DataFrame:
        """Return a DataFrame with columns: open, high, low, close, volume."""
        key = (pair, interval_minutes)

        candles = await self._broker.get_historical_prices(
            pair=pair,
            interval_minutes=interval_minutes,
            limit=count,
        )

        if not candles:
            logger.warning("no_candles", pair=pair, interval=interval_minutes)
            return self._cache.get(key, pd.DataFrame())

        df = self._candles_to_df(candles)
        self._cache[key] = df
        logger.debug(
            "bars_fetched",
            pair=pair,
            interval=interval_minutes,
            rows=len(df),
        )
        return df

    def get_cached(
        self, pair: str, interval_minutes: int = 60
    ) -> pd.DataFrame | None:
        return self._cache.get((pair, interval_minutes))

    def clear_cache(self) -> None:
        self._cache.clear()

    @staticmethod
    def _candles_to_df(candles: list[OHLCV]) -> pd.DataFrame:
        data = [
            {
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df
