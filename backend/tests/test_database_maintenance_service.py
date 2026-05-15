import unittest

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.database import Base
from app.services.database_maintenance_service import ensure_runtime_database_shape


class DatabaseMaintenanceServiceTest(unittest.TestCase):
    def test_runtime_database_shape_creates_expected_indexes(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )

        try:
            Base.metadata.create_all(bind=engine)
            ensure_runtime_database_shape(engine)

            inspector = inspect(engine)
            transaction_columns = {
                item["name"] for item in inspector.get_columns("transactions")
            }
            transaction_index_names = {
                item["name"] for item in inspector.get_indexes("transactions")
            }
            learning_index_names = {
                item["name"] for item in inspector.get_indexes("category_learning_events")
            }

            self.assertIn("entry_source", transaction_columns)
            self.assertIn("category_confidence", transaction_columns)
            self.assertIn("category_source", transaction_columns)
            self.assertIn("category_reason", transaction_columns)
            self.assertIn("import_file_name", transaction_columns)
            self.assertIn("import_file_type", transaction_columns)
            self.assertIn("imported_at", transaction_columns)
            self.assertIn(
                "ix_transactions_runtime_owner_account_date_id",
                transaction_index_names,
            )
            self.assertIn(
                "ix_transactions_runtime_owner_account_source_date_id",
                transaction_index_names,
            )
            self.assertIn(
                "ix_transactions_runtime_owner_account_category_confidence",
                transaction_index_names,
            )
            self.assertIn(
                "ix_transactions_runtime_owner_account_import_file_at",
                transaction_index_names,
            )
            self.assertIn(
                "ix_category_learning_events_runtime_owner_merchant_type_bucket",
                learning_index_names,
            )
        finally:
            Base.metadata.drop_all(bind=engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
