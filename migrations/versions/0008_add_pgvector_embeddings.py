"""add pgvector extension and playbook_embeddings table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-06 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector — no-op on SQLite (which can't run pgvector anyway)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
        op.execute(
            """
            CREATE TABLE IF NOT EXISTS playbook_embeddings (
                chunk_id    TEXT        NOT NULL,
                version_id  TEXT        NOT NULL,
                content     TEXT        NOT NULL,
                content_hash TEXT       NOT NULL,
                embedding   vector(384),
                PRIMARY KEY (chunk_id, version_id)
            )
            """
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_pbe_version ON playbook_embeddings (version_id)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TABLE IF EXISTS playbook_embeddings")
        # Extension is intentionally left installed — shared with other potential users.
