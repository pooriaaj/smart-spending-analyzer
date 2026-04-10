from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import Account, Transaction, User
from app.routes.account_routes import router as account_router


class AccountRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        cls.session_local = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False, future=True)
        Base.metadata.create_all(bind=cls.engine)

        with cls.session_local() as session:
            user = User(email="accounts@example.com", password_hash="hashed")
            session.add(user)
            session.flush()

            chequing = Account(
                name="Daily Spending",
                type="chequing",
                owner_id=user.id,
                is_active=True,
            )
            savings = Account(
                name="Travel Savings",
                type="savings",
                owner_id=user.id,
                is_active=True,
            )
            session.add_all([chequing, savings])
            session.commit()

            cls.user_id = user.id
            cls.chequing_account_id = chequing.id
            cls.savings_account_id = savings.id

        app = FastAPI()
        app.include_router(account_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="accounts@example.com", password_hash="hashed")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        Base.metadata.drop_all(bind=cls.engine)
        cls.engine.dispose()

    def tearDown(self) -> None:
        with self.session_local() as session:
            session.query(Transaction).delete()
            session.commit()

    def test_list_accounts_returns_financial_stats(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll",
                        date=date(2026, 1, 2),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=180.0,
                        category="Groceries",
                        description="Costco",
                        date=date(2026, 1, 4),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Transfer",
                        description="Savings Transfer",
                        date=date(2026, 1, 5),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get("/accounts/")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        chequing = next(item for item in payload if item["id"] == self.chequing_account_id)
        savings = next(item for item in payload if item["id"] == self.savings_account_id)

        self.assertEqual(chequing["total_income"], 2000.0)
        self.assertEqual(chequing["total_expenses"], 180.0)
        self.assertEqual(chequing["balance"], 1820.0)
        self.assertEqual(chequing["top_category"], "Groceries")
        self.assertEqual(savings["total_income"], 500.0)
        self.assertEqual(savings["total_expenses"], 0.0)
        self.assertEqual(savings["balance"], 500.0)


if __name__ == "__main__":
    unittest.main()
