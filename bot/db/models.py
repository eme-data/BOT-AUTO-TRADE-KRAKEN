"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")  # admin / editor / viewer
    totp_secret = Column(String(64), nullable=True)  # TOTP 2FA secret (None = disabled)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    order_id = Column(String(128), unique=True, nullable=False, index=True)
    pair = Column(String(32), nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # buy / sell
    size = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    fee = Column(Float, default=0.0)
    profit = Column(Float, nullable=True)
    status = Column(String(16), nullable=False, default="OPEN")  # OPEN / CLOSED / SHADOW
    strategy = Column(String(64), nullable=True)
    metadata_ = Column("metadata", JSON, nullable=True)
    opened_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    closed_at = Column(DateTime(timezone=True), nullable=True)


class SignalLog(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    pair = Column(String(32), nullable=False, index=True)
    strategy = Column(String(64), nullable=False)
    signal_type = Column(String(8), nullable=False)  # BUY / SELL / HOLD
    confidence = Column(Float, default=0.0)
    indicators = Column(JSON, nullable=True)
    executed = Column(Boolean, default=False)
    order_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    action = Column(String(64), nullable=False, index=True)  # login, settings_update, trade_opened, user_created, etc.
    resource = Column(String(64), nullable=True)  # settings, trade, user, bot
    resource_id = Column(String(128), nullable=True)  # ID of affected resource
    details = Column(JSON, nullable=True)  # extra context
    ip_address = Column(String(45), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"
    __table_args__ = (
        UniqueConstraint("key", "user_id", name="uq_app_settings_key_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    key = Column(String(128), nullable=False, index=True)
    value = Column(Text, nullable=True)
    encrypted = Column(Boolean, default=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StrategyState(Base):
    __tablename__ = "strategy_state"
    __table_args__ = (
        UniqueConstraint("name", "user_id", name="uq_strategy_state_name_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    name = Column(String(64), nullable=False)
    enabled = Column(Boolean, default=True)
    config = Column(JSON, nullable=True)
    state = Column(JSON, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class WatchedMarket(Base):
    __tablename__ = "watched_markets"
    __table_args__ = (
        UniqueConstraint("pair", "user_id", name="uq_watched_markets_pair_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    pair = Column(String(32), nullable=False)
    active = Column(Boolean, default=True)
    added_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class DailyPnL(Base):
    __tablename__ = "daily_pnl"
    __table_args__ = (
        UniqueConstraint("date", "user_id", name="uq_daily_pnl_date_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    date = Column(DateTime(timezone=True), nullable=False)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)


class TradeNote(Base):
    __tablename__ = "trade_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=False, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id"), nullable=True, index=True)
    content = Column(Text, nullable=False)
    tags = Column(JSON, nullable=True)  # ["mistake", "good_entry", "lesson_learned"]
    mood = Column(String(16), nullable=True)  # confident, uncertain, fearful, neutral
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(Text, nullable=False, unique=True)
    p256dh = Column(Text, nullable=False)
    auth = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class AIAnalysisLog(Base):
    __tablename__ = "ai_analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("admin_users.id"), nullable=True, index=True)
    pair = Column(String(32), nullable=False, index=True)
    mode = Column(String(32), nullable=False)  # pre_trade / market_review / sentiment / post_trade
    verdict = Column(String(16), nullable=False)  # APPROVE / REJECT / ADJUST
    confidence = Column(Float, default=0.0)
    reasoning = Column(Text, nullable=True)
    market_summary = Column(Text, nullable=True)
    risk_warnings = Column(JSON, nullable=True)
    suggested_adjustments = Column(JSON, nullable=True)
    signal_direction = Column(String(8), nullable=True)
    signal_strategy = Column(String(64), nullable=True)
    model_used = Column(String(64), nullable=True)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    order_id = Column(String(128), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
