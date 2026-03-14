"""SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
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


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    encrypted = Column(Boolean, default=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class StrategyState(Base):
    __tablename__ = "strategy_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    pair = Column(String(32), unique=True, nullable=False)
    active = Column(Boolean, default=True)
    added_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class DailyPnL(Base):
    __tablename__ = "daily_pnl"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime(timezone=True), nullable=False, unique=True)
    realized_pnl = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)


class AIAnalysisLog(Base):
    __tablename__ = "ai_analysis_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
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


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
