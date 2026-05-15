"""create audit_log table for tracking data mutations

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-15 00:04:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("table_name", sa.String(64), nullable=False),
        sa.Column("row_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("changed_by", sa.String(), nullable=True),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.Column("diff_json", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_table_row", "audit_log", ["table_name", "row_id"])
    op.create_index("ix_audit_log_changed_at", "audit_log", ["changed_at"])


def downgrade() -> None:
    op.drop_index("ix_audit_log_changed_at", table_name="audit_log")
    op.drop_index("ix_audit_log_table_row", table_name="audit_log")
    op.drop_table("audit_log")
