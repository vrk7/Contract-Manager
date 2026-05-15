"""add indexes on analyses for status and type queries

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-15 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_analyses_status_created_at", "analyses", ["status", "created_at"])
    op.create_index("ix_analyses_type_created_at", "analyses", ["analysis_type", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_analyses_type_created_at", table_name="analyses")
    op.drop_index("ix_analyses_status_created_at", table_name="analyses")
