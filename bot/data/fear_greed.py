"""Crypto Fear & Greed Index client."""

from __future__ import annotations

import time
from dataclasses import dataclass

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1&format=json"


@dataclass
class FearGreedData:
    """Fear & Greed Index data."""
    value: int  # 0-100 (0=extreme fear, 100=extreme greed)
    label: str  # "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"
    timestamp: int

    @property
    def normalized(self) -> float:
        """Normalize to 0-1 scale for scoring."""
        return self.value / 100.0

    @property
    def is_extreme_fear(self) -> bool:
        return self.value <= 10

    @property
    def is_fear(self) -> bool:
        return self.value <= 30

    @property
    def is_greed(self) -> bool:
        return self.value >= 60

    @property
    def is_extreme_greed(self) -> bool:
        return self.value >= 75


class FearGreedClient:
    """Fetch Crypto Fear & Greed Index."""

    def __init__(self, cache_ttl: int = 900) -> None:
        self._cache_ttl = cache_ttl
        self._cached: FearGreedData | None = None
        self._cached_at: float = 0

    async def get_index(self) -> FearGreedData:
        """Get current Fear & Greed Index."""
        if self._cached and (time.time() - self._cached_at) < self._cache_ttl:
            return self._cached

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(FEAR_GREED_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.warning("fear_greed_api_error", status=resp.status)
                        return self._cached or FearGreedData(value=50, label="Neutral", timestamp=0)

                    data = await resp.json()
                    item = data.get("data", [{}])[0]
                    result = FearGreedData(
                        value=int(item.get("value", 50)),
                        label=item.get("value_classification", "Neutral"),
                        timestamp=int(item.get("timestamp", 0)),
                    )
                    self._cached = result
                    self._cached_at = time.time()
                    logger.info("fear_greed_fetched", value=result.value, label=result.label)
                    return result

        except Exception as exc:
            logger.warning("fear_greed_error", error=str(exc))
            return self._cached or FearGreedData(value=50, label="Neutral", timestamp=0)
