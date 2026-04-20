"""Configuration management – DB-first with .env fallback.

Settings hierarchy:
  1. Database (app_settings table) – set via dashboard UI
  2. .env file – initial defaults / infrastructure config
  3. Hardcoded defaults

Only infrastructure settings (DB, Redis, Dashboard) stay in .env.
All trading settings (Kraken creds, risk, autopilot, telegram) are
managed from the dashboard and stored encrypted in the database.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = structlog.get_logger(__name__)

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# Keys that contain secrets and must be encrypted in DB
SENSITIVE_KEYS: set[str] = {
    "kraken_api_key",
    "kraken_api_secret",
    "exchange_password",
    "telegram_bot_token",
    "ai_api_key",
}

# All settings manageable from the dashboard, grouped by category
SETTINGS_SCHEMA: dict[str, dict[str, dict[str, Any]]] = {
    "kraken": {
        "exchange_id": {
            "label": "Exchange",
            "type": "select",
            "options": ["kraken", "binance", "coinbase", "okx", "bybit", "kucoin", "bitfinex", "gateio"],
            "default": "kraken",
        },
        "kraken_api_key": {"label": "API Key", "type": "password", "default": ""},
        "kraken_api_secret": {"label": "API Secret", "type": "password", "default": ""},
        "exchange_password": {"label": "Exchange Password/Passphrase (si requis)", "type": "password", "default": ""},
        "exchange_quote_currency": {
            "label": "Devise de cotation",
            "type": "select",
            "options": ["USD", "USDT", "EUR", "USDC"],
            "default": "USD",
        },
        "kraken_acc_type": {
            "label": "Account Type",
            "type": "select",
            "options": ["DEMO", "LIVE"],
            "default": "DEMO",
        },
    },
    "risk": {
        "bot_max_daily_loss": {"label": "Max Daily Loss ($)", "type": "number", "default": -500.0},
        "bot_max_position_size": {"label": "Max Position Size", "type": "number", "default": 1.0},
        "bot_max_open_positions": {"label": "Max Open Positions", "type": "number", "default": 5},
        "bot_max_per_pair": {"label": "Max Per Pair", "type": "number", "default": 1},
        "bot_risk_per_trade_pct": {"label": "Risk Per Trade (%)", "type": "number", "default": 2.0},
        "bot_default_stop_pct": {"label": "Default Stop (%)", "type": "number", "default": 3.0},
        "bot_default_limit_pct": {"label": "Default Limit (%)", "type": "number", "default": 6.0},
        "bot_paper_trading": {"label": "Paper Trading Mode", "type": "toggle", "default": True},
        "risk_max_daily_loss_pct": {"label": "Max Daily Loss (%)", "type": "number", "default": 0.05, "min": 0.01, "max": 0.5},
        "risk_stop_loss_pct": {"label": "Stop Loss (%)", "type": "number", "default": 0.03},
        "risk_max_position_pct": {"label": "Max Position Size (%)", "type": "number", "default": 0.15},
        "risk_max_open_trades": {"label": "Max Open Trades", "type": "number", "default": 4},
        "use_post_only_orders": {"label": "Post-only limit orders (saves ~0.15% per leg)", "type": "toggle", "default": True},
        "post_only_max_wait_sec": {"label": "Post-only fill timeout (seconds)", "type": "number", "default": 60},
        "strategy_autodisable_enabled": {"label": "Auto-disable losing strategies (30d)", "type": "toggle", "default": True},
        "strategy_autodisable_min_trades": {"label": "Auto-disable: min closed trades (30d)", "type": "number", "default": 10},
        "strategy_autodisable_lookback_days": {"label": "Auto-disable: lookback window (days)", "type": "number", "default": 30},
    },
    "autopilot": {
        "autopilot_enabled": {"label": "Enabled", "type": "toggle", "default": True},
        "autopilot_shadow_mode": {"label": "Shadow Mode (paper)", "type": "toggle", "default": True},
        "autopilot_scan_interval_minutes": {"label": "Scan Interval (min)", "type": "number", "default": 60},
        "autopilot_max_active": {"label": "Max Active Pairs", "type": "number", "default": 3},
        "autopilot_min_score": {"label": "Min Score Threshold", "type": "number", "default": 0.40},
        "autopilot_allowed_strategies": {
            "label": "Autopilot allowed strategies (comma-separated)",
            "type": "text",
            "default": "funding_divergence",
        },
    },
    "notifications": {
        "telegram_bot_token": {"label": "Telegram Bot Token", "type": "password", "default": ""},
        "telegram_chat_id": {"label": "Telegram Chat ID", "type": "text", "default": ""},
        "discord_webhook_url": {"label": "Discord Webhook URL", "type": "text", "default": ""},
        "discord_enabled": {"label": "Notifications Discord", "type": "toggle", "default": False},
    },
    "ai": {
        "ai_enabled": {"label": "Activer l'analyse IA", "type": "toggle", "default": False},
        "ai_api_key": {"label": "Cle API Claude (Anthropic)", "type": "password", "default": ""},
        "ai_model": {
            "label": "Modele Claude",
            "type": "select",
            "options": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001", "claude-opus-4-6"],
            "default": "claude-sonnet-4-6",
        },
        "ai_max_tokens": {"label": "Max tokens par requete", "type": "number", "default": 1024},
        "ai_pre_trade_enabled": {"label": "Validation pre-trade", "type": "toggle", "default": True},
        "ai_market_review_enabled": {"label": "Revue de marche periodique", "type": "toggle", "default": False},
        "ai_sentiment_enabled": {"label": "Analyse de sentiment", "type": "toggle", "default": False},
        "ai_post_trade_enabled": {"label": "Analyse post-trade", "type": "toggle", "default": True},
        "ai_min_confidence": {"label": "Confiance min. pour valider (%)", "type": "number", "default": 0.5},
    },
    "polymarket": {
        "polymarket_enabled": {"label": "Enable Polymarket Sentiment", "type": "toggle", "default": True},
        "polymarket_cache_ttl_minutes": {"label": "Cache TTL (minutes)", "type": "number", "default": 15},
    },
    "targets": {
        "profit_target_daily": {"type": "number", "label": "Objectif quotidien ($)", "default": 10.0},
        "profit_target_weekly": {"type": "number", "label": "Objectif hebdomadaire ($)", "default": 50.0},
    },
}

# Flat set of all DB-manageable keys
ALL_DB_KEYS: set[str] = {
    key for group in SETTINGS_SCHEMA.values() for key in group
}


class Settings(BaseSettings):
    """Settings loaded from .env – infrastructure only."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Infrastructure (always from .env) ──────────────
    db_host: str = "timescaledb"
    db_port: int = 5432
    db_name: str = "trading_kraken"
    db_user: str = "trader"
    db_password: str = "change_me_in_production"

    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""

    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000
    dashboard_secret_key: str = "change_me_random_secret_key"
    dashboard_admin_user: str = "admin"
    dashboard_admin_password: str = "admin"

    log_level: str = "INFO"

    # ── Trading settings (overridden by DB at runtime) ─
    exchange_id: str = "kraken"
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    exchange_password: str = ""
    exchange_quote_currency: str = "USD"
    kraken_acc_type: Literal["LIVE", "DEMO"] = "DEMO"

    bot_max_daily_loss: float = -500.0
    bot_max_position_size: float = 1.0
    bot_max_open_positions: int = 5
    bot_max_per_pair: int = 1
    bot_risk_per_trade_pct: float = 2.0
    bot_default_stop_pct: float = 3.0
    bot_default_limit_pct: float = 6.0
    bot_paper_trading: bool = True
    risk_max_daily_loss_pct: float = 0.05
    risk_stop_loss_pct: float = 0.03
    risk_max_position_pct: float = 0.15
    risk_max_open_trades: int = 4
    use_post_only_orders: bool = True
    post_only_max_wait_sec: int = 60
    strategy_autodisable_enabled: bool = True
    strategy_autodisable_min_trades: int = 10
    strategy_autodisable_lookback_days: int = 30

    autopilot_enabled: bool = True
    autopilot_shadow_mode: bool = True
    autopilot_scan_interval_minutes: int = 30
    autopilot_max_active: int = 3
    autopilot_min_score: float = 0.40
    # Comma-separated whitelist of strategy keys that autopilot may instantiate.
    # Only strategies listed here will be attached to qualifying pairs. Leave
    # empty to restore the legacy behaviour (no filter).
    autopilot_allowed_strategies: str = "funding_divergence"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    discord_webhook_url: str = ""
    discord_enabled: bool = False

    # ── AI (Claude) ────────────────────────────────────
    ai_enabled: bool = False
    ai_api_key: str = ""
    ai_model: str = "claude-sonnet-4-6"
    ai_max_tokens: int = 1024
    ai_pre_trade_enabled: bool = True
    ai_market_review_enabled: bool = False
    ai_sentiment_enabled: bool = False
    ai_post_trade_enabled: bool = True
    ai_min_confidence: float = 0.5

    # ── Polymarket ─────────────────────────────────────
    polymarket_enabled: bool = True
    polymarket_cache_ttl_minutes: int = 15

    # ── Profit Targets ──────────────────────────────────
    profit_target_daily: float = 10.0
    profit_target_weekly: float = 50.0

    # ── Derived ────────────────────────────────────────
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/0"

    def apply_db_overrides(self, db_values: dict[str, str]) -> None:
        """Apply settings loaded from the database over current values."""
        type_map = {
            "float": float,
            "int": int,
            "bool": lambda v: v.lower() in ("true", "1", "yes", "on"),
            "str": str,
        }
        count = 0
        for key, raw_value in db_values.items():
            if not hasattr(self, key):
                continue
            current = getattr(self, key)
            try:
                if isinstance(current, bool):
                    coerced = type_map["bool"](raw_value)
                elif isinstance(current, int):
                    coerced = int(float(raw_value))
                elif isinstance(current, float):
                    coerced = float(raw_value)
                else:
                    coerced = raw_value
                object.__setattr__(self, key, coerced)
                count += 1
            except (ValueError, TypeError) as exc:
                logger.warning("config_coerce_error", key=key, error=str(exc))
        if count:
            logger.info("settings_loaded_from_db", count=count)

    @property
    def is_configured(self) -> bool:
        """True if Kraken API credentials are set or paper trading is enabled."""
        if self.bot_paper_trading:
            return True
        return bool(self.kraken_api_key and self.kraken_api_secret)


