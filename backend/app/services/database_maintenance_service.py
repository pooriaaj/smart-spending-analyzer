from __future__ import annotations

import logging
from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.models import AssistantLearningExample

logger = logging.getLogger(__name__)


POSTGRES_COMPATIBILITY_STATEMENTS = (
    # create_all() does not add columns to existing production tables.
    "ALTER TABLE category_learning_events ADD COLUMN IF NOT EXISTS signal_source VARCHAR(40) DEFAULT 'manual'",
    "ALTER TABLE category_learning_events ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 1",
    "ALTER TABLE category_learning_events ADD COLUMN IF NOT EXISTS affected_count INTEGER DEFAULT 1",
    "ALTER TABLE category_learning_events ADD COLUMN IF NOT EXISTS amount_bucket VARCHAR(20)",
    "ALTER TABLE category_learning_events ADD COLUMN IF NOT EXISTS account_id INTEGER",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS entry_source VARCHAR(40) DEFAULT 'manual'",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_confidence DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_source VARCHAR(80)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS category_reason VARCHAR(500)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS import_file_name VARCHAR(255)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS import_file_type VARCHAR(40)",
    "ALTER TABLE transactions ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP WITH TIME ZONE",
    "ALTER TABLE merchant_category_profiles ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 0.9",
    "ALTER TABLE merchant_category_profiles ADD COLUMN IF NOT EXISTS confirmation_count INTEGER DEFAULT 1",
    "ALTER TABLE merchant_category_profiles ADD COLUMN IF NOT EXISTS last_amount DOUBLE PRECISION",
    "ALTER TABLE merchant_category_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE merchant_category_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE merchant_lookup_cache ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION DEFAULT 0.78",
    "ALTER TABLE merchant_lookup_cache ADD COLUMN IF NOT EXISTS matched_signal VARCHAR(160)",
    "ALTER TABLE merchant_lookup_cache ADD COLUMN IF NOT EXISTS provider VARCHAR(40) DEFAULT 'semantic'",
    "ALTER TABLE merchant_lookup_cache ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE merchant_lookup_cache ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMP WITH TIME ZONE",
)


RUNTIME_INDEX_STATEMENTS = (
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_date_id
    ON transactions (owner_id, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_type_date_id
    ON transactions (owner_id, type, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_category_date_id
    ON transactions (owner_id, category, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_source_date_id
    ON transactions (owner_id, entry_source, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_date_id
    ON transactions (owner_id, account_id, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_type_date_id
    ON transactions (owner_id, account_id, type, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_category_date_id
    ON transactions (owner_id, account_id, category, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_source_date_id
    ON transactions (owner_id, account_id, entry_source, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_category_confidence
    ON transactions (owner_id, account_id, entry_source, category_confidence, date DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_transactions_runtime_owner_account_import_file_at
    ON transactions (owner_id, account_id, import_file_name, imported_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_category_learning_events_runtime_owner_merchant_type_bucket
    ON category_learning_events (owner_id, merchant_key, transaction_type, amount_bucket)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_merchant_profiles_runtime_owner_key_type
    ON merchant_category_profiles (owner_id, merchant_key, transaction_type)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_merchant_profiles_runtime_key_type_owner
    ON merchant_category_profiles (merchant_key, transaction_type, owner_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_merchant_profiles_runtime_owner_type_key
    ON merchant_category_profiles (owner_id, transaction_type, merchant_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_assistant_learning_runtime_owner_created
    ON assistant_learning_examples (owner_id, created_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_assistant_learning_runtime_owner_intent_created
    ON assistant_learning_examples (owner_id, intent, created_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_assistant_learning_runtime_owner_account_created
    ON assistant_learning_examples (owner_id, account_id, created_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_users_runtime_reset_token_hash
    ON users (reset_token_hash)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_users_runtime_reset_token_expires_at
    ON users (reset_token_expires_at)
    """,
)


def _statements_for_dialect(dialect_name: str) -> Iterable[str]:
    if dialect_name == "postgresql":
        yield from POSTGRES_COMPATIBILITY_STATEMENTS
    yield from RUNTIME_INDEX_STATEMENTS


def ensure_runtime_database_shape(engine: Engine) -> None:
    """Keep production databases aligned with the query paths added after launch.

    SQLAlchemy's create_all() is intentionally conservative: it creates missing tables,
    but it does not migrate existing tables or add newly introduced indexes. These
    idempotent statements protect deployed databases that were created before the
    latest learning and transaction pagination upgrades.
    """

    dialect_name = engine.dialect.name
    try:
        AssistantLearningExample.__table__.create(bind=engine, checkfirst=True)
    except Exception as exc:
        logger.warning("Assistant learning table maintenance skipped: %s", exc)

    for statement in _statements_for_dialect(dialect_name):
        try:
            with engine.begin() as connection:
                connection.execute(text(statement))
        except Exception as exc:
            logger.warning("Database maintenance statement skipped: %s", exc)
