"""Kraken REST API client via ccxt."""

from __future__ import annotations

import asyncio
import time as _time
from datetime import datetime, timezone
from functools import wraps
from typing import Any

import ccxt.async_support as ccxt
import structlog

from bot.broker.base import (
    AbstractBroker,
    PostOnlyRejectedError,
    PostOnlyTimeoutError,
)
from bot.broker.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from bot.broker.rate_limiter import KrakenRateLimiter
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
from bot.config import settings

logger = structlog.get_logger(__name__)

# ── Interval mapping (minutes → ccxt timeframe string) ─
_INTERVAL_MAP: dict[int, str] = {
    1: "1m",
    5: "5m",
    15: "15m",
    30: "30m",
    60: "1h",
    240: "4h",
    1440: "1d",
    10080: "1w",
}


_PUBLIC_ENDPOINTS = {"get_ticker", "get_historical_prices", "get_tradeable_pairs"}
_ORDER_ENDPOINTS = {"open_position", "close_position"}


def _auto_retry(max_retries: int = 3, delay: float = 5.0):
    """Retry on transient exchange errors with circuit-breaker integration."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            # args[0] is ``self`` (KrakenRestClient instance)
            client: KrakenRestClient | None = None
            if args and isinstance(args[0], KrakenRestClient):
                client = args[0]

            operation = fn.__name__

            # ── Rate limiting ──
            if client is not None:
                if operation in _ORDER_ENDPOINTS:
                    # Order endpoints use the matching engine limiter
                    await client.matching_limiter.acquire(cost=1)
                elif operation in _PUBLIC_ENDPOINTS:
                    await client.rate_limiter.acquire(cost=1)
                else:
                    # Private non-order endpoints cost 2
                    await client.rate_limiter.acquire(cost=2)

            # ── Check circuit breaker before attempting ──
            if client is not None:
                await client.circuit_breaker.pre_call(operation)

            last_err: Exception | None = None
            for attempt in range(1, max_retries + 1):
                try:
                    result = await fn(*args, **kwargs)
                    # Success → record and return
                    if client is not None:
                        await client.circuit_breaker.record_success(operation)
                    return result
                except (
                    ccxt.NetworkError,
                    ccxt.ExchangeNotAvailable,
                    ccxt.RequestTimeout,
                ) as exc:
                    last_err = exc
                    logger.warning(
                        "kraken_retry",
                        fn=fn.__name__,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(delay)
                except ccxt.RateLimitExceeded as exc:
                    last_err = exc
                    logger.error("kraken_rate_limit", fn=fn.__name__)
                    await asyncio.sleep(delay * 2)

            # All retries exhausted → record failure in circuit breaker
            if client is not None:
                await client.circuit_breaker.record_failure(operation)
            raise last_err  # type: ignore[misc]

        return wrapper

    return decorator


class KrakenRestClient(AbstractBroker):
    """Kraken exchange client built on ccxt async."""

    def __init__(self, api_key: str | None = None, api_secret: str | None = None, quote_currency: str = "USD") -> None:
        self._exchange: ccxt.kraken | None = None
        self._api_key = api_key
        self._api_secret = api_secret
        self._quote = quote_currency
        self.circuit_breaker = CircuitBreaker()
        self.rate_limiter = KrakenRateLimiter(max_tokens=15, refill_rate=1.0)
        self.matching_limiter = KrakenRateLimiter(max_tokens=60, refill_rate=1.0)

    # ── Lifecycle ──────────────────────────────────────

    async def connect(self) -> None:
        self._exchange = ccxt.kraken(
            {
                "apiKey": self._api_key or settings.kraken_api_key,
                "secret": self._api_secret or settings.kraken_api_secret,
                "enableRateLimit": True,
                "options": {"defaultType": "spot"},
            }
        )
        # Note: Kraken does not support sandbox mode in ccxt.
        # DEMO mode is handled by PaperBroker at the bot level.
        await self._exchange.load_markets()
        logger.info(
            "kraken_connected",
            markets=len(self._exchange.markets),
        )

    async def disconnect(self) -> None:
        if self._exchange:
            await self._exchange.close()
            logger.info("kraken_disconnected")

    @property
    def exchange(self) -> ccxt.kraken:
        if self._exchange is None:
            raise RuntimeError("Broker not connected. Call connect() first.")
        return self._exchange

    @property
    def health_status(self) -> dict:
        """Return the current circuit breaker state for all operations."""
        return self.circuit_breaker.health_status

    # ── Market data ────────────────────────────────────

    @_auto_retry()
    async def get_ticker(self, pair: str) -> Tick:
        data = await self.exchange.fetch_ticker(pair)
        return Tick(
            pair=pair,
            bid=float(data["bid"] or 0),
            ask=float(data["ask"] or 0),
            last=float(data["last"] or 0),
            volume=float(data["baseVolume"] or 0),
            timestamp=datetime.now(timezone.utc),
        )

    @_auto_retry()
    async def get_historical_prices(
        self,
        pair: str,
        interval_minutes: int = 60,
        since: int | None = None,
        limit: int = 500,
    ) -> list[OHLCV]:
        timeframe = _INTERVAL_MAP.get(interval_minutes, "1h")
        raw = await self.exchange.fetch_ohlcv(
            pair, timeframe=timeframe, since=since, limit=limit
        )
        return [
            OHLCV(
                timestamp=datetime.fromtimestamp(candle[0] / 1000, tz=timezone.utc),
                open=float(candle[1]),
                high=float(candle[2]),
                low=float(candle[3]),
                close=float(candle[4]),
                volume=float(candle[5]),
            )
            for candle in raw
        ]

    # ── Trading ────────────────────────────────────────

    @_auto_retry()
    async def open_position(self, order: OrderRequest) -> OrderResult:
        side = order.direction.value  # "buy" or "sell"
        params: dict[str, Any] = {}

        # Stop-loss as a separate conditional close order on Kraken
        if order.stop_loss_pct and order.order_type.value == "market":
            # We'll place stop-loss after the main order
            pass

        result = await self.exchange.create_order(
            symbol=order.pair,
            type=order.order_type.value,
            side=side,
            amount=order.size,
            price=order.price,
            params=params,
        )

        order_id = result["id"]
        fill_price = float(result.get("average") or result.get("price") or 0)
        fee = float((result.get("fee") or {}).get("cost", 0))

        logger.info(
            "order_opened",
            pair=order.pair,
            side=side,
            size=order.size,
            price=fill_price,
            order_id=order_id,
        )

        return OrderResult(
            order_id=order_id,
            pair=order.pair,
            direction=order.direction,
            size=order.size,
            price=fill_price,
            status=OrderStatus.OPEN,
            fee=fee,
            raw=result,
        )

    async def open_position_post_only(self, order: OrderRequest) -> OrderResult:
        """Place a maker-only limit order, polling until filled or cancelled.

        Saves the spread between Kraken's taker (0.40% tier 0) and maker
        (0.25% tier 0) fees. Raises PostOnlyRejectedError if the exchange
        refused the order, or PostOnlyTimeoutError if it didn't fill within
        ``order.max_wait_sec`` (default 60s).
        """
        if order.limit_price is None or order.limit_price <= 0:
            raise ValueError("post_only requires order.limit_price > 0")

        side = order.direction.value
        wait_sec = float(order.max_wait_sec) if order.max_wait_sec else 60.0

        # Place the order. Kraken / ccxt exposes post-only as `postOnly: True`.
        try:
            placed = await self.exchange.create_order(
                symbol=order.pair,
                type="limit",
                side=side,
                amount=order.size,
                price=order.limit_price,
                params={"postOnly": True},
            )
        except Exception as exc:
            # Most ccxt errors here mean the exchange rejected the order
            # because it would have crossed (i.e. matched immediately).
            msg = str(exc).lower()
            if "post" in msg and ("only" in msg or "reject" in msg):
                raise PostOnlyRejectedError(str(exc)) from exc
            raise

        order_id = placed["id"]
        logger.info(
            "post_only_submitted",
            pair=order.pair, side=side, price=order.limit_price,
            size=order.size, order_id=order_id, max_wait_sec=wait_sec,
        )

        deadline = _time.monotonic() + wait_sec
        last_status: dict[str, Any] | None = None
        poll_interval = 2.0
        while _time.monotonic() < deadline:
            await asyncio.sleep(poll_interval)
            try:
                last_status = await self.exchange.fetch_order(order_id, order.pair)
            except Exception as exc:
                logger.warning(
                    "post_only_poll_error",
                    pair=order.pair, order_id=order_id, error=str(exc),
                )
                continue
            status_value = (last_status.get("status") or "").lower()
            if status_value in ("closed", "filled"):
                fill_price = float(
                    last_status.get("average") or last_status.get("price") or order.limit_price
                )
                fee_info = last_status.get("fee") or {}
                fee = float(fee_info.get("cost", 0)) if isinstance(fee_info, dict) else 0.0
                logger.info(
                    "post_only_filled",
                    pair=order.pair, order_id=order_id,
                    fill_price=fill_price, fee=fee,
                )
                return OrderResult(
                    order_id=order_id, pair=order.pair,
                    direction=order.direction, size=order.size,
                    price=fill_price, status=OrderStatus.OPEN,
                    fee=fee, raw=last_status,
                )
            if status_value in ("canceled", "cancelled", "rejected", "expired"):
                raise PostOnlyRejectedError(
                    f"order {order_id} ended in status {status_value}"
                )

        # Timed out — try to cancel before bailing out.
        try:
            await self.exchange.cancel_order(order_id, order.pair)
            logger.info("post_only_canceled_timeout",
                        pair=order.pair, order_id=order_id)
        except Exception as exc:
            logger.warning(
                "post_only_cancel_error",
                pair=order.pair, order_id=order_id, error=str(exc),
            )
        raise PostOnlyTimeoutError(
            f"order {order_id} not filled within {wait_sec:.0f}s"
        )

    @_auto_retry()
    async def close_position(
        self, order_id: str, pair: str, size: float
    ) -> OrderResult:
        # On Kraken we close by placing an opposite market order
        # Determine current direction from open orders
        result = await self.exchange.create_order(
            symbol=pair,
            type="market",
            side="sell",  # default; caller should provide correct side
            amount=size,
        )

        logger.info("position_closed", pair=pair, order_id=order_id)

        return OrderResult(
            order_id=result["id"],
            pair=pair,
            direction=Direction.SELL,
            size=size,
            price=float(result.get("average") or result.get("price") or 0),
            status=OrderStatus.CLOSED,
            fee=float((result.get("fee") or {}).get("cost", 0)),
            raw=result,
        )

    @_auto_retry()
    async def get_open_positions(self) -> list[Position]:
        # Fetch balance and compute "positions" from non-zero holdings
        balance = await self.exchange.fetch_balance()
        positions: list[Position] = []
        for currency, amount_info in balance.get("total", {}).items():
            fiat = {"USD", "EUR", "ZUSD", "ZEUR", "USDT", "USDC"}
            if currency in fiat:
                continue
            total = float(amount_info) if amount_info else 0.0
            if total <= 0:
                continue
            pair = f"{currency}/{self._quote}"
            try:
                ticker = await self.get_ticker(pair)
                current_price = ticker.last
            except Exception:
                current_price = 0.0
            # Skip dust positions (value < 1 in quote currency)
            position_value = total * current_price if current_price > 0 else 0
            if position_value < 1.0:
                continue
            positions.append(
                Position(
                    pair=pair,
                    direction=Direction.BUY,
                    size=total,
                    entry_price=0.0,  # spot – not tracked natively
                    current_price=current_price,
                )
            )
        return positions

    @_auto_retry()
    async def get_account_balance(self) -> AccountBalance:
        balance = await self.exchange.fetch_balance()
        # Try configured quote currency, then common fallbacks
        for cur in [self._quote, f"Z{self._quote}", self._quote.upper()]:
            free = float(balance.get("free", {}).get(cur, 0) or 0)
            total = float(balance.get("total", {}).get(cur, 0) or 0)
            if total > 0 or free > 0:
                return AccountBalance(
                    total_balance=total,
                    available_balance=free,
                    currency=self._quote,
                )
        return AccountBalance(
            total_balance=0.0,
            available_balance=0.0,
            currency=self._quote,
        )

    @_auto_retry()
    async def get_tradeable_pairs(self) -> list[dict]:
        await self.exchange.load_markets()
        pairs: list[dict] = []
        for symbol, market in self.exchange.markets.items():
            if not market.get("active"):
                continue
            pairs.append(
                {
                    "symbol": symbol,
                    "base": market.get("base", ""),
                    "quote": market.get("quote", ""),
                    "min_amount": market.get("limits", {})
                    .get("amount", {})
                    .get("min"),
                    "min_cost": market.get("limits", {})
                    .get("cost", {})
                    .get("min"),
                    "maker_fee": market.get("maker"),
                    "taker_fee": market.get("taker"),
                }
            )
        return pairs
