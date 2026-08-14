"""Add cashflow_role to transactions and the memory that learns it.

Records what the owner says a movement really was, so the app stops guessing
whether a transfer was earned, spent, or only moved between their own accounts,
and remembers the answer per counterparty so it never asks twice.

Revision ID: 20260814_0003
Revises: 20260701_0002
Create Date: 2026-08-14 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260814_0003"
down_revision: str | None = "20260701_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable on purpose: no answer means the automatic rules still apply, so
    # existing rows keep working without a backfill.
    op.add_column(
        "transactions",
        sa.Column("cashflow_role", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_transactions_cashflow_role",
        "transactions",
        ["cashflow_role"],
    )

    op.create_table(
        "cashflow_role_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("confirmation_count", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "merchant_key",
            "transaction_type",
            name="uq_cashflow_role_memory_owner_key_type",
        ),
    )
    op.create_index(
        "ix_cashflow_role_memories_id", "cashflow_role_memories", ["id"]
    )
    op.create_index(
        "ix_cashflow_role_memories_owner_id", "cashflow_role_memories", ["owner_id"]
    )
    op.create_index(
        "ix_cashflow_role_memories_transaction_type",
        "cashflow_role_memories",
        ["transaction_type"],
    )
    op.create_index(
        "ix_cashflow_role_memories_owner_key",
        "cashflow_role_memories",
        ["owner_id", "merchant_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_cashflow_role_memories_owner_key", table_name="cashflow_role_memories")
    op.drop_index("ix_cashflow_role_memories_transaction_type", table_name="cashflow_role_memories")
    op.drop_index("ix_cashflow_role_memories_owner_id", table_name="cashflow_role_memories")
    op.drop_index("ix_cashflow_role_memories_id", table_name="cashflow_role_memories")
    op.drop_table("cashflow_role_memories")
    op.drop_index("ix_transactions_cashflow_role", table_name="transactions")
    op.drop_column("transactions", "cashflow_role")
