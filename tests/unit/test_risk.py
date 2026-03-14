"""Unit tests for risk management."""

import pytest

from bot.broker.models import AccountBalance, Direction, Position
from bot.risk.manager import RiskManager
from bot.strategies.base import Signal, SignalType


def _make_signal(pair: str = "BTC/USD", direction: Direction = Direction.BUY) -> Signal:
    return Signal(
        signal_type=SignalType.BUY,
        pair=pair,
        direction=direction,
        confidence=0.8,
        strategy_name="test",
        stop_loss_pct=3.0,
        take_profit_pct=6.0,
    )


def _make_balance(available: float = 10000.0) -> AccountBalance:
    return AccountBalance(
        total_balance=available, available_balance=available
    )


class TestRiskManager:
    def test_allows_valid_signal(self):
        rm = RiskManager()
        check = rm.check_signal(_make_signal(), [], _make_balance())
        assert check.allowed

    def test_blocks_on_max_positions(self):
        rm = RiskManager()
        rm.max_open_positions = 1
        positions = [
            Position(pair="ETH/USD", direction=Direction.BUY, size=0.5, entry_price=3000)
        ]
        check = rm.check_signal(_make_signal(), positions, _make_balance())
        assert not check.allowed
        assert "Max open positions" in check.reason

    def test_blocks_duplicate_pair(self):
        rm = RiskManager()
        rm.max_per_pair = 1
        positions = [
            Position(pair="BTC/USD", direction=Direction.BUY, size=0.1, entry_price=50000)
        ]
        check = rm.check_signal(_make_signal(), positions, _make_balance())
        assert not check.allowed

    def test_blocks_opposite_direction(self):
        rm = RiskManager()
        positions = [
            Position(pair="BTC/USD", direction=Direction.SELL, size=0.1, entry_price=50000)
        ]
        check = rm.check_signal(_make_signal(), positions, _make_balance())
        assert not check.allowed
        assert "Opposite" in check.reason

    def test_emergency_stop_on_daily_loss(self):
        rm = RiskManager()
        rm.max_daily_loss = -100.0
        rm.state.daily_pnl = -150.0
        check = rm.check_signal(_make_signal(), [], _make_balance())
        assert not check.allowed
        assert rm.state.emergency_stop

    def test_position_size_calculation(self):
        rm = RiskManager()
        signal = _make_signal()
        balance = _make_balance(10000.0)
        size = rm.calculate_position_size(signal, balance, 50000.0)
        # risk_amount = 10000 * 2% = 200
        # size = 200 / (50000 * 3%) = 200 / 1500 ≈ 0.133
        assert 0.1 < size < 0.2

    def test_correlation_block(self):
        rm = RiskManager()
        positions = [
            Position(pair="BTC/USD", direction=Direction.BUY, size=0.1, entry_price=50000)
        ]
        signal = _make_signal(pair="BTC/EUR", direction=Direction.BUY)
        check = rm.check_signal(signal, positions, _make_balance())
        assert not check.allowed
        assert "Correlated" in check.reason
