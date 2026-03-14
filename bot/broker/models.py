"""Data models for broker interactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop-loss"
    TAKE_PROFIT = "take-profit"


class OrderStatus(str, Enum):
    PENDING = "pending"
    OPEN = "open"
    CLOSED = "closed"
    CANCELED = "canceled"
    EXPIRED = "expired"


@dataclass
class Tick:
    pair: str
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass
class OHLCV:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class OrderRequest:
    pair: str
    direction: Direction
    size: float
    order_type: OrderType = OrderType.MARKET
    price: float | None = None
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderResult:
    order_id: str
    pair: str
    direction: Direction
    size: float
    price: float
    status: OrderStatus
    timestamp: datetime = field(default_factory=datetime.utcnow)
    fee: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class Position:
    pair: str
    direction: Direction
    size: float
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss: float | None = None
    take_profit: float | None = None
    opened_at: datetime = field(default_factory=datetime.utcnow)
    order_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        if self.direction == Direction.BUY:
            return ((self.current_price - self.entry_price) / self.entry_price) * 100
        return ((self.entry_price - self.current_price) / self.entry_price) * 100


@dataclass
class AccountBalance:
    total_balance: float = 0.0
    available_balance: float = 0.0
    margin_used: float = 0.0
    unrealized_pnl: float = 0.0
    currency: str = "USD"
