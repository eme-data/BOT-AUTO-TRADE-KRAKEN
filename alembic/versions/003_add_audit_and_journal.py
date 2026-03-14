"""Add audit_logs and trade_notes tables.

Revision ID: 003_audit_journal
Revises: 002_add_user_id
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = "003_audit_journal"
down_revision = "002_add_user_id"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    return name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("audit_logs"):
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("admin_users.id"), nullable=True),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("resource", sa.String(64), nullable=True),
            sa.Column("resource_id", sa.String(128), nullable=True),
            sa.Column("details", sa.JSON, nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_action", "audit_logs", ["action"])

    if not _table_exists("trade_notes"):
        op.create_table(
            "trade_notes",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.Integer, sa.ForeignKey("admin_users.id"), nullable=False),
            sa.Column("trade_id", sa.Integer, sa.ForeignKey("trades.id"), nullable=True),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("tags", sa.JSON, nullable=True),
            sa.Column("mood", sa.String(16), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_trade_notes_user_id", "trade_notes", ["user_id"])
        op.create_index("ix_trade_notes_trade_id", "trade_notes", ["trade_id"])


def downgrade() -> None:
    if _table_exists("trade_notes"):
        op.drop_table("trade_notes")
    if _table_exists("audit_logs"):
        op.drop_table("audit_logs")
