"""Main bot orchestrator – ties all components together."""

from __future__ import annotations

import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone

import pandas as pd
import redis.asyncio as redis
import structlog

from bot.autopilot.manager import AutopilotManager
from bot.broker.kraken_rest import KrakenRestClient
from bot.broker.kraken_ws import KrakenWSClient
from bot.broker.models import Direction, OrderRequest, Tick
from bot.broker.paper_broker import PaperBroker
from bot.config import settings, SENSITIVE_KEYS
from bot.data.historical import HistoricalDataManager
from bot.data.indicators import add_all_indicators
from bot.ai.analyzer import ClaudeAnalyzer
from bot.ai.models import AIVerdict, AnalysisMode
from bot.db.repository import AIAnalysisRepository, SettingsRepository, SignalRepository, TradeRepository
from bot.db.session import close_db, get_session, init_db
from bot.metrics import (
    account_balance_gauge,
    daily_pnl_gauge,
    open_positions_gauge,
    order_latency_histogram,
    orders_placed_counter,
    orders_rejected_counter,
    signals_generated_counter,
    start_metrics_server,
    tick_counter,
)
from bot.notifications import (
    notify_bot_status,
    notify_error,
    notify_trade_opened,
)
from bot.risk.manager import RiskManager
from bot.risk.trailing_stop import TrailingStopManager, TrailingStopState
from bot.strategies.base import Signal, SignalType
from bot.strategies.registry import StrategyRegistry

logger = structlog.get_logger(__name__)


