"""Kraken API rate limiter using a token bucket algorithm."""

from __future__ import annotations

import asyncio
import time

import structlog

logger = structlog.get_logger(__name__)


class KrakenRateLimiter:
    """Kraken API rate limiter using token bucket algorithm.

    Kraken rules:
    - REST API: 15 tokens max, 1 token per second recovery
    - Matching engine: 60 tokens max for orders
    - Different endpoints cost different tokens (1 for public, 1-2 for private)
    """

    def __init__(
        self, max_tokens: int = 15, refill_rate: float = 1.0
    ) -> None:
        """Initialise the rate limiter.

        Args:
            max_tokens: Maximum number of tokens in the bucket.
            refill_rate: Tokens added per second.
        """
        self.max_tokens = max_tokens
        self.tokens: float = float(max_tokens)
        self.refill_rate = refill_rate
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(
            self.max_tokens, self.tokens + elapsed * self.refill_rate
        )
        self._last_refill = now

    async def acquire(self, cost: int = 1) -> None:
        """Wait until tokens are available, then consume.

        Args:
            cost: Number of tokens to consume.
        """
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                # Calculate how long to wait for enough tokens
                deficit = cost - self.tokens
                wait_time = deficit / self.refill_rate

            logger.debug(
                "rate_limiter_waiting",
                wait_seconds=round(wait_time, 2),
                tokens_available=round(self.tokens, 2),
                cost=cost,
            )
            await asyncio.sleep(wait_time)

    async def try_acquire(self, cost: int = 1) -> bool:
        """Non-blocking acquire. Returns False if not enough tokens.

        Args:
            cost: Number of tokens to consume.

        Returns:
            True if tokens were consumed, False otherwise.
        """
        async with self._lock:
            self._refill()
            if self.tokens >= cost:
                self.tokens -= cost
                return True
            return False

    @property
    def available_tokens(self) -> float:
        """Current number of available tokens (without consuming)."""
        self._refill()
        return self.tokens
