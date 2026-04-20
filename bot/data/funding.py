"""Binance perpetual-futures funding-rate client.

Used by FundingDivergenceStrategy as a contrarian signal: when Binance
perpetual funding goes deeply negative it indicates crowded short
positioning on leverage, which empirically precedes short-covering
rallies on spot. We trade the spot move on Kraken.

Exposes:
  - ``FundingRateClient.get_history(pair, days)`` for backtesting
  - ``FundingRateClient.get_latest(pair)`` for live signals
  - ``kraken_to_binance_perp`` mapper from a Kraken spot pair (``BTC/USD``)
    to the matching Binance perp symbol in ccxt notation
    (``BTC/USDT:USDT``).

Notes on latency: Binance updates funding every 8 hours. Retail traders
are not competing with HFT desks on this channel — a 2-5 minute fetch
latency has no material impact on signal quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import ccxt.async_support as ccxt
import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


# ── Symbol mapping ────────────────────────────────────

# Most Kraken quote currencies (USD, EUR, USDC) do not have a direct perp on
# Binance — the deepest perp liquidity is USDT-quoted. This mapper normalizes
# the base asset and returns the ccxt perp symbol.
def kraken_to_binance_perp(pair: str) -> Optional[str]:
    """Translate a Kraken spot pair to the matching Binance perp, or None."""
    if "/" not in pair:
        return None
    base, _quote = pair.split("/", 1)
    base = base.upper()
    # Binance does not list perps for every Kraken base. Return None for
    # obvious non-candidates; the caller just skips them.
    if not base or len(base) > 6:
        return None
    return f"{base}/USDT:USDT"


@dataclass
class FundingSample:
    """One historical funding observation."""

    timestamp: datetime
    rate: float  # per-period rate (Binance: every 8 hours)


class FundingRateClient:
    """Thin async wrapper around ccxt.binance funding-rate endpoints."""

    def __init__(self) -> None:
        self._exchange: Optional[ccxt.binance] = None

    async def _get_exchange(self) -> ccxt.binance:
        if self._exchange is None:
            self._exchange = ccxt.binance(
                {"options": {"defaultType": "future"}, "enableRateLimit": True}
            )
        return self._exchange

    async def close(self) -> None:
        if self._exchange is not None:
            try:
                await self._exchange.close()
            except Exception as exc:
                logger.warning("funding_close_error", error=str(exc))
            self._exchange = None

    async def get_latest(self, kraken_pair: str) -> Optional[FundingSample]:
        """Return the most recent funding rate for the given Kraken pair."""
        sym = kraken_to_binance_perp(kraken_pair)
        if sym is None:
            return None
        ex = await self._get_exchange()
        try:
            data = await ex.fetch_funding_rate(sym)
        except Exception as exc:
            logger.warning("funding_latest_error", pair=kraken_pair, error=str(exc))
            return None
        ts = data.get("timestamp") or data.get("fundingTimestamp")
        rate = data.get("fundingRate")
        if ts is None or rate is None:
            return None
        return FundingSample(
            timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
            rate=float(rate),
        )

    async def get_history(
        self, kraken_pair: str, days: int = 180
    ) -> list[FundingSample]:
        """Return historical funding samples, paginated back ``days`` days.

        Binance caps ``fundingRateHistory`` at 1000 rows per request and
        returns periods spaced by 8h, so we paginate by ``since`` until we
        reach the target horizon (180 days ≈ 540 samples, well under the
        1000 cap — a single page usually suffices).
        """
        sym = kraken_to_binance_perp(kraken_pair)
        if sym is None:
            return []
        ex = await self._get_exchange()
        since_ms = int(
            (datetime.now(timezone.utc).timestamp() - days * 86400) * 1000
        )
        samples: list[FundingSample] = []
        seen: set[int] = set()
        while True:
            try:
                batch = await ex.fetch_funding_rate_history(
                    sym, since=since_ms, limit=1000
                )
            except Exception as exc:
                logger.warning(
                    "funding_history_error",
                    pair=kraken_pair, error=str(exc), fetched=len(samples),
                )
                break
            if not batch:
                break
            new_rows = 0
            for row in batch:
                ts = row.get("timestamp")
                rate = row.get("fundingRate")
                if ts is None or rate is None or ts in seen:
                    continue
                seen.add(ts)
                samples.append(FundingSample(
                    timestamp=datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    rate=float(rate),
                ))
                new_rows += 1
            if new_rows == 0 or len(batch) < 1000:
                break
            since_ms = int(batch[-1]["timestamp"]) + 1
        samples.sort(key=lambda s: s.timestamp)
        return samples

    @staticmethod
    def samples_to_df(samples: list[FundingSample]) -> pd.DataFrame:
        """Convert samples to a timestamp-indexed DataFrame with a funding_rate col."""
        if not samples:
            return pd.DataFrame(columns=["funding_rate"])
        df = pd.DataFrame(
            {"timestamp": [s.timestamp for s in samples],
             "funding_rate": [s.rate for s in samples]}
        )
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        return df
