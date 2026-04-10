from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import Account, Transaction, User
from app.routes.analytics_routes import router as analytics_router


class AnalyticsRouteTest(unittest.TestCase):
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
            user = User(email="analytics@example.com", password_hash="hashed")
            session.add(user)
            session.flush()

            chequing_account = Account(
                name="Daily Spending",
                type="chequing",
                owner_id=user.id,
                is_active=True,
            )
            savings_account = Account(
                name="Travel Savings",
                type="savings",
                owner_id=user.id,
                is_active=True,
            )
            session.add_all([chequing_account, savings_account])
            session.commit()

            cls.user_id = user.id
            cls.chequing_account_id = chequing_account.id
            cls.savings_account_id = savings_account.id

        app = FastAPI()
        app.include_router(analytics_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="analytics@example.com", password_hash="hashed")

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

    def seed_transactions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Employer Payroll",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=150.0,
                        category="Groceries",
                        description="Costco",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=100.0,
                        category="Groceries",
                        description="FreshCo",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=1200.0,
                        category="Salary",
                        description="Side Income",
                        date=date(2026, 1, 10),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                    Transaction(
                        amount=60.0,
                        category="Entertainment",
                        description="Movie Night",
                        date=date(2026, 1, 14),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                    Transaction(
                        amount=90.0,
                        category="Entertainment",
                        description="Concert Ticket",
                        date=date(2026, 2, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                ]
            )
            session.commit()

    def test_dashboard_respects_account_scope(self) -> None:
        self.seed_transactions()

        response = self.client.get(
            "/analytics/dashboard",
            params={"account_id": self.savings_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["summary"]["total_income"], 1200.0)
        self.assertEqual(payload["summary"]["total_expenses"], 150.0)
        self.assertEqual(payload["summary"]["balance"], 1050.0)
        self.assertEqual(payload["top_category"]["category"], "Entertainment")
        self.assertTrue(
            all(item["account_id"] == self.savings_account_id for item in payload["recent_transactions"])
        )

    def test_dashboard_rejects_unknown_account_scope(self) -> None:
        response = self.client.get("/analytics/dashboard", params={"account_id": 999999})

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["detail"], "Account not found")

    def test_assistant_suggestions_are_account_aware(self) -> None:
        self.seed_transactions()

        response = self.client.get(
            "/analytics/assistant-suggestions",
            params={"account_id": self.savings_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Why is Entertainment my top expense category?", suggestions)
        self.assertIn("How can I reduce Entertainment spending?", suggestions)
        self.assertNotIn("Why is Groceries my top expense category?", suggestions)

    def test_assistant_response_reports_scoped_balance(self) -> None:
        self.seed_transactions()

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
                json={
                    "question": "What is my balance?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.savings_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["scope_label"], "Travel Savings (savings)")
        self.assertIn("$1050.00", payload["answer"])
        self.assertIn("Balance: $1050.00", payload["supporting_points"])

    def test_assistant_response_focuses_on_explicit_category(self) -> None:
        self.seed_transactions()

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
                json={
                    "question": "How is groceries looking?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Groceries", payload["answer"])
        self.assertIn("Groceries total in this scope: $250.00", payload["supporting_points"])
        self.assertTrue(
            any("FreshCo ($100.00)" in item for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["category"], "Groceries")
        self.assertEqual(payload["suggested_actions"][0]["account_id"], self.chequing_account_id)

    def test_assistant_response_shows_recent_transactions_for_focused_category(self) -> None:
        self.seed_transactions()

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
                json={
                    "question": "Show me groceries transactions",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Here is the focused view for Groceries.", payload["answer"])
        self.assertTrue(
            any("Costco ($150.00)" in item and "FreshCo ($100.00)" in item for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["category"], "Groceries")
        self.assertEqual(payload["suggested_actions"][0]["page"], "transactions")
        self.assertEqual(payload["suggested_actions"][0]["account_id"], self.chequing_account_id)


if __name__ == "__main__":
    unittest.main()
