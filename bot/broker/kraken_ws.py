"""Kraken WebSocket client for real-time market data."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import structlog
import websockets
from websockets.asyncio.client import ClientConnection

from bot.broker.models import Tick

logger = structlog.get_logger(__name__)

KRAKEN_WS_PUBLIC = "wss://ws.kraken.com/v2"
KRAKEN_WS_PRIVATE = "wss://ws-auth.kraken.com/v2"


class KrakenWSClient:
    """Handles real-time WebSocket streaming from Kraken."""

    def __init__(self) -> None:
        self._ws: ClientConnection | None = None
        self._subscriptions: dict[str, set[str]] = {}  # channel -> {pair, ...}
        self._running = False
        self._on_tick: Callable[[Tick], Coroutine[Any, Any, None]] | None = None
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 60.0

    def set_tick_callback(
        self, callback: Callable[[Tick], Coroutine[Any, Any, None]]
    ) -> None:
        self._on_tick = callback

    async def connect(self) -> None:
        self._running = True
        asyncio.create_task(self._run_loop())
        logger.info("kraken_ws_started")

    async def disconnect(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("kraken_ws_stopped")

    async def subscribe_ticker(self, pairs: list[str]) -> None:
        self._subscriptions.setdefault("ticker", set()).update(pairs)
        if self._ws:
            await self._send_subscribe("ticker", pairs)

    async def unsubscribe_ticker(self, pairs: list[str]) -> None:
        if "ticker" in self._subscriptions:
            self._subscriptions["ticker"] -= set(pairs)
        if self._ws:
            await self._send_unsubscribe("ticker", pairs)

    # ── Internal ───────────────────────────────────────

    async def _run_loop(self) -> None:
        while self._running:
            try:
                async with websockets.connect(KRAKEN_WS_PUBLIC) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1.0
                    logger.info("kraken_ws_connected")

                    # Re-subscribe on (re)connect
                    for channel, pairs in self._subscriptions.items():
                        if pairs:
                            await self._send_subscribe(channel, list(pairs))

                    async for raw_msg in ws:
                        await self._handle_message(raw_msg)

            except websockets.ConnectionClosed as exc:
                logger.warning("kraken_ws_closed", reason=str(exc))
            except Exception as exc:
                logger.error("kraken_ws_error", error=str(exc))

            if self._running:
                logger.info(
                    "kraken_ws_reconnecting",
                    delay=self._reconnect_delay,
                )
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    async def _send_subscribe(self, channel: str, pairs: list[str]) -> None:
        msg = {
            "method": "subscribe",
            "params": {"channel": channel, "symbol": pairs},
        }
        if self._ws:
            await self._ws.send(json.dumps(msg))
            logger.debug("ws_subscribed", channel=channel, pairs=pairs)

    async def _send_unsubscribe(self, channel: str, pairs: list[str]) -> None:
        msg = {
            "method": "unsubscribe",
            "params": {"channel": channel, "symbol": pairs},
        }
        if self._ws:
            await self._ws.send(json.dumps(msg))

    async def _handle_message(self, raw: str | bytes) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return

        # Kraken v2 WS sends channel data as:
        # {"channel": "ticker", "type": "update", "data": [...]}
        channel = data.get("channel")
        msg_type = data.get("type")

        if channel == "heartbeat" or msg_type in ("subscribe", "unsubscribe"):
            return

        if channel == "ticker" and msg_type in ("snapshot", "update"):
            await self._handle_ticker(data.get("data", []))

    async def _handle_ticker(self, items: list[dict[str, Any]]) -> None:
        if not self._on_tick:
            return
        for item in items:
            symbol = item.get("symbol", "")
            tick = Tick(
                pair=symbol,
                bid=float(item.get("bid", 0)),
                ask=float(item.get("ask", 0)),
                last=float(item.get("last", 0)),
                volume=float(item.get("volume", 0)),
                timestamp=datetime.now(timezone.utc),
            )
            try:
                await self._on_tick(tick)
            except Exception as exc:
                logger.error("tick_callback_error", pair=symbol, error=str(exc))
