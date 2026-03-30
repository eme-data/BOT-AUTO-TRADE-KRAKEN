"""Multi-tenant bot manager – one UserBotContext per configured user."""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import time as _time_mod
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import redis.asyncio as aioredis
import structlog

from bot.config import UserSettings, settings, SENSITIVE_KEYS
from bot.db.models import AdminUser
from bot.db.repository import SettingsRepository
from bot.db.session import get_session, init_db, close_db

logger = structlog.get_logger(__name__)

HEALTH_STALE_SECONDS = 600  # 10 minutes – loop considered dead after this
HEALTH_CHECK_INTERVAL = 60  # seconds between health monitor ticks


async def _load_user_settings(user_id: int) -> UserSettings:
    """Load a UserSettings instance from the database."""
    from bot.crypto import decrypt

    us = UserSettings(user_id)
    try:
        async with get_session() as session:
            repo = SettingsRepository(session, user_id=user_id)
            db_values = await repo.get_decrypted_values(decrypt)
        if db_values:
            us.apply_db_overrides(db_values)
            logger.info("user_settings_loaded", user_id=user_id, keys=list(db_values.keys()))
    except Exception as exc:
        logger.warning("user_settings_load_error", user_id=user_id, error=str(exc))
    return us


def _sanitize_metadata(meta: dict | None) -> dict | None:
    """Convert numpy/bool types to JSON-safe Python types."""
    if not meta:
        return meta
    clean = {}
    for k, v in meta.items():
        if hasattr(v, 'item'):  # numpy scalar
            clean[k] = v.item()
        elif isinstance(v, (int, float, str, bool, type(None))):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


