from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_baseline_creates_current_schema(tmp_path, monkeypatch) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "alembic_baseline.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    original_environ = dict(os.environ)

    alembic_config = Config(str(backend_dir / "alembic.ini"))
    try:
        command.upgrade(alembic_config, "head")
        command.check(alembic_config)
    finally:
        os.environ.clear()
        os.environ.update(original_environ)

    engine = create_engine(database_url, future=True)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        expected_tables = {
            "accounts",
            "alembic_version",
            "assistant_chat_messages",
            "assistant_learning_examples",
            "assistant_usage_events",
            "budget_plans",
            "category_learning_events",
            "category_memories",
            "merchant_category_profiles",
            "merchant_lookup_cache",
            "saved_scenarios",
            "transactions",
            "user_learning_preferences",
            "users",
        }
        assert expected_tables <= table_names

        transaction_columns = {column["name"] for column in inspector.get_columns("transactions")}
        assert {
            "entry_source",
            "category_confidence",
            "category_source",
            "category_reason",
            "import_file_name",
            "import_file_type",
            "imported_at",
        } <= transaction_columns

        transaction_indexes = {index["name"] for index in inspector.get_indexes("transactions")}
        assert {
            "ix_transactions_owner_account_date",
            "ix_transactions_owner_account_source_date",
            "ix_transactions_owner_account_category_confidence",
            "ix_transactions_owner_account_import_file_at",
        } <= transaction_indexes

        with engine.connect() as connection:
            current_revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert current_revision == "20260701_0002"
    finally:
        engine.dispose()
