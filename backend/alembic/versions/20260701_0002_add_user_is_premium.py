"""Add is_premium flag to users.

Revision ID: 20260701_0002
Revises: 20260528_0001
Create Date: 2026-07-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0002"
down_revision: str | None = "20260528_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add the premium flag with a server default so existing users backfill to
    # False (free tier) without a null window.
    op.add_column(
        "users",
        sa.Column(
            "is_premium",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_premium")