class TradingBot:
    """Central orchestrator for the Kraken trading bot."""

    def __init__(self) -> None:
        # Core components – select broker based on paper trading mode
        if settings.bot_paper_trading:
            logger.info("bot_mode", mode="PAPER TRADING", msg="Using PaperBroker – no real orders will be placed")
            self.broker = PaperBroker()
        else:
            logger.info("bot_mode", mode="LIVE", msg="Using KrakenRestClient – real orders enabled")
            self.broker = KrakenRestClient()
        self.ws_client = KrakenWSClient()
        self.data_mgr = HistoricalDataManager(self.broker)
        self.strategy_registry = StrategyRegistry()
        self.risk_manager = RiskManager()
        self.trailing_stop_mgr = TrailingStopManager()
        self.autopilot: AutopilotManager | None = None
        self.ai_analyzer = ClaudeAnalyzer()

        # Redis for pub/sub commands & live logs
        self._redis: redis.Redis | None = None
        self._running = False
        self._log_buffer: deque[dict] = deque(maxlen=500)

        # Active pairs being streamed
        self._active_pairs: set[str] = set()

    # ── Log publishing ────────────────────────────────

    async def _publish_log(self, level: str, event: str, **kwargs) -> None:
        """Buffer a log entry and publish to Redis for the dashboard."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "event": event,
            **{k: str(v) for k, v in kwargs.items()},
        }
        self._log_buffer.append(entry)
        if self._redis:
            try:
                payload = json.dumps(entry)
                await self._redis.publish("bot:logs", payload)
                # Also persist to a list for REST API access
                await self._redis.lpush("bot:logs:history", payload)
                await self._redis.ltrim("bot:logs:history", 0, 499)
            except Exception:
                pass

    # ── Settings from DB ───────────────────────────────

    async def _load_settings_from_db(self) -> None:
        """Load trading settings from DB, decrypting sensitive values."""
        from bot.crypto import decrypt

        try:
            async with get_session() as session:
                repo = SettingsRepository(session)
                db_values = await repo.get_decrypted_values(decrypt)

            if db_values:
                settings.apply_db_overrides(db_values)
                logger.info("settings_loaded_from_db", keys=list(db_values.keys()))
            else:
                logger.info("no_db_settings_found, using .env defaults")
        except Exception as exc:
            logger.warning("db_settings_load_error", error=str(exc))

    async def _reload_settings(self) -> None:
        """Reload settings from DB and re-apply to running components."""
        await self._load_settings_from_db()

        # Re-apply risk settings
        self.risk_manager.max_daily_loss = settings.bot_max_daily_loss
        self.risk_manager.max_position_size = settings.bot_max_position_size
        self.risk_manager.max_open_positions = settings.bot_max_open_positions
        self.risk_manager.max_per_pair = settings.bot_max_per_pair
        self.risk_manager.risk_per_trade_pct = settings.bot_risk_per_trade_pct

        # Re-apply autopilot settings (autopilot is always created)
        if self.autopilot:
            was_enabled = self.autopilot.enabled
            self.autopilot.enabled = settings.autopilot_enabled
            self.autopilot.shadow_mode = settings.autopilot_shadow_mode
            self.autopilot.max_active = settings.autopilot_max_active
            self.autopilot.min_score = settings.autopilot_min_score
            if not was_enabled and settings.autopilot_enabled:
                logger.info("autopilot_enabled_via_settings")

        logger.info("settings_reloaded")

    # ── Lifecycle ──────────────────────────────────────

    async def start(self) -> None:
        logger.info("bot_starting")

        # Database
        await init_db()

        # Load settings from DB (overrides .env defaults)
        await self._load_settings_from_db()

        # Check if credentials are configured
        if not settings.is_configured:
            logger.warning(
                "kraken_not_configured",
                msg="No API credentials found. Configure them via the dashboard at /settings"
            )
            # Still start the dashboard/redis so user can configure
        else:
            # Broker
            await self.broker.connect()

        # Redis
        try:
            self._redis = redis.from_url(settings.redis_url)
            await self._redis.ping()
            logger.info("redis_connected")
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))
            self._redis = None

        # Strategies
        self.strategy_registry.load_defaults()

        # Autopilot – always create so it can be enabled via dashboard
        self.autopilot = AutopilotManager(
            self.broker,
            self.ws_client,
            self.data_mgr,
            self.strategy_registry,
            redis_client=self._redis,
        )
        self.autopilot.enabled = settings.autopilot_enabled

        # WebSocket tick callback
        self.ws_client.set_tick_callback(self._on_tick)

        # Prometheus metrics
        try:
            start_metrics_server(port=8001)
        except Exception:
            pass  # metrics port may already be bound

        self._running = True

        if settings.is_configured:
            # Start WebSocket streaming
            await self.ws_client.connect()

            # Subscribe to default pairs
            default_pairs = ["BTC/USD", "ETH/USD", "SOL/USD"]
            await self.ws_client.subscribe_ticker(default_pairs)
            self._active_pairs.update(default_pairs)

            # Warm up historical data
            for pair in default_pairs:
                try:
                    df = await self.data_mgr.get_bars(pair, interval_minutes=60, count=250)
                    if not df.empty:
                        add_all_indicators(df)
                except Exception as exc:
                    logger.warning("warmup_error", pair=pair, error=str(exc))

        mode = "PAPER" if settings.bot_paper_trading else "LIVE"
        await notify_bot_status(f"Bot started on Kraken ({mode} mode)")
        logger.info("bot_started", pairs=list(self._active_pairs), mode=mode)
        await self._publish_log("INFO", "bot_started", mode=mode, pairs=str(list(self._active_pairs)))

        # Start background tasks (return_exceptions prevents one crash from killing all)
        results = await asyncio.gather(
            self._bar_update_loop(),
            self._account_metrics_loop(),
            self._autopilot_loop(),
            self._redis_command_listener(),
            return_exceptions=True,
        )
        # Log any crashed tasks
        task_names = ["bar_update", "account_metrics", "autopilot", "redis_listener"]
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.error("background_task_crashed", task=name, error=str(result))

    async def stop(self) -> None:
        logger.info("bot_stopping")
        self._running = False

        await self.ws_client.disconnect()
        await self.broker.disconnect()
        await self.ai_analyzer.close()

        if self._redis:
            await self._redis.close()

        await close_db()
        await notify_bot_status("Bot stopped")
        logger.info("bot_stopped")

    # ── Tick processing ────────────────────────────────

    async def _on_tick(self, tick: Tick) -> None:
        tick_counter.inc()

        # Trailing stops
        triggered = self.trailing_stop_mgr.update_on_tick(tick)
        for order_id in triggered:
            await self._close_on_trailing_stop(order_id, tick)

        # Strategy dispatch
        signals = self.strategy_registry.dispatch_tick(tick)
        for signal in signals:
            await self._process_signal(signal)

    async def _process_signal(self, signal: Signal) -> None:
        signals_generated_counter.labels(
            strategy=signal.strategy_name,
            signal_type=signal.signal_type.value,
        ).inc()

        if signal.signal_type == SignalType.HOLD:
            return

        # Risk check
        positions = await self.broker.get_open_positions()
        balance = await self.broker.get_account_balance()

        check = self.risk_manager.check_signal(signal, positions, balance)
        if not check.allowed:
            orders_rejected_counter.labels(reason=check.reason).inc()
            logger.info("signal_rejected", reason=check.reason, pair=signal.pair)
            await self._publish_log("INFO", "signal_rejected", pair=signal.pair, reason=check.reason)
            return

        # Shadow mode for autopilot strategies
        is_autopilot = signal.strategy_name.startswith("ap_")
        if is_autopilot and settings.autopilot_shadow_mode:
            await self._log_shadow_trade(signal)
            return

        # ── AI validation (optional) ──────────────────
        ai_result = None
        if self.ai_analyzer.is_enabled and settings.ai_pre_trade_enabled:
            ai_result = await self._run_ai_validation(signal, positions, balance)
            if ai_result and ai_result.verdict == AIVerdict.REJECT:
                orders_rejected_counter.labels(reason="ai_rejected").inc()
                logger.info(
                    "ai_rejected_signal",
                    pair=signal.pair,
                    reasoning=ai_result.reasoning,
                )
                return
            # Apply AI adjustments if any
            if ai_result and ai_result.verdict == AIVerdict.ADJUST:
                adj = ai_result.suggested_adjustments
                if adj.get("stop_loss_pct") is not None:
                    signal.stop_loss_pct = float(adj["stop_loss_pct"])
                if adj.get("take_profit_pct") is not None:
                    signal.take_profit_pct = float(adj["take_profit_pct"])
                logger.info(
                    "ai_adjusted_signal",
                    pair=signal.pair,
                    adjustments=adj,
                )

        # Calculate position size
        ticker = await self.broker.get_ticker(signal.pair)

        # Spread filter: reject if bid/ask spread would eat into the TP
        if ticker.bid > 0 and ticker.ask > 0:
            mid = (ticker.bid + ticker.ask) / 2
            spread_pct = (ticker.ask - ticker.bid) / mid * 100 if mid > 0 else 0
            tp_pct = signal.take_profit_pct or 5.0
            if spread_pct > tp_pct * 0.25:
                logger.info(
                    "signal_rejected_wide_spread", pair=signal.pair,
                    spread_pct=round(spread_pct, 3), tp_pct=tp_pct,
                )
                orders_rejected_counter.labels(reason="wide_spread").inc()
                return

        size = self.risk_manager.calculate_position_size(
            signal, balance, ticker.last
        )

        # Apply AI size factor if set
        if (
            self.ai_analyzer.is_enabled
            and settings.ai_pre_trade_enabled
            and ai_result
            and ai_result.suggested_adjustments.get("size_factor") is not None
        ):
            size *= float(ai_result.suggested_adjustments["size_factor"])

        if size <= 0:
            logger.warning("zero_size", pair=signal.pair)
            return

        # Execute
        order = OrderRequest(
            pair=signal.pair,
            direction=signal.direction,
            size=size,
            stop_loss_pct=signal.stop_loss_pct,
            take_profit_pct=signal.take_profit_pct,
            metadata=signal.metadata,
        )

        t0 = time.monotonic()
        try:
            result = await self.broker.open_position(order)
        except Exception as exc:
            logger.error("order_error", pair=signal.pair, error=str(exc))
            await self._publish_log("ERROR", "order_error", pair=signal.pair, error=str(exc))
            await notify_error(f"Order failed: {exc}")
            return

        latency = time.monotonic() - t0
        order_latency_histogram.observe(latency)
        orders_placed_counter.labels(
            strategy=signal.strategy_name,
            direction=signal.direction.value,
            pair=signal.pair,
        ).inc()

        # Persist trade (mark as PAPER when in paper trading mode)
        trade_status = "PAPER" if settings.bot_paper_trading else None
        async with get_session() as session:
            repo = TradeRepository(session)
            await repo.create_trade(
                order_id=result.order_id,
                pair=signal.pair,
                direction=signal.direction.value,
                size=size,
                entry_price=result.price,
                stop_loss=(
                    result.price * (1 - signal.stop_loss_pct / 100)
                    if signal.stop_loss_pct
                    else None
                ),
                take_profit=(
                    result.price * (1 + (signal.take_profit_pct + 2 * self.risk_manager.fee_calculator.taker_fee * 100) / 100)
                    if signal.take_profit_pct
                    else None
                ),
                fee=result.fee,
                strategy=signal.strategy_name,
                metadata_=signal.metadata,
                **({"status": trade_status} if trade_status else {}),
            )

            sig_repo = SignalRepository(session)
            await sig_repo.log_signal(
                pair=signal.pair,
                strategy=signal.strategy_name,
                signal_type=signal.signal_type.value,
                confidence=signal.confidence,
                indicators=signal.metadata,
                executed=True,
                order_id=result.order_id,
            )

        # Register trailing stop
        if signal.stop_loss_pct:
            self.trailing_stop_mgr.register(
                TrailingStopState(
                    pair=signal.pair,
                    direction=signal.direction,
                    entry_price=result.price,
                    trail_pct=signal.stop_loss_pct,
                    order_id=result.order_id,
                )
            )

        # Publish trade opened event to Redis
        if self._redis:
            try:
                await self._redis.publish(
                    "bot:trades",
                    json.dumps({
                        "type": "trade_opened",
                        "pair": signal.pair,
                        "direction": signal.direction.value,
                        "price": result.price,
                        "size": size,
                        "strategy": signal.strategy_name,
                    }),
                )
            except Exception:
                pass

        # Notify
        await notify_trade_opened(
            pair=signal.pair,
            direction=signal.direction.value,
            size=size,
            price=result.price,
            strategy=signal.strategy_name,
        )

        logger.info(
            "trade_opened",
            pair=signal.pair,
            direction=signal.direction.value,
            size=size,
            price=result.price,
            strategy=signal.strategy_name,
        )
        await self._publish_log(
            "INFO", "trade_opened",
            pair=signal.pair, direction=signal.direction.value,
            size=size, price=result.price, strategy=signal.strategy_name,
        )

    async def _close_on_trailing_stop(self, order_id: str, tick: Tick) -> None:
        stop = self.trailing_stop_mgr.get_stop(order_id)
        if not stop:
            return

        try:
            result = await self.broker.close_position(
                order_id=order_id,
                pair=stop.pair,
                size=0,  # close full position
            )
            self.trailing_stop_mgr.unregister(order_id)

            profit = 0.0
            if stop.direction == Direction.BUY:
                profit = (tick.last - stop.entry_price) * result.size
            else:
                profit = (stop.entry_price - tick.last) * result.size

            self.risk_manager.update_daily_pnl(profit)

            async with get_session() as session:
                repo = TradeRepository(session)
                await repo.close_trade(
                    order_id=order_id,
                    exit_price=tick.last,
                    profit=profit,
                    fee=result.fee,
                )

            # Publish trade closed event to Redis
            if self._redis:
                try:
                    await self._redis.publish(
                        "bot:trades",
                        json.dumps({
                            "type": "trade_closed",
                            "pair": stop.pair,
                            "profit": profit,
                            "exit_price": tick.last,
                        }),
                    )
                except Exception:
                    pass

            logger.info(
                "trailing_stop_hit",
                order_id=order_id,
                pair=stop.pair,
                profit=profit,
            )
            await self._publish_log("INFO", "trade_closed", pair=stop.pair, profit=profit)

        except Exception as exc:
            logger.error(
                "trailing_stop_close_error",
                order_id=order_id,
                error=str(exc),
            )

    async def _log_shadow_trade(self, signal: Signal) -> None:
        async with get_session() as session:
            repo = TradeRepository(session)
            ticker = await self.broker.get_ticker(signal.pair)
            await repo.create_trade(
                order_id=f"shadow_{signal.pair}_{int(time.time())}",
                pair=signal.pair,
                direction=signal.direction.value,
                size=0.0,
                entry_price=ticker.last,
                strategy=signal.strategy_name,
                status="SHADOW",
                metadata_=signal.metadata,
            )
        logger.info(
            "shadow_trade",
            pair=signal.pair,
            direction=signal.direction.value,
            strategy=signal.strategy_name,
        )

    # ── AI analysis ─────────────────────────────────────

    async def _run_ai_validation(
        self,
        signal: Signal,
        positions: list,
        balance,
    ):
        """Run AI pre-trade validation and persist the analysis."""
        from bot.ai.models import AIAnalysisResult

        try:
            # Prepare recent bars for context
            cached_df = self.data_mgr.get_cached(signal.pair, 60)
            recent_bars = []
            if cached_df is not None and not cached_df.empty:
                for _, row in cached_df.tail(10).iterrows():
                    recent_bars.append({
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                    })

            # Prepare positions for context
            pos_dicts = [
                {
                    "pair": p.pair,
                    "direction": p.direction.value,
                    "size": p.size,
                    "entry_price": p.entry_price,
                }
                for p in positions
            ]

            ai_result = await self.ai_analyzer.validate_signal(
                pair=signal.pair,
                direction=signal.direction.value,
                strategy=signal.strategy_name,
                confidence=signal.confidence,
                indicators=signal.metadata,
                recent_bars=recent_bars,
                open_positions=pos_dicts,
                account_balance=balance.available_balance,
            )

            # Persist analysis log
            async with get_session() as session:
                ai_repo = AIAnalysisRepository(session)
                await ai_repo.save(
                    pair=signal.pair,
                    mode="pre_trade",
                    verdict=ai_result.verdict.value,
                    confidence=ai_result.confidence,
                    reasoning=ai_result.reasoning,
                    market_summary=ai_result.market_summary,
                    risk_warnings=ai_result.risk_warnings,
                    suggested_adjustments=ai_result.suggested_adjustments,
                    signal_direction=signal.direction.value,
                    signal_strategy=signal.strategy_name,
                    model_used=ai_result.model_used,
                    tokens_used=ai_result.tokens_used,
                    latency_ms=ai_result.latency_ms,
                )

            return ai_result

        except Exception as exc:
            logger.error("ai_validation_error", error=str(exc))
            # On error, don't block trading — return None (= approve)
            return None

    # ── Background loops ───────────────────────────────

    async def _bar_update_loop(self) -> None:
        """Fetch fresh bars every 5 minutes and run bar-based strategies.

        Fetches both H1 (primary) and D1 (higher-timeframe) data.  When D1
        data is available the multi-timeframe dispatch path is used; otherwise
        the original single-timeframe ``dispatch_bar`` is used as a fallback.
        """
        while self._running:
            await asyncio.sleep(300)  # 5 min
            if not settings.is_configured:
                continue
            for pair in list(self._active_pairs):
                try:
                    # Primary timeframe – H1
                    df = await self.data_mgr.get_bars(pair, interval_minutes=60, count=250)
                    if df.empty:
                        continue
                    df = add_all_indicators(df)

                    # Higher timeframe – D1
                    df_d1: pd.DataFrame | None = None
                    try:
                        df_d1 = await self.data_mgr.get_bars(
                            pair, interval_minutes=1440, count=100
                        )
                        if df_d1 is not None and not df_d1.empty:
                            df_d1 = add_all_indicators(df_d1)
                        else:
                            df_d1 = None
                    except Exception as d1_exc:
                        logger.warning(
                            "d1_fetch_error",
                            pair=pair,
                            error=str(d1_exc),
                        )
                        df_d1 = None

                    # Dispatch – prefer multi-timeframe when D1 is available
                    if df_d1 is not None:
                        signals = self.strategy_registry.dispatch_bar_mtf(
                            pair, df, df_d1
                        )
                    else:
                        signals = self.strategy_registry.dispatch_bar(pair, df)

                    for signal in signals:
                        await self._process_signal(signal)
                except Exception as exc:
                    logger.error("bar_update_error", pair=pair, error=str(exc))
                    try:
                        await self._publish_log("ERROR", "bar_update_error", pair=pair, error=str(exc))
                    except Exception:
                        pass

    async def _account_metrics_loop(self) -> None:
        """Update account metrics every minute."""
        while self._running:
            await asyncio.sleep(60)
            if not settings.is_configured:
                continue
            try:
                balance = await self.broker.get_account_balance()
                account_balance_gauge.set(balance.total_balance)
                daily_pnl_gauge.set(self.risk_manager.state.daily_pnl)

                positions = await self.broker.get_open_positions()
                open_positions_gauge.set(len(positions))

                # Publish status to Redis as JSON
                if self._redis:
                    status_data = {
                        "type": "status",
                        "balance": balance.total_balance,
                        "pnl": self.risk_manager.state.daily_pnl,
                        "positions": len(positions),
                    }
                    await self._redis.publish("bot:status", json.dumps(status_data))
                    # Also store balance for the dashboard REST endpoint
                    balance_data = {
                        "total_balance": balance.total_balance,
                        "available_balance": balance.available_balance,
                        "currency": balance.currency,
                        "open_positions": len(positions),
                        "positions": [
                            {
                                "pair": p.pair,
                                "direction": p.direction.value if hasattr(p.direction, "value") else str(p.direction),
                                "size": p.size,
                                "entry_price": p.entry_price,
                                "unrealized_pnl": getattr(p, "unrealized_pnl", 0.0),
                            }
                            for p in positions
                        ],
                        "mode": "PAPER" if settings.bot_paper_trading else "LIVE",
                    }
                    await self._redis.set("bot:last_balance", json.dumps(balance_data))
                await self._publish_log(
                    "DEBUG", "account_update",
                    balance=balance.total_balance,
                    pnl=self.risk_manager.state.daily_pnl,
                    open_positions=len(positions),
                )
            except Exception as exc:
                logger.error("metrics_error", error=str(exc))

    async def _autopilot_loop(self) -> None:
        """Run autopilot scan cycle periodically. Auto-restarts on crash."""
        if not self.autopilot:
            return
        while self._running:
            try:
                await self._autopilot_loop_inner()
            except Exception as exc:
                logger.error("autopilot_loop_crashed", error=str(exc), msg="Restarting in 30s")
                await asyncio.sleep(30)

    async def _autopilot_loop_inner(self) -> None:
        """Inner autopilot loop."""
        # Run first scan shortly after startup
        first_run = True
        while self._running:
            if first_run:
                first_run = False
                await asyncio.sleep(15)  # Small delay for warmup
            else:
                interval = settings.autopilot_scan_interval_minutes * 60
                await asyncio.sleep(interval)
            if not settings.is_configured:
                continue
            if not self.autopilot.enabled:
                continue
            try:
                await self._publish_log("INFO", "autopilot_cycle_start", status="scanning")
                results = await self.autopilot.run_scan_cycle()
                active = self.autopilot.active_scores
                if results:
                    top_pairs = ", ".join(f"{s.pair}({s.composite:.0%})" for s in results[:5])
                    await self._publish_log(
                        "INFO", "autopilot_scan_done",
                        scanned=str(len(results)),
                        active=str(len(active)),
                        top=top_pairs,
                    )
                else:
                    await self._publish_log(
                        "WARNING", "autopilot_no_results",
                        msg="Aucune paire au-dessus du seuil minimum",
                    )
                # Log each activated pair
                for pair, score in active.items():
                    await self._publish_log(
                        "DEBUG", "autopilot_pair_active",
                        pair=pair,
                        score=f"{score.composite:.0%}",
                        regime=score.regime,
                        direction=score.direction_bias,
                        strategy=score.recommended_strategy or "auto",
                    )
            except Exception as exc:
                logger.error("autopilot_error", error=str(exc))
                try:
                    await self._publish_log("ERROR", "autopilot_error", error=str(exc))
                except Exception:
                    pass  # Don't let log publishing crash the loop

    async def _redis_command_listener(self) -> None:
        """Listen for commands on Redis pub/sub."""
        if not self._redis:
            return
        try:
            pubsub = self._redis.pubsub()
            await pubsub.subscribe("bot:commands")
            while self._running:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if msg and msg["type"] == "message":
                    await self._handle_command(msg["data"].decode())
        except Exception as exc:
            logger.error("redis_listener_error", error=str(exc))

    async def _handle_command(self, command: str) -> None:
        logger.info("command_received", command=command)
        await self._publish_log("INFO", "command_received", command=command)
        if command == "stop":
            self._running = False
        elif command == "reload_settings":
            await self._reload_settings()
        elif command == "autopilot_scan_now":
            if self.autopilot:
                await self.autopilot.run_scan_cycle()
        elif command == "daily_reset":
            self.risk_manager.reset_daily()


async def main() -> None:
    bot = TradingBot()
    try:
        await bot.start()
    except KeyboardInterrupt:
        pass
    finally:
        await bot.stop()
