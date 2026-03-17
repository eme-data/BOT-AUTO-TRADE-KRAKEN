"""Market discovery – finds tradeable crypto pairs on Kraken."""

from __future__ import annotations

import structlog

from bot.broker.kraken_rest import KrakenRestClient
from bot.broker.paper_broker import PaperBroker
from bot.autopilot.models import ScanResult

logger = structlog.get_logger(__name__)


def _get_real_broker(broker) -> KrakenRestClient:
    """Extract the real KrakenRestClient from a broker (handles PaperBroker)."""
    if isinstance(broker, PaperBroker):
        return broker.real_broker
    return broker

# Base assets to scan (quote currency is added dynamically)
_BASE_ASSETS: list[str] = [
    # ── Top caps ──────────────────────────────
    "BTC", "ETH", "SOL", "XRP", "ADA",
    "DOT", "AVAX", "LINK", "ATOM", "LTC",
    # ── Meme coins ────────────────────────────
    "DOGE", "SHIB", "PEPE", "FLOKI", "BONK",
    # ── DeFi / Layer 2 ───────────────────────
    "UNI", "AAVE", "MKR", "CRV", "LDO",
    "ARB", "OP", "MATIC", "IMX",
    # ── Ecosystemes ──────────────────────────
    "NEAR", "APT", "SUI", "SEI", "INJ",
    "FIL", "RENDER", "FET", "GRT",
    # ── Autres altcoins ──────────────────────
    "BCH", "ALGO", "XLM", "VET", "SAND",
    "MANA", "ENS", "COMP",
]


def get_discovery_pairs(quote: str = "USD") -> list[str]:
    """Build discovery pair list for the given quote currency."""
    return [f"{base}/{quote}" for base in _BASE_ASSETS]

# Quote currencies we trade against
ALLOWED_QUOTES = {"USD", "EUR", "USDT"}


class MarketScanner:
    """Discovers and filters tradeable pairs on Kraken."""

    def __init__(self, broker, quote_currency: str = "USD") -> None:
        self._broker = broker
        self._real_broker = _get_real_broker(broker)
        self._quote = quote_currency

    async def scan_discovery(
        self, custom_pairs: list[str] | None = None
    ) -> list[ScanResult]:
        """Scan a predefined list of pairs."""
        pairs_to_check = custom_pairs or get_discovery_pairs(self._quote)
        results: list[ScanResult] = []

        markets = self._real_broker.exchange.markets
        for pair in pairs_to_check:
            market = markets.get(pair)
            if not market or not market.get("active"):
                continue
            quote = market.get("quote", "")
            if quote not in ALLOWED_QUOTES:
                continue
            results.append(
                ScanResult(
                    pair=pair,
                    base=market.get("base", ""),
                    quote=quote,
                    tradeable=True,
                )
            )

        logger.info("scan_discovery", found=len(results))
        return results

    async def scan_by_volume(self, top_n: int = 20) -> list[ScanResult]:
        """Scan all active pairs and sort by 24h volume."""
        all_pairs = await self._real_broker.get_tradeable_pairs()
        results: list[ScanResult] = []

        for info in all_pairs:
            if info["quote"] not in ALLOWED_QUOTES:
                continue
            try:
                ticker = await self._real_broker.get_ticker(info["symbol"])
                results.append(
                    ScanResult(
                        pair=info["symbol"],
                        base=info["base"],
                        quote=info["quote"],
                        volume_24h=ticker.volume * ticker.last,
                    )
                )
            except Exception:
                continue

        results.sort(key=lambda r: r.volume_24h, reverse=True)
        top = results[:top_n]
        logger.info("scan_by_volume", found=len(top))
        return top
