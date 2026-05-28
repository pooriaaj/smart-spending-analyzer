"""Initial schema baseline.

Revision ID: 20260528_0001
Revises:
Create Date: 2026-05-28 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260528_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("reset_token_hash", sa.String(length=255), nullable=True),
        sa.Column("reset_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_id", "users", ["id"], unique=False)
    op.create_index("ix_users_reset_token_expires_at", "users", ["reset_token_expires_at"], unique=False)
    op.create_index("ix_users_reset_token_hash", "users", ["reset_token_hash"], unique=False)

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_accounts_id", "accounts", ["id"], unique=False)
    op.create_index("ix_accounts_owner_id", "accounts", ["owner_id"], unique=False)
    op.create_index("ix_accounts_owner_name", "accounts", ["owner_id", "name"], unique=False)

    op.create_table(
        "merchant_lookup_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("matched_signal", sa.String(length=160), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("merchant_key", "transaction_type", name="uq_merchant_lookup_cache_key_type"),
    )
    op.create_index("ix_merchant_lookup_cache_id", "merchant_lookup_cache", ["id"], unique=False)
    op.create_index("ix_merchant_lookup_cache_key", "merchant_lookup_cache", ["merchant_key"], unique=False)
    op.create_index("ix_merchant_lookup_cache_transaction_type", "merchant_lookup_cache", ["transaction_type"], unique=False)

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("category_confidence", sa.Float(), nullable=False),
        sa.Column("category_source", sa.String(length=80), nullable=True),
        sa.Column("category_reason", sa.String(length=500), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("entry_source", sa.String(length=40), nullable=False),
        sa.Column("import_file_name", sa.String(length=255), nullable=True),
        sa.Column("import_file_type", sa.String(length=40), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"], unique=False)
    op.create_index("ix_transactions_account_date", "transactions", ["account_id", "date"], unique=False)
    op.create_index("ix_transactions_category", "transactions", ["category"], unique=False)
    op.create_index("ix_transactions_date", "transactions", ["date"], unique=False)
    op.create_index("ix_transactions_entry_source", "transactions", ["entry_source"], unique=False)
    op.create_index("ix_transactions_id", "transactions", ["id"], unique=False)
    op.create_index(
        "ix_transactions_owner_account_category_confidence",
        "transactions",
        ["owner_id", "account_id", "entry_source", "category_confidence", "date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_owner_account_category_date",
        "transactions",
        ["owner_id", "account_id", "category", "date"],
        unique=False,
    )
    op.create_index("ix_transactions_owner_account_date", "transactions", ["owner_id", "account_id", "date"], unique=False)
    op.create_index(
        "ix_transactions_owner_account_import_file_at",
        "transactions",
        ["owner_id", "account_id", "import_file_name", "imported_at"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_owner_account_source_date",
        "transactions",
        ["owner_id", "account_id", "entry_source", "date"],
        unique=False,
    )
    op.create_index(
        "ix_transactions_owner_account_type_date",
        "transactions",
        ["owner_id", "account_id", "type", "date"],
        unique=False,
    )
    op.create_index("ix_transactions_owner_category", "transactions", ["owner_id", "category"], unique=False)
    op.create_index("ix_transactions_owner_category_date", "transactions", ["owner_id", "category", "date"], unique=False)
    op.create_index("ix_transactions_owner_date", "transactions", ["owner_id", "date"], unique=False)
    op.create_index("ix_transactions_owner_id", "transactions", ["owner_id"], unique=False)
    op.create_index("ix_transactions_owner_source_date", "transactions", ["owner_id", "entry_source", "date"], unique=False)
    op.create_index("ix_transactions_owner_type", "transactions", ["owner_id", "type"], unique=False)
    op.create_index("ix_transactions_owner_type_date", "transactions", ["owner_id", "type", "date"], unique=False)
    op.create_index("ix_transactions_type", "transactions", ["type"], unique=False)

    op.create_table(
        "category_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "keyword", "transaction_type", name="uq_category_memory_owner_keyword_type"),
    )
    op.create_index("ix_category_memories_id", "category_memories", ["id"], unique=False)
    op.create_index("ix_category_memories_owner_id", "category_memories", ["owner_id"], unique=False)
    op.create_index("ix_category_memories_owner_keyword", "category_memories", ["owner_id", "keyword"], unique=False)
    op.create_index("ix_category_memories_transaction_type", "category_memories", ["transaction_type"], unique=False)

    op.create_table(
        "merchant_category_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confirmation_count", sa.Integer(), nullable=False),
        sa.Column("last_amount", sa.Float(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "merchant_key", "transaction_type", name="uq_merchant_profile_owner_key_type"),
    )
    op.create_index("ix_merchant_category_profiles_id", "merchant_category_profiles", ["id"], unique=False)
    op.create_index("ix_merchant_category_profiles_owner_id", "merchant_category_profiles", ["owner_id"], unique=False)
    op.create_index(
        "ix_merchant_category_profiles_transaction_type",
        "merchant_category_profiles",
        ["transaction_type"],
        unique=False,
    )
    op.create_index(
        "ix_merchant_profiles_key_type_owner",
        "merchant_category_profiles",
        ["merchant_key", "transaction_type", "owner_id"],
        unique=False,
    )
    op.create_index("ix_merchant_profiles_owner_key", "merchant_category_profiles", ["owner_id", "merchant_key"], unique=False)
    op.create_index(
        "ix_merchant_profiles_owner_type_key",
        "merchant_category_profiles",
        ["owner_id", "transaction_type", "merchant_key"],
        unique=False,
    )

    op.create_table(
        "user_learning_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("community_learning_enabled", sa.Boolean(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_learning_preferences_id", "user_learning_preferences", ["id"], unique=False)
    op.create_index("ix_user_learning_preferences_owner_id", "user_learning_preferences", ["owner_id"], unique=True)

    op.create_table(
        "assistant_chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("scope_label", sa.String(length=160), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_chat_messages_account_id", "assistant_chat_messages", ["account_id"], unique=False)
    op.create_index("ix_assistant_chat_messages_created_at", "assistant_chat_messages", ["created_at"], unique=False)
    op.create_index("ix_assistant_chat_messages_id", "assistant_chat_messages", ["id"], unique=False)
    op.create_index("ix_assistant_chat_messages_owner_id", "assistant_chat_messages", ["owner_id"], unique=False)
    op.create_index("ix_assistant_chat_owner_account_created", "assistant_chat_messages", ["owner_id", "account_id", "created_at"], unique=False)
    op.create_index("ix_assistant_chat_owner_created", "assistant_chat_messages", ["owner_id", "created_at"], unique=False)

    op.create_table(
        "assistant_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("request_chars", sa.Integer(), nullable=False),
        sa.Column("response_chars", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_usage_events_created_at", "assistant_usage_events", ["created_at"], unique=False)
    op.create_index("ix_assistant_usage_events_id", "assistant_usage_events", ["id"], unique=False)
    op.create_index("ix_assistant_usage_events_owner_id", "assistant_usage_events", ["owner_id"], unique=False)
    op.create_index("ix_assistant_usage_owner_created", "assistant_usage_events", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_assistant_usage_owner_provider_created", "assistant_usage_events", ["owner_id", "provider", "created_at"], unique=False)

    op.create_table(
        "assistant_learning_examples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("scope_label", sa.String(length=160), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_assistant_learning_examples_account_id", "assistant_learning_examples", ["account_id"], unique=False)
    op.create_index("ix_assistant_learning_examples_created_at", "assistant_learning_examples", ["created_at"], unique=False)
    op.create_index("ix_assistant_learning_examples_id", "assistant_learning_examples", ["id"], unique=False)
    op.create_index("ix_assistant_learning_examples_owner_id", "assistant_learning_examples", ["owner_id"], unique=False)
    op.create_index(
        "ix_assistant_learning_owner_account_created",
        "assistant_learning_examples",
        ["owner_id", "account_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_learning_owner_created",
        "assistant_learning_examples",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_assistant_learning_owner_intent_created",
        "assistant_learning_examples",
        ["owner_id", "intent", "created_at"],
        unique=False,
    )

    op.create_table(
        "category_learning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("merchant_key", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("signal_source", sa.String(length=40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("affected_count", sa.Integer(), nullable=False),
        sa.Column("amount_bucket", sa.String(length=20), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_category_learning_events_account_id", "category_learning_events", ["account_id"], unique=False)
    op.create_index("ix_category_learning_events_category", "category_learning_events", ["category"], unique=False)
    op.create_index("ix_category_learning_events_id", "category_learning_events", ["id"], unique=False)
    op.create_index("ix_category_learning_events_merchant_key", "category_learning_events", ["merchant_key"], unique=False)
    op.create_index("ix_category_learning_events_owner_category", "category_learning_events", ["owner_id", "category"], unique=False)
    op.create_index("ix_category_learning_events_owner_created", "category_learning_events", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_category_learning_events_owner_id", "category_learning_events", ["owner_id"], unique=False)
    op.create_index("ix_category_learning_events_owner_merchant", "category_learning_events", ["owner_id", "merchant_key"], unique=False)
    op.create_index("ix_category_learning_events_transaction_type", "category_learning_events", ["transaction_type"], unique=False)

    op.create_table(
        "budget_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.String(length=7), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_budget_plans_account_id", "budget_plans", ["account_id"], unique=False)
    op.create_index("ix_budget_plans_category", "budget_plans", ["category"], unique=False)
    op.create_index("ix_budget_plans_id", "budget_plans", ["id"], unique=False)
    op.create_index("ix_budget_plans_month", "budget_plans", ["month"], unique=False)
    op.create_index("ix_budget_plans_owner_account_month", "budget_plans", ["owner_id", "account_id", "month"], unique=False)
    op.create_index("ix_budget_plans_owner_id", "budget_plans", ["owner_id"], unique=False)
    op.create_index("ix_budget_plans_owner_month", "budget_plans", ["owner_id", "month"], unique=False)

    op.create_table(
        "saved_scenarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("income_adjustment", sa.Float(), nullable=False),
        sa.Column("expense_adjustment", sa.Float(), nullable=False),
        sa.Column("target_balance", sa.Float(), nullable=True),
        sa.Column("event_month_offset", sa.Integer(), nullable=True),
        sa.Column("event_amount", sa.Float(), nullable=True),
        sa.Column("event_label", sa.String(length=80), nullable=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_saved_scenarios_account_id", "saved_scenarios", ["account_id"], unique=False)
    op.create_index("ix_saved_scenarios_id", "saved_scenarios", ["id"], unique=False)
    op.create_index("ix_saved_scenarios_owner_account", "saved_scenarios", ["owner_id", "account_id"], unique=False)
    op.create_index("ix_saved_scenarios_owner_id", "saved_scenarios", ["owner_id"], unique=False)


def downgrade() -> None:
    raise RuntimeError(
        "Downgrade for the initial schema would drop all application tables. "
        "It is intentionally disabled; restore from a verified backup instead."
    )
