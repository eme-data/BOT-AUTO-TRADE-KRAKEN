"""Market discovery – finds tradeable crypto pairs on Kraken."""

from __future__ import annotations

import structlog

from bot.broker.kraken_rest import KrakenRestClient
from bot.autopilot.models import ScanResult

logger = structlog.get_logger(__name__)

# Default pairs to scan when in discovery mode
DEFAULT_DISCOVERY_PAIRS: list[str] = [
    # ── Top caps ──────────────────────────────
    "BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD",
    "DOT/USD", "AVAX/USD", "LINK/USD", "ATOM/USD", "LTC/USD",
    # ── Meme coins ────────────────────────────
    "DOGE/USD", "SHIB/USD", "PEPE/USD", "FLOKI/USD", "BONK/USD",
    # ── DeFi / Layer 2 ───────────────────────
    "UNI/USD", "AAVE/USD", "MKR/USD", "CRV/USD", "LDO/USD",
    "ARB/USD", "OP/USD", "MATIC/USD", "IMX/USD",
    # ── Ecosystemes ──────────────────────────
    "NEAR/USD", "APT/USD", "SUI/USD", "SEI/USD", "INJ/USD",
    "FIL/USD", "RENDER/USD", "FET/USD", "GRT/USD",
    # ── Autres altcoins ──────────────────────
    "BCH/USD", "ALGO/USD", "XLM/USD", "VET/USD", "SAND/USD",
    "MANA/USD", "ENS/USD", "COMP/USD",
    # ── EUR variants ─────────────────────────
    "BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR",
]

# Quote currencies we trade against
ALLOWED_QUOTES = {"USD", "EUR", "USDT"}


class MarketScanner:
    """Discovers and filters tradeable pairs on Kraken."""

    def __init__(self, broker: KrakenRestClient) -> None:
        self._broker = broker

    async def scan_discovery(
        self, custom_pairs: list[str] | None = None
    ) -> list[ScanResult]:
        """Scan a predefined list of pairs."""
        pairs_to_check = custom_pairs or DEFAULT_DISCOVERY_PAIRS
        results: list[ScanResult] = []

        markets = self._broker.exchange.markets
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
        all_pairs = await self._broker.get_tradeable_pairs()
        results: list[ScanResult] = []

        for info in all_pairs:
            if info["quote"] not in ALLOWED_QUOTES:
                continue
            try:
                ticker = await self._broker.get_ticker(info["symbol"])
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
