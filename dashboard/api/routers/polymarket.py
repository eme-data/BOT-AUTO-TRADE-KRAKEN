"""Polymarket trends and sentiment endpoints for the trading dashboard."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Path

from dashboard.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/polymarket",
    tags=["polymarket"],
    dependencies=[Depends(get_current_user)],
)

# ── helpers ──────────────────────────────────────────────────────────

TRACKED_PAIRS = [
    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
    "DOT/USD", "AVAX/USD", "LINK/USD", "MATIC/USD", "ATOM/USD",
]

_PAIR_KEYWORDS: dict[str, list[str]] = {
    "BTC/USD": ["bitcoin", "btc"],
    "ETH/USD": ["ethereum", "eth"],
    "SOL/USD": ["solana", "sol"],
    "XRP/USD": ["xrp", "ripple"],
    "ADA/USD": ["cardano", "ada"],
    "DOT/USD": ["polkadot", "dot"],
    "AVAX/USD": ["avalanche", "avax"],
    "LINK/USD": ["chainlink", "link"],
    "MATIC/USD": ["polygon", "matic"],
    "ATOM/USD": ["cosmos", "atom"],
}


def _get_polymarket_client() -> Any | None:
    """Try to import and instantiate the PolymarketClient."""
    try:
        from bot.data.polymarket import PolymarketClient  # type: ignore
        return PolymarketClient()
    except Exception:
        logger.debug("PolymarketClient unavailable, using mock data")
        return None


def _mock_trending_markets() -> list[dict[str, Any]]:
    """Return sample trending markets when the real client is unavailable."""
    return [
        {
            "id": "1",
            "question": "Will Bitcoin exceed $150,000 by end of 2026?",
            "probability": 0.62,
            "volume": 4_850_000,
            "category": "Crypto",
            "related_pair": "BTC/USD",
        },
        {
            "id": "2",
            "question": "Will Ethereum reach $10,000 in 2026?",
            "probability": 0.38,
            "volume": 2_120_000,
            "category": "Crypto",
            "related_pair": "ETH/USD",
        },
        {
            "id": "3",
            "question": "Will the SEC approve a Solana spot ETF in 2026?",
            "probability": 0.55,
            "volume": 1_750_000,
            "category": "Regulation",
            "related_pair": "SOL/USD",
        },
        {
            "id": "4",
            "question": "Will total crypto market cap exceed $5T in Q2 2026?",
            "probability": 0.48,
            "volume": 3_200_000,
            "category": "Crypto",
            "related_pair": "BTC/USD",
        },
        {
            "id": "5",
            "question": "Will Bitcoin dominance stay above 50% through June 2026?",
            "probability": 0.71,
            "volume": 1_420_000,
            "category": "Crypto",
            "related_pair": "BTC/USD",
        },
        {
            "id": "6",
            "question": "Will a major US crypto regulation bill pass in 2026?",
            "probability": 0.64,
            "volume": 2_890_000,
            "category": "Regulation",
            "related_pair": None,
        },
        {
            "id": "7",
            "question": "Will XRP settle above $5 by mid-2026?",
            "probability": 0.29,
            "volume": 980_000,
            "category": "Crypto",
            "related_pair": "XRP/USD",
        },
        {
            "id": "8",
            "question": "Will the Fed cut rates before July 2026?",
            "probability": 0.73,
            "volume": 5_100_000,
            "category": "Macro",
            "related_pair": None,
        },
        {
            "id": "9",
            "question": "Will DeFi TVL exceed $300B in 2026?",
            "probability": 0.44,
            "volume": 1_150_000,
            "category": "DeFi",
            "related_pair": "ETH/USD",
        },
    ]


def _compute_sentiment(markets: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive an overall crypto sentiment score from market probabilities."""
    if not markets:
        return {
            "overall_score": 50,
            "risk_level": "Medium",
            "key_factors": ["No market data available"],
        }

    total_volume = sum(m.get("volume", 0) for m in markets)
    if total_volume == 0:
        avg_prob = sum(m.get("probability", 0.5) for m in markets) / len(markets)
    else:
        avg_prob = sum(
            m.get("probability", 0.5) * m.get("volume", 0)
            for m in markets
        ) / total_volume

    score = round(avg_prob * 100)

    if score >= 65:
        risk_level = "Low"
    elif score >= 40:
        risk_level = "Medium"
    else:
        risk_level = "High"

    sorted_markets = sorted(markets, key=lambda m: m.get("volume", 0), reverse=True)
    key_factors = []
    for m in sorted_markets[:5]:
        prob_pct = round(m.get("probability", 0.5) * 100)
        direction = "bullish" if prob_pct >= 55 else "bearish" if prob_pct <= 45 else "neutral"
        key_factors.append(
            f"{m['question'][:80]} -- {prob_pct}% ({direction})"
        )

    return {
        "overall_score": score,
        "risk_level": risk_level,
        "key_factors": key_factors,
    }


