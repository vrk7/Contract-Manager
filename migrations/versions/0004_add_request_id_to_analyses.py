"""add request_id column to analyses for request tracing

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-15 00:02:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("request_id", sa.String(), nullable=True))
    op.create_index("ix_analyses_request_id", "analyses", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_analyses_request_id", table_name="analyses")
    op.drop_column("analyses", "request_id")
