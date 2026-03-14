"""Trailing stop manager – adjusts stops on real-time ticks."""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from bot.broker.models import Direction, Tick

logger = structlog.get_logger(__name__)


@dataclass
class TrailingStopState:
    pair: str
    direction: Direction
    entry_price: float
    trail_pct: float  # trailing distance as percentage
    highest: float = 0.0
    lowest: float = float("inf")
    current_stop: float = 0.0
    order_id: str = ""

    def __post_init__(self) -> None:
        if self.direction == Direction.BUY:
            self.highest = self.entry_price
            self.current_stop = self.entry_price * (1 - self.trail_pct / 100)
        else:
            self.lowest = self.entry_price
            self.current_stop = self.entry_price * (1 + self.trail_pct / 100)


class TrailingStopManager:
    """Tracks and updates trailing stops for open positions."""

    def __init__(self) -> None:
        self._stops: dict[str, TrailingStopState] = {}  # order_id -> state

    def register(self, state: TrailingStopState) -> None:
        self._stops[state.order_id] = state
        logger.info(
            "trailing_stop_registered",
            order_id=state.order_id,
            pair=state.pair,
            trail_pct=state.trail_pct,
            initial_stop=state.current_stop,
        )

    def unregister(self, order_id: str) -> None:
        self._stops.pop(order_id, None)

    def update_on_tick(self, tick: Tick) -> list[str]:
        """Update trailing stops on tick. Returns list of order_ids that were hit."""
        triggered: list[str] = []

        for order_id, state in list(self._stops.items()):
            if state.pair != tick.pair:
                continue

            price = tick.last
            updated = False

            if state.direction == Direction.BUY:
                if price > state.highest:
                    state.highest = price
                    new_stop = price * (1 - state.trail_pct / 100)
                    if new_stop > state.current_stop:
                        state.current_stop = new_stop
                        updated = True
                if price <= state.current_stop:
                    triggered.append(order_id)

            else:  # SELL
                if price < state.lowest:
                    state.lowest = price
                    new_stop = price * (1 + state.trail_pct / 100)
                    if new_stop < state.current_stop:
                        state.current_stop = new_stop
                        updated = True
                if price >= state.current_stop:
                    triggered.append(order_id)

            if updated:
                logger.debug(
                    "trailing_stop_moved",
                    order_id=order_id,
                    new_stop=state.current_stop,
                    price=price,
                )

        return triggered

    def get_stop(self, order_id: str) -> TrailingStopState | None:
        return self._stops.get(order_id)

    @property
    def active_stops(self) -> dict[str, TrailingStopState]:
        return dict(self._stops)