def _pair_sentiment(pair: str, markets: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute sentiment for a specific trading pair."""
    keywords = _PAIR_KEYWORDS.get(pair, [pair.split("/")[0].lower()])

    related = [
        m for m in markets
        if m.get("related_pair") == pair
        or any(kw in m.get("question", "").lower() for kw in keywords)
    ]

    if not related:
        return {
            "pair": pair,
            "bullish_probability": 0.5,
            "bearish_probability": 0.5,
            "confidence": 0.0,
            "market_count": 0,
            "total_volume": 0,
            "related_markets": [],
        }

    total_volume = sum(m.get("volume", 0) for m in related)
    if total_volume > 0:
        bullish = sum(
            m.get("probability", 0.5) * m.get("volume", 0)
            for m in related
        ) / total_volume
    else:
        bullish = sum(m.get("probability", 0.5) for m in related) / len(related)

    count_factor = min(len(related) / 5.0, 1.0)
    volume_factor = min(total_volume / 5_000_000, 1.0)
    confidence = round((count_factor * 0.4 + volume_factor * 0.6) * 100)

    return {
        "pair": pair,
        "bullish_probability": round(bullish, 4),
        "bearish_probability": round(1 - bullish, 4),
        "confidence": confidence,
        "market_count": len(related),
        "total_volume": total_volume,
        "related_markets": [
            {
                "question": m["question"],
                "probability": m.get("probability", 0.5),
                "volume": m.get("volume", 0),
                "category": m.get("category", ""),
            }
            for m in sorted(related, key=lambda x: x.get("volume", 0), reverse=True)
        ],
    }


# ── endpoints ────────────────────────────────────────────────────────


@router.get("/trends")
async def get_trends():
    """Return trending crypto prediction markets from Polymarket."""
    client = _get_polymarket_client()
    if client is not None:
        try:
            markets = await client.get_trending_markets()  # type: ignore
            return markets
        except Exception:
            logger.exception("Failed to fetch from PolymarketClient")

    return _mock_trending_markets()


@router.get("/sentiment")
async def get_sentiment():
    """Return macro crypto sentiment derived from Polymarket data."""
    client = _get_polymarket_client()
    markets: list[dict[str, Any]] = []
    if client is not None:
        try:
            markets = await client.get_trending_markets()  # type: ignore
        except Exception:
            logger.exception("Failed to fetch from PolymarketClient")

    if not markets:
        markets = _mock_trending_markets()

    return _compute_sentiment(markets)


@router.get("/pair/{pair:path}")
async def get_pair_sentiment(pair: str = Path(..., description="Trading pair, e.g. BTC/USD")):
    """Return sentiment for a specific trading pair."""
    pair = pair.upper()
    if pair not in _PAIR_KEYWORDS and "/" not in pair:
        pair = f"{pair}/USD"

    client = _get_polymarket_client()
    markets: list[dict[str, Any]] = []
    if client is not None:
        try:
            markets = await client.get_trending_markets()  # type: ignore
        except Exception:
            logger.exception("Failed to fetch from PolymarketClient")

    if not markets:
        markets = _mock_trending_markets()

    return _pair_sentiment(pair, markets)
