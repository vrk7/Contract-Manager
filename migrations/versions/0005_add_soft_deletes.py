"""add deleted_at soft-delete column to analyses and playbook_versions

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-15 00:03:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.add_column("playbook_versions", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_analyses_deleted_at", "analyses", ["deleted_at"])
    op.create_index("ix_playbook_versions_deleted_at", "playbook_versions", ["deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_playbook_versions_deleted_at", table_name="playbook_versions")
    op.drop_index("ix_analyses_deleted_at", table_name="analyses")
    op.drop_column("playbook_versions", "deleted_at")
    op.drop_column("analyses", "deleted_at")
