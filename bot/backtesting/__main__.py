"""CLI entry point: python -m bot.backtesting --strategy macd_trend --pair BTC/USD --days 90"""

from __future__ import annotations

import argparse
import asyncio

from bot.backtesting.runner import run_backtest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a backtest for a trading strategy on historical Kraken data."
    )
    parser.add_argument(
        "--strategy",
        type=str,
        required=True,
        help="Strategy name (e.g. macd_trend, rsi_mean_reversion)",
    )
    parser.add_argument(
        "--pair",
        type=str,
        default="BTC/USD",
        help="Trading pair (default: BTC/USD)",
    )
    parser.add_argument(
        "--timeframe",
        type=int,
        default=60,
        help="Candle interval in minutes (default: 60)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Number of days of history (default: 90)",
    )
    parser.add_argument(
        "--balance",
        type=float,
        default=10_000.0,
        help="Initial simulated balance in USD (default: 10000)",
    )

    args = parser.parse_args()

    asyncio.run(
        run_backtest(
            strategy_name=args.strategy,
            pair=args.pair,
            timeframe_minutes=args.timeframe,
            days=args.days,
            initial_balance=args.balance,
        )
    )


if __name__ == "__main__":
    main()
