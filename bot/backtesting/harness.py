"""Automated multi-strategy × multi-pair backtest harness.

Runs every active strategy against a basket of Kraken pairs and produces
a pass/fail report so the user can objectively decide which strategies
belong in production.

Pass thresholds (per strategy, aggregated across pairs):
  - Annualized Sharpe >= 1.0
  - Profit factor    >= 1.3
  - Max drawdown     <= 20%
  - Total trades     >= 20  (statistical significance)

A strategy is considered "production-ready" only when at least 60% of
the tested pairs pass all thresholds.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import structlog

from bot.backtesting.engine import BacktestEngine
from bot.backtesting.models import BacktestResult
from bot.broker.kraken_rest import KrakenRestClient
from bot.data.indicators import add_all_indicators
from bot.strategies.registry import STRATEGY_CLASSES

logger = structlog.get_logger(__name__)


# ── Defaults ──────────────────────────────────────────

DEFAULT_STRATEGIES: tuple[str, ...] = (
    "macd_trend",
    "rsi_mean_reversion",
    "trend_follower",
    "scalper",
)

DEFAULT_PAIRS: tuple[str, ...] = (
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "ADA/USD",
    "DOT/USD",
    "LINK/USD",
    "AVAX/USD",
    "LTC/USD",
    "DOGE/USD",
)

# Kraken tier-0 taker fee and a realistic slippage estimate for alt pairs.
DEFAULT_TAKER_FEE = 0.004
DEFAULT_MAKER_FEE = 0.0025
DEFAULT_SLIPPAGE = 0.0015

# Pass/fail thresholds
MIN_SHARPE = 1.0
MIN_PROFIT_FACTOR = 1.3
MAX_DRAWDOWN_PCT = 20.0
MIN_TRADES = 20
MIN_PAIRS_PASSING_PCT = 0.60


# ── Dataclasses ───────────────────────────────────────


@dataclass
class HarnessRun:
    """Single (strategy, pair) result."""

    strategy: str
    pair: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_win: float
    avg_loss: float
    passed: bool
    failure_reasons: list[str]


@dataclass
class StrategyVerdict:
    """Aggregated verdict for a strategy across all tested pairs."""

    strategy: str
    pairs_tested: int
    pairs_passed: int
    pass_rate: float
    avg_sharpe: float
    avg_profit_factor: float
    avg_max_drawdown: float
    avg_total_return: float
    avg_trades: float
    production_ready: bool
    best_pair: str
    worst_pair: str


@dataclass
class HarnessReport:
    """Top-level report written to disk."""

    generated_at: str
    config: dict
    runs: list[HarnessRun]
    verdicts: list[StrategyVerdict]


# ── Core harness ──────────────────────────────────────


def _evaluate_run(result: BacktestResult) -> tuple[bool, list[str]]:
    """Apply pass/fail thresholds to a single backtest result."""
    reasons: list[str] = []
    if result.total_trades < MIN_TRADES:
        reasons.append(f"trades<{MIN_TRADES} ({result.total_trades})")
    if result.sharpe_ratio < MIN_SHARPE:
        reasons.append(f"sharpe<{MIN_SHARPE} ({result.sharpe_ratio:.2f})")
    if result.profit_factor < MIN_PROFIT_FACTOR:
        reasons.append(f"PF<{MIN_PROFIT_FACTOR} ({result.profit_factor:.2f})")
    if result.max_drawdown > MAX_DRAWDOWN_PCT:
        reasons.append(f"maxDD>{MAX_DRAWDOWN_PCT}% ({result.max_drawdown:.1f})")
    return (not reasons), reasons


async def _fetch_pair_bars(
    client: KrakenRestClient,
    pair: str,
    timeframe_minutes: int,
    days: int,
) -> pd.DataFrame:
    """Fetch OHLCV bars, paginated to bypass Kraken's 720-candle limit."""
    candles_per_day = (24 * 60) // timeframe_minutes
    target = candles_per_day * days

    all_bars = []
    since_ms: int | None = int(
        (datetime.now(timezone.utc).timestamp() - days * 86400) * 1000
    )
    batch_limit = 720

    while len(all_bars) < target:
        batch = await client.get_historical_prices(
            pair,
            interval_minutes=timeframe_minutes,
            since=since_ms,
            limit=batch_limit,
        )
        if not batch:
            break
        all_bars.extend(batch)
        since_ms = int(batch[-1].timestamp.timestamp() * 1000) + 1
        if len(batch) < batch_limit:
            break

    if not all_bars:
        return pd.DataFrame()

    # De-duplicate by timestamp (Kraken sometimes repeats the last candle)
    seen = set()
    unique = []
    for b in all_bars:
        if b.timestamp not in seen:
            seen.add(b.timestamp)
            unique.append(b)

    df = pd.DataFrame(
        [
            {
                "timestamp": b.timestamp,
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
            }
            for b in unique
        ]
    )
    df.set_index("timestamp", inplace=True)
    df.sort_index(inplace=True)
    return df


