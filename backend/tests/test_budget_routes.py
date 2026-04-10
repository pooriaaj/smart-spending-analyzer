from __future__ import annotations

import calendar
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

    def test_list_budgets_returns_smart_suggestions_for_unbudgeted_categories(self) -> None:
        with self.session_local() as session:
            session.add(
                BudgetPlan(
                    month="2026-02",
                    category="groceries",
                    amount=150.0,
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.add_all(
                [
                    Transaction(
                        amount=90.0,
                        category="restaurant",
                        description="Dinner",
                        date=date(2025, 12, 12),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=120.0,
                        category="restaurant",
                        description="Dining Out",
                        date=date(2026, 1, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=150.0,
                        category="restaurant",
                        description="Weekend Dinner",
                        date=date(2026, 2, 7),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=60.0,
                        category="transport",
                        description="Gas",
                        date=date(2026, 2, 3),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
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

        suggestions = payload["suggestions"]
        self.assertGreaterEqual(len(suggestions), 2)

        top_suggestion = suggestions[0]
        self.assertEqual(top_suggestion["category"], "restaurant")
        self.assertEqual(top_suggestion["suggested_amount"], 150.0)
        self.assertEqual(top_suggestion["average_spent"], 120.0)
        self.assertEqual(top_suggestion["latest_month_spent"], 150.0)
        self.assertIn("current month pace", top_suggestion["note"].lower())
        self.assertTrue(all(item["category"] != "groceries" for item in suggestions))

    def test_copy_previous_month_budgets_copies_missing_and_skips_existing(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    BudgetPlan(
                        month="2026-01",
                        category="groceries",
                        amount=220.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    BudgetPlan(
                        month="2026-01",
                        category="restaurant",
                        amount=140.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    BudgetPlan(
                        month="2026-02",
                        category="groceries",
                        amount=250.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/budgets/copy-previous-month",
            json={
                "month": "2026-02",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["source_month"], "2026-01")
        self.assertEqual(payload["target_month"], "2026-02")
        self.assertEqual(payload["copied_count"], 1)
        self.assertEqual(payload["skipped_existing_count"], 1)

        with self.session_local() as session:
            february_budgets = (
                session.query(BudgetPlan)
                .filter(
                    BudgetPlan.owner_id == self.user_id,
                    BudgetPlan.month == "2026-02",
                    BudgetPlan.account_id == self.chequing_account_id,
                )
                .order_by(BudgetPlan.category.asc())
                .all()
            )

        self.assertEqual([budget.category for budget in february_budgets], ["groceries", "restaurant"])
        restaurant_budget = next(budget for budget in february_budgets if budget.category == "restaurant")
        self.assertEqual(float(restaurant_budget.amount), 140.0)

    def test_copy_previous_month_budgets_handles_missing_source_month(self) -> None:
        response = self.client.post(
            "/budgets/copy-previous-month",
            json={
                "month": "2026-01",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["source_month"], "2025-12")
        self.assertEqual(payload["copied_count"], 0)
        self.assertEqual(payload["skipped_existing_count"], 0)
        self.assertIn("No budgets were found", payload["message"])

    def test_list_budgets_includes_current_month_pacing_guidance(self) -> None:
        today = date.today()
        current_month = today.strftime("%Y-%m")
        days_total = calendar.monthrange(today.year, today.month)[1]
        days_remaining = days_total - today.day + 1

        with self.session_local() as session:
            session.add(
                BudgetPlan(
                    month=current_month,
                    category="groceries",
                    amount=310.0,
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.add(
                Transaction(
                    amount=155.0,
                    category="groceries",
                    description="Current Month Grocery Run",
                    date=date(today.year, today.month, 1),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        response = self.client.get(
            "/budgets/",
            params={
                "month": current_month,
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        budget = response.json()["budgets"][0]

        self.assertEqual(budget["days_total"], days_total)
        self.assertEqual(budget["days_elapsed"], today.day)
        self.assertEqual(budget["days_remaining"], days_remaining)
        self.assertAlmostEqual(budget["daily_pace"], 155.0 / today.day, places=2)
        self.assertAlmostEqual(budget["daily_allowance"], 155.0 / days_remaining, places=2)
        self.assertIn("pace", budget["pace_note"].lower())

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
