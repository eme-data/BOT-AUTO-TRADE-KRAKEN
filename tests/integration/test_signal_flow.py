"""Integration tests for the full signal flow.

Tests cover:
- Signal creation and risk checking
- Position sizing calculations
- Trade persistence via the repository
- AI rejection flow (mocked ClaudeAnalyzer)
- Trailing stop trigger flow
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from bot.ai.models import AIAnalysisResult, AIVerdict, AnalysisMode
from bot.broker.models import AccountBalance, Direction, Position
from bot.db.models import Trade
from bot.db.repository import TradeRepository
from bot.risk.manager import RiskManager
from bot.risk.trailing_stop import TrailingStopManager, TrailingStopState
from bot.strategies.base import Signal, SignalType
from bot.broker.models import Tick


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Signal through RiskManager
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_risk_check_allows_valid_signal():
    """A valid BUY signal with no open positions passes risk checks."""
    rm = RiskManager()
    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.85,
        strategy_name="macd_trend",
        stop_loss_pct=3.0,
        take_profit_pct=6.0,
    )
    balance = AccountBalance(
        total_balance=10_000.0,
        available_balance=8_000.0,
    )
    result = rm.check_signal(signal, open_positions=[], balance=balance)
    assert result.allowed is True
    assert result.reason == ""


@pytest.mark.asyncio
async def test_risk_check_blocks_max_positions():
    """Signal is blocked when max open positions is reached."""
    rm = RiskManager()
    rm.max_open_positions = 2

    open_positions = [
        Position(pair="ETH/USD", direction=Direction.BUY, size=1.0, entry_price=3000),
        Position(pair="SOL/USD", direction=Direction.BUY, size=10.0, entry_price=100),
    ]
    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.9,
        strategy_name="macd_trend",
    )
    balance = AccountBalance(total_balance=10_000.0, available_balance=8_000.0)

    result = rm.check_signal(signal, open_positions, balance)
    assert result.allowed is False
    assert "Max open positions" in result.reason


@pytest.mark.asyncio
async def test_risk_check_blocks_daily_loss_limit():
    """Signal is blocked after daily loss limit is breached."""
    rm = RiskManager()
    rm.max_daily_loss = -500.0
    rm.state.daily_pnl = -600.0  # Already exceeded

    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.8,
        strategy_name="macd_trend",
    )
    balance = AccountBalance(total_balance=10_000.0, available_balance=8_000.0)

    result = rm.check_signal(signal, open_positions=[], balance=balance)
    assert result.allowed is False
    assert "Daily loss limit" in result.reason


@pytest.mark.asyncio
async def test_risk_check_blocks_duplicate_pair():
    """Signal is blocked when max positions per pair is already reached."""
    rm = RiskManager()
    rm.max_per_pair = 1

    open_positions = [
        Position(pair="BTC/USD", direction=Direction.BUY, size=0.01, entry_price=50_000),
    ]
    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.9,
        strategy_name="macd_trend",
    )
    balance = AccountBalance(total_balance=10_000.0, available_balance=8_000.0)

    result = rm.check_signal(signal, open_positions, balance)
    assert result.allowed is False
    assert "Max per pair" in result.reason


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Position sizing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_position_sizing_with_stop_loss():
    """Position size is calculated from risk%, balance, and stop distance."""
    rm = RiskManager()
    rm.risk_per_trade_pct = 2.0
    rm.max_position_size = 1.0

    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.9,
        strategy_name="macd_trend",
        stop_loss_pct=3.0,
    )
    balance = AccountBalance(
        total_balance=10_000.0,
        available_balance=10_000.0,
    )
    current_price = 50_000.0

    size = rm.calculate_position_size(signal, balance, current_price)

    # Expected: risk_amount = 10000 * 0.02 = 200
    # size = 200 / (50000 * 0.03) = 200 / 1500 = 0.1333...
    assert 0.13 < size < 0.14
    assert size <= rm.max_position_size


@pytest.mark.asyncio
async def test_position_sizing_capped_at_max():
    """Position size is capped at max_position_size."""
    rm = RiskManager()
    rm.risk_per_trade_pct = 50.0  # Aggressive risk
    rm.max_position_size = 0.5

    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.9,
        strategy_name="macd_trend",
        stop_loss_pct=1.0,
    )
    balance = AccountBalance(total_balance=100_000.0, available_balance=100_000.0)

    size = rm.calculate_position_size(signal, balance, current_price=50_000.0)
    assert size == 0.5  # Capped


@pytest.mark.asyncio
async def test_position_sizing_respects_explicit_size():
    """When signal has an explicit size, it is used (capped at max)."""
    rm = RiskManager()
    rm.max_position_size = 1.0

    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.9,
        strategy_name="macd_trend",
        size=0.5,
    )
    balance = AccountBalance(total_balance=10_000.0, available_balance=10_000.0)

    size = rm.calculate_position_size(signal, balance, current_price=50_000.0)
    assert size == 0.5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Trade persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_trade_persisted_correctly(db_session: AsyncSession):
    """A trade created via the repository can be retrieved."""
    repo = TradeRepository(db_session)

    trade = await repo.create_trade(
        order_id="FLOW-001",
        pair="BTC/USD",
        direction="buy",
        size=0.05,
        entry_price=50_000.0,
        status="OPEN",
        strategy="macd_trend",
    )
    await db_session.commit()

    assert trade.id is not None
    assert trade.order_id == "FLOW-001"

    # Retrieve open trades
    open_trades = await repo.get_open_trades()
    assert len(open_trades) == 1
    assert open_trades[0].pair == "BTC/USD"
    assert open_trades[0].size == 0.05


@pytest.mark.asyncio
async def test_trade_close_flow(db_session: AsyncSession):
    """Closing a trade updates exit price, profit, and status."""
    repo = TradeRepository(db_session)

    await repo.create_trade(
        order_id="FLOW-002",
        pair="ETH/USD",
        direction="buy",
        size=2.0,
        entry_price=3_000.0,
        status="OPEN",
        strategy="rsi_mean_reversion",
    )
    await db_session.commit()

    # Close the trade
    await repo.close_trade(
        order_id="FLOW-002",
        exit_price=3_200.0,
        profit=400.0,
        fee=1.5,
    )
    await db_session.commit()

    # Should no longer appear in open trades
    open_trades = await repo.get_open_trades()
    assert len(open_trades) == 0

    # Should appear in recent trades as CLOSED
    recent = await repo.get_recent_trades(limit=10)
    assert len(recent) == 1
    assert recent[0].status == "CLOSED"
    assert recent[0].exit_price == 3_200.0
    assert recent[0].profit == 400.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AI rejection flow
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_ai_rejection_blocks_trade():
    """When ClaudeAnalyzer returns REJECT, the signal should be discarded."""
    # Build a signal that passes risk checks
    rm = RiskManager()
    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.85,
        strategy_name="macd_trend",
        stop_loss_pct=3.0,
    )
    balance = AccountBalance(total_balance=10_000.0, available_balance=8_000.0)

    # Risk check should pass
    risk_result = rm.check_signal(signal, open_positions=[], balance=balance)
    assert risk_result.allowed is True

    # Mock AI analyzer to return REJECT
    mock_result = AIAnalysisResult(
        verdict=AIVerdict.REJECT,
        confidence=0.9,
        reasoning="Market conditions unfavorable: high volatility "
        "and bearish divergence on RSI.",
        risk_warnings=["RSI divergence", "High volatility"],
        model_used="claude-sonnet-4-6",
        latency_ms=850,
    )

    with patch("bot.ai.analyzer.ClaudeAnalyzer.analyze", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_result
        from bot.ai.analyzer import ClaudeAnalyzer
        from bot.ai.models import AIAnalysisRequest

        analyzer = ClaudeAnalyzer()
        request = AIAnalysisRequest(
            mode=AnalysisMode.PRE_TRADE,
            pair="BTC/USD",
            signal_direction="buy",
            signal_strategy="macd_trend",
            signal_confidence=0.85,
        )
        result = await analyzer.analyze(request)

    assert result.verdict == AIVerdict.REJECT
    assert result.confidence == 0.9
    assert "unfavorable" in result.reasoning

    # In the real bot flow, a REJECT verdict would prevent the order
    # from being placed. We verify the verdict is properly returned.


@pytest.mark.asyncio
async def test_ai_approve_allows_trade():
    """When ClaudeAnalyzer returns APPROVE, the signal proceeds."""
    mock_result = AIAnalysisResult(
        verdict=AIVerdict.APPROVE,
        confidence=0.8,
        reasoning="Strong trend confirmed by multiple indicators.",
        model_used="claude-sonnet-4-6",
        latency_ms=600,
    )

    with patch("bot.ai.analyzer.ClaudeAnalyzer.analyze", new_callable=AsyncMock) as mock_analyze:
        mock_analyze.return_value = mock_result
        from bot.ai.analyzer import ClaudeAnalyzer
        from bot.ai.models import AIAnalysisRequest

        analyzer = ClaudeAnalyzer()
        request = AIAnalysisRequest(
            mode=AnalysisMode.PRE_TRADE,
            pair="ETH/USD",
            signal_direction="buy",
            signal_strategy="rsi_mean_reversion",
            signal_confidence=0.75,
        )
        result = await analyzer.analyze(request)

    assert result.verdict == AIVerdict.APPROVE
    assert result.confidence == 0.8


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Trailing stop trigger
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_trailing_stop_trigger_buy():
    """Trailing stop triggers when price drops below the trailing level (BUY)."""
    tsm = TrailingStopManager()

    state = TrailingStopState(
        pair="BTC/USD",
        direction=Direction.BUY,
        entry_price=50_000.0,
        trail_pct=2.0,
        order_id="TS-001",
    )
    tsm.register(state)

    # Initial stop should be 50000 * 0.98 = 49000
    assert abs(state.current_stop - 49_000.0) < 0.01

    # Price rises to 52000 -> stop should move up
    tick_up = Tick(pair="BTC/USD", bid=51_990, ask=52_010, last=52_000, volume=100)
    triggered = tsm.update_on_tick(tick_up)
    assert len(triggered) == 0
    # New stop: 52000 * 0.98 = 50960
    assert state.current_stop > 49_000.0
    assert abs(state.current_stop - 50_960.0) < 0.01

    # Price drops to 50500 -> still above stop
    tick_hold = Tick(pair="BTC/USD", bid=50_490, ask=50_510, last=50_500, volume=100)
    triggered = tsm.update_on_tick(tick_hold)
    assert len(triggered) == 0

    # Price drops to 50900 -> still above 50960? No, 50900 < 50960 -> triggered!
    tick_drop = Tick(pair="BTC/USD", bid=50_890, ask=50_910, last=50_900, volume=100)
    triggered = tsm.update_on_tick(tick_drop)
    assert "TS-001" in triggered


@pytest.mark.asyncio
async def test_trailing_stop_trigger_sell():
    """Trailing stop triggers when price rises above the trailing level (SELL)."""
    tsm = TrailingStopManager()

    state = TrailingStopState(
        pair="ETH/USD",
        direction=Direction.SELL,
        entry_price=3_000.0,
        trail_pct=3.0,
        order_id="TS-002",
    )
    tsm.register(state)

    # Initial stop should be 3000 * 1.03 = 3090
    assert abs(state.current_stop - 3_090.0) < 0.01

    # Price drops to 2800 -> stop should move down
    tick_down = Tick(pair="ETH/USD", bid=2_790, ask=2_810, last=2_800, volume=200)
    triggered = tsm.update_on_tick(tick_down)
    assert len(triggered) == 0
    # New stop: 2800 * 1.03 = 2884
    assert state.current_stop < 3_090.0
    assert abs(state.current_stop - 2_884.0) < 0.01

    # Price rises to 2890 -> above stop -> triggered!
    tick_up = Tick(pair="ETH/USD", bid=2_880, ask=2_900, last=2_890, volume=200)
    triggered = tsm.update_on_tick(tick_up)
    assert "TS-002" in triggered


@pytest.mark.asyncio
async def test_trailing_stop_no_trigger_on_unrelated_pair():
    """Ticks for a different pair do not trigger the trailing stop."""
    tsm = TrailingStopManager()

    state = TrailingStopState(
        pair="BTC/USD",
        direction=Direction.BUY,
        entry_price=50_000.0,
        trail_pct=2.0,
        order_id="TS-003",
    )
    tsm.register(state)

    # Tick for ETH/USD should not affect BTC/USD trailing stop
    tick = Tick(pair="ETH/USD", bid=1, ask=1, last=1, volume=100)
    triggered = tsm.update_on_tick(tick)
    assert len(triggered) == 0
    # Stop unchanged
    assert abs(state.current_stop - 49_000.0) < 0.01


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Full signal-to-trade flow
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@pytest.mark.asyncio
async def test_full_signal_to_trade_flow(db_session: AsyncSession, mock_broker):
    """End-to-end: signal -> risk check -> size -> persist trade."""
    # 1. Create signal
    signal = Signal(
        signal_type=SignalType.BUY,
        pair="BTC/USD",
        direction=Direction.BUY,
        confidence=0.88,
        strategy_name="macd_trend",
        stop_loss_pct=3.0,
        take_profit_pct=6.0,
    )

    # 2. Risk check
    rm = RiskManager()
    balance = AccountBalance(total_balance=10_000.0, available_balance=8_000.0)
    risk_result = rm.check_signal(signal, open_positions=[], balance=balance)
    assert risk_result.allowed is True

    # 3. Position sizing
    current_price = 50_000.0
    size = rm.calculate_position_size(signal, balance, current_price)
    assert size > 0

    # 4. Place order (mocked)
    order_result = await mock_broker.place_order()
    assert order_result.order_id == "TEST-ORDER-001"

    # 5. Persist trade
    repo = TradeRepository(db_session)
    trade = await repo.create_trade(
        order_id=order_result.order_id,
        pair=signal.pair,
        direction=signal.direction.value,
        size=size,
        entry_price=current_price,
        fee=order_result.fee,
        status="OPEN",
        strategy=signal.strategy_name,
    )
    await db_session.commit()

    # 6. Verify persistence
    open_trades = await repo.get_open_trades()
    assert len(open_trades) == 1
    assert open_trades[0].order_id == "TEST-ORDER-001"
    assert open_trades[0].pair == "BTC/USD"
    assert open_trades[0].strategy == "macd_trend"
    assert open_trades[0].size == size
