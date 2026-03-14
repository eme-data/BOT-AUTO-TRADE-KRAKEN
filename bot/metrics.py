"""Prometheus metrics collection."""

from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

# ── Gauges ─────────────────────────────────────────────
account_balance_gauge = Gauge(
    "kraken_account_balance_usd", "Account balance in USD"
)
daily_pnl_gauge = Gauge(
    "kraken_daily_pnl_usd", "Daily realised P&L in USD"
)
open_positions_gauge = Gauge(
    "kraken_open_positions", "Number of open positions"
)

# ── Counters ───────────────────────────────────────────
orders_placed_counter = Counter(
    "kraken_orders_placed_total",
    "Total orders placed",
    ["strategy", "direction", "pair"],
)
orders_rejected_counter = Counter(
    "kraken_orders_rejected_total",
    "Total orders rejected by risk manager",
    ["reason"],
)
signals_generated_counter = Counter(
    "kraken_signals_generated_total",
    "Total signals generated",
    ["strategy", "signal_type"],
)
tick_counter = Counter(
    "kraken_ticks_received_total", "Total ticks received"
)
ws_reconnect_counter = Counter(
    "kraken_ws_reconnects_total", "WebSocket reconnections"
)

# ── Histograms ─────────────────────────────────────────
order_latency_histogram = Histogram(
    "kraken_order_latency_seconds",
    "Order execution latency",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)


def start_metrics_server(port: int = 8001) -> None:
    """Start Prometheus HTTP metrics endpoint."""
    start_http_server(port)
