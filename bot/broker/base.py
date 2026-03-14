"""Abstract broker interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from bot.broker.models import (
    AccountBalance,
    OHLCV,
    OrderRequest,
    OrderResult,
    Position,
    Tick,
)


class AbstractBroker(ABC):
    """Interface that all broker implementations must follow."""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the exchange."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully close all connections."""

    @abstractmethod
    async def get_ticker(self, pair: str) -> Tick:
        """Get current ticker for a pair."""

    @abstractmethod
    async def get_historical_prices(
        self, pair: str, interval_minutes: int, since: int | None = None
    ) -> list[OHLCV]:
        """Fetch historical OHLCV bars."""

    @abstractmethod
    async def open_position(self, order: OrderRequest) -> OrderResult:
        """Submit a new order."""

    @abstractmethod
    async def close_position(self, order_id: str, pair: str, size: float) -> OrderResult:
        """Close an open position."""

    @abstractmethod
    async def get_open_positions(self) -> list[Position]:
        """Return all currently open positions."""

    @abstractmethod
    async def get_account_balance(self) -> AccountBalance:
        """Return account balance info."""

    @abstractmethod
    async def get_tradeable_pairs(self) -> list[dict]:
        """Return list of tradeable pairs with info."""
