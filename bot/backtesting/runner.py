"""CLI runner for backtesting strategies against historical Kraken data."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pandas as pd

from bot.backtesting.engine import BacktestEngine
from bot.backtesting.models import BacktestResult
from bot.broker.kraken_rest import KrakenRestClient
from bot.data.indicators import add_all_indicators
from bot.strategies.registry import STRATEGY_CLASSES


async def run_backtest(
    strategy_name: str,
    pair: str = "BTC/USD",
    timeframe_minutes: int = 60,
    days: int = 90,
    initial_balance: float = 10_000.0,
) -> BacktestResult:
    """Fetch historical data, run strategy backtest, and print results.

    Parameters
    ----------
    strategy_name:
        Key in STRATEGY_CLASSES (e.g. "macd_trend").
    pair:
        Trading pair symbol (e.g. "BTC/USD").
    timeframe_minutes:
        Candle interval in minutes (e.g. 60 for 1h bars).
    days:
        Number of days of historical data to fetch.
    initial_balance:
        Starting simulated balance in USD.
    """
    # ── Resolve strategy ──
    if strategy_name not in STRATEGY_CLASSES:
        available = ", ".join(sorted(STRATEGY_CLASSES.keys()))
        raise ValueError(
            f"Unknown strategy '{strategy_name}'. Available: {available}"
        )
    strategy = STRATEGY_CLASSES[strategy_name]()

    # ── Fetch historical data ──
    client = KrakenRestClient()
    try:
        await client.connect()

        # Calculate how many candles we need
        candles_per_day = (24 * 60) // timeframe_minutes
        limit = candles_per_day * days

        # Kraken has a max of 720 candles per request, so paginate
        all_ohlcv = []
        since_ms: int | None = int(
            (datetime.now(timezone.utc).timestamp() - days * 86400) * 1000
        )
        batch_limit = 720

        while len(all_ohlcv) < limit:
            batch = await client.get_historical_prices(
                pair,
                interval_minutes=timeframe_minutes,
                since=since_ms,
                limit=batch_limit,
            )
            if not batch:
                break
            all_ohlcv.extend(batch)
            # Move since forward past the last candle
            last_ts = batch[-1].timestamp
            since_ms = int(last_ts.timestamp() * 1000) + 1
            if len(batch) < batch_limit:
                break  # No more data available

        if not all_ohlcv:
            raise RuntimeError(f"No historical data returned for {pair}")

        # De-duplicate by timestamp
        seen = set()
        unique_ohlcv = []
        for bar in all_ohlcv:
            ts = bar.timestamp
            if ts not in seen:
                seen.add(ts)
                unique_ohlcv.append(bar)

        # Build DataFrame
        df = pd.DataFrame(
            [
                {
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in unique_ohlcv
            ]
        )
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)

    finally:
        await client.disconnect()

    # ── Add indicators ──
    df = add_all_indicators(df)

    # ── Run backtest ──
    engine = BacktestEngine(
        strategy=strategy,
        initial_balance=initial_balance,
        maker_fee=0.0016,
        taker_fee=0.0026,
        slippage=0.0005,
    )
    result = engine.run(df, pair)

    # ── Print results ──
    _print_results(result, strategy_name, pair, timeframe_minutes, days)

    return result


def _print_results(
    result: BacktestResult,
    strategy_name: str,
    pair: str,
    timeframe_minutes: int,
    days: int,
) -> None:
    """Print a formatted results table to stdout."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  BACKTEST RESULTS")
    print(f"{sep}")
    print(f"  Strategy:       {strategy_name}")
    print(f"  Pair:           {pair}")
    print(f"  Timeframe:      {timeframe_minutes}m")
    print(f"  Period:         {days} days")
    print(f"{sep}")
    print(f"  Total Return:   {result.total_return:+.2f}%")
    print(f"  Sharpe Ratio:   {result.sharpe_ratio:.2f}")
    print(f"  Max Drawdown:   {result.max_drawdown:.2f}%")
    print(f"{'-' * 60}")
    print(f"  Total Trades:   {result.total_trades}")
    print(f"  Win Rate:       {result.win_rate:.1%}")
    print(f"  Profit Factor:  {result.profit_factor:.2f}")
    print(f"  Winning Trades: {result.winning_trades}")
    print(f"  Losing Trades:  {result.losing_trades}")
    print(f"  Avg Win:        ${result.avg_win:.2f}")
    print(f"  Avg Loss:       ${result.avg_loss:.2f}")
    print(f"{sep}")

    if result.trades:
        print(f"\n  Last 10 Trades:")
        print(f"  {'Dir':<5} {'Entry':>10} {'Exit':>10} {'PnL':>10} {'PnL%':>8} {'Fee':>8}")
        print(f"  {'-' * 55}")
        for trade in result.trades[-10:]:
            print(
                f"  {trade.direction:<5} "
                f"{trade.entry_price:>10.2f} "
                f"{trade.exit_price:>10.2f} "
                f"{trade.pnl:>+10.2f} "
                f"{trade.pnl_pct:>+7.2f}% "
                f"{trade.fee:>8.2f}"
            )
    print()
