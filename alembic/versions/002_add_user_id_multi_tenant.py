"""Add user_id to all tables for multi-tenant isolation.

Revision ID: 002_add_user_id
Revises: 001_initial_schema
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = "002_add_user_id"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    """Check if a column already exists in a table."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def _has_constraint(table: str, name: str) -> bool:
    """Check if a unique constraint exists."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    ucs = inspector.get_unique_constraints(table)
    return any(c["name"] == name for c in ucs)


def _has_index(table: str, name: str) -> bool:
    """Check if an index exists."""
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    indexes = inspector.get_indexes(table)
    return any(i["name"] == name for i in indexes)


def _add_user_id_column(table: str) -> None:
    """Add user_id FK column if it doesn't exist."""
    if not _has_column(table, "user_id"):
        op.add_column(
            table,
            sa.Column(
                "user_id",
                sa.Integer,
                sa.ForeignKey("admin_users.id"),
                nullable=True,
            ),
        )
    idx_name = f"ix_{table}_user_id"
    if not _has_index(table, idx_name):
        op.create_index(idx_name, table, ["user_id"])


def upgrade() -> None:
    # --- admin_users: add role column if missing ---
    if not _has_column("admin_users", "role"):
        op.add_column(
            "admin_users",
            sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        )

    # --- Add user_id to all data tables ---
    for table in ["trades", "signals", "app_settings", "strategy_state",
                   "watched_markets", "daily_pnl", "ai_analysis_logs"]:
        _add_user_id_column(table)

    # --- app_settings: composite unique (key, user_id) ---
    if _has_index("app_settings", "ix_app_settings_key"):
        # Check if it's a unique index
        bind = op.get_bind()
        inspector = sa_inspect(bind)
        indexes = inspector.get_indexes("app_settings")
        for idx in indexes:
            if idx["name"] == "ix_app_settings_key" and idx.get("unique"):
                op.drop_index("ix_app_settings_key", table_name="app_settings")
                op.create_index("ix_app_settings_key", "app_settings", ["key"])
                break
    if not _has_constraint("app_settings", "uq_app_settings_key_user"):
        op.create_unique_constraint(
            "uq_app_settings_key_user", "app_settings", ["key", "user_id"]
        )

    # --- strategy_state: composite unique (name, user_id) ---
    if not _has_constraint("strategy_state", "uq_strategy_state_name_user"):
        try:
            op.drop_constraint("strategy_state_name_key", "strategy_state", type_="unique")
        except Exception:
            pass
        op.create_unique_constraint(
            "uq_strategy_state_name_user", "strategy_state", ["name", "user_id"]
        )

    # --- watched_markets: composite unique (pair, user_id) ---
    if not _has_constraint("watched_markets", "uq_watched_markets_pair_user"):
        try:
            op.drop_constraint("watched_markets_pair_key", "watched_markets", type_="unique")
        except Exception:
            pass
        op.create_unique_constraint(
            "uq_watched_markets_pair_user", "watched_markets", ["pair", "user_id"]
        )

    # --- daily_pnl: composite unique (date, user_id) ---
    if not _has_constraint("daily_pnl", "uq_daily_pnl_date_user"):
        try:
            op.drop_constraint("daily_pnl_date_key", "daily_pnl", type_="unique")
        except Exception:
            pass
        op.create_unique_constraint(
            "uq_daily_pnl_date_user", "daily_pnl", ["date", "user_id"]
        )


def downgrade() -> None:
    # --- ai_analysis_logs ---
    if _has_index("ai_analysis_logs", "ix_ai_analysis_logs_user_id"):
        op.drop_index("ix_ai_analysis_logs_user_id", table_name="ai_analysis_logs")
    if _has_column("ai_analysis_logs", "user_id"):
        op.drop_column("ai_analysis_logs", "user_id")

    # --- daily_pnl ---
    if _has_constraint("daily_pnl", "uq_daily_pnl_date_user"):
        op.drop_constraint("uq_daily_pnl_date_user", "daily_pnl", type_="unique")
    op.create_unique_constraint("daily_pnl_date_key", "daily_pnl", ["date"])
    if _has_index("daily_pnl", "ix_daily_pnl_user_id"):
        op.drop_index("ix_daily_pnl_user_id", table_name="daily_pnl")
    if _has_column("daily_pnl", "user_id"):
        op.drop_column("daily_pnl", "user_id")

    # --- watched_markets ---
    if _has_constraint("watched_markets", "uq_watched_markets_pair_user"):
        op.drop_constraint("uq_watched_markets_pair_user", "watched_markets", type_="unique")
    op.create_unique_constraint("watched_markets_pair_key", "watched_markets", ["pair"])
    if _has_index("watched_markets", "ix_watched_markets_user_id"):
        op.drop_index("ix_watched_markets_user_id", table_name="watched_markets")
    if _has_column("watched_markets", "user_id"):
        op.drop_column("watched_markets", "user_id")

    # --- strategy_state ---
    if _has_constraint("strategy_state", "uq_strategy_state_name_user"):
        op.drop_constraint("uq_strategy_state_name_user", "strategy_state", type_="unique")
    op.create_unique_constraint("strategy_state_name_key", "strategy_state", ["name"])
    if _has_index("strategy_state", "ix_strategy_state_user_id"):
        op.drop_index("ix_strategy_state_user_id", table_name="strategy_state")
    if _has_column("strategy_state", "user_id"):
        op.drop_column("strategy_state", "user_id")

    # --- app_settings ---
    if _has_constraint("app_settings", "uq_app_settings_key_user"):
        op.drop_constraint("uq_app_settings_key_user", "app_settings", type_="unique")
    if _has_index("app_settings", "ix_app_settings_key"):
        op.drop_index("ix_app_settings_key", table_name="app_settings")
    op.create_index("ix_app_settings_key", "app_settings", ["key"], unique=True)
    if _has_index("app_settings", "ix_app_settings_user_id"):
        op.drop_index("ix_app_settings_user_id", table_name="app_settings")
    if _has_column("app_settings", "user_id"):
        op.drop_column("app_settings", "user_id")

    # --- signals ---
    if _has_index("signals", "ix_signals_user_id"):
        op.drop_index("ix_signals_user_id", table_name="signals")
    if _has_column("signals", "user_id"):
        op.drop_column("signals", "user_id")

    # --- trades ---
    if _has_index("trades", "ix_trades_user_id"):
        op.drop_index("ix_trades_user_id", table_name="trades")
    if _has_column("trades", "user_id"):
        op.drop_column("trades", "user_id")

    # --- admin_users ---
    if _has_column("admin_users", "role"):
        op.drop_column("admin_users", "role")
