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
from app.models import Account, BudgetPlan, Transaction, User
from app.routes.budget_routes import router as budget_router


class BudgetRouteTest(unittest.TestCase):
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
            user = User(email="budgets@example.com", password_hash="hashed")
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
        app.include_router(budget_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="budgets@example.com", password_hash="hashed")

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
            session.query(BudgetPlan).delete()
            session.commit()

    def test_list_budgets_returns_computed_progress(self) -> None:
        with self.session_local() as session:
            session.add(
                BudgetPlan(
                    month="2026-02",
                    category="groceries",
                    amount=120.0,
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.add_all(
                [
                    Transaction(
                        amount=70.0,
                        category="groceries",
                        description="Costco",
                        date=date(2026, 2, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=30.0,
                        category="groceries",
                        description="FreshCo",
                        date=date(2026, 2, 6),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=20.0,
                        category="restaurant",
                        description="Lunch",
                        date=date(2026, 2, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/budgets/",
            params={
                "month": "2026-02",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["summary"]["total_budgeted"], 120.0)
        self.assertEqual(payload["summary"]["total_spent"], 100.0)
        self.assertEqual(payload["summary"]["at_risk_count"], 1)
        self.assertEqual(payload["summary"]["over_budget_count"], 0)
        self.assertIn("groceries", payload["available_categories"])

        budget = payload["budgets"][0]
        self.assertEqual(budget["category"], "groceries")
        self.assertEqual(budget["spent_amount"], 100.0)
        self.assertAlmostEqual(budget["remaining_amount"], 20.0)
        self.assertAlmostEqual(budget["usage_percent"], 83.3333333333, places=2)
        self.assertEqual(budget["status"], "at_risk")

    def test_post_budget_upserts_existing_budget_with_normalized_category(self) -> None:
        first_response = self.client.post(
            "/budgets/",
            json={
                "month": "2026-02",
                "category": "Grocery",
                "amount": 250.0,
                "account_id": self.chequing_account_id,
            },
        )
        self.assertEqual(first_response.status_code, 200, first_response.text)

        second_response = self.client.post(
            "/budgets/",
            json={
                "month": "2026-02",
                "category": "Groceries",
                "amount": 300.0,
                "account_id": self.chequing_account_id,
            },
        )
        self.assertEqual(second_response.status_code, 200, second_response.text)

        first_budget = first_response.json()
        second_budget = second_response.json()

        self.assertEqual(first_budget["id"], second_budget["id"])
        self.assertEqual(second_budget["category"], "groceries")
        self.assertEqual(second_budget["amount"], 300.0)

        with self.session_local() as session:
            budgets = (
                session.query(BudgetPlan)
                .filter(
                    BudgetPlan.owner_id == self.user_id,
                    BudgetPlan.month == "2026-02",
                    BudgetPlan.account_id == self.chequing_account_id,
                )
                .all()
            )

        self.assertEqual(len(budgets), 1)
        self.assertEqual(float(budgets[0].amount), 300.0)

    def test_budget_route_rejects_unknown_account(self) -> None:
        response = self.client.get(
            "/budgets/",
            params={
                "month": "2026-02",
                "account_id": 999999,
            },
        )

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["detail"], "Account not found")


if __name__ == "__main__":
    unittest.main()
