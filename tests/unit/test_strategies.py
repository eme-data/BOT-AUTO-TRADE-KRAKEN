"""Unit tests for trading strategies."""

import pandas as pd
import numpy as np
import pytest

from bot.strategies.macd_trend import MACDTrendStrategy
from bot.strategies.rsi_mean_reversion import RSIMeanReversionStrategy
from bot.strategies.base import SignalType


def _make_df(n: int = 120, trend: str = "up") -> pd.DataFrame:
    """Create a synthetic OHLCV DataFrame with indicators."""
    np.random.seed(42)
    base = 100.0
    prices = []
    for i in range(n):
        if trend == "up":
            base += np.random.normal(0.1, 0.5)
        elif trend == "down":
            base -= np.random.normal(0.1, 0.5)
        else:
            base += np.random.normal(0.0, 0.5)
        prices.append(max(base, 1.0))

    close = pd.Series(prices)
    df = pd.DataFrame(
        {
            "open": close - np.random.uniform(0, 0.5, n),
            "high": close + np.random.uniform(0, 1, n),
            "low": close - np.random.uniform(0, 1, n),
            "close": close,
            "volume": np.random.uniform(100, 1000, n),
        }
    )

    # Add minimal indicators
    from bot.data.indicators import add_all_indicators
    df = add_all_indicators(df)
    return df


class TestMACDTrend:
    def test_no_signal_on_insufficient_data(self):
        strategy = MACDTrendStrategy()
        df = _make_df(n=30)
        signal = strategy.on_bar("BTC/USD", df)
        assert signal is None

    def test_returns_signal_or_none(self):
        strategy = MACDTrendStrategy()
        df = _make_df(n=120, trend="up")
        signal = strategy.on_bar("BTC/USD", df)
        if signal is not None:
            assert signal.signal_type in (SignalType.BUY, SignalType.SELL)
            assert signal.pair == "BTC/USD"
            assert signal.confidence >= 0

    def test_config(self):
        strategy = MACDTrendStrategy(atr_stop_multiplier=3.0)
        config = strategy.get_config()
        assert config["atr_stop_multiplier"] == 3.0


class TestRSIMeanReversion:
    def test_no_signal_on_insufficient_data(self):
        strategy = RSIMeanReversionStrategy()
        df = _make_df(n=100)
        signal = strategy.on_bar("ETH/USD", df)
        assert signal is None

    def test_returns_signal_or_none(self):
        strategy = RSIMeanReversionStrategy()
        df = _make_df(n=260, trend="up")
        signal = strategy.on_bar("ETH/USD", df)
        if signal is not None:
            assert signal.signal_type in (SignalType.BUY, SignalType.SELL)

    def test_config(self):
        strategy = RSIMeanReversionStrategy(rsi_oversold=25.0)
        assert strategy.get_config()["rsi_oversold"] == 25.0
