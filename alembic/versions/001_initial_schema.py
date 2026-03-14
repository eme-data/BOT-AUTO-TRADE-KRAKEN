"""Initial schema – all core tables.

Revision ID: 001_initial_schema
Revises:
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- trades -----------------------------------------------------------
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(128), nullable=False),
        sa.Column("pair", sa.String(32), nullable=False),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("size", sa.Float, nullable=False),
        sa.Column("entry_price", sa.Float, nullable=False),
        sa.Column("exit_price", sa.Float, nullable=True),
        sa.Column("stop_loss", sa.Float, nullable=True),
        sa.Column("take_profit", sa.Float, nullable=True),
        sa.Column("fee", sa.Float, server_default="0.0"),
        sa.Column("profit", sa.Float, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("strategy", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trades_order_id", "trades", ["order_id"], unique=True)
    op.create_index("ix_trades_pair", "trades", ["pair"], unique=False)

    # Enable TimescaleDB hypertable on trades for time-series performance.
    # Requires the TimescaleDB extension to be installed on the database.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
    op.execute(
        "SELECT create_hypertable('trades', 'opened_at', "
        "migrate_data => true, if_not_exists => true)"
    )

    # --- signals ----------------------------------------------------------
    op.create_table(
        "signals",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pair", sa.String(32), nullable=False),
        sa.Column("strategy", sa.String(64), nullable=False),
        sa.Column("signal_type", sa.String(8), nullable=False),
        sa.Column("confidence", sa.Float, server_default="0.0"),
        sa.Column("indicators", sa.JSON, nullable=True),
        sa.Column("executed", sa.Boolean, server_default=sa.text("false")),
        sa.Column("order_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_signals_pair", "signals", ["pair"], unique=False)

    # --- app_settings -----------------------------------------------------
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("encrypted", sa.Boolean, server_default=sa.text("false")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)

    # --- strategy_state ---------------------------------------------------
    op.create_table(
        "strategy_state",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("true")),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("state", sa.JSON, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # --- watched_markets --------------------------------------------------
    op.create_table(
        "watched_markets",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pair", sa.String(32), nullable=False, unique=True),
        sa.Column("active", sa.Boolean, server_default=sa.text("true")),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    # --- daily_pnl --------------------------------------------------------
    op.create_table(
        "daily_pnl",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "date", sa.DateTime(timezone=True), nullable=False, unique=True
        ),
        sa.Column("realized_pnl", sa.Float, server_default="0.0"),
        sa.Column("unrealized_pnl", sa.Float, server_default="0.0"),
        sa.Column("winning_trades", sa.Integer, server_default="0"),
        sa.Column("losing_trades", sa.Integer, server_default="0"),
    )

    # --- ai_analysis_logs -------------------------------------------------
    op.create_table(
        "ai_analysis_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pair", sa.String(32), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float, server_default="0.0"),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("market_summary", sa.Text, nullable=True),
        sa.Column("risk_warnings", sa.JSON, nullable=True),
        sa.Column("suggested_adjustments", sa.JSON, nullable=True),
        sa.Column("signal_direction", sa.String(8), nullable=True),
        sa.Column("signal_strategy", sa.String(64), nullable=True),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("tokens_used", sa.Integer, server_default="0"),
        sa.Column("latency_ms", sa.Integer, server_default="0"),
        sa.Column("order_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_ai_analysis_logs_pair", "ai_analysis_logs", ["pair"], unique=False
    )

    # --- admin_users ------------------------------------------------------
    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(256), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("admin_users")
    op.drop_table("ai_analysis_logs")
    op.drop_table("daily_pnl")
    op.drop_table("watched_markets")
    op.drop_table("strategy_state")
    op.drop_table("app_settings")
    op.drop_table("signals")
    # trades is a TimescaleDB hypertable; standard DROP TABLE works fine.
    op.drop_table("trades")
    op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE")
