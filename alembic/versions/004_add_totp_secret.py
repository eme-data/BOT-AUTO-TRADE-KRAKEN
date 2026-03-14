"""Add totp_secret column to admin_users for 2FA.

Revision ID: 004_totp_secret
Revises: 003_audit_journal
Create Date: 2026-03-14

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

# revision identifiers, used by Alembic.
revision = "004_totp_secret"
down_revision = "003_audit_journal"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa_inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    if not _has_column("admin_users", "totp_secret"):
        op.add_column(
            "admin_users",
            sa.Column("totp_secret", sa.String(64), nullable=True),
        )


def downgrade() -> None:
    if _has_column("admin_users", "totp_secret"):
        op.drop_column("admin_users", "totp_secret")