def _build_verdict(strategy: str, runs: list[HarnessRun]) -> StrategyVerdict:
    """Aggregate runs into a per-strategy verdict."""
    if not runs:
        return StrategyVerdict(
            strategy=strategy, pairs_tested=0, pairs_passed=0, pass_rate=0.0,
            avg_sharpe=0.0, avg_profit_factor=0.0, avg_max_drawdown=0.0,
            avg_total_return=0.0, avg_trades=0.0, production_ready=False,
            best_pair="", worst_pair="",
        )

    passed = [r for r in runs if r.passed]
    pass_rate = len(passed) / len(runs)

    # Filter out infinity profit factors (all-winners edge case) for avg stability
    finite_pf = [r.profit_factor for r in runs if r.profit_factor != float("inf")]

    by_return = sorted(runs, key=lambda r: r.total_return, reverse=True)

    return StrategyVerdict(
        strategy=strategy,
        pairs_tested=len(runs),
        pairs_passed=len(passed),
        pass_rate=pass_rate,
        avg_sharpe=sum(r.sharpe_ratio for r in runs) / len(runs),
        avg_profit_factor=(
            sum(finite_pf) / len(finite_pf) if finite_pf else 0.0
        ),
        avg_max_drawdown=sum(r.max_drawdown for r in runs) / len(runs),
        avg_total_return=sum(r.total_return for r in runs) / len(runs),
        avg_trades=sum(r.total_trades for r in runs) / len(runs),
        production_ready=pass_rate >= MIN_PAIRS_PASSING_PCT,
        best_pair=by_return[0].pair,
        worst_pair=by_return[-1].pair,
    )


