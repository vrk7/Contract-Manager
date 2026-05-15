"""add index on playbook_chunks.version_id for fast per-version lookups

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-15 00:01:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_playbook_chunks_version_id", "playbook_chunks", ["version_id"])


def downgrade() -> None:
    op.drop_index("ix_playbook_chunks_version_id", table_name="playbook_chunks")