settings = Settings()


class UserSettings:
    """Per-user trading settings loaded from the database.

    Infrastructure settings (DB, Redis, ports) come from the global
    ``settings`` singleton.  Everything else is loaded per-user from
    the ``app_settings`` table filtered by ``user_id``.
    """

    # Defaults mirrored from Settings class / SETTINGS_SCHEMA
    _DEFAULTS: dict[str, Any] = {
        "exchange_id": "kraken",
        "kraken_api_key": "",
        "kraken_api_secret": "",
        "exchange_password": "",
        "exchange_quote_currency": "USD",
        "kraken_acc_type": "DEMO",
        "bot_max_daily_loss": -500.0,
        "bot_max_position_size": 1.0,
        "bot_max_open_positions": 5,
        "bot_max_per_pair": 1,
        "bot_risk_per_trade_pct": 2.0,
        "bot_default_stop_pct": 3.0,
        "bot_default_limit_pct": 6.0,
        "bot_paper_trading": True,
        "risk_max_daily_loss_pct": 0.05,
        "risk_stop_loss_pct": 0.03,
        "risk_max_position_pct": 0.15,
        "risk_max_open_trades": 4,
        "use_post_only_orders": True,
        "post_only_max_wait_sec": 60,
        "strategy_autodisable_enabled": True,
        "strategy_autodisable_min_trades": 10,
        "strategy_autodisable_lookback_days": 30,
        "autopilot_enabled": True,
        "autopilot_shadow_mode": True,
        "autopilot_scan_interval_minutes": 30,
        "autopilot_max_active": 3,
        "autopilot_min_score": 0.40,
        "autopilot_allowed_strategies": "funding_divergence",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "discord_webhook_url": "",
        "discord_enabled": False,
        "ai_enabled": False,
        "ai_api_key": "",
        "ai_model": "claude-sonnet-4-6",
        "ai_max_tokens": 1024,
        "ai_pre_trade_enabled": True,
        "ai_market_review_enabled": False,
        "ai_sentiment_enabled": False,
        "ai_post_trade_enabled": True,
        "ai_min_confidence": 0.5,
        "polymarket_enabled": True,
        "polymarket_cache_ttl_minutes": 15,
        "profit_target_daily": 10.0,
        "profit_target_weekly": 50.0,
    }

    def __init__(self, user_id: int) -> None:
        self.user_id = user_id
        self._values: dict[str, Any] = dict(self._DEFAULTS)

    # ── Attribute access (dynamic) ──────────────────────
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name == "user_id":
            raise AttributeError(name)
        try:
            return self._values[name]
        except KeyError:
            # Fall through to global settings for infra keys
            return getattr(settings, name)

    # ── Load from DB ────────────────────────────────────
    def apply_db_overrides(self, db_values: dict[str, str]) -> None:
        """Apply user-specific settings from the database."""
        for key, raw_value in db_values.items():
            if key not in self._DEFAULTS:
                continue
            default = self._DEFAULTS[key]
            try:
                if isinstance(default, bool):
                    self._values[key] = raw_value.lower() in ("true", "1", "yes", "on")
                elif isinstance(default, int):
                    self._values[key] = int(float(raw_value))
                elif isinstance(default, float):
                    self._values[key] = float(raw_value)
                else:
                    self._values[key] = raw_value
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "user_config_coerce_error",
                    user_id=self.user_id, key=key, error=str(exc),
                )

    @property
    def is_configured(self) -> bool:
        if self._values.get("bot_paper_trading"):
            return True
        return bool(
            self._values.get("kraken_api_key")
            and self._values.get("kraken_api_secret")
        )

    # Infrastructure (delegated to global)
    @property
    def database_url(self) -> str:
        return settings.database_url

    @property
    def redis_url(self) -> str:
        return settings.redis_url
