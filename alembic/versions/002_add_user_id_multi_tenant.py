"""Add user_id to all tables for multi-tenant isolation.

Revision ID: 002_add_user_id
Revises: 001_initial_schema
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002_add_user_id"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- admin_users: add role column if missing ---
    op.add_column(
        "admin_users",
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
    )

    # --- trades: add user_id FK ---
    op.add_column(
        "trades",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_trades_user_id", "trades", ["user_id"])

    # --- signals: add user_id FK ---
    op.add_column(
        "signals",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_signals_user_id", "signals", ["user_id"])

    # --- app_settings: add user_id FK + composite unique ---
    op.add_column(
        "app_settings",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_app_settings_user_id", "app_settings", ["user_id"])
    # Drop old unique index on key alone, replace with composite
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.create_index("ix_app_settings_key", "app_settings", ["key"])
    op.create_unique_constraint(
        "uq_app_settings_key_user", "app_settings", ["key", "user_id"]
    )

    # --- strategy_state: add user_id FK + composite unique ---
    op.add_column(
        "strategy_state",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_strategy_state_user_id", "strategy_state", ["user_id"])
    # Drop old unique on name, replace with composite
    op.drop_constraint("strategy_state_name_key", "strategy_state", type_="unique")
    op.create_unique_constraint(
        "uq_strategy_state_name_user", "strategy_state", ["name", "user_id"]
    )

    # --- watched_markets: add user_id FK + composite unique ---
    op.add_column(
        "watched_markets",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_watched_markets_user_id", "watched_markets", ["user_id"])
    # Drop old unique on pair, replace with composite
    op.drop_constraint("watched_markets_pair_key", "watched_markets", type_="unique")
    op.create_unique_constraint(
        "uq_watched_markets_pair_user", "watched_markets", ["pair", "user_id"]
    )

    # --- daily_pnl: add user_id FK + composite unique ---
    op.add_column(
        "daily_pnl",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_daily_pnl_user_id", "daily_pnl", ["user_id"])
    # Drop old unique on date, replace with composite
    op.drop_constraint("daily_pnl_date_key", "daily_pnl", type_="unique")
    op.create_unique_constraint(
        "uq_daily_pnl_date_user", "daily_pnl", ["date", "user_id"]
    )

    # --- ai_analysis_logs: add user_id FK ---
    op.add_column(
        "ai_analysis_logs",
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_ai_analysis_logs_user_id", "ai_analysis_logs", ["user_id"])


def downgrade() -> None:
    # --- ai_analysis_logs ---
    op.drop_index("ix_ai_analysis_logs_user_id", table_name="ai_analysis_logs")
    op.drop_column("ai_analysis_logs", "user_id")

    # --- daily_pnl ---
    op.drop_constraint("uq_daily_pnl_date_user", "daily_pnl", type_="unique")
    op.create_unique_constraint("daily_pnl_date_key", "daily_pnl", ["date"])
    op.drop_index("ix_daily_pnl_user_id", table_name="daily_pnl")
    op.drop_column("daily_pnl", "user_id")

    # --- watched_markets ---
    op.drop_constraint("uq_watched_markets_pair_user", "watched_markets", type_="unique")
    op.create_unique_constraint("watched_markets_pair_key", "watched_markets", ["pair"])
    op.drop_index("ix_watched_markets_user_id", table_name="watched_markets")
    op.drop_column("watched_markets", "user_id")

    # --- strategy_state ---
    op.drop_constraint("uq_strategy_state_name_user", "strategy_state", type_="unique")
    op.create_unique_constraint("strategy_state_name_key", "strategy_state", ["name"])
    op.drop_index("ix_strategy_state_user_id", table_name="strategy_state")
    op.drop_column("strategy_state", "user_id")

    # --- app_settings ---
    op.drop_constraint("uq_app_settings_key_user", "app_settings", type_="unique")
    op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)
    op.drop_index("ix_app_settings_user_id", table_name="app_settings")
    op.drop_column("app_settings", "user_id")

    # --- signals ---
    op.drop_index("ix_signals_user_id", table_name="signals")
    op.drop_column("signals", "user_id")

    # --- trades ---
    op.drop_index("ix_trades_user_id", table_name="trades")
    op.drop_column("trades", "user_id")

    # --- admin_users ---
    op.drop_column("admin_users", "role")