async def run_harness(
    strategies: tuple[str, ...] = DEFAULT_STRATEGIES,
    pairs: tuple[str, ...] = DEFAULT_PAIRS,
    timeframe_minutes: int = 60,
    days: int = 180,
    initial_balance: float = 1000.0,
    taker_fee: float = DEFAULT_TAKER_FEE,
    maker_fee: float = DEFAULT_MAKER_FEE,
    slippage: float = DEFAULT_SLIPPAGE,
    output_path: Path | None = None,
) -> HarnessReport:
    """Run every (strategy, pair) combo and return a consolidated report."""
    unknown = [s for s in strategies if s not in STRATEGY_CLASSES]
    if unknown:
        raise ValueError(
            f"Unknown strategies: {unknown}. "
            f"Available: {sorted(STRATEGY_CLASSES.keys())}"
        )

    # ── Fetch bars for every pair once (cache in memory) ──
    client = KrakenRestClient()
    pair_bars: dict[str, pd.DataFrame] = {}
    try:
        await client.connect()
        for pair in pairs:
            try:
                logger.info("harness_fetch_start", pair=pair, days=days)
                df = await _fetch_pair_bars(client, pair, timeframe_minutes, days)
                if df.empty:
                    logger.warning("harness_no_data", pair=pair)
                    continue
                pair_bars[pair] = add_all_indicators(df)
                logger.info("harness_fetch_done", pair=pair, bars=len(df))
            except Exception as exc:
                logger.error("harness_fetch_error", pair=pair, error=str(exc))
    finally:
        await client.disconnect()

    # ── Run every (strategy, pair) combo ──
    runs: list[HarnessRun] = []
    for strategy_name in strategies:
        for pair, df in pair_bars.items():
            try:
                strategy = STRATEGY_CLASSES[strategy_name]()
                engine = BacktestEngine(
                    strategy=strategy,
                    initial_balance=initial_balance,
                    maker_fee=maker_fee,
                    taker_fee=taker_fee,
                    slippage=slippage,
                )
                result = engine.run(df, pair)
                passed, reasons = _evaluate_run(result)
                runs.append(HarnessRun(
                    strategy=strategy_name, pair=pair,
                    total_return=result.total_return,
                    sharpe_ratio=result.sharpe_ratio,
                    max_drawdown=result.max_drawdown,
                    win_rate=result.win_rate,
                    profit_factor=(
                        result.profit_factor
                        if result.profit_factor != float("inf") else 999.0
                    ),
                    total_trades=result.total_trades,
                    avg_win=result.avg_win, avg_loss=result.avg_loss,
                    passed=passed, failure_reasons=reasons,
                ))
            except Exception as exc:
                logger.error(
                    "harness_run_error",
                    strategy=strategy_name, pair=pair, error=str(exc),
                )

    # ── Build verdicts ──
    verdicts: list[StrategyVerdict] = []
    for strategy_name in strategies:
        strategy_runs = [r for r in runs if r.strategy == strategy_name]
        verdicts.append(_build_verdict(strategy_name, strategy_runs))

    report = HarnessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        config={
            "strategies": list(strategies),
            "pairs": list(pairs),
            "timeframe_minutes": timeframe_minutes,
            "days": days,
            "initial_balance": initial_balance,
            "taker_fee": taker_fee,
            "maker_fee": maker_fee,
            "slippage": slippage,
            "min_sharpe": MIN_SHARPE,
            "min_profit_factor": MIN_PROFIT_FACTOR,
            "max_drawdown_pct": MAX_DRAWDOWN_PCT,
            "min_trades": MIN_TRADES,
            "min_pairs_passing_pct": MIN_PAIRS_PASSING_PCT,
        },
        runs=runs,
        verdicts=verdicts,
    )

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(asdict(report), indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("harness_report_written", path=str(output_path))

    return report


# ── Pretty printing ───────────────────────────────────


def print_report(report: HarnessReport) -> None:
    """Print a compact human-readable report to stdout."""
    cfg = report.config
    sep = "=" * 84
    print(f"\n{sep}")
    print("  BACKTEST HARNESS — AUTOMATED STRATEGY EVALUATION")
    print(sep)
    print(f"  Generated : {report.generated_at}")
    print(f"  Period    : {cfg['days']} days @ {cfg['timeframe_minutes']}m bars")
    print(f"  Fees      : taker {cfg['taker_fee']*100:.2f}% | maker {cfg['maker_fee']*100:.2f}%")
    print(f"  Slippage  : {cfg['slippage']*100:.2f}% | Initial balance: ${cfg['initial_balance']:,.0f}")
    print(f"  Threshold : Sharpe>={MIN_SHARPE} | PF>={MIN_PROFIT_FACTOR} | "
          f"maxDD<={MAX_DRAWDOWN_PCT}% | trades>={MIN_TRADES}")
    print(f"  Production ready if >={int(MIN_PAIRS_PASSING_PCT*100)}% of pairs pass")
    print(sep)

    # ── Per-run table ──
    header = (
        f"  {'Strategy':<20} {'Pair':<10} {'Ret%':>8} {'Sharpe':>7} "
        f"{'PF':>6} {'maxDD%':>8} {'Win%':>6} {'Trades':>6}  Verdict"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for run in report.runs:
        status = "PASS" if run.passed else "FAIL"
        note = "" if run.passed else "  (" + ", ".join(run.failure_reasons) + ")"
        print(
            f"  {run.strategy:<20} {run.pair:<10} "
            f"{run.total_return:>+7.1f}% {run.sharpe_ratio:>7.2f} "
            f"{run.profit_factor:>6.2f} {run.max_drawdown:>7.1f}% "
            f"{run.win_rate*100:>5.1f}% {run.total_trades:>6d}  {status}{note}"
        )

    # ── Per-strategy verdicts ──
    print("\n  " + "=" * 82)
    print("  STRATEGY VERDICTS")
    print("  " + "=" * 82)
    vh = (
        f"  {'Strategy':<20} {'Pass':>10} {'AvgSharpe':>10} {'AvgPF':>7} "
        f"{'AvgDD%':>8} {'AvgRet%':>8}  Ready"
    )
    print(vh)
    print("  " + "-" * (len(vh) - 2))
    for v in report.verdicts:
        ready = "YES" if v.production_ready else "no"
        print(
            f"  {v.strategy:<20} {v.pairs_passed}/{v.pairs_tested:>2} ({v.pass_rate*100:>3.0f}%) "
            f"{v.avg_sharpe:>10.2f} {v.avg_profit_factor:>7.2f} "
            f"{v.avg_max_drawdown:>7.1f}% {v.avg_total_return:>+7.1f}%  {ready}"
        )

    # ── Summary ──
    ready_strats = [v.strategy for v in report.verdicts if v.production_ready]
    print("\n  " + "=" * 82)
    if ready_strats:
        print(f"  Production-ready strategies: {', '.join(ready_strats)}")
    else:
        print("  No strategy passed. Keep bot_paper_trading=True "
              "until parameters are retuned.")
    print("  " + "=" * 82 + "\n")


# ── CLI ───────────────────────────────────────────────


def _parse_args(argv: list[str] | None = None):
    import argparse
    parser = argparse.ArgumentParser(
        prog="python -m bot.backtesting.harness",
        description="Automated multi-strategy × multi-pair backtest harness.",
    )
    parser.add_argument(
        "--strategies", nargs="+", default=list(DEFAULT_STRATEGIES),
        help="Strategy keys to evaluate (default: all).",
    )
    parser.add_argument(
        "--pairs", nargs="+", default=list(DEFAULT_PAIRS),
        help="Trading pairs to test (default: top 10 Kraken).",
    )
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--timeframe", type=int, default=60)
    parser.add_argument("--balance", type=float, default=1000.0)
    parser.add_argument("--taker-fee", type=float, default=DEFAULT_TAKER_FEE)
    parser.add_argument("--maker-fee", type=float, default=DEFAULT_MAKER_FEE)
    parser.add_argument("--slippage", type=float, default=DEFAULT_SLIPPAGE)
    parser.add_argument(
        "--output", type=Path,
        default=Path("data/backtest_reports") / (
            f"harness_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.json"
        ),
        help="Path to write JSON report (default: data/backtest_reports/...).",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    report = asyncio.run(run_harness(
        strategies=tuple(args.strategies),
        pairs=tuple(args.pairs),
        timeframe_minutes=args.timeframe,
        days=args.days,
        initial_balance=args.balance,
        taker_fee=args.taker_fee,
        maker_fee=args.maker_fee,
        slippage=args.slippage,
        output_path=args.output,
    ))
    print_report(report)


if __name__ == "__main__":
    main()
