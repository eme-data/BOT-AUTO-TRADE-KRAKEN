"""Generic CCXT broker – supports any exchange (Binance, Coinbase, OKX, etc.)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import ccxt.async_support as ccxt
import structlog

from bot.broker.base import AbstractBroker
from bot.broker.models import (
    AccountBalance,
    Direction,
    OHLCV,
    OrderRequest,
    OrderResult,
    OrderStatus,
    Position,
    Tick,
)

logger = structlog.get_logger(__name__)

_INTERVAL_MAP: dict[int, str] = {
    1: "1m", 5: "5m", 15: "15m", 30: "30m",
    60: "1h", 240: "4h", 1440: "1d", 10080: "1w",
}

# Exchanges supported via ccxt
SUPPORTED_EXCHANGES = {
    "kraken": ccxt.kraken,
    "binance": ccxt.binance,
    "coinbase": ccxt.coinbase,
    "coinbasepro": ccxt.coinbasepro,
    "okx": ccxt.okx,
    "bybit": ccxt.bybit,
    "kucoin": ccxt.kucoin,
    "bitfinex": ccxt.bitfinex,
    "gateio": ccxt.gateio,
}


class CCXTBroker(AbstractBroker):
    """Generic exchange broker using ccxt. Works with any supported exchange."""

    def __init__(
        self,
        exchange_id: str = "kraken",
        api_key: str | None = None,
        api_secret: str | None = None,
        password: str | None = None,
        quote_currency: str = "USD",
    ) -> None:
        self._exchange_id = exchange_id.lower()
        self._api_key = api_key
        self._api_secret = api_secret
        self._password = password
        self._quote = quote_currency
        self._exchange: Any = None

    async def connect(self) -> None:
        exchange_class = SUPPORTED_EXCHANGES.get(self._exchange_id)
        if exchange_class is None:
            raise ValueError(
                f"Unsupported exchange: {self._exchange_id}. "
                f"Supported: {', '.join(SUPPORTED_EXCHANGES.keys())}"
            )

        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if self._api_key:
            config["apiKey"] = self._api_key
        if self._api_secret:
            config["secret"] = self._api_secret
        if self._password:
            config["password"] = self._password

        self._exchange = exchange_class(config)

        # Binance testnet support
        if self._exchange_id == "binance" and not self._api_key:
            self._exchange.set_sandbox_mode(True)

        await self._exchange.load_markets()
        logger.info(
            "ccxt_broker_connected",
            exchange=self._exchange_id,
            markets=len(self._exchange.markets),
            quote=self._quote,
        )

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            logger.info("ccxt_broker_disconnected", exchange=self._exchange_id)

    @property
    def exchange(self):
        if self._exchange is None:
            raise RuntimeError("Broker not connected. Call connect() first.")
        return self._exchange

    # ── Market data ────────────────────────────────────

    async def get_ticker(self, pair: str) -> Tick:
        data = await self.exchange.fetch_ticker(pair)
        return Tick(
            pair=pair,
            bid=float(data.get("bid") or 0),
            ask=float(data.get("ask") or 0),
            last=float(data.get("last") or 0),
            volume=float(data.get("baseVolume") or 0),
            timestamp=datetime.now(timezone.utc),
        )

    async def get_historical_prices(
        self, pair: str, interval_minutes: int = 60,
        since: int | None = None, limit: int = 500,
    ) -> list[OHLCV]:
        timeframe = _INTERVAL_MAP.get(interval_minutes, "1h")
        raw = await self.exchange.fetch_ohlcv(
            pair, timeframe=timeframe, since=since, limit=limit,
        )
        return [
            OHLCV(
                timestamp=datetime.fromtimestamp(c[0] / 1000, tz=timezone.utc),
                open=float(c[1]), high=float(c[2]),
                low=float(c[3]), close=float(c[4]),
                volume=float(c[5]),
            )
            for c in raw
        ]

    # ── Trading ────────────────────────────────────────

    async def open_position(self, order: OrderRequest) -> OrderResult:
        side = order.direction.value
        result = await self.exchange.create_order(
            symbol=order.pair,
            type=order.order_type.value,
            side=side,
            amount=order.size,
            price=order.price,
        )
        return OrderResult(
            order_id=result["id"],
            pair=order.pair,
            direction=order.direction,
            size=order.size,
            price=float(result.get("average") or result.get("price") or 0),
            status=OrderStatus.OPEN,
            fee=float(result.get("fee", {}).get("cost", 0)),
            raw=result,
        )

    async def close_position(self, order_id: str, pair: str, size: float) -> OrderResult:
        result = await self.exchange.create_order(
            symbol=pair, type="market", side="sell", amount=size,
        )
        return OrderResult(
            order_id=result["id"],
            pair=pair,
            direction=Direction.SELL,
            size=size,
            price=float(result.get("average") or result.get("price") or 0),
            status=OrderStatus.CLOSED,
            fee=float(result.get("fee", {}).get("cost", 0)),
            raw=result,
        )

    async def get_open_positions(self) -> list[Position]:
        balance = await self.exchange.fetch_balance()
        positions: list[Position] = []
        stablecoins = {"USD", "EUR", "USDT", "USDC", "BUSD", "ZUSD", "ZEUR"}
        for currency, amount in balance.get("total", {}).items():
            if currency in stablecoins:
                continue
            total = float(amount) if amount else 0.0
            if total <= 0:
                continue
            pair = f"{currency}/{self._quote}"
            try:
                ticker = await self.get_ticker(pair)
                current_price = ticker.last
            except Exception:
                current_price = 0.0
            positions.append(
                Position(
                    pair=pair, direction=Direction.BUY,
                    size=total, entry_price=0.0,
                    current_price=current_price,
                )
            )
        return positions

    async def get_account_balance(self) -> AccountBalance:
        balance = await self.exchange.fetch_balance()
        free = float(balance.get("free", {}).get(self._quote, 0) or 0)
        total = float(balance.get("total", {}).get(self._quote, 0) or 0)
        return AccountBalance(
            total_balance=total,
            available_balance=free,
            currency=self._quote,
        )

    async def get_tradeable_pairs(self) -> list[dict]:
        await self.exchange.load_markets()
        pairs: list[dict] = []
        for symbol, market in self.exchange.markets.items():
            if not market.get("active"):
                continue
            pairs.append({
                "symbol": symbol,
                "base": market.get("base", ""),
                "quote": market.get("quote", ""),
                "min_amount": market.get("limits", {}).get("amount", {}).get("min"),
                "min_cost": market.get("limits", {}).get("cost", {}).get("min"),
                "maker_fee": market.get("maker"),
                "taker_fee": market.get("taker"),
            })
        return pairs
