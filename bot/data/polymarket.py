"""Polymarket prediction-market client for crypto sentiment signals.

Fetches prediction markets from Polymarket's public APIs (CLOB + Gamma),
filters for crypto-related markets, and extracts directional sentiment
signals that can inform trading decisions.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import aiohttp
import structlog

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────

CLOB_BASE_URL = "https://clob.polymarket.com"
GAMMA_BASE_URL = "https://gamma-api.polymarket.com"

CRYPTO_KEYWORDS: dict[str, str] = {
    "bitcoin": "BTC/USD",
    "btc": "BTC/USD",
    "ethereum": "ETH/USD",
    "eth": "ETH/USD",
    "solana": "SOL/USD",
    "sol": "SOL/USD",
    "xrp": "XRP/USD",
    "ripple": "XRP/USD",
    "cardano": "ADA/USD",
    "ada": "ADA/USD",
    "dogecoin": "DOGE/USD",
    "doge": "DOGE/USD",
    "polkadot": "DOT/USD",
    "dot": "DOT/USD",
    "avalanche": "AVAX/USD",
    "avax": "AVAX/USD",
    "chainlink": "LINK/USD",
    "link": "LINK/USD",
    "polygon": "MATIC/USD",
    "matic": "MATIC/USD",
}

# General crypto keywords (not mapped to a single pair)
GENERAL_CRYPTO_KEYWORDS: list[str] = [
    "crypto",
    "cryptocurrency",
    "defi",
    "blockchain",
    "stablecoin",
    "sec",
    "etf",
    "binance",
    "coinbase",
]

# Build a regex pattern matching any crypto keyword (word-boundary)
_ALL_KEYWORDS = list(CRYPTO_KEYWORDS.keys()) + GENERAL_CRYPTO_KEYWORDS
_CRYPTO_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _ALL_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Sentiment classification patterns
_PRICE_TARGET_UP = re.compile(
    r"will .+?(reach|hit|exceed|surpass|above|over)\b.*?\$[\d,]+",
    re.IGNORECASE,
)
_PRICE_TARGET_DOWN = re.compile(
    r"will .+?(drop|fall|below|under|crash|decline)\b.*?\$[\d,]+",
    re.IGNORECASE,
)
_REGULATORY_POSITIVE = re.compile(
    r"will .+?(approv|adopt|pass|accept|legaliz|regulat)",
    re.IGNORECASE,
)

DEFAULT_CACHE_TTL_SECONDS = 15 * 60  # 15 minutes


# ── Data Models ────────────────────────────────────────────────────────


@dataclass
class PolymarketMarket:
    """A single Polymarket prediction market relevant to crypto."""

    id: str
    question: str
    description: str
    probability: float  # 0-1
    volume: float
    liquidity: float
    end_date: str
    category: str  # "price_target_up", "price_target_down", "regulatory", "general"
    outcomes: list[str]
    related_pair: str | None  # e.g. "BTC/USD" or None for general crypto


@dataclass
class PairSentiment:
    """Aggregated sentiment for a specific trading pair."""

    pair: str
    bullish_probability: float  # 0-1
    bearish_probability: float  # 0-1
    market_count: int
    avg_volume: float
    confidence: float  # 0-1, based on volume/liquidity
    signals: list[str]  # list of relevant market summaries


@dataclass
class MarketTrend:
    """A trending / high-volume prediction market."""

    market_id: str
    question: str
    probability: float
    volume_24h: float
    price_change_24h: float
    category: str


@dataclass
class MacroSentiment:
    """Overall crypto market sentiment derived from prediction markets."""

    overall_score: float  # 0-1: 0 = very bearish, 1 = very bullish
    risk_level: str  # "low", "medium", "high"
    key_factors: list[str]
    market_count: int


# ── Cache Entry ────────────────────────────────────────────────────────


@dataclass
class _CacheEntry:
    data: Any
    timestamp: float


# ── Client ─────────────────────────────────────────────────────────────


class PolymarketClient:
    """Async client for Polymarket public APIs.

    Fetches crypto-related prediction markets and derives sentiment
    signals for use in trading decisions.
    """

    def __init__(self, cache_ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS) -> None:
        self._cache_ttl = cache_ttl_seconds
        self._cache: dict[str, _CacheEntry] = {}
        self._session: aiohttp.ClientSession | None = None

    # ── Session lifecycle ──────────────────────────────

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Cache helpers ──────────────────────────────────

    def _cache_get(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.time() - entry.timestamp > self._cache_ttl:
            del self._cache[key]
            return None
        return entry.data

    def _cache_set(self, key: str, data: Any) -> None:
        self._cache[key] = _CacheEntry(data=data, timestamp=time.time())

    # ── Low-level API calls ────────────────────────────

    async def _fetch_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """GET *url* and return parsed JSON, or ``None`` on failure."""
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 429:
                    logger.warning("polymarket_rate_limited", url=url)
                    return None
                if resp.status != 200:
                    logger.warning(
                        "polymarket_api_error",
                        url=url,
                        status=resp.status,
                    )
                    return None
                return await resp.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning("polymarket_request_failed", url=url, error=str(exc))
            return None

    async def _fetch_gamma_markets(
        self,
        tag: str = "crypto",
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch markets from the Gamma search API."""
        params: dict[str, Any] = {
            "tag": tag,
            "active": "true",
            "closed": "false",
            "limit": limit,
            "offset": offset,
        }
        data = await self._fetch_json(f"{GAMMA_BASE_URL}/markets", params=params)
        if data is None:
            return []
        # Gamma returns a list directly
        if isinstance(data, list):
            return data
        # Some versions wrap in {"data": [...]}
        if isinstance(data, dict) and "data" in data:
            return data["data"]  # type: ignore[no-any-return]
        return []

    async def _fetch_clob_markets(
        self,
        next_cursor: str = "",
    ) -> tuple[list[dict[str, Any]], str]:
        """Fetch markets from the CLOB API. Returns (markets, next_cursor)."""
        params: dict[str, Any] = {}
        if next_cursor:
            params["next_cursor"] = next_cursor
        data = await self._fetch_json(f"{CLOB_BASE_URL}/markets", params=params)
        if data is None:
            return [], ""
        if isinstance(data, dict):
            markets = data.get("data", data.get("markets", []))
            cursor = data.get("next_cursor", "")
            return markets, cursor
        if isinstance(data, list):
            return data, ""
        return [], ""

    async def _fetch_clob_market(self, condition_id: str) -> dict[str, Any] | None:
        """Fetch a single market from the CLOB API."""
        data = await self._fetch_json(f"{CLOB_BASE_URL}/markets/{condition_id}")
        if data is None:
            return None
        return data  # type: ignore[no-any-return]

    # ── Market classification helpers ──────────────────

    @staticmethod
    def _detect_related_pair(text: str) -> str | None:
        """Return the Kraken trading pair mentioned in *text*, or None."""
        lower = text.lower()
        for keyword, pair in CRYPTO_KEYWORDS.items():
            if re.search(rf"\b{re.escape(keyword)}\b", lower):
                return pair
        return None

    @staticmethod
    def _classify_category(question: str) -> str:
        """Classify a market question into a sentiment category."""
        if _PRICE_TARGET_UP.search(question):
            return "price_target_up"
        if _PRICE_TARGET_DOWN.search(question):
            return "price_target_down"
        if _REGULATORY_POSITIVE.search(question):
            return "regulatory"
        return "general"

    @staticmethod
    def _is_crypto_related(text: str) -> bool:
        """Return True if *text* mentions any crypto keyword."""
        return bool(_CRYPTO_PATTERN.search(text))

    @staticmethod
    def _parse_market(raw: dict[str, Any]) -> PolymarketMarket | None:
        """Convert raw API dict to PolymarketMarket, or None if invalid."""
        question = raw.get("question", raw.get("title", ""))
        description = raw.get("description", "")
        full_text = f"{question} {description}"

        if not PolymarketClient._is_crypto_related(full_text):
            return None

        # Extract probability - different API shapes
        probability = 0.5
        for prob_key in ("outcomePrices", "outcome_prices"):
            prices = raw.get(prob_key)
            if prices:
                try:
                    if isinstance(prices, str):
                        import json as _json

                        prices = _json.loads(prices)
                    if isinstance(prices, list) and len(prices) > 0:
                        probability = float(prices[0])
                except (ValueError, TypeError, IndexError):
                    pass
                break
        else:
            # Try direct probability field
            for pkey in ("probability", "price", "lastTradePrice"):
                val = raw.get(pkey)
                if val is not None:
                    try:
                        probability = float(val)
                        break
                    except (ValueError, TypeError):
                        pass

        # Volume / liquidity
        volume = 0.0
        for vkey in ("volume", "volumeNum", "volume_num", "clobRewards"):
            val = raw.get(vkey)
            if val is not None:
                try:
                    volume = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        liquidity = 0.0
        for lkey in ("liquidity", "liquidityNum", "liquidity_num"):
            val = raw.get(lkey)
            if val is not None:
                try:
                    liquidity = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        # Outcomes
        outcomes_raw = raw.get("outcomes", raw.get("tokens", []))
        if isinstance(outcomes_raw, str):
            import json as _json

            try:
                outcomes_raw = _json.loads(outcomes_raw)
            except (ValueError, TypeError):
                outcomes_raw = []
        outcomes: list[str] = []
        if isinstance(outcomes_raw, list):
            for o in outcomes_raw:
                if isinstance(o, str):
                    outcomes.append(o)
                elif isinstance(o, dict):
                    outcomes.append(o.get("outcome", o.get("name", str(o))))

        end_date = raw.get("endDate", raw.get("end_date_iso", raw.get("end_date", "")))
        if end_date is None:
            end_date = ""

        market_id = str(
            raw.get("condition_id", raw.get("conditionId", raw.get("id", "")))
        )

        return PolymarketMarket(
            id=market_id,
            question=question,
            description=description[:500],
            probability=probability,
            volume=volume,
            liquidity=liquidity,
            end_date=str(end_date),
            category=PolymarketClient._classify_category(question),
            outcomes=outcomes if outcomes else ["Yes", "No"],
            related_pair=PolymarketClient._detect_related_pair(full_text),
        )

    # ── Public methods ─────────────────────────────────

    async def fetch_crypto_markets(self) -> list[PolymarketMarket]:
        """Fetch all active crypto-related prediction markets.

        Uses the Gamma API for keyword search, then supplements
        with CLOB pagination.  Results are cached.
        """
        cached = self._cache_get("crypto_markets")
        if cached is not None:
            return cached  # type: ignore[return-value]

        markets: list[PolymarketMarket] = []
        seen_ids: set[str] = set()

        # 1. Gamma API - tagged crypto markets
        try:
            raw_markets = await self._fetch_gamma_markets(tag="crypto", limit=50)
            for raw in raw_markets:
                m = self._parse_market(raw)
                if m and m.id not in seen_ids:
                    markets.append(m)
                    seen_ids.add(m.id)
        except Exception:
            logger.exception("polymarket_gamma_fetch_error")

        # 2. CLOB API - first page (may contain non-tagged crypto markets)
        try:
            clob_markets, _ = await self._fetch_clob_markets()
            for raw in clob_markets:
                m = self._parse_market(raw)
                if m and m.id not in seen_ids:
                    markets.append(m)
                    seen_ids.add(m.id)
        except Exception:
            logger.exception("polymarket_clob_fetch_error")

        logger.info("polymarket_markets_fetched", count=len(markets))
        self._cache_set("crypto_markets", markets)
        return markets

    async def get_sentiment_for_pair(self, pair: str) -> PairSentiment | None:
        """Aggregate sentiment for a specific trading pair (e.g. ``BTC/USD``).

        Returns ``None`` if no relevant markets are found.
        """
        cache_key = f"pair_sentiment:{pair}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        markets = await self.fetch_crypto_markets()
        relevant = [m for m in markets if m.related_pair == pair]

        if not relevant:
            return None

        bullish_scores: list[float] = []
        bearish_scores: list[float] = []
        signals: list[str] = []
        total_volume = 0.0

        for m in relevant:
            total_volume += m.volume
            short_q = m.question[:120]

            if m.category == "price_target_up":
                bullish_scores.append(m.probability)
                bearish_scores.append(1.0 - m.probability)
                signals.append(f"[BULLISH {m.probability:.0%}] {short_q}")
            elif m.category == "price_target_down":
                bearish_scores.append(m.probability)
                bullish_scores.append(1.0 - m.probability)
                signals.append(f"[BEARISH {m.probability:.0%}] {short_q}")
            elif m.category == "regulatory":
                # Regulatory approval generally bullish
                bullish_scores.append(m.probability)
                bearish_scores.append(1.0 - m.probability)
                signals.append(f"[REGULATORY {m.probability:.0%}] {short_q}")
            else:
                # Default: use probability as bullish score
                bullish_scores.append(m.probability)
                bearish_scores.append(1.0 - m.probability)
                signals.append(f"[GENERAL {m.probability:.0%}] {short_q}")

        avg_bullish = sum(bullish_scores) / len(bullish_scores) if bullish_scores else 0.5
        avg_bearish = sum(bearish_scores) / len(bearish_scores) if bearish_scores else 0.5
        avg_volume = total_volume / len(relevant) if relevant else 0.0

        # Confidence: higher when more markets with more volume
        market_count_factor = min(len(relevant) / 5.0, 1.0)
        volume_factor = min(avg_volume / 100_000.0, 1.0) if avg_volume > 0 else 0.1
        confidence = 0.5 * market_count_factor + 0.5 * volume_factor

        result = PairSentiment(
            pair=pair,
            bullish_probability=round(avg_bullish, 4),
            bearish_probability=round(avg_bearish, 4),
            market_count=len(relevant),
            avg_volume=round(avg_volume, 2),
            confidence=round(confidence, 4),
            signals=signals,
        )
        self._cache_set(cache_key, result)
        return result

    async def get_market_trends(self) -> list[MarketTrend]:
        """Return trending / high-volume crypto prediction markets.

        Sorted by volume descending.
        """
        cached = self._cache_get("market_trends")
        if cached is not None:
            return cached  # type: ignore[return-value]

        markets = await self.fetch_crypto_markets()

        trends: list[MarketTrend] = []
        for m in sorted(markets, key=lambda x: x.volume, reverse=True)[:20]:
            trends.append(
                MarketTrend(
                    market_id=m.id,
                    question=m.question,
                    probability=m.probability,
                    volume_24h=m.volume,
                    price_change_24h=0.0,  # not available from basic API
                    category=m.category,
                )
            )

        self._cache_set("market_trends", trends)
        return trends

    async def get_macro_sentiment(self) -> MacroSentiment:
        """Compute overall crypto market sentiment from all markets.

        Returns a ``MacroSentiment`` with an ``overall_score`` in [0, 1]
        where 0 is very bearish and 1 is very bullish.
        """
        cached = self._cache_get("macro_sentiment")
        if cached is not None:
            return cached  # type: ignore[return-value]

        markets = await self.fetch_crypto_markets()

        if not markets:
            result = MacroSentiment(
                overall_score=0.5,
                risk_level="medium",
                key_factors=["No prediction market data available"],
                market_count=0,
            )
            self._cache_set("macro_sentiment", result)
            return result

        scores: list[float] = []
        key_factors: list[str] = []
        bullish_count = 0
        bearish_count = 0

        for m in markets:
            if m.category == "price_target_up":
                scores.append(m.probability)
                if m.probability > 0.6:
                    bullish_count += 1
                    if len(key_factors) < 5:
                        key_factors.append(
                            f"Bullish: {m.question[:80]} ({m.probability:.0%})"
                        )
            elif m.category == "price_target_down":
                scores.append(1.0 - m.probability)
                if m.probability > 0.6:
                    bearish_count += 1
                    if len(key_factors) < 5:
                        key_factors.append(
                            f"Bearish: {m.question[:80]} ({m.probability:.0%})"
                        )
            elif m.category == "regulatory":
                scores.append(m.probability)
                if m.probability > 0.6 and len(key_factors) < 5:
                    key_factors.append(
                        f"Regulatory tailwind: {m.question[:80]} ({m.probability:.0%})"
                    )
            else:
                scores.append(m.probability)

        overall = sum(scores) / len(scores) if scores else 0.5

        # Risk level
        if overall < 0.35 or bearish_count > bullish_count * 2:
            risk_level = "high"
        elif overall > 0.65 and bearish_count < bullish_count:
            risk_level = "low"
        else:
            risk_level = "medium"

        if not key_factors:
            key_factors.append(
                f"Aggregated from {len(markets)} crypto prediction markets"
            )

        result = MacroSentiment(
            overall_score=round(overall, 4),
            risk_level=risk_level,
            key_factors=key_factors,
            market_count=len(markets),
        )
        self._cache_set("macro_sentiment", result)
        return result
