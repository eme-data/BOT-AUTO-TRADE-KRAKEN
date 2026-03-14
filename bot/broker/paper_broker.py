"""Paper (simulated) broker for paper trading mode.

Uses real Kraken market data for prices but executes all trades virtually
with simulated fills, fee tracking, and virtual balance management.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import structlog

from bot.broker.base import AbstractBroker
from bot.broker.kraken_rest import KrakenRestClient
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

# Simulated slippage applied to market fills
_SLIPPAGE_PCT = 0.0005  # 0.05%


class PaperBroker(AbstractBroker):
    """Simulated broker for paper trading. Tracks virtual positions and balance."""

    def __init__(
        self,
        initial_balance: float = 10_000.0,
        maker_fee: float = 0.0025,
        taker_fee: float = 0.004,
    ) -> None:
        self._balance = initial_balance
        self._initial_balance = initial_balance
        self._positions: dict[str, Position] = {}  # order_id -> Position
        self._order_counter = 0
        self._maker_fee = maker_fee
        self._taker_fee = taker_fee
        self._price_feed: dict[str, float] = {}  # pair -> last price
        self._real_broker: KrakenRestClient | None = None  # for market data only
        self._total_fees_paid = 0.0
        self._closed_pnl = 0.0

    # ── Lifecycle ──────────────────────────────────────

    async def connect(self) -> None:
        """Connect the real broker for market data (read-only)."""
        self._real_broker = KrakenRestClient()
        await self._real_broker.connect()
        logger.info(
            "paper_broker_connected",
            initial_balance=self._initial_balance,
            maker_fee=self._maker_fee,
            taker_fee=self._taker_fee,
        )

    async def disconnect(self) -> None:
        """Disconnect the underlying real broker."""
        if self._real_broker:
            await self._real_broker.disconnect()
        logger.info(
            "paper_broker_disconnected",
            final_balance=self._balance,
            total_fees=self._total_fees_paid,
            closed_pnl=self._closed_pnl,
        )

    @property
    def real_broker(self) -> KrakenRestClient:
        if self._real_broker is None:
            raise RuntimeError("PaperBroker not connected. Call connect() first.")
        return self._real_broker

    # ── Market data (delegated to real broker) ─────────

    async def get_ticker(self, pair: str) -> Tick:
        """Use real market data."""
        tick = await self.real_broker.get_ticker(pair)
        self._price_feed[pair] = tick.last
        return tick

    async def get_historical_prices(
        self,
        pair: str,
        interval_minutes: int = 60,
        since: int | None = None,
        limit: int = 500,
    ) -> list[OHLCV]:
        return await self.real_broker.get_historical_prices(
            pair, interval_minutes, since, limit
        )

    async def get_tradeable_pairs(self) -> list[dict]:
        return await self.real_broker.get_tradeable_pairs()

    # ── Trading (simulated) ────────────────────────────

    def _next_order_id(self) -> str:
        self._order_counter += 1
        return f"PAPER-{self._order_counter}-{int(time.time())}"

    def _apply_slippage(self, price: float, direction: Direction) -> float:
        """Apply slippage: worse price for the trader."""
        if direction == Direction.BUY:
            return price * (1 + _SLIPPAGE_PCT)
        return price * (1 - _SLIPPAGE_PCT)

    def _calculate_fee(self, notional: float) -> float:
        """Calculate taker fee on notional value (market orders)."""
        return notional * self._taker_fee

    async def open_position(self, order: OrderRequest) -> OrderResult:
        """Simulate order fill at current market price with slippage."""
        # Get current market price
        tick = await self.get_ticker(order.pair)
        fill_price = self._apply_slippage(tick.last, order.direction)

        notional = fill_price * order.size
        fee = self._calculate_fee(notional)

        # Check sufficient balance
        if notional + fee > self._balance:
            raise RuntimeError(
                f"Paper broker: insufficient balance. "
                f"Need {notional + fee:.2f}, have {self._balance:.2f}"
            )

        # Deduct from balance
        self._balance -= notional + fee
        self._total_fees_paid += fee

        order_id = self._next_order_id()

        # Track position
        position = Position(
            pair=order.pair,
            direction=order.direction,
            size=order.size,
            entry_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=0.0,
            stop_loss=None,
            take_profit=None,
            opened_at=datetime.now(timezone.utc),
            order_id=order_id,
            metadata={"status": "PAPER"},
        )
        self._positions[order_id] = position

        logger.info(
            "paper_order_opened",
            order_id=order_id,
            pair=order.pair,
            direction=order.direction.value,
            size=order.size,
            fill_price=fill_price,
            fee=fee,
            remaining_balance=self._balance,
        )

        return OrderResult(
            order_id=order_id,
            pair=order.pair,
            direction=order.direction,
            size=order.size,
            price=fill_price,
            status=OrderStatus.OPEN,
            fee=fee,
            raw={"paper": True, "slippage_applied": True},
        )

    async def close_position(
        self, order_id: str, pair: str, size: float
    ) -> OrderResult:
        """Close a virtual position and calculate P&L."""
        position = self._positions.get(order_id)
        if position is None:
            raise RuntimeError(
                f"Paper broker: position {order_id} not found"
            )

        # Get current market price
        tick = await self.get_ticker(pair)

        # Apply slippage in the closing direction (opposite of entry)
        close_direction = (
            Direction.SELL
            if position.direction == Direction.BUY
            else Direction.BUY
        )
        fill_price = self._apply_slippage(tick.last, close_direction)

        close_size = position.size if size == 0 else min(size, position.size)
        notional = fill_price * close_size
        fee = self._calculate_fee(notional)
        self._total_fees_paid += fee

        # Calculate P&L
        if position.direction == Direction.BUY:
            pnl = (fill_price - position.entry_price) * close_size
        else:
            pnl = (position.entry_price - fill_price) * close_size

        # Credit balance: return notional + pnl - fee
        # (original notional was already deducted on open)
        self._balance += notional - fee
        self._closed_pnl += pnl - fee

        # Remove position
        del self._positions[order_id]

        logger.info(
            "paper_position_closed",
            order_id=order_id,
            pair=pair,
            fill_price=fill_price,
            pnl=pnl,
            fee=fee,
            remaining_balance=self._balance,
        )

        return OrderResult(
            order_id=order_id,
            pair=pair,
            direction=close_direction,
            size=close_size,
            price=fill_price,
            status=OrderStatus.CLOSED,
            fee=fee,
            raw={"paper": True, "pnl": pnl},
        )

    async def get_open_positions(self) -> list[Position]:
        """Return tracked virtual positions with updated unrealized P&L."""
        for pos in self._positions.values():
            current_price = self._price_feed.get(pos.pair, pos.entry_price)
            pos.current_price = current_price
            if pos.direction == Direction.BUY:
                pos.unrealized_pnl = (current_price - pos.entry_price) * pos.size
            else:
                pos.unrealized_pnl = (pos.entry_price - current_price) * pos.size
        return list(self._positions.values())

    async def get_account_balance(self) -> AccountBalance:
        """Return virtual balance with unrealized P&L."""
        unrealized = sum(
            pos.unrealized_pnl for pos in self._positions.values()
        )

        # Margin used = sum of notional values of open positions
        margin_used = sum(
            pos.entry_price * pos.size for pos in self._positions.values()
        )

        return AccountBalance(
            total_balance=self._balance + margin_used + unrealized,
            available_balance=self._balance,
            margin_used=margin_used,
            unrealized_pnl=unrealized,
            currency="USD",
        )
