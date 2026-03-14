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
    "telegram_bot_token",
    "ai_api_key",
}

# All settings manageable from the dashboard, grouped by category
SETTINGS_SCHEMA: dict[str, dict[str, dict[str, Any]]] = {
    "kraken": {
        "kraken_api_key": {"label": "API Key", "type": "password", "default": ""},
        "kraken_api_secret": {"label": "API Secret", "type": "password", "default": ""},
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
    },
    "autopilot": {
        "autopilot_enabled": {"label": "Enabled", "type": "toggle", "default": False},
        "autopilot_shadow_mode": {"label": "Shadow Mode (paper)", "type": "toggle", "default": True},
        "autopilot_scan_interval_minutes": {"label": "Scan Interval (min)", "type": "number", "default": 60},
        "autopilot_max_active": {"label": "Max Active Pairs", "type": "number", "default": 3},
        "autopilot_min_score": {"label": "Min Score Threshold", "type": "number", "default": 0.55},
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
        "ai_post_trade_enabled": {"label": "Analyse post-trade", "type": "toggle", "default": False},
        "ai_min_confidence": {"label": "Confiance min. pour valider (%)", "type": "number", "default": 0.5},
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
    kraken_api_key: str = ""
    kraken_api_secret: str = ""
    kraken_acc_type: Literal["LIVE", "DEMO"] = "DEMO"

    bot_max_daily_loss: float = -500.0
    bot_max_position_size: float = 1.0
    bot_max_open_positions: int = 5
    bot_max_per_pair: int = 1
    bot_risk_per_trade_pct: float = 2.0
    bot_default_stop_pct: float = 3.0
    bot_default_limit_pct: float = 6.0
    bot_paper_trading: bool = True

    autopilot_enabled: bool = False
    autopilot_shadow_mode: bool = True
    autopilot_scan_interval_minutes: int = 30
    autopilot_max_active: int = 3
    autopilot_min_score: float = 0.55

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
    ai_post_trade_enabled: bool = False
    ai_min_confidence: float = 0.5

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
