"""add users table and user_id FK on analyses

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-16 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.add_column("analyses", sa.Column("user_id", sa.String(), nullable=True))
    op.create_foreign_key("fk_analyses_user_id", "analyses", "users", ["user_id"], ["id"])
    op.create_index("ix_analyses_user_id", "analyses", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_analyses_user_id", table_name="analyses")
    op.drop_constraint("fk_analyses_user_id", "analyses", type_="foreignkey")
    op.drop_column("analyses", "user_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