class UserBotContext:
    """All trading components scoped to a single user."""

    def __init__(self, user_id: int, user_settings: UserSettings, redis_client: aioredis.Redis | None) -> None:
        from bot.autopilot.manager import AutopilotManager
        from bot.broker.kraken_rest import KrakenRestClient
        from bot.broker.kraken_ws import KrakenWSClient
        from bot.broker.paper_broker import PaperBroker
        from bot.data.historical import HistoricalDataManager
        from bot.ai.analyzer import ClaudeAnalyzer
        from bot.risk.manager import RiskManager
        from bot.risk.trailing_stop import TrailingStopManager
        from bot.strategies.registry import StrategyRegistry

        self.user_id = user_id
        self.cfg = user_settings
        self._redis = redis_client
        self._running = False
        self._started_at: float | None = None

        # Drawdown protection
        self._daily_pnl: float = 0.0
        self._daily_pnl_reset_date: str = ""
        self._trading_paused: bool = False
        self._pause_reason: str = ""

        # Anomaly detection
        from bot.anomaly_detector import AnomalyDetector
        self.anomaly_detector = AnomalyDetector()

        # Health tracking – each loop writes its timestamp here
        self._last_loop_run: dict[str, float] = {
            "bar_update": 0.0,
            "account_metrics": 0.0,
            "autopilot": 0.0,
            "redis_listener": 0.0,
            "price_alerts": 0.0,
            "dca": 0.0,
            "sync_positions": 0.0,
        }
        self._last_tick_at: float = 0.0
        self._cooldowns: dict[str, float] = {}  # pair -> last close timestamp
        self._signal_lock = asyncio.Lock()  # prevent concurrent signal processing

        # Broker
        if self.cfg.bot_paper_trading:
            logger.info("user_bot_mode", user_id=user_id, mode="PAPER")
            self.broker = PaperBroker()
        else:
            exchange_id = getattr(self.cfg, "exchange_id", "kraken")
            logger.info("user_bot_mode", user_id=user_id, mode="LIVE", exchange=exchange_id)
            if exchange_id != "kraken":
                from bot.broker.ccxt_broker import CCXTBroker
                self.broker = CCXTBroker(
                    exchange_id=exchange_id,
                    api_key=self.cfg.kraken_api_key,
                    api_secret=self.cfg.kraken_api_secret,
                    password=getattr(self.cfg, "exchange_password", None) or None,
                    quote_currency=getattr(self.cfg, "exchange_quote_currency", "USD"),
                )
            else:
                self.broker = KrakenRestClient(
                    api_key=self.cfg.kraken_api_key,
                    api_secret=self.cfg.kraken_api_secret,
                    quote_currency=getattr(self.cfg, "exchange_quote_currency", "USD"),
                )

        self.ws_client = KrakenWSClient()
        self.data_mgr = HistoricalDataManager(self.broker)
        self.strategy_registry = StrategyRegistry()
        self.risk_manager = RiskManager(cfg=self.cfg)
        self.risk_manager.max_per_pair = 2  # Allow 2 positions per pair
        self.trailing_stop_mgr = TrailingStopManager()

        # Polymarket sentiment (optional)
        self.polymarket_client = None
        if getattr(self.cfg, "polymarket_enabled", False):
            try:
                from bot.data.polymarket import PolymarketClient
                self.polymarket_client = PolymarketClient(
                    cache_ttl_seconds=getattr(self.cfg, "polymarket_cache_ttl_minutes", 15) * 60,
                )
                logger.info("polymarket_enabled", user_id=user_id)
            except Exception as exc:
                logger.warning("polymarket_init_error", user_id=user_id, error=str(exc))

        # Fear & Greed Index (preferred sentiment source)
        self.fear_greed_client = None
        try:
            from bot.data.fear_greed import FearGreedClient
            self.fear_greed_client = FearGreedClient()
            logger.info("fear_greed_enabled", user_id=user_id)
        except Exception as exc:
            logger.warning("fear_greed_init_error", user_id=user_id, error=str(exc))

        self.ai_analyzer = ClaudeAnalyzer(polymarket_client=self.polymarket_client)
        self.autopilot: AutopilotManager | None = None

        self._active_pairs: set[str] = set()

    # ── Health status ──────────────────────────────────

    @property
    def health_status(self) -> dict[str, Any]:
        """Return a snapshot of this context's health."""
        now = _time_mod.time()

        def _loop_status(name: str) -> str:
            last = self._last_loop_run.get(name, 0.0)
            if last == 0.0:
                return "not_started"
            return "alive" if (now - last) < HEALTH_STALE_SECONDS else "dead"

        uptime = (now - self._started_at) if self._started_at else 0.0

        return {
            "user_id": self.user_id,
            "running": self._running,
            "uptime_seconds": round(uptime, 1),
            "last_tick_at": (
                datetime.fromtimestamp(self._last_tick_at, tz=timezone.utc).isoformat()
                if self._last_tick_at
                else None
            ),
            "active_pairs": sorted(self._active_pairs),
            "active_pairs_count": len(self._active_pairs),
            "mode": "PAPER" if self.cfg.bot_paper_trading else "LIVE",
            "daily_pnl": round(self._daily_pnl, 2),
            "trading_paused": self._trading_paused,
            "pause_reason": self._pause_reason,
            "loops_status": {
                "bar_update": _loop_status("bar_update"),
                "account_metrics": _loop_status("account_metrics"),
                "autopilot": _loop_status("autopilot"),
                "redis_listener": _loop_status("redis_listener"),
                "price_alerts": _loop_status("price_alerts"),
                "dca": _loop_status("dca"),
            },
        }

    # ── Redis helpers (namespaced) ──────────────────────

    def _rkey(self, key: str) -> str:
        return f"bot:user:{self.user_id}:{key}"

    async def _set_cooldown(self, pair: str) -> None:
        """Set a 1-hour cooldown on a pair, persisted in Redis."""
        self._cooldowns[f"cooldown:{pair}"] = _time_mod.time()
        if self._redis:
            try:
                await self._redis.setex(self._rkey(f"cooldown:{pair}"), 3600, "1")
            except Exception:
                pass

    async def publish_log(self, level: str, event: str, **kwargs: Any) -> None:
        # Also log to stdout for docker logs visibility
        log_fn = logger.info if level in ("INFO", "DEBUG") else logger.warning if level == "WARNING" else logger.error
        log_fn(event, user_id=self.user_id, **kwargs)

        entry = {
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "level": level,
            "event": event,
            "user_id": self.user_id,
            **{k: str(v) for k, v in kwargs.items()},
        }
        if self._redis:
            try:
                payload = json.dumps(entry)
                await self._redis.publish(self._rkey("logs"), payload)
                # Also publish on the global channel so legacy dashboard still works
                await self._redis.publish("bot:logs", payload)
                await self._redis.lpush(self._rkey("logs:history"), payload)
                await self._redis.ltrim(self._rkey("logs:history"), 0, 499)
                # Legacy key (backwards compat)
                await self._redis.lpush("bot:logs:history", payload)
                await self._redis.ltrim("bot:logs:history", 0, 499)
            except Exception:
                pass

    # ── Lifecycle ──────────────────────────────────────

    async def start(self) -> None:
        from bot.autopilot.manager import AutopilotManager

        if not self.cfg.is_configured:
            logger.warning("user_not_configured", user_id=self.user_id)
            return

        await self.broker.connect()

        self.strategy_registry.load_defaults()

        self.autopilot = AutopilotManager(
            self.broker,
            self.ws_client,
            self.data_mgr,
            self.strategy_registry,
            redis_client=self._redis,
            user_id=self.user_id,
            polymarket_client=self.polymarket_client,
            fear_greed_client=self.fear_greed_client,
            quote_currency=getattr(self.cfg, "exchange_quote_currency", "USD"),
        )
        self.autopilot.apply_user_config(self.cfg)

        self.ws_client.set_tick_callback(self._on_tick)

        await self.ws_client.connect()

        quote = getattr(self.cfg, "exchange_quote_currency", "USD")
        default_pairs = [f"BTC/{quote}", f"ETH/{quote}", f"SOL/{quote}"]
        await self.ws_client.subscribe_ticker(default_pairs)
        self._active_pairs.update(default_pairs)

        for pair in default_pairs:
            try:
                from bot.data.indicators import add_all_indicators
                df = await self.data_mgr.get_bars(pair, interval_minutes=60, count=250)
                if not df.empty:
                    add_all_indicators(df)
            except Exception as exc:
                logger.warning("warmup_error", user_id=self.user_id, pair=pair, error=str(exc))

        # Register trailing stops and subscribe tickers for existing open positions
        if not self.cfg.bot_paper_trading:
            try:
                from bot.risk.trailing_stop import TrailingStopState
                from bot.broker.models import Direction
                async with get_session() as session:
                    from bot.db.repository import TradeRepository
                    repo = TradeRepository(session, user_id=self.user_id)
                    db_trades = await repo.get_open_trades()
                    trail_pct = float(getattr(self.cfg, "risk_stop_loss_pct", 0.03)) * 100
                    # Subscribe to tickers for all open position pairs
                    open_pairs = list({t.pair for t in db_trades if t.pair not in self._active_pairs})
                    if open_pairs:
                        await self.ws_client.subscribe_ticker(open_pairs)
                        self._active_pairs.update(open_pairs)
                        logger.info("startup_subscribed_position_pairs", user_id=self.user_id, pairs=open_pairs)
                    for t in db_trades:
                        if t.entry_price and t.entry_price > 0:
                            self.trailing_stop_mgr.register(
                                TrailingStopState(
                                    pair=t.pair,
                                    direction=Direction.BUY if t.direction in ("buy", "BUY") else Direction.SELL,
                                    entry_price=t.entry_price,
                                    trail_pct=trail_pct,
                                    order_id=t.order_id,
                                )
                            )
                            # Set stop_loss in DB if missing
                            if not t.stop_loss:
                                t.stop_loss = t.entry_price * (1 - trail_pct / 100)
                    await session.commit()
                    logger.info("startup_trailing_stops_registered", user_id=self.user_id, count=len(db_trades))
            except Exception as exc:
                logger.error("startup_trailing_stops_error", user_id=self.user_id, error=str(exc))

        self._running = True
        self._started_at = _time_mod.time()
        mode = "PAPER" if self.cfg.bot_paper_trading else "LIVE"
        logger.info("user_bot_started", user_id=self.user_id, mode=mode, pairs=list(self._active_pairs))
        await self.publish_log("INFO", "bot_started", mode=mode, pairs=str(list(self._active_pairs)))

    async def run_loops(self) -> None:
        """Run background loops. Call after start()."""
        results = await asyncio.gather(
            self._bar_update_loop(),
            self._account_metrics_loop(),
            self._autopilot_loop(),
            self._redis_command_listener(),
            self._price_alert_loop(),
            self._dca_loop(),
            self._sync_positions_loop(),
            return_exceptions=True,
        )
        task_names = ["bar_update", "account_metrics", "autopilot", "redis_listener", "price_alerts", "dca", "sync_positions"]
        for name, result in zip(task_names, results):
            if isinstance(result, Exception):
                logger.error("user_task_crashed", user_id=self.user_id, task=name, error=str(result))

    async def stop(self) -> None:
        self._running = False
        await self.ws_client.disconnect()
        await self.broker.disconnect()
        await self.ai_analyzer.close()
        if self.polymarket_client:
            await self.polymarket_client.close()
        logger.info("user_bot_stopped", user_id=self.user_id)

    # ── Reload settings ────────────────────────────────

    async def reload_settings(self) -> None:
        self.cfg = await _load_user_settings(self.user_id)
        self.risk_manager.max_daily_loss = self.cfg.bot_max_daily_loss
        self.risk_manager.max_position_size = self.cfg.bot_max_position_size
        self.risk_manager.max_open_positions = self.cfg.bot_max_open_positions
        self.risk_manager.max_per_pair = self.cfg.bot_max_per_pair
        self.risk_manager.risk_per_trade_pct = self.cfg.bot_risk_per_trade_pct
        if self.autopilot:
            self.autopilot.enabled = self.cfg.autopilot_enabled
            self.autopilot.shadow_mode = self.cfg.autopilot_shadow_mode
            self.autopilot.max_active = self.cfg.autopilot_max_active
            self.autopilot.min_score = self.cfg.autopilot_min_score
        logger.info("user_settings_reloaded", user_id=self.user_id)

    # ── Tick / signal processing (delegated from TradingBot logic) ─

    async def _on_tick(self, tick) -> None:
        from bot.metrics import tick_counter
        tick_counter.inc()
        self._last_tick_at = _time_mod.time()
        triggered = self.trailing_stop_mgr.update_on_tick(tick)
        for order_id in triggered:
            await self._close_on_trailing_stop(order_id, tick)
        signals = self.strategy_registry.dispatch_tick(tick)
        for signal in signals:
            await self._process_signal(signal)

    def _check_drawdown_protection(self) -> bool:
        """Reset daily PnL at midnight, pause if max loss exceeded. Returns True if paused."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self._daily_pnl_reset_date:
            self._daily_pnl = 0.0
            self._daily_pnl_reset_date = today
            if self._trading_paused:
                self._trading_paused = False
                self._pause_reason = ""
                logger.info("trading_unpaused_new_day", user_id=self.user_id)

        max_loss_pct = getattr(self.cfg, "risk_max_daily_loss_pct", 0.05)
        if max_loss_pct > 0 and self._daily_pnl < 0:
            # Use cached balance from account_metrics loop, fallback to 100
            balance = getattr(self, '_cached_balance', 100.0)
            threshold = -abs(max_loss_pct) * balance
            if self._daily_pnl <= threshold and not self._trading_paused:
                self._trading_paused = True
                self._pause_reason = f"Daily loss limit: {self._daily_pnl:.2f} (threshold: {threshold:.2f})"
                logger.warning("trading_paused_drawdown", user_id=self.user_id, daily_pnl=self._daily_pnl, threshold=threshold)
                asyncio.ensure_future(self.publish_log("WARNING", "trading_paused", reason=self._pause_reason))
                try:
                    from bot.notifications_push import send_push_to_user
                    asyncio.ensure_future(send_push_to_user(
                        self.user_id,
                        "Trading en pause",
                        self._pause_reason,
                        tag="drawdown",
                    ))
                except Exception:
                    pass
        return self._trading_paused

    async def _process_signal(self, signal) -> None:
        import time as _time
        from bot.broker.models import OrderRequest
        from bot.ai.models import AIVerdict
        from bot.db.repository import TradeRepository, SignalRepository
        from bot.metrics import (
            orders_placed_counter, orders_rejected_counter,
            signals_generated_counter, order_latency_histogram,
        )
        from bot.notifications import notify_error, notify_trade_opened
        from bot.risk.trailing_stop import TrailingStopState

        logger.info("process_signal_start", user_id=self.user_id,
                     pair=signal.pair, direction=signal.direction.value,
                     strategy=signal.strategy_name)
        async with self._signal_lock:
            try:
                await self._process_signal_inner(signal)
            except Exception as exc:
                logger.error("process_signal_error", user_id=self.user_id,
                             pair=signal.pair, error=str(exc), error_type=type(exc).__name__)

    async def _process_signal_inner(self, signal) -> None:
        import time as _time
        from bot.broker.models import OrderRequest
        from bot.ai.models import AIVerdict
        from bot.db.repository import TradeRepository, SignalRepository
        from bot.metrics import (
            orders_placed_counter, orders_rejected_counter,
            signals_generated_counter, order_latency_histogram,
        )
        from bot.notifications import notify_error, notify_trade_opened
        from bot.risk.trailing_stop import TrailingStopState

        # Drawdown protection check
        if self._check_drawdown_protection():
            await self.publish_log("INFO", "signal_skipped_paused", pair=signal.pair, reason=self._pause_reason)
            return

        signals_generated_counter.labels(
            strategy=signal.strategy_name, signal_type=signal.signal_type.value
        ).inc()

        from bot.strategies.base import SignalType
        from bot.broker.models import Direction
        if signal.signal_type == SignalType.HOLD:
            return

        # Cooldown: don't reopen a pair within 60 minutes of last close
        # Check both in-memory and Redis (survives restarts)
        cooldown_key = f"cooldown:{signal.pair}"
        if signal.direction == Direction.BUY:
            in_cooldown = False
            if cooldown_key in self._cooldowns:
                elapsed = _time_mod.time() - self._cooldowns[cooldown_key]
                if elapsed < 3600:
                    in_cooldown = True
                    remaining = int((3600 - elapsed) / 60)
            if not in_cooldown and self._redis:
                try:
                    redis_key = self._rkey(f"cooldown:{signal.pair}")
                    ttl = await self._redis.ttl(redis_key)
                    if ttl > 0:
                        in_cooldown = True
                        remaining = int(ttl / 60)
                except Exception:
                    pass
            if in_cooldown:
                logger.info("signal_cooldown", user_id=self.user_id,
                            pair=signal.pair, remaining_min=remaining)
                return

        # Spot exchange: SELL signal = close existing BUY position
        if signal.direction == Direction.SELL:
            owned = await self.broker.get_open_positions()
            matching = [p for p in owned if p.pair == signal.pair and p.size > 0]
            if not matching:
                await self.publish_log("INFO", "sell_skipped_no_position",
                                       pair=signal.pair, strategy=signal.strategy_name)
                return
            # Close the position instead of opening a SHORT
            for pos in matching:
                await self._close_position_by_signal(signal, pos)
            return

        positions = await self.broker.get_open_positions()
        balance = await self.broker.get_account_balance()

        # Hard check: don't open if we already have this pair on Kraken
        existing_pairs = {p.pair for p in positions if p.size * p.current_price >= 1.0}
        if signal.pair in existing_pairs:
            logger.info("signal_rejected", user_id=self.user_id, pair=signal.pair,
                        reason=f"Already holding {signal.pair}")
            return

        check = self.risk_manager.check_signal(signal, positions, balance)
        if not check.allowed:
            orders_rejected_counter.labels(reason=check.reason).inc()
            logger.info("signal_rejected", user_id=self.user_id, pair=signal.pair, reason=check.reason)
            return

        is_autopilot = signal.strategy_name.startswith("ap_")
        if is_autopilot and self.cfg.autopilot_shadow_mode:
            await self._log_shadow_trade(signal)
            return

        # AI validation
        ai_result = None
        if self.ai_analyzer.is_enabled and self.cfg.ai_pre_trade_enabled:
            ai_result = await self._run_ai_validation(signal, positions, balance)
            if ai_result and ai_result.verdict == AIVerdict.REJECT:
                orders_rejected_counter.labels(reason="ai_rejected").inc()
                await self.publish_log("INFO", "signal_rejected_by_ai",
                                       pair=signal.pair, strategy=signal.strategy_name,
                                       reason=ai_result.raw_response[:200] if ai_result.raw_response else "no details")
                return
            if ai_result and ai_result.verdict == AIVerdict.ADJUST:
                adj = ai_result.suggested_adjustments
                if adj.get("stop_loss_pct") is not None:
                    signal.stop_loss_pct = float(adj["stop_loss_pct"])
                if adj.get("take_profit_pct") is not None:
                    signal.take_profit_pct = float(adj["take_profit_pct"])

        ticker = await self.broker.get_ticker(signal.pair)

        # Sentiment-based position sizing: adapt size to Fear & Greed level
        # Never block trades entirely — instead reduce position size in fearful markets
        is_bearish_scalp = signal.metadata.get("bearish_mode") if signal.metadata else False
        _fg_size_factor = 1.0  # Will be applied to position sizing later
        if signal.direction == Direction.BUY and self.fear_greed_client:
            try:
                fg = await self.fear_greed_client.get_index()
                if fg.value <= 10:
                    # Extreme panic: trade with 20% of normal size
                    _fg_size_factor = 0.20
                    logger.info("signal_size_extreme_fear", user_id=self.user_id,
                                pair=signal.pair, fear_greed=fg.value, size_factor=0.20)
                elif fg.value <= 30:
                    # Fear: trade with 50% of normal size
                    _fg_size_factor = 0.50
                    logger.info("signal_size_fear", user_id=self.user_id,
                                pair=signal.pair, fear_greed=fg.value, size_factor=0.50)
                elif fg.value <= 50:
                    # Neutral: normal size
                    _fg_size_factor = 1.0
                else:
                    # Greed: full size
                    _fg_size_factor = 1.0
            except Exception:
                pass

        # BTC trend gate: reduce size for altcoins if BTC is in strong downtrend
        # Only block if BTC is >5% below EMA50 (crash territory), otherwise just reduce size
        if signal.direction == Direction.BUY and not signal.pair.startswith("BTC") and not is_bearish_scalp:
            try:
                btc_pair = "BTC/" + signal.pair.split("/")[1]
                btc_bars = await self.data_mgr.get_bars(btc_pair, interval_minutes=60, count=50)
                if not btc_bars.empty and len(btc_bars) >= 20:
                    from bot.data.indicators import add_all_indicators
                    btc_bars = add_all_indicators(btc_bars)
                    btc_close = btc_bars["close"].iloc[-1]
                    btc_ema50 = btc_bars["ema_50"].iloc[-1] if "ema_50" in btc_bars.columns else None
                    if btc_ema50 and not pd.isna(btc_ema50) and btc_close < btc_ema50:
                        drop_pct = (btc_ema50 - btc_close) / btc_ema50
                        if drop_pct > 0.05:
                            # BTC crash: block altcoin buys
                            logger.info("signal_blocked_btc_crash", user_id=self.user_id,
                                        pair=signal.pair, btc_drop_pct=round(drop_pct*100, 1))
                            return
                        else:
                            # BTC mild downtrend: reduce size by 50%
                            _fg_size_factor *= 0.5
                            logger.info("signal_reduced_btc_downtrend", user_id=self.user_id,
                                        pair=signal.pair, btc_drop_pct=round(drop_pct*100, 1))
            except Exception:
                pass

        # Simple position sizing: fixed % of available balance in quote currency
        max_pct = float(getattr(self.cfg, "risk_max_position_pct", 0.15))
        # Apply Fear & Greed size factor
        max_pct *= _fg_size_factor
        # Bearish scalps use additional 50% reduction
        if is_bearish_scalp:
            max_pct *= 0.5
        order_value = balance.available_balance * max_pct
        if ticker.last <= 0 or order_value < 1.0:
            logger.info("order_skipped_low_value", user_id=self.user_id, pair=signal.pair,
                        order_value=round(order_value, 2), ticker_last=ticker.last)
            return
        size = order_value / ticker.last

        # AI adjustment (optional)
        if ai_result and ai_result.suggested_adjustments.get("size_factor") is not None:
            size *= float(ai_result.suggested_adjustments["size_factor"])

        if size <= 0:
            return

        # Check exchange minimum order size
        try:
            market = self.broker.exchange.markets.get(signal.pair, {})
            min_amount = market.get("limits", {}).get("amount", {}).get("min", 0) or 0
            min_cost = market.get("limits", {}).get("cost", {}).get("min", 0) or 0
            if size < min_amount:
                await self.publish_log("INFO", "order_below_minimum",
                                       pair=signal.pair, size=size, min_amount=min_amount)
                return
            if order_value < min_cost:
                await self.publish_log("INFO", "order_below_min_cost",
                                       pair=signal.pair, value=order_value, min_cost=min_cost)
                return
        except Exception:
            pass

        logger.info("order_sizing", pair=signal.pair,
                     direction=signal.direction.value,
                     balance=round(balance.available_balance, 2),
                     order_value=round(order_value, 2),
                     size=round(size, 8), price=ticker.last)

        order = OrderRequest(
            pair=signal.pair, direction=signal.direction, size=size,
            stop_loss_pct=signal.stop_loss_pct, take_profit_pct=signal.take_profit_pct,
            metadata=signal.metadata,
        )
        t0 = _time.monotonic()
        try:
            result = await self.broker.open_position(order)
        except Exception as exc:
            logger.error("order_error", user_id=self.user_id, pair=signal.pair,
                         error=str(exc), error_type=type(exc).__name__)
            await self.publish_log("ERROR", "order_error", pair=signal.pair, error=str(exc))
            await notify_error(f"Order failed: {exc}")
            return

        logger.info("order_success", user_id=self.user_id, pair=signal.pair,
                     order_id=result.order_id, price=result.price, fee=result.fee)

        latency = _time.monotonic() - t0
        order_latency_histogram.observe(latency)
        orders_placed_counter.labels(
            strategy=signal.strategy_name, direction=signal.direction.value, pair=signal.pair
        ).inc()

        # Always fetch real fill price and fees from Kraken (market orders return 0)
        fill_price = result.price
        fill_fee = result.fee or 0
        try:
            import asyncio as _aio
            await _aio.sleep(1.5)  # Wait for fill
            filled = await self.broker.exchange.fetch_order(result.order_id, signal.pair)
            fetched_price = float(filled.get("average") or filled.get("price") or 0)
            fetched_fee = float((filled.get("fee") or {}).get("cost", 0))
            if fetched_price > 0:
                fill_price = fetched_price
            if fetched_fee > 0:
                fill_fee = fetched_fee
            logger.info("fill_price_fetched", user_id=self.user_id, pair=signal.pair,
                        fill_price=fill_price, fee=fill_fee, order_id=result.order_id)
        except Exception as exc:
            logger.warning("fill_price_fetch_error", user_id=self.user_id, error=str(exc))
            if fill_price == 0 or fill_price is None:
                fill_price = ticker.last

        trade_status = "PAPER" if self.cfg.bot_paper_trading else None
        try:
            async with get_session() as session:
                repo = TradeRepository(session, user_id=self.user_id)
                await repo.create_trade(
                    order_id=result.order_id, pair=signal.pair,
                    direction=signal.direction.value, size=size,
                    entry_price=fill_price,
                    stop_loss=(fill_price * (1 - signal.stop_loss_pct / 100) if signal.stop_loss_pct else None),
                    take_profit=(fill_price * (1 + signal.take_profit_pct / 100) if signal.take_profit_pct else None),
                    fee=fill_fee, strategy=signal.strategy_name,
                    metadata_=_sanitize_metadata(signal.metadata),
                    **({"status": trade_status} if trade_status else {}),
                )
                sig_repo = SignalRepository(session, user_id=self.user_id)
                await sig_repo.log_signal(
                    pair=signal.pair, strategy=signal.strategy_name,
                    signal_type=signal.signal_type.value, confidence=signal.confidence,
                    indicators=signal.metadata, executed=True, order_id=result.order_id,
                )
            logger.info("trade_saved_to_db", user_id=self.user_id, pair=signal.pair,
                        order_id=result.order_id, entry_price=fill_price, size=size)
        except Exception as exc:
            logger.error("trade_db_save_error", user_id=self.user_id, pair=signal.pair,
                         error=str(exc), error_type=type(exc).__name__)

        if signal.stop_loss_pct:
            self.trailing_stop_mgr.register(
                TrailingStopState(
                    pair=signal.pair, direction=signal.direction,
                    entry_price=result.price, trail_pct=signal.stop_loss_pct,
                    order_id=result.order_id,
                )
            )

        if self._redis:
            try:
                await self._redis.publish(
                    self._rkey("trades"),
                    json.dumps({
                        "type": "trade_opened", "pair": signal.pair,
                        "direction": signal.direction.value, "price": result.price,
                        "size": size, "strategy": signal.strategy_name,
                    }),
                )
            except Exception:
                pass

        # Web Push notification (fire-and-forget)
        try:
            from bot.notifications_push import notify_trade_push
            asyncio.ensure_future(notify_trade_push(
                user_id=self.user_id, trade_type="trade_opened",
                pair=signal.pair, direction=signal.direction.value,
                price=result.price, size=size, strategy=signal.strategy_name,
            ))
        except Exception:
            pass

        await notify_trade_opened(
            pair=signal.pair, direction=signal.direction.value,
            size=size, price=result.price, strategy=signal.strategy_name,
        )
        await self.publish_log(
            "INFO", "trade_opened", pair=signal.pair,
            direction=signal.direction.value, size=size,
            price=result.price, strategy=signal.strategy_name,
        )

    async def _close_position_by_signal(self, signal, position) -> None:
        """Close an existing position when a strategy generates an opposite signal."""
        from bot.db.repository import TradeRepository

        logger.info("closing_position_by_signal", user_id=self.user_id,
                     pair=signal.pair, strategy=signal.strategy_name,
                     size=position.size, current_price=position.current_price)
        try:
            from bot.broker.models import OrderRequest, OrderType, Direction
            close_order = OrderRequest(
                pair=signal.pair, direction=Direction.SELL,
                size=position.size, order_type=OrderType.MARKET,
            )
            result = await self.broker.close_position(
                order_id="signal_close", pair=signal.pair, size=position.size
            )
            order_id = result.order_id or ""

            # Fetch fill price and fees
            import asyncio as _aio
            await _aio.sleep(1.5)
            exit_price = position.current_price
            exit_fee = result.fee or 0.0
            try:
                filled = await self.broker._exchange.fetch_order(order_id, signal.pair)
                fetched_price = float(filled.get("average") or filled.get("price") or 0)
                fetched_fee = float((filled.get("fee") or {}).get("cost", 0))
                if fetched_price > 0:
                    exit_price = fetched_price
                if fetched_fee > 0:
                    exit_fee = fetched_fee
            except Exception:
                pass

            # Find trade in DB and close it
            async with get_session() as session:
                repo = TradeRepository(session, user_id=self.user_id)
                trades = await repo.get_open_by_pair(signal.pair)
                for trade in trades:
                    profit = (exit_price - trade.entry_price) * trade.size - exit_fee - (trade.fee or 0)
                    await repo.close_trade(order_id=trade.order_id, exit_price=exit_price,
                                           profit=profit, fee=exit_fee)
                    self._daily_pnl += profit
                    await self._set_cooldown(signal.pair)
                    logger.info("trade_closed_by_signal", user_id=self.user_id,
                                pair=signal.pair, profit=round(profit, 4),
                                strategy=signal.strategy_name)
                    await self.publish_log("INFO", "trade_closed", pair=signal.pair, profit=profit)

            # Unregister trailing stops for this pair
            for oid in list(self.trailing_stop_mgr._stops.keys()):
                s = self.trailing_stop_mgr._stops.get(oid)
                if s and s.pair == signal.pair:
                    self.trailing_stop_mgr.unregister(oid)

        except Exception as exc:
            logger.error("close_by_signal_error", user_id=self.user_id,
                         pair=signal.pair, error=str(exc))

    async def _close_on_trailing_stop(self, order_id: str, tick) -> None:
        from bot.broker.models import Direction
        from bot.db.repository import TradeRepository

        stop = self.trailing_stop_mgr.get_stop(order_id)
        if not stop:
            return
        try:
            # Get actual size from DB trade or trailing stop state
            close_size = stop.size if hasattr(stop, 'size') and stop.size else 0
            if close_size <= 0:
                async with get_session() as session:
                    repo = TradeRepository(session, user_id=self.user_id)
                    trade = await repo.get_by_order_id(order_id)
                    if trade:
                        close_size = trade.size
            if close_size <= 0:
                logger.warning("trailing_stop_no_size", user_id=self.user_id, pair=stop.pair)
                return
            result = await self.broker.close_position(order_id=order_id, pair=stop.pair, size=close_size)
            self.trailing_stop_mgr.unregister(order_id)
            profit = (tick.last - stop.entry_price) * result.size if stop.direction == Direction.BUY else (stop.entry_price - tick.last) * result.size
            self.risk_manager.update_daily_pnl(profit)
            self._daily_pnl += profit
            async with get_session() as session:
                repo = TradeRepository(session, user_id=self.user_id)
                await repo.close_trade(order_id=order_id, exit_price=tick.last, profit=profit, fee=result.fee)
            await self._set_cooldown(stop.pair)
            await self.publish_log("INFO", "trade_closed", pair=stop.pair, profit=profit)

            # Publish trade_closed event to Redis
            if self._redis:
                try:
                    await self._redis.publish(
                        self._rkey("trades"),
                        json.dumps({
                            "type": "trade_closed", "pair": stop.pair,
                            "direction": stop.direction.value,
                            "price": tick.last, "profit": profit,
                        }),
                    )
                except Exception:
                    pass

            # Web Push notification (fire-and-forget)
            try:
                from bot.notifications_push import notify_trade_push
                asyncio.ensure_future(notify_trade_push(
                    user_id=self.user_id, trade_type="trade_closed",
                    pair=stop.pair, direction=stop.direction.value,
                    price=tick.last, profit=profit,
                ))
            except Exception:
                pass

            # Post-trade AI review (fire-and-forget)
            if self.ai_analyzer.is_enabled and self.cfg.ai_post_trade_enabled:
                asyncio.ensure_future(
                    self._run_post_trade_review(
                        pair=stop.pair,
                        direction=stop.direction.value,
                        entry_price=stop.entry_price,
                        exit_price=tick.last,
                        profit=profit,
                        size=result.size,
                        fee=result.fee,
                        strategy=getattr(stop, "strategy", None),
                        stop_loss=getattr(stop, "stop_loss", None),
                        take_profit=getattr(stop, "take_profit", None),
                    )
                )
        except Exception as exc:
            logger.error("trailing_stop_close_error", user_id=self.user_id, order_id=order_id, error=str(exc))

    async def _run_post_trade_review(
        self,
        pair: str,
        direction: str,
        entry_price: float,
        exit_price: float,
        profit: float,
        size: float = 0.0,
        fee: float = 0.0,
        strategy: str | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> None:
        """Run AI post-trade review and save it to DB."""
        from bot.db.repository import AIAnalysisRepository

        try:
            trade_data = {
                "pair": pair,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "profit": profit,
                "size": size,
                "fee": fee,
                "duration_minutes": 0,  # not tracked in trailing stop state
                "strategy": strategy or "unknown",
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            }

            review = await self.ai_analyzer.review_closed_trade(trade_data)

            # Save as AIAnalysisLog with mode="post_trade"
            async with get_session() as session:
                ai_repo = AIAnalysisRepository(session, user_id=self.user_id)
                await ai_repo.save(
                    pair=pair,
                    mode="post_trade",
                    verdict=review.get("verdict", "APPROVE"),
                    confidence=review.get("confidence", 0.0),
                    reasoning=review.get("reasoning", ""),
                    market_summary=review.get("market_summary", ""),
                    risk_warnings=review.get("risk_warnings", []),
                    suggested_adjustments={
                        "score": review.get("score", 5),
                        "lessons_learned": review.get("lessons_learned", []),
                        "what_went_well": review.get("what_went_well", []),
                        "what_could_improve": review.get("what_could_improve", []),
                    },
                    signal_direction=direction,
                    signal_strategy=strategy or "unknown",
                    model_used=review.get("model_used", ""),
                    latency_ms=review.get("latency_ms", 0),
                )

            logger.info(
                "post_trade_review_done",
                user_id=self.user_id,
                pair=pair,
                score=review.get("score", 5),
                profit=profit,
            )
        except Exception as exc:
            logger.error(
                "post_trade_review_error",
                user_id=self.user_id,
                pair=pair,
                error=str(exc),
            )

    async def _log_shadow_trade(self, signal) -> None:
        import time as _time
        from bot.db.repository import TradeRepository

        async with get_session() as session:
            repo = TradeRepository(session, user_id=self.user_id)
            ticker = await self.broker.get_ticker(signal.pair)
            await repo.create_trade(
                order_id=f"shadow_{signal.pair}_{int(_time.time())}",
                pair=signal.pair, direction=signal.direction.value,
                size=0.0, entry_price=ticker.last,
                strategy=signal.strategy_name, status="SHADOW",
                metadata_=signal.metadata,
            )

    async def _run_ai_validation(self, signal, positions, balance):
        from bot.db.repository import AIAnalysisRepository
        from bot.data.indicators import add_all_indicators

        try:
            cached_df = self.data_mgr.get_cached(signal.pair, 60)
            recent_bars = []
            if cached_df is not None and not cached_df.empty:
                for _, row in cached_df.tail(10).iterrows():
                    recent_bars.append({
                        "open": row["open"], "high": row["high"],
                        "low": row["low"], "close": row["close"], "volume": row["volume"],
                    })
            pos_dicts = [
                {"pair": p.pair, "direction": p.direction.value, "size": p.size, "entry_price": p.entry_price}
                for p in positions
            ]
            ai_result = await self.ai_analyzer.validate_signal(
                pair=signal.pair, direction=signal.direction.value,
                strategy=signal.strategy_name, confidence=signal.confidence,
                indicators=signal.metadata, recent_bars=recent_bars,
                open_positions=pos_dicts, account_balance=balance.available_balance,
            )
            async with get_session() as session:
                ai_repo = AIAnalysisRepository(session, user_id=self.user_id)
                await ai_repo.save(
                    pair=signal.pair, mode="pre_trade",
                    verdict=ai_result.verdict.value, confidence=ai_result.confidence,
                    reasoning=ai_result.reasoning, market_summary=ai_result.market_summary,
                    risk_warnings=ai_result.risk_warnings,
                    suggested_adjustments=ai_result.suggested_adjustments,
                    signal_direction=signal.direction.value,
                    signal_strategy=signal.strategy_name,
                    model_used=ai_result.model_used,
                    tokens_used=ai_result.tokens_used, latency_ms=ai_result.latency_ms,
                )
            return ai_result
        except Exception as exc:
            logger.error("ai_validation_error", user_id=self.user_id, error=str(exc))
            return None

    # ── Background loops ───────────────────────────────

    async def _check_stops_polling(self) -> None:
        """Fallback stop-loss/take-profit check via REST polling.

        Runs every cycle in case WebSocket ticks are not arriving.
        """
        from bot.db.repository import TradeRepository
        from bot.broker.models import Direction

        try:
            async with get_session() as session:
                repo = TradeRepository(session, user_id=self.user_id)
                open_trades = await repo.get_open_trades()

            if not open_trades:
                return

            for trade in open_trades:
                try:
                    ticker = await self.broker.get_ticker(trade.pair)
                    price = ticker.last
                    if price <= 0:
                        continue

                    should_close = False
                    reason = ""

                    # Stop-loss check
                    if trade.stop_loss and price <= trade.stop_loss:
                        should_close = True
                        reason = f"stop_loss ({price:.4f} <= {trade.stop_loss:.4f})"

                    # Take-profit check
                    if trade.take_profit and price >= trade.take_profit:
                        should_close = True
                        reason = f"take_profit ({price:.4f} >= {trade.take_profit:.4f})"

                    if should_close:
                        logger.info("polling_stop_triggered", user_id=self.user_id,
                                    pair=trade.pair, reason=reason, price=price)
                        try:
                            result = await self.broker.close_position(
                                order_id=trade.order_id, pair=trade.pair, size=trade.size
                            )
                            # Fetch real fee from Kraken
                            close_fee = 0.0
                            try:
                                import asyncio as _aio2
                                await _aio2.sleep(1)
                                filled = await self.broker.exchange.fetch_order(result.order_id, trade.pair)
                                close_fee = float((filled.get("fee") or {}).get("cost", 0))
                            except Exception:
                                pass
                            fee = close_fee
                            profit = (price - trade.entry_price) * trade.size - fee - (trade.fee or 0)
                            self._daily_pnl += profit

                            async with get_session() as session:
                                repo = TradeRepository(session, user_id=self.user_id)
                                await repo.close_trade(
                                    order_id=trade.order_id,
                                    exit_price=price,
                                    profit=profit,
                                    fee=fee,
                                )

                            # Unregister from trailing stop if registered
                            self.trailing_stop_mgr.unregister(trade.order_id)

                            await self._set_cooldown(trade.pair)
                            logger.info("trade_closed_by_polling", user_id=self.user_id,
                                        pair=trade.pair, profit=round(profit, 4),
                                        exit_price=price, reason=reason)
                            await self.publish_log("INFO", "trade_closed",
                                                   pair=trade.pair, profit=round(profit, 4))

                            # Push notification
                            try:
                                from bot.notifications_push import notify_trade_push
                                asyncio.ensure_future(notify_trade_push(
                                    user_id=self.user_id, trade_type="trade_closed",
                                    pair=trade.pair, direction=trade.direction,
                                    price=price, profit=profit,
                                ))
                            except Exception:
                                pass
                        except Exception as exc:
                            logger.error("polling_close_error", user_id=self.user_id,
                                         pair=trade.pair, error=str(exc))
                    else:
                        # Update trailing stop: if price moved up, tighten stop-loss
                        if trade.stop_loss and trade.direction == "buy":
                            trail_pct = float(getattr(self.cfg, "risk_stop_loss_pct", 0.03))
                            new_stop = price * (1 - trail_pct)
                            if new_stop > trade.stop_loss:
                                async with get_session() as session:
                                    from sqlalchemy import update as sql_update
                                    from bot.db.models import Trade
                                    await session.execute(
                                        sql_update(Trade)
                                        .where(Trade.order_id == trade.order_id)
                                        .values(stop_loss=new_stop)
                                    )
                                    await session.commit()
                except Exception as exc:
                    logger.warning("stop_check_error", user_id=self.user_id,
                                   pair=trade.pair, error=str(exc))
        except Exception as exc:
            logger.warning("polling_stops_error", user_id=self.user_id, error=str(exc))

    async def _bar_update_loop(self) -> None:
        import pandas as pd
        from bot.data.indicators import add_all_indicators

        while self._running:
            await asyncio.sleep(120)  # 2 minutes for faster signal detection
            self._last_loop_run["bar_update"] = _time_mod.time()
            if not self.cfg.is_configured:
                continue

            # Check stops via polling (fallback for unreliable WebSocket)
            await self._check_stops_polling()
            # Merge default pairs + autopilot-activated pairs
            all_pairs = set(self._active_pairs)
            if self.autopilot and self.autopilot.active_scores:
                all_pairs.update(self.autopilot.active_scores.keys())
            for pair in list(all_pairs):
                try:
                    df = await self.data_mgr.get_bars(pair, interval_minutes=60, count=250)
                    if df.empty:
                        continue
                    df = add_all_indicators(df)
                    df_d1 = None
                    try:
                        df_d1 = await self.data_mgr.get_bars(pair, interval_minutes=1440, count=100)
                        if df_d1 is not None and not df_d1.empty:
                            df_d1 = add_all_indicators(df_d1)
                        else:
                            df_d1 = None
                    except Exception:
                        df_d1 = None
                    # Anomaly detection
                    anomalies = self.anomaly_detector.check(pair, df)
                    for a in anomalies:
                        await self.publish_log(
                            "WARNING" if a.severity in ("medium", "low") else "ERROR",
                            f"anomaly_{a.type}",
                            pair=a.pair, severity=a.severity, message=a.message,
                        )
                        if a.severity in ("high", "critical"):
                            try:
                                from bot.notifications_push import send_push_to_user
                                asyncio.ensure_future(send_push_to_user(
                                    self.user_id,
                                    f"Anomalie {a.pair}",
                                    a.message,
                                    tag=f"anomaly-{a.pair}",
                                ))
                            except Exception:
                                pass

                    if df_d1 is not None:
                        signals = self.strategy_registry.dispatch_bar_mtf(pair, df, df_d1)
                    else:
                        signals = self.strategy_registry.dispatch_bar(pair, df)
                    for signal in signals:
                        logger.info("signal_generated", user_id=self.user_id, pair=pair,
                                    direction=signal.direction.value, strategy=signal.strategy_name,
                                    trigger=signal.metadata.get("trigger", ""))
                        await self._process_signal(signal)
                except Exception as exc:
                    logger.error("bar_update_error", user_id=self.user_id, pair=pair, error=str(exc))

    async def _account_metrics_loop(self) -> None:
        from bot.metrics import account_balance_gauge, daily_pnl_gauge, open_positions_gauge

        while self._running:
            await asyncio.sleep(60)
            self._last_loop_run["account_metrics"] = _time_mod.time()
            if not self.cfg.is_configured:
                continue
            try:
                balance = await self.broker.get_account_balance()
                self._cached_balance = balance.available_balance or 100.0
                account_balance_gauge.set(balance.total_balance)
                daily_pnl_gauge.set(self.risk_manager.state.daily_pnl)
                positions = await self.broker.get_open_positions()
                open_positions_gauge.set(len(positions))
                if self._redis:
                    balance_data = {
                        "total_balance": balance.total_balance,
                        "available_balance": balance.available_balance,
                        "currency": balance.currency,
                        "open_positions": len(positions),
                        "positions": [
                            {
                                "pair": p.pair,
                                "direction": p.direction.value if hasattr(p.direction, "value") else str(p.direction),
                                "size": p.size, "entry_price": p.entry_price,
                                "unrealized_pnl": getattr(p, "unrealized_pnl", 0.0),
                            }
                            for p in positions
                        ],
                        "mode": "PAPER" if self.cfg.bot_paper_trading else "LIVE",
                    }
                    await self._redis.set(self._rkey("last_balance"), json.dumps(balance_data))
                    # Legacy key for backwards compat
                    await self._redis.set("bot:last_balance", json.dumps(balance_data))
            except Exception as exc:
                logger.error("metrics_error", user_id=self.user_id, error=str(exc))

    async def _autopilot_loop(self) -> None:
        if not self.autopilot:
            return
        while self._running:
            try:
                await self._autopilot_loop_inner()
            except Exception as exc:
                logger.error("autopilot_loop_crashed", user_id=self.user_id, error=str(exc))
                await asyncio.sleep(30)

    async def _autopilot_loop_inner(self) -> None:
        first_run = True
        while self._running:
            if first_run:
                first_run = False
                await asyncio.sleep(15)
            else:
                interval = self.cfg.autopilot_scan_interval_minutes * 60
                await asyncio.sleep(interval)
            self._last_loop_run["autopilot"] = _time_mod.time()
            if not self.cfg.is_configured or not self.autopilot.enabled:
                continue
            try:
                await self.publish_log("INFO", "autopilot_cycle_start", status="scanning")
                results = await self.autopilot.run_scan_cycle()
                active = self.autopilot.active_scores
                if results:
                    top_pairs = ", ".join(f"{s.pair}({s.composite:.0%})" for s in results[:5])
                    await self.publish_log(
                        "INFO", "autopilot_scan_done",
                        scanned=str(len(results)), active=str(len(active)), top=top_pairs,
                    )
                else:
                    await self.publish_log("WARNING", "autopilot_no_results", msg="No pairs above threshold")
                for pair, score in active.items():
                    await self.publish_log(
                        "DEBUG", "autopilot_pair_active", pair=pair,
                        score=f"{score.composite:.0%}", regime=score.regime,
                        direction=score.direction_bias, strategy=score.recommended_strategy or "auto",
                    )
            except Exception as exc:
                logger.error("autopilot_error", user_id=self.user_id, error=str(exc))
                try:
                    await self.publish_log("ERROR", "autopilot_error", error=str(exc))
                except Exception:
                    pass

    async def _price_alert_loop(self) -> None:
        """Check price alerts every 30 seconds."""
        from bot.db.repository import PriceAlertRepository

        while self._running:
            await asyncio.sleep(30)
            self._last_loop_run["price_alerts"] = _time_mod.time()
            try:
                async with get_session() as session:
                    repo = PriceAlertRepository(session, user_id=self.user_id)
                    alerts = await repo.get_active()
                    for alert in alerts:
                        try:
                            ticker = await self.broker.get_ticker(alert.pair)
                            triggered = False
                            if alert.condition == "above" and ticker.last >= alert.target_price:
                                triggered = True
                            elif alert.condition == "below" and ticker.last <= alert.target_price:
                                triggered = True
                            if triggered:
                                await repo.trigger(alert.id)
                                await session.commit()
                                # Send push notification
                                try:
                                    from bot.notifications_push import send_push_to_user
                                    direction = "\u2191" if alert.condition == "above" else "\u2193"
                                    await send_push_to_user(
                                        self.user_id,
                                        f"\U0001f514 Alerte {alert.pair}",
                                        f"{direction} Prix atteint: {ticker.last:.2f} (seuil: {alert.target_price:.2f})",
                                    )
                                except Exception:
                                    pass
                                await self.publish_log(
                                    "INFO", "price_alert_triggered",
                                    pair=alert.pair, price=ticker.last, target=alert.target_price,
                                )
                        except Exception:
                            pass
            except Exception as exc:
                logger.debug("price_alert_check_error", error=str(exc))

    async def _dca_loop(self) -> None:
        """Execute due DCA orders every 60 seconds."""
        from bot.db.repository import DCAScheduleRepository

        while self._running:
            await asyncio.sleep(60)
            self._last_loop_run["dca"] = _time_mod.time()
            try:
                now = datetime.now(timezone.utc)
                async with get_session() as session:
                    repo = DCAScheduleRepository(session, user_id=self.user_id)
                    all_scheds = await repo.get_all()
                    for sched in all_scheds:
                        if not sched.active or not sched.next_run or sched.next_run > now:
                            continue
                        try:
                            ticker = await self.broker.get_ticker(sched.pair)
                            size = sched.amount_usd / ticker.last
                            if size <= 0:
                                continue
                            from bot.broker.models import OrderRequest, Direction
                            order = OrderRequest(
                                pair=sched.pair, direction=Direction.BUY,
                                size=size, metadata={"source": "dca"},
                            )
                            result = await self.broker.open_position(order)

                            # Calculate next run
                            from datetime import timedelta
                            freq_map = {
                                "daily": timedelta(days=1),
                                "weekly": timedelta(weeks=1),
                                "biweekly": timedelta(weeks=2),
                                "monthly": timedelta(days=30),
                            }
                            next_run = now + freq_map.get(sched.frequency, timedelta(days=1))

                            await repo.record_execution(sched.id, sched.amount_usd, size, next_run)
                            await session.commit()

                            await self.publish_log(
                                "INFO", "dca_executed",
                                pair=sched.pair, amount=sched.amount_usd, size=size, price=ticker.last,
                            )

                            # Push notification
                            try:
                                from bot.notifications_push import send_push_to_user
                                await send_push_to_user(
                                    self.user_id,
                                    f"\U0001f4b0 DCA {sched.pair}",
                                    f"Achat {size:.6f} @ {ticker.last:.2f} ({sched.amount_usd} USD)",
                                )
                            except Exception:
                                pass
                        except Exception as exc:
                            logger.warning("dca_execution_error", pair=sched.pair, error=str(exc))
            except Exception as exc:
                logger.debug("dca_loop_error", error=str(exc))

    # ── Position sync (reconciliation Kraken ↔ DB) ────────

    async def _sync_positions_loop(self) -> None:
        """Every 5 minutes, reconcile Kraken positions with DB trades.
        - Close DB trades that no longer exist on Kraken
        - Register Kraken positions missing from DB
        """
        from bot.db.repository import TradeRepository

        while self._running:
            try:
                await asyncio.sleep(300)  # 5 minutes
                self._last_loop_run["sync_positions"] = _time_mod.time()

                if self.cfg.bot_paper_trading:
                    continue

                # Get real Kraken positions
                positions = await self.broker.get_open_positions()
                kraken_map = {}
                for p in positions:
                    val = p.size * p.current_price
                    if val >= 1.0:  # Ignore dust
                        kraken_map[p.pair] = p

                # Get DB open trades
                async with get_session() as session:
                    repo = TradeRepository(session, user_id=self.user_id)
                    db_trades = await repo.get_open_trades()

                    db_pairs = {}
                    for t in db_trades:
                        pair = t.pair
                        if pair not in db_pairs:
                            db_pairs[pair] = []
                        db_pairs[pair].append(t)

                    changes = False

                    # 1. Close DB trades not on Kraken anymore (position was sold)
                    for pair, trades in db_pairs.items():
                        if pair not in kraken_map:
                            for t in trades:
                                # Try to fetch the last known price for P&L calculation
                                try:
                                    ticker = await self.broker.get_ticker(pair)
                                    exit_price = ticker.last if ticker else (t.entry_price or 0)
                                except Exception:
                                    exit_price = t.entry_price or 0
                                entry_fee = t.fee or 0
                                exit_fee = exit_price * (t.size or 0) * 0.004  # estimate 0.4% fee
                                profit = (exit_price - (t.entry_price or 0)) * (t.size or 0) - entry_fee - exit_fee
                                t.status = "CLOSED"
                                t.exit_price = exit_price
                                t.profit = round(profit, 6)
                                t.fee = round(entry_fee + exit_fee, 6)
                                t.closed_at = _dt.datetime.now(_dt.timezone.utc)
                                logger.info("sync_closed_ghost", user_id=self.user_id,
                                            pair=pair, trade_id=t.id, profit=round(profit, 4),
                                            exit_price=exit_price)
                                changes = True

                    # 2. Close duplicate trades (keep only 1 per pair)
                    for pair, trades in db_pairs.items():
                        if pair in kraken_map and len(trades) > 1:
                            # Keep the most recent, close others
                            sorted_trades = sorted(trades, key=lambda t: t.id, reverse=True)
                            for t in sorted_trades[1:]:
                                t.status = "CLOSED"
                                t.closed_at = _dt.datetime.now(_dt.timezone.utc)
                                logger.info("sync_closed_duplicate", user_id=self.user_id,
                                            pair=pair, trade_id=t.id)
                                changes = True

                    # 3. Register Kraken positions missing from DB
                    db_open_pairs = {t.pair for t in db_trades if t.status not in ("closed", "CLOSED")}
                    for pair, pos in kraken_map.items():
                        if pair not in db_open_pairs:
                            sync_order_id = f"sync_{pair.replace('/', '_')}_{int(_time_mod.time())}"
                            trail_pct_sync = float(getattr(self.cfg, "risk_stop_loss_pct", 0.03)) * 100
                            await repo.create_trade(
                                order_id=sync_order_id,
                                pair=pair,
                                direction="buy",
                                size=pos.size,
                                entry_price=pos.current_price,
                                stop_loss=pos.current_price * (1 - trail_pct_sync / 100),
                                fee=0,
                                strategy="auto_sync",
                            )
                            # Register trailing stop for synced position
                            from bot.risk.trailing_stop import TrailingStopState
                            from bot.broker.models import Direction
                            trail_pct = float(getattr(self.cfg, "risk_stop_loss_pct", 0.03)) * 100
                            self.trailing_stop_mgr.register(
                                TrailingStopState(
                                    pair=pair,
                                    direction=Direction.BUY,
                                    entry_price=pos.current_price,
                                    trail_pct=trail_pct,
                                    order_id=sync_order_id,
                                )
                            )
                            logger.info("sync_registered_missing", user_id=self.user_id,
                                        pair=pair, size=pos.size, price=pos.current_price)
                            changes = True

                    if changes:
                        await session.commit()
                        logger.info("sync_positions_complete", user_id=self.user_id,
                                    kraken=len(kraken_map), db_before=len(db_trades))
                    else:
                        logger.debug("sync_positions_ok", user_id=self.user_id,
                                     positions=len(kraken_map))

            except Exception as exc:
                logger.debug("sync_loop_error", error=str(exc))

    async def _redis_command_listener(self) -> None:
        if not self._redis:
            return
        try:
            pubsub = self._redis.pubsub()
            # Listen on user-specific AND global channel
            await pubsub.subscribe(self._rkey("commands"), "bot:commands")
            while self._running:
                self._last_loop_run["redis_listener"] = _time_mod.time()
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    await self._handle_command(msg["data"].decode())
        except Exception as exc:
            logger.error("redis_listener_error", user_id=self.user_id, error=str(exc))

    async def _handle_command(self, command: str) -> None:
        logger.info("command_received", user_id=self.user_id, command=command)
        if command == "stop":
            self._running = False
        elif command == "reload_settings":
            await self.reload_settings()
        elif command == "autopilot_scan_now":
            if self.autopilot:
                await self.autopilot.run_scan_cycle()
        elif command == "daily_reset":
            self.risk_manager.reset_daily()


class UserBotManager:
    """Manages N UserBotContext instances – one per configured user."""

    def __init__(self) -> None:
        self.contexts: dict[int, UserBotContext] = {}
        self._redis: aioredis.Redis | None = None
        self._running = False
        self._context_tasks: dict[int, asyncio.Task] = {}

    async def start(self) -> None:
        logger.info("user_bot_manager_starting")

        await init_db()

        # Connect Redis
        try:
            self._redis = aioredis.from_url(settings.redis_url)
            await self._redis.ping()
            logger.info("redis_connected")
        except Exception as exc:
            logger.warning("redis_unavailable", error=str(exc))
            self._redis = None

        # Prometheus metrics
        from bot.metrics import start_metrics_server
        try:
            start_metrics_server(port=8001)
        except Exception:
            pass

        # Discover configured users
        from sqlalchemy import select
        async with get_session() as session:
            result = await session.execute(select(AdminUser))
            users = list(result.scalars().all())

        if not users:
            logger.warning("no_users_found", msg="No admin users in DB. Waiting for first login.")
            # Still keep running so the dashboard is accessible
            # Fall back to legacy single-bot mode using global settings
            await self._run_legacy_single_bot()
            return

        logger.info("users_discovered", count=len(users), users=[u.username for u in users])

        self._running = True

        # Create a context per user
        for user in users:
            user_settings = await _load_user_settings(user.id)
            ctx = UserBotContext(user.id, user_settings, self._redis)
            self.contexts[user.id] = ctx
            try:
                await ctx.start()
                task = asyncio.create_task(
                    ctx.run_loops(), name=f"user_bot_{user.id}"
                )
                self._context_tasks[user.id] = task
            except Exception as exc:
                logger.error("user_bot_start_error", user_id=user.id, error=str(exc))

        if self._context_tasks:
            from bot.notifications import notify_bot_status
            mode_summary = ", ".join(
                f"user:{uid}({'PAPER' if ctx.cfg.bot_paper_trading else 'LIVE'})"
                for uid, ctx in self.contexts.items()
            )
            await notify_bot_status(f"Multi-tenant bot started: {mode_summary}")

            # Run the health monitor alongside user tasks
            health_task = asyncio.create_task(
                self._health_monitor_loop(), name="health_monitor"
            )
            all_tasks = list(self._context_tasks.values()) + [health_task]
            await asyncio.gather(*all_tasks, return_exceptions=True)

    # ── Health monitor ──────────────────────────────────

    async def _health_monitor_loop(self) -> None:
        """Periodically check every context's health, publish to Redis, and
        auto-restart contexts that appear stalled."""
        while self._running:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            now = _time_mod.time()
            all_health: dict[str, Any] = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "contexts": {},
            }

            for uid, ctx in list(self.contexts.items()):
                health = ctx.health_status
                all_health["contexts"][str(uid)] = health

                # Check if context needs a restart: it must be running, started
                # more than 5 min ago, and have at least one dead loop.
                if not ctx._running:
                    continue
                if ctx._started_at and (now - ctx._started_at) < HEALTH_STALE_SECONDS:
                    # Too early to judge – loops haven't had a chance yet
                    continue

                dead_loops = [
                    name
                    for name, status in health["loops_status"].items()
                    if status == "dead"
                ]
                if dead_loops:
                    logger.warning(
                        "health_check_stale_loops",
                        user_id=uid,
                        dead_loops=dead_loops,
                        msg="Auto-restarting context",
                    )
                    await self._restart_context(uid)

                # Also restart if the context task itself has finished
                task = self._context_tasks.get(uid)
                if task and task.done():
                    exc = task.exception() if not task.cancelled() else None
                    logger.warning(
                        "health_check_task_dead",
                        user_id=uid,
                        error=str(exc) if exc else "task finished",
                        msg="Auto-restarting context",
                    )
                    await self._restart_context(uid)

            # Publish to Redis
            if self._redis:
                try:
                    payload = json.dumps(all_health)
                    await self._redis.set("bot:health", payload)
                    # Also per-user keys
                    for uid_str, h in all_health["contexts"].items():
                        await self._redis.set(
                            f"bot:user:{uid_str}:health", json.dumps(h)
                        )
                except Exception as exc:
                    logger.debug("health_redis_publish_error", error=str(exc))

            logger.debug(
                "health_check_complete",
                contexts=len(all_health["contexts"]),
            )

    async def _restart_context(self, user_id: int) -> None:
        """Stop and restart a single user's bot context."""
        ctx = self.contexts.get(user_id)
        if not ctx:
            return

        logger.info("restarting_user_context", user_id=user_id)

        # Cancel the existing task
        old_task = self._context_tasks.pop(user_id, None)
        if old_task and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except (asyncio.CancelledError, Exception):
                pass

        # Stop the old context gracefully
        try:
            await ctx.stop()
        except Exception as exc:
            logger.warning("restart_stop_error", user_id=user_id, error=str(exc))

        # Rebuild from fresh settings
        try:
            user_settings = await _load_user_settings(user_id)
            new_ctx = UserBotContext(user_id, user_settings, self._redis)
            self.contexts[user_id] = new_ctx
            await new_ctx.start()
            task = asyncio.create_task(
                new_ctx.run_loops(), name=f"user_bot_{user_id}"
            )
            self._context_tasks[user_id] = task
            logger.info("user_context_restarted", user_id=user_id)
        except Exception as exc:
            logger.error("restart_failed", user_id=user_id, error=str(exc))

    async def _run_legacy_single_bot(self) -> None:
        """Fallback: run the old single-bot when no users exist yet."""
        from bot.main import TradingBot
        bot = TradingBot()
        try:
            await bot.start()
        finally:
            await bot.stop()

    async def stop(self) -> None:
        self._running = False
        # Cancel all context tasks
        for uid, task in self._context_tasks.items():
            if not task.done():
                task.cancel()
        for uid, ctx in self.contexts.items():
            try:
                await ctx.stop()
            except Exception as exc:
                logger.error("user_bot_stop_error", user_id=uid, error=str(exc))
        self._context_tasks.clear()
        if self._redis:
            await self._redis.close()
        await close_db()
        logger.info("user_bot_manager_stopped")
