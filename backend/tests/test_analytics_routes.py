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
from app.models import (
    Account,
    BudgetPlan,
    CategoryLearningEvent,
    MerchantCategoryProfile,
    SavedScenario,
    Transaction,
    User,
)
from app.routes.analytics_routes import router as analytics_router
from app.routes.assistant_routes import router as assistant_router


class FixedBudgetDate(date):
    @classmethod
    def today(cls) -> "FixedBudgetDate":
        return cls(2026, 4, 10)


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
        app.include_router(assistant_router)

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
            session.query(SavedScenario).delete()
            session.query(Transaction).delete()
            session.query(BudgetPlan).delete()
            session.query(CategoryLearningEvent).delete()
            session.query(MerchantCategoryProfile).delete()
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

    def seed_budget(self, *, month: str, category: str, amount: float, account_id: int | None = None) -> None:
        with self.session_local() as session:
            session.add(
                BudgetPlan(
                    month=month,
                    category=category,
                    amount=amount,
                    owner_id=self.user_id,
                    account_id=account_id,
                )
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
        self.assertEqual(payload["top_category"]["category"], "entertainment")
        self.assertEqual(payload["account_comparison"], [])
        self.assertEqual(payload["data_quality"]["transaction_count"], 3)
        self.assertEqual(payload["data_quality"]["manual_count"], 3)
        self.assertEqual(payload["data_quality"]["source_summary"]["total_transactions"], 3)
        self.assertTrue(
            all(item["account_id"] == self.savings_account_id for item in payload["recent_transactions"])
        )

    def test_dashboard_includes_account_comparison_for_all_accounts_scope(self) -> None:
        self.seed_transactions()

        response = self.client.get("/analytics/dashboard")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(len(payload["account_comparison"]), 2)
        self.assertEqual(payload["account_comparison"][0]["name"], "Daily Spending")
        self.assertEqual(payload["account_comparison"][0]["total_expenses"], 250.0)

    def test_dashboard_rejects_unknown_account_scope(self) -> None:
        response = self.client.get("/analytics/dashboard", params={"account_id": 999999})

        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["detail"], "Account not found")

    def test_analytics_routes_reject_invalid_transaction_type_filter(self) -> None:
        endpoints = [
            "/analytics/dashboard",
            "/analytics/summary",
            "/analytics/category-breakdown",
            "/analytics/monthly-summary",
            "/analytics/recent-transactions",
            "/analytics/top-expense-category",
        ]

        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                response = self.client.get(endpoint, params={"transaction_type": "transfer"})

                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(
                    response.json()["detail"],
                    "Transaction type must be income or expense",
                )

    def test_category_breakdown_merges_accented_category_aliases(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=7.5,
                        category="Café",
                        description="Morning latte",
                        date=date(2026, 4, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=4.25,
                        category="coffee",
                        description="Afternoon coffee",
                        date=date(2026, 4, 3),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/category-breakdown",
            params={"account_id": self.chequing_account_id, "category": "Cafe"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [{"category": "cafe", "total": 11.75}])

    def test_analytics_treats_signed_imported_amounts_by_transaction_type(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=-500.0,
                        category="Salary",
                        description="Imported payroll with negative sign",
                        date=date(2026, 4, 1),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=-75.0,
                        category="Groceries",
                        description="Imported grocery with negative sign",
                        date=date(2026, 4, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        summary_response = self.client.get(
            "/analytics/summary",
            params={"account_id": self.chequing_account_id, "month": "2026-04"},
        )
        category_response = self.client.get(
            "/analytics/category-breakdown",
            params={"account_id": self.chequing_account_id, "month": "2026-04"},
        )
        monthly_response = self.client.get(
            "/analytics/monthly-summary",
            params={
                "account_id": self.chequing_account_id,
                "start_date": "2026-04-01",
                "end_date": "2026-04-30",
            },
        )

        self.assertEqual(summary_response.status_code, 200, summary_response.text)
        self.assertEqual(category_response.status_code, 200, category_response.text)
        self.assertEqual(monthly_response.status_code, 200, monthly_response.text)

        self.assertEqual(summary_response.json()["total_income"], 500.0)
        self.assertEqual(summary_response.json()["total_expenses"], 75.0)
        self.assertEqual(summary_response.json()["balance"], 425.0)
        self.assertEqual(category_response.json(), [{"category": "groceries", "total": 75.0}])
        self.assertEqual(monthly_response.json()[0]["income"], 500.0)
        self.assertEqual(monthly_response.json()[0]["expenses"], 75.0)
        self.assertEqual(monthly_response.json()[0]["balance"], 425.0)

    def test_money_map_guides_empty_users_to_import(self) -> None:
        response = self.client.get("/analytics/money-map")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["status"], "empty")
        self.assertEqual(payload["confidence_level"], "Low")
        self.assertEqual(payload["transaction_count"], 0)
        self.assertEqual(payload["actions"][0]["page"], "import")
        self.assertIn("Upload one bank statement", payload["narrative"])

    def test_money_map_summarizes_imported_statement_patterns(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2400.0,
                        category="salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=140.0,
                        category="groceries",
                        description="FreshCo Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=18.99,
                        category="entertainment",
                        description="Spotify Premium",
                        date=date(2026, 1, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2400.0,
                        category="salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=18.99,
                        category="entertainment",
                        description="Spotify Premium",
                        date=date(2026, 2, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2400.0,
                        category="salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=18.99,
                        category="entertainment",
                        description="Spotify Premium",
                        date=date(2026, 3, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="spotify",
                        display_name="Spotify",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        owner_id=self.user_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/money-map",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["scope_label"], "Daily Spending (chequing)")
        self.assertGreater(payload["transaction_count"], 0)
        self.assertEqual(payload["month_count"], 3)
        self.assertGreaterEqual(payload["learned_merchant_count"], 1)
        self.assertTrue(any(item["category"] == "entertainment" for item in payload["top_categories"]))
        self.assertTrue(any(item["description"] == "Spotify Premium" for item in payload["recurring_highlights"]))

    def test_money_map_exposes_grouped_category_learning_candidates(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=8.90,
                        category="other",
                        description="SQDC77068 MTL",
                        date=date(2026, 3, 16),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=12.60,
                        category="other",
                        description="SQDC77068 MTL",
                        date=date(2026, 3, 16),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/money-map",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(len(payload["learning_candidates"]), 1)
        candidate = payload["learning_candidates"][0]
        self.assertEqual(candidate["merchant_key"], "sqdc")
        self.assertEqual(candidate["suggested_category"], "smoking")
        self.assertEqual(candidate["transaction_count"], 2)
        self.assertTrue(candidate["review_required"])
        self.assertTrue(any(action["label"] == "Teach merchant groups" for action in payload["actions"]))

    def test_recurring_expenses_route_detects_monthly_patterns(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=15.99,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 1, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=15.99,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 2, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=18.99,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 3, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=120.0,
                        category="Groceries",
                        description="FreshCo",
                        date=date(2026, 3, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/recurring-expenses",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["description"], "Spotify Premium")
        self.assertEqual(payload["items"][0]["occurrences"], 3)
        self.assertEqual(payload["items"][0]["cadence"], "monthly")
        self.assertEqual(payload["items"][0]["review_priority"], "high")
        self.assertEqual(payload["items"][0]["next_expected_date"], "2026-04-07")
        self.assertGreater(payload["items"][0]["latest_change_percent"], 0)

    def test_recurring_transactions_route_detects_income_and_expense_patterns(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2500.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2500.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 1, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 2, 8),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/recurring-transactions",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        items = response.json()["items"]

        self.assertTrue(any(item["type"] == "income" and "Payroll" in item["description"] for item in items))
        self.assertTrue(any(item["type"] == "expense" and item["description"] == "Gym Membership" for item in items))

    def test_future_simulator_respects_account_scope_and_adjustments(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=600.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=700.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=5000.0,
                        category="Salary",
                        description="Savings Payroll",
                        date=date(2026, 3, 10),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.savings_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            response = self.client.get(
                "/analytics/future-simulator",
                params={
                    "account_id": self.chequing_account_id,
                    "months": 3,
                    "income_adjustment": 100,
                    "expense_adjustment": -50,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["scope_label"], "Daily Spending (chequing)")
        self.assertEqual(payload["months"], 3)
        self.assertEqual(payload["starting_balance"], 4200.0)
        self.assertEqual(payload["baseline_monthly_income"], 2000.0)
        self.assertEqual(payload["baseline_monthly_expenses"], 600.0)
        self.assertEqual(payload["adjusted_monthly_income"], 2100.0)
        self.assertEqual(payload["adjusted_monthly_expenses"], 550.0)
        self.assertEqual(payload["monthly_net_change"], 1550.0)
        self.assertEqual(payload["baseline_monthly_net_change"], 1400.0)
        self.assertEqual(payload["baseline_projected_end_balance"], 8400.0)
        self.assertEqual(payload["scenario_impact_amount"], 450.0)
        self.assertEqual(payload["projected_end_balance"], 8850.0)
        self.assertEqual(payload["risk_level"], "healthy")
        self.assertEqual(payload["data_quality_level"], "high")
        self.assertGreater(payload["data_quality_score"], 0.8)
        self.assertEqual(payload["data_review_action_count"], 0)
        self.assertEqual(len(payload["timeline"]), 3)
        self.assertEqual(payload["timeline"][0]["month"], "2026-05")
        self.assertEqual(payload["timeline"][0]["baseline_ending_balance"], 5600.0)
        self.assertEqual(payload["timeline"][0]["balance_delta"], 150.0)

    def test_future_simulator_recommendations_include_recurring_plan(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Cancel Gym Membership",
                        months=6,
                        income_adjustment=0.0,
                        expense_adjustment=-50.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/future-simulator-recommendations",
            params={"account_id": self.chequing_account_id, "months": 6},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["scope_label"], "Daily Spending (chequing)")
        self.assertTrue(any(item["source"] == "recurring" for item in payload["items"]))
        recurring_plan = next(item for item in payload["items"] if item["source"] == "recurring")
        self.assertIn("Gym Membership", recurring_plan["label"])
        self.assertEqual(recurring_plan["expense_adjustment"], -50.0)
        self.assertTrue(recurring_plan["is_saved"])
        self.assertIsNotNone(recurring_plan["saved_scenario_id"])

    def test_future_simulator_uses_budget_projection_when_it_is_higher_than_history(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            with self.session_local() as session:
                session.add_all(
                    [
                        Transaction(
                            amount=1500.0,
                            category="Salary",
                            description="Payroll Jan",
                            date=date(2026, 1, 3),
                            type="income",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=100.0,
                            category="Groceries",
                            description="Groceries Jan",
                            date=date(2026, 1, 4),
                            type="expense",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=1500.0,
                            category="Salary",
                            description="Payroll Feb",
                            date=date(2026, 2, 3),
                            type="income",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=120.0,
                            category="Groceries",
                            description="Groceries Feb",
                            date=date(2026, 2, 4),
                            type="expense",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=1500.0,
                            category="Salary",
                            description="Payroll Mar",
                            date=date(2026, 3, 3),
                            type="income",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=80.0,
                            category="Groceries",
                            description="Groceries Mar",
                            date=date(2026, 3, 4),
                            type="expense",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        BudgetPlan(
                            month="2026-04",
                            category="groceries",
                            amount=200.0,
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                        Transaction(
                            amount=90.0,
                            category="groceries",
                            description="Large Grocery Run",
                            date=date(2026, 4, 2),
                            type="expense",
                            owner_id=self.user_id,
                            account_id=self.chequing_account_id,
                        ),
                    ]
                )
                session.commit()

            response = self.client.get(
                "/analytics/future-simulator",
                params={
                    "account_id": self.chequing_account_id,
                    "months": 2,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["baseline_monthly_income"], 1500.0)
        self.assertEqual(payload["baseline_monthly_expenses"], 270.0)
        self.assertIn("budget projections", " ".join(payload["assumptions"]).lower())

    def test_future_simulator_supports_one_time_events(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=600.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=600.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=600.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            response = self.client.get(
                "/analytics/future-simulator",
                params={
                    "account_id": self.chequing_account_id,
                    "months": 3,
                    "event_amount": -1200,
                    "event_month_offset": 2,
                    "event_label": "Planned Trip",
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["one_time_event_month"], "2026-06")
        self.assertEqual(payload["one_time_event_amount"], -1200.0)
        self.assertEqual(payload["one_time_event_label"], "Planned Trip")
        self.assertEqual(payload["scenario_impact_amount"], -1200.0)
        self.assertEqual(payload["projected_end_balance"], 7200.0)
        self.assertIn("planned trip", payload["narrative"].lower())
        self.assertIn("2026-06", " ".join(payload["assumptions"]))
        self.assertEqual(payload["timeline"][1]["month"], "2026-06")
        self.assertEqual(payload["timeline"][1]["one_time_event_amount"], -1200.0)
        self.assertEqual(payload["timeline"][1]["one_time_event_label"], "Planned Trip")
        self.assertEqual(payload["timeline"][1]["net_change"], 200.0)
        self.assertEqual(payload["timeline"][2]["ending_balance"], 7200.0)

    def test_future_simulator_returns_goal_guidance(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/analytics/future-simulator",
            params={
                "account_id": self.chequing_account_id,
                "months": 3,
                "target_balance": 10000,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["goal_balance"], 10000.0)
        self.assertEqual(payload["goal_gap_amount"], 1000.0)
        self.assertAlmostEqual(payload["required_monthly_net"], 1833.33, places=2)
        self.assertAlmostEqual(payload["required_income_lift"], 333.33, places=2)
        self.assertAlmostEqual(payload["required_expense_reduction"], 333.33, places=2)
        self.assertIn("10000.00", payload["goal_note"])
        self.assertAlmostEqual(payload["reduction_plan_target"], 333.33, places=2)
        self.assertAlmostEqual(payload["reduction_plan_coverage_amount"], 333.33, places=2)
        self.assertEqual(payload["reduction_plan"][0]["category"], "Rent")
        self.assertAlmostEqual(
            payload["reduction_plan"][0]["suggested_monthly_reduction"],
            333.33,
            places=2,
        )
        self.assertAlmostEqual(
            payload["reduction_plan"][0]["suggested_budget_amount"],
            166.67,
            places=2,
        )
        self.assertIn("larger recurring expense", payload["reduction_plan"][0]["reason"].lower())

    def test_assistant_suggestions_are_account_aware(self) -> None:
        self.seed_transactions()

        response = self.client.get(
            "/assistant/suggestions",
            params={"account_id": self.savings_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Why is entertainment my top expense category?", suggestions)
        self.assertIn("How can I reduce entertainment spending?", suggestions)
        self.assertIn("What will my balance look like in 3 months?", suggestions)
        self.assertNotIn("Why is Groceries my top expense category?", suggestions)

    def test_assistant_suggestions_include_budget_prompt_when_budgets_exist(self) -> None:
        self.seed_transactions()
        self.seed_budget(
            month="2026-02",
            category="groceries",
            amount=120.0,
            account_id=self.chequing_account_id,
        )

        response = self.client.get(
            "/assistant/suggestions",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Which budget is closest to the limit?", suggestions)

    def test_assistant_suggestions_include_projected_budget_prompt(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            with self.session_local() as session:
                session.add(
                    BudgetPlan(
                        month="2026-04",
                        category="groceries",
                        amount=200.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.add(
                    Transaction(
                        amount=90.0,
                        category="groceries",
                        description="Large Grocery Run",
                        date=date(2026, 4, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.commit()

            response = self.client.get(
                "/assistant/suggestions",
                params={"account_id": self.chequing_account_id},
            )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Which budget is projected to go over?", suggestions)

    def test_assistant_response_reports_scoped_balance(self) -> None:
        self.seed_transactions()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ):
            response = self.client.post(
                "/assistant/response",
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

    def test_assistant_resource_question_is_not_hijacked_by_budget_history(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Can you send some YouTube links so I can learn how to cook the recipes?",
                    "history": [
                        {
                            "role": "user",
                            "content": "Am I on track with my budget?",
                        },
                        {
                            "role": "assistant",
                            "content": "You do not have any budgets set for 2026-04 in All accounts combined yet.",
                        },
                    ],
                    "mode": "balanced",
                    "account_id": None,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertNotIn("You do not have any budgets set", payload["answer"])
        self.assertIn("youtube.com/results?search_query=Can+you+send", payload["answer"])
        self.assertIn("not about your financial data", payload["supporting_points"][0])
        self.assertEqual(payload["suggested_actions"][0]["page"], "external_resource")

    def test_assistant_resource_question_uses_llm_answer_when_available(self) -> None:
        llm_answer = {
            "answer": (
                "Here are a few beginner-friendly cooking searches to start with: "
                "https://www.youtube.com/results?search_query=easy+beginner+recipes"
            ),
            "supporting_points": [
                "This is a general learning request, not a finance-data question.",
            ],
            "suggested_followups": [
                "How much do I spend on groceries?",
            ],
            "action_type": "external_resource",
            "action_label": "Open cooking videos",
            "action_reason": "The user asked for learning links.",
            "action_target": "easy beginner recipes",
        }

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=llm_answer,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Can you send some YouTube links so I can learn how to cook the recipes?",
                    "history": [
                        {
                            "role": "assistant",
                            "content": "You do not have any budgets set for 2026-04 in All accounts combined yet.",
                        },
                    ],
                    "mode": "balanced",
                    "account_id": None,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertEqual(payload["answer"], llm_answer["answer"])
        self.assertEqual(payload["suggested_actions"][0]["label"], "Open cooking videos")
        self.assertEqual(payload["suggested_actions"][0]["page"], "external_resource")

    def test_assistant_generic_link_request_gets_external_resource_fallback(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Can you send links for beginner cooking recipes?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": None,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertIn("youtube.com/results?search_query=Can+you+send+links", payload["answer"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "external_resource")

    def test_assistant_off_topic_question_has_safe_rule_based_redirect(self) -> None:
        self.seed_transactions()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How do I cook pasta?",
                    "history": [
                        {
                            "role": "assistant",
                            "content": "Your balance is $500 and your top expense category is groceries.",
                        },
                    ],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertIn("mainly built to help with your money", payload["answer"])
        self.assertIn("does not look related to your financial data", payload["supporting_points"][0])
        self.assertNotIn("Your balance is", payload["answer"])

    def test_assistant_weather_question_has_safe_rule_based_redirect(self) -> None:
        self.seed_transactions()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "What is the weather tomorrow?",
                    "history": [
                        {
                            "role": "assistant",
                            "content": "Your budgets are on track this month.",
                        },
                    ],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertIn("mainly built to help with your money", payload["answer"])
        self.assertNotIn("budgets are on track", payload["answer"].lower())

    def test_assistant_off_topic_question_uses_llm_answer_when_available(self) -> None:
        llm_answer = {
            "answer": "Boil salted water, add pasta, stir, and cook until tender.",
            "supporting_points": [
                "No financial data is needed for this general cooking answer.",
            ],
            "suggested_followups": [
                "How much did I spend on groceries?",
            ],
            "action_type": "none",
            "action_label": None,
            "action_reason": None,
            "action_target": None,
        }

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=llm_answer,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How do I cook pasta?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertEqual(payload["answer"], llm_answer["answer"])
        self.assertEqual(payload["suggested_actions"], [])

    def test_assistant_finance_question_with_cooking_term_stays_financial(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=44.0,
                    category="education",
                    description="Cooking class",
                    date=date(2026, 4, 11),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How much did I spend on cooking classes?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertNotIn("mainly built to help with your money", payload["answer"])
        self.assertNotEqual(payload["suggested_actions"], [])

    def test_assistant_finance_question_with_programming_term_stays_financial(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=29.0,
                    category="education",
                    description="Python course",
                    date=date(2026, 4, 12),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How much did I spend on Python courses?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertNotIn("mainly built to help with your money", payload["answer"])
        self.assertNotEqual(payload["suggested_actions"], [])

    def test_assistant_review_path_has_rule_based_answer_without_llm(self) -> None:
        self.seed_transactions()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Should I review charts or transactions first?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Start with the recent transactions", payload["answer"])
        self.assertIn("Recent transactions available: 3", payload["supporting_points"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "transactions")
        self.assertEqual(payload["suggested_actions"][1]["section"], "trends")

    def test_assistant_youtube_merchant_question_stays_financial(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=12.99,
                    category="subscriptions",
                    description="YouTube Premium",
                    date=date(2026, 4, 7),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How much did I spend on YouTube?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertNotIn("broader learning request", payload["answer"])
        self.assertNotEqual(payload["suggested_actions"][0]["page"], "external_resource")

    def test_assistant_google_merchant_question_stays_financial(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=3.99,
                    category="subscriptions",
                    description="Google One",
                    date=date(2026, 4, 9),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ) as mocked_llm:
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How much did I spend on Google?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        mocked_llm.assert_called_once()
        self.assertNotIn("broader learning request", payload["answer"])
        self.assertNotEqual(payload["suggested_actions"][0]["page"], "external_resource")

    def test_assistant_response_surfaces_low_data_quality_context(self) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=42.25,
                    category="other",
                    description="Unknown merchant",
                    date=date(2026, 4, 13),
                    type="expense",
                    entry_source="pdf_import",
                    import_file_name="april-statement.pdf",
                    import_file_type="pdf_statement",
                    owner_id=self.user_id,
                    account_id=self.chequing_account_id,
                )
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Give me a summary",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(
            any(point.startswith("Data quality:") for point in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["label"], "Review data quality")
        self.assertEqual(payload["suggested_actions"][0]["section"], "review")

    def test_assistant_response_focuses_on_explicit_category(self) -> None:
        self.seed_transactions()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ):
            response = self.client.post(
                "/assistant/response",
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

    def test_assistant_response_reports_budget_status_for_focused_category(self) -> None:
        self.seed_transactions()
        self.seed_budget(
            month="2026-02",
            category="groceries",
            amount=120.0,
            account_id=self.chequing_account_id,
        )

        with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How is my groceries budget looking?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Groceries", payload["answer"])
        self.assertIn("83.3%", payload["answer"])
        self.assertIn("Budget: $120.00", payload["supporting_points"])
        self.assertIn("Spent so far: $100.00", payload["supporting_points"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "budgets")
        self.assertEqual(payload["suggested_actions"][0]["account_id"], self.chequing_account_id)
        self.assertEqual(payload["suggested_actions"][1]["page"], "transactions")

    def test_assistant_response_mentions_budget_forecast_for_focused_category(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            with self.session_local() as session:
                session.add(
                    BudgetPlan(
                        month="2026-04",
                        category="groceries",
                        amount=200.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.add(
                    Transaction(
                        amount=90.0,
                        category="groceries",
                        description="Large Grocery Run",
                        date=date(2026, 4, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.commit()

            with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
                response = self.client.post(
                    "/assistant/response",
                    json={
                        "question": "How is my groceries budget looking?",
                        "history": [],
                        "mode": "balanced",
                        "account_id": self.chequing_account_id,
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("projected to finish", payload["answer"])
        self.assertTrue(
            any("Projected month-end:" in item for item in payload["supporting_points"])
        )

    def test_assistant_saving_advice_uses_budget_action_insights(self) -> None:
        with patch("app.services.budget_metrics.date", FixedBudgetDate):
            with self.session_local() as session:
                session.add(
                    BudgetPlan(
                        month="2026-04",
                        category="groceries",
                        amount=200.0,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.add(
                    Transaction(
                        amount=90.0,
                        category="groceries",
                        description="Large Grocery Run",
                        date=date(2026, 4, 2),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    )
                )
                session.commit()

            with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
                response = self.client.post(
                    "/assistant/response",
                    json={
                        "question": "Give me saving advice",
                        "history": [],
                        "mode": "balanced",
                        "account_id": self.chequing_account_id,
                    },
                )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Groceries", payload["answer"])
        self.assertIn("projected to finish", payload["answer"].lower())
        self.assertEqual(payload["suggested_actions"][0]["page"], "budgets")
        self.assertEqual(payload["suggested_actions"][0]["category"], "groceries")
        self.assertGreater(payload["suggested_actions"][0]["amount"], 200.0)
        self.assertEqual(payload["suggested_actions"][1]["page"], "transactions")

    def test_assistant_saving_advice_can_use_recurring_savings_levers(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "Give me saving advice",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Gym Membership", payload["answer"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "transactions")
        self.assertEqual(payload["suggested_actions"][0]["section"], "recurring")
        self.assertEqual(payload["suggested_actions"][1]["page"], "simulator")
        self.assertEqual(payload["suggested_actions"][1]["expense_adjustment"], -50.0)

    def test_assistant_response_shows_recent_transactions_for_focused_category(self) -> None:
        self.seed_transactions()

        with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/assistant/response",
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

    def test_assistant_can_answer_future_balance_questions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "What will my balance look like in 3 months?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("$9000.00", payload["answer"])
        self.assertIn("Starting balance: $4500.00", payload["supporting_points"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertEqual(payload["suggested_actions"][0]["account_id"], self.chequing_account_id)

    def test_assistant_can_answer_target_balance_questions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.assistant_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "How much do I need to save each month to reach 10000 in 3 months?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("10000.00", payload["answer"])
        self.assertTrue(
            any("need about $333.33 more net cash flow" in item for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertEqual(payload["suggested_actions"][0]["months_ahead"], 3)
        self.assertEqual(payload["suggested_actions"][0]["target_balance"], 10000.0)
        self.assertEqual(payload["suggested_actions"][0]["account_id"], self.chequing_account_id)

    def test_assistant_can_answer_one_time_event_simulator_questions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.budget_metrics.date", FixedBudgetDate), patch(
            "app.services.assistant_service.generate_llm_assistant_response",
            return_value=None,
        ):
            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "What happens if I have a 1200 repair in 2 months?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("$6300.00", payload["answer"])
        self.assertTrue(
            any("Repair in 2026-06 for -$1200.00" in item for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertEqual(payload["suggested_actions"][0]["months_ahead"], 2)
        self.assertEqual(payload["suggested_actions"][0]["event_amount"], -1200.0)
        self.assertEqual(payload["suggested_actions"][0]["event_month_offset"], 2)
        self.assertEqual(payload["suggested_actions"][0]["event_label"], "Repair")

    def test_assistant_can_compare_accounts_in_all_accounts_scope(self) -> None:
        self.seed_transactions()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which account is driving my spending?",
                "history": [],
                "mode": "balanced",
                "account_id": None,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Daily Spending", payload["answer"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "accounts")
        self.assertEqual(payload["suggested_actions"][1]["account_id"], self.chequing_account_id)

    def test_assistant_account_comparison_requires_all_accounts_scope(self) -> None:
        self.seed_transactions()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Compare my accounts",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("can't compare accounts", payload["answer"])
        self.assertEqual(payload["scope_label"], "Daily Spending (chequing)")
        self.assertEqual(payload["suggested_actions"][0]["page"], "accounts")

    def test_saved_scenarios_can_be_created_updated_listed_and_deleted(self) -> None:
        self.seed_transactions()

        create_response = self.client.post(
            "/analytics/saved-scenarios",
            json={
                "name": "Trip Pressure Plan",
                "months": 6,
                "income_adjustment": 0,
                "expense_adjustment": -200,
                "target_balance": 10000,
                "event_month_offset": 2,
                "event_amount": -1200,
                "event_label": "Planned trip",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(create_response.status_code, 200, create_response.text)
        created_payload = create_response.json()

        self.assertEqual(created_payload["name"], "Trip Pressure Plan")
        self.assertEqual(created_payload["account_id"], self.chequing_account_id)
        self.assertEqual(created_payload["event_amount"], -1200.0)
        self.assertEqual(created_payload["event_month_offset"], 2)
        self.assertEqual(created_payload["event_label"], "Planned trip")

        update_response = self.client.put(
            f"/analytics/saved-scenarios/{created_payload['id']}",
            json={
                "name": "Updated Trip Pressure Plan",
                "months": 4,
                "income_adjustment": 250,
                "expense_adjustment": -150,
                "target_balance": 9500,
                "event_month_offset": 1,
                "event_amount": -800,
                "event_label": "Repair",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(update_response.status_code, 200, update_response.text)
        updated_payload = update_response.json()

        self.assertEqual(updated_payload["id"], created_payload["id"])
        self.assertEqual(updated_payload["name"], "Updated Trip Pressure Plan")
        self.assertEqual(updated_payload["months"], 4)
        self.assertEqual(updated_payload["income_adjustment"], 250.0)
        self.assertEqual(updated_payload["expense_adjustment"], -150.0)
        self.assertEqual(updated_payload["target_balance"], 9500.0)
        self.assertEqual(updated_payload["event_amount"], -800.0)
        self.assertEqual(updated_payload["event_month_offset"], 1)
        self.assertEqual(updated_payload["event_label"], "Repair")

        list_response = self.client.get(
            "/analytics/saved-scenarios",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(list_response.status_code, 200, list_response.text)
        listed_payload = list_response.json()

        self.assertEqual(len(listed_payload), 1)
        self.assertEqual(listed_payload[0]["id"], created_payload["id"])
        self.assertEqual(listed_payload[0]["name"], "Updated Trip Pressure Plan")
        self.assertIsNotNone(listed_payload[0]["projected_end_balance"])
        self.assertIsNotNone(listed_payload[0]["monthly_net_change"])
        self.assertIn(listed_payload[0]["risk_level"], {"healthy", "watch", "high"})
        self.assertIsNotNone(listed_payload[0]["lowest_balance"])
        self.assertIsNotNone(listed_payload[0]["goal_gap_amount"])

        delete_response = self.client.delete(
            f"/analytics/saved-scenarios/{created_payload['id']}"
        )

        self.assertEqual(delete_response.status_code, 200, delete_response.text)
        self.assertIn("deleted", delete_response.json()["message"].lower())

        second_list_response = self.client.get(
            "/analytics/saved-scenarios",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(second_list_response.status_code, 200, second_list_response.text)
        self.assertEqual(second_list_response.json(), [])

    def test_assistant_can_compare_saved_scenarios(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.add_all(
                [
                    SavedScenario(
                        name="Aggressive Cut Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=-200.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Repair Shock Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=2,
                        event_amount=-1200.0,
                        event_label="Repair",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which saved scenario looks strongest?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Aggressive Cut Plan", payload["answer"])
        self.assertTrue(
            any("Aggressive Cut Plan" in item for item in payload["supporting_points"])
        )
        self.assertTrue(
            any("Repair Shock Plan" in item for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertIsNotNone(payload["suggested_actions"][0]["saved_scenario_id"])
        self.assertIsNotNone(payload["suggested_actions"][0]["compare_saved_scenario_id"])

    def test_assistant_can_compare_named_saved_scenarios(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.add_all(
                [
                    SavedScenario(
                        name="Aggressive Cut Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=-200.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Repair Shock Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=2,
                        event_amount=-1200.0,
                        event_label="Repair",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Bonus Lift Plan",
                        months=3,
                        income_adjustment=500.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Compare Aggressive Cut Plan and Repair Shock Plan",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Aggressive Cut Plan", payload["answer"])
        self.assertNotIn("Bonus Lift Plan", " ".join(payload["supporting_points"]))
        self.assertTrue(
            any("Repair Shock Plan" in item for item in payload["supporting_points"])
        )

    def test_assistant_can_rank_saved_scenarios_by_safety(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.add_all(
                [
                    SavedScenario(
                        name="Safe Balance Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Big Swing Plan",
                        months=3,
                        income_adjustment=4000.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=1,
                        event_amount=-11000.0,
                        event_label="Emergency",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which saved scenario is safest?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Safe Balance Plan", payload["answer"])
        self.assertTrue(
            any("floor" in item.lower() for item in payload["supporting_points"])
        )
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertIsNotNone(payload["suggested_actions"][0]["saved_scenario_id"])

    def test_assistant_understands_natural_saved_plan_questions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.add_all(
                [
                    SavedScenario(
                        name="Goal Stretch Plan",
                        months=3,
                        income_adjustment=500.0,
                        expense_adjustment=0.0,
                        target_balance=9500.0,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Repair Shock Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=2,
                        event_amount=-1200.0,
                        event_label="Repair",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which plan gets me closest to my goal?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Goal Stretch Plan", payload["answer"])
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertIsNotNone(payload["suggested_actions"][0]["saved_scenario_id"])

    def test_assistant_can_summarize_saved_plan_portfolio(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Jan",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Feb",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2000.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=500.0,
                        category="Rent",
                        description="Rent Mar",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.add_all(
                [
                    SavedScenario(
                        name="Steady Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Stretch Goal Plan",
                        months=3,
                        income_adjustment=500.0,
                        expense_adjustment=0.0,
                        target_balance=9500.0,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Trip Event Plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=2,
                        event_amount=-1200.0,
                        event_label="Trip",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Show my saved plans",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("saved simulator plan", payload["answer"])
        self.assertTrue(any("Portfolio:" in item for item in payload["supporting_points"]))
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertIn(
            payload["suggested_followups"][0],
            {
                "Which saved scenario looks strongest?",
                "Which saved scenario is safest?",
                "Which saved scenario has the best monthly cash flow?",
                "Which saved scenario gets me closest to my goal?",
            },
        )

    def test_assistant_can_answer_recurring_expense_questions(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=14.99,
                        category="Entertainment",
                        description="Netflix Subscription",
                        date=date(2026, 1, 12),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=14.99,
                        category="Entertainment",
                        description="Netflix Subscription",
                        date=date(2026, 2, 12),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=17.99,
                        category="Entertainment",
                        description="Netflix Subscription",
                        date=date(2026, 3, 12),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which subscriptions should I review first?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("recurring", payload["answer"].lower())
        self.assertIn("Netflix Subscription", payload["answer"])
        self.assertTrue(any("Netflix Subscription" in item for item in payload["supporting_points"]))
        self.assertEqual(payload["suggested_actions"][0]["page"], "transactions")
        self.assertEqual(payload["suggested_actions"][0]["section"], "recurring")
        self.assertEqual(payload["suggested_actions"][0]["description"], "Netflix Subscription")

    def test_assistant_uses_llm_for_recurring_merchant_explanations(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=4.96,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 1, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=5.29,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 2, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=6.29,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 3, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        with patch("app.services.assistant_service.generate_llm_assistant_response") as mock_llm:
            mock_llm.return_value = {
                "answer": (
                    "THE UPS STORE is most likely a shipping, mailbox, printing, or package-service charge. "
                    "Your app sees it as a small recurring expense, but the exact purpose depends on your receipt."
                ),
                "supporting_points": [],
                "suggested_followups": [],
                "action_type": "none",
                "action_label": None,
                "action_target": None,
            }

            response = self.client.post(
                "/assistant/response",
                json={
                    "question": "What is THE UPS STORE? What am I paying for?",
                    "history": [],
                    "mode": "balanced",
                    "account_id": self.chequing_account_id,
                },
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        llm_kwargs = mock_llm.call_args.kwargs

        self.assertIn("shipping", payload["answer"].lower())
        self.assertTrue(
            any(
                item["description"] == "THE UPS STORE #"
                for item in llm_kwargs["recurring_expenses"]
            )
        )
        action_types = {item.get("action_type") for item in payload["suggested_actions"]}
        self.assertIn("show_matching_transactions", action_types)
        self.assertIn("learn_merchant_category", action_types)

    def test_assistant_can_learn_merchant_category_from_chat(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=4.96,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 1, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=5.29,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 2, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=6.29,
                        category="Other",
                        description="THE UPS STORE #",
                        date=date(2026, 3, 10),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Please remember that THE UPS STORE is shipping?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertIn("remember", payload["answer"].lower())
        self.assertTrue(
            any(
                item.get("action_type") == "show_matching_transactions"
                for item in payload["suggested_actions"]
            )
        )

        with self.session_local() as session:
            categories = {
                category
                for (category,) in session.query(Transaction.category)
                .filter(Transaction.description == "THE UPS STORE #")
                .all()
            }
            profile = (
                session.query(MerchantCategoryProfile)
                .filter(
                    MerchantCategoryProfile.owner_id == self.user_id,
                    MerchantCategoryProfile.merchant_key == "the ups store",
                )
                .first()
            )
            learning_event = (
                session.query(CategoryLearningEvent)
                .filter(CategoryLearningEvent.owner_id == self.user_id)
                .first()
            )

        self.assertEqual(categories, {"shipping"})
        self.assertIsNotNone(profile)
        self.assertEqual(profile.category, "shipping")
        self.assertIsNotNone(learning_event)
        self.assertEqual(learning_event.category, "shipping")

    def test_assistant_reports_category_learning_cleanup_candidates(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=8.90,
                        category="Other",
                        description="SQDC77068 MTL",
                        date=date(2026, 3, 16),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=12.60,
                        category="Other",
                        description="SQDC77068 MTL",
                        date=date(2026, 3, 20),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which categories still need cleanup?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("merchant group", payload["answer"].lower())
        self.assertIn("Sqdc", payload["answer"])
        self.assertTrue(any("smoking" in point.lower() for point in payload["supporting_points"]))
        learning_actions = [
            item for item in payload["suggested_actions"]
            if item.get("action_type") == "learn_merchant_category"
        ]
        self.assertTrue(learning_actions)
        self.assertEqual(learning_actions[0]["merchant_key"], "sqdc")
        self.assertEqual(learning_actions[0]["category"], "smoking")

    def test_assistant_can_model_cancelling_biggest_subscription(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "What happens if I cancel my biggest subscription?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("Gym Membership", payload["answer"])
        self.assertIn("$50.00 per month", payload["answer"])
        self.assertTrue(
            any(action["page"] == "simulator" and action["expense_adjustment"] == -50.0 for action in payload["suggested_actions"])
        )

    def test_assistant_does_not_recommend_canceling_essential_phone_bill(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=79.78,
                        category="Phone",
                        description="VIRGIN PLUS VERDUN QC",
                        date=date(2026, 1, 24),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=79.78,
                        category="Phone",
                        description="VIRGIN PLUS VERDUN QC",
                        date=date(2026, 2, 24),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=82.49,
                        category="Phone",
                        description="VIRGIN PLUS VERDUN QC",
                        date=date(2026, 3, 24),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "What happens if I cancel my biggest subscription?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        answer = payload["answer"].lower()

        self.assertIn("virgin plus", answer)
        self.assertIn("not treat", answer)
        self.assertIn("review", answer)
        self.assertNotIn("if you cancel virgin plus", answer)
        self.assertFalse(
            any(
                action["label"].lower().startswith("model cancelling virgin plus")
                for action in payload["suggested_actions"]
            )
        )

    def test_assistant_can_recommend_a_savings_scenario(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Jan",
                        date=date(2026, 1, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 1, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Feb",
                        date=date(2026, 2, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 2, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=2200.0,
                        category="Salary",
                        description="Payroll Mar",
                        date=date(2026, 3, 3),
                        type="income",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Health",
                        description="Gym Membership",
                        date=date(2026, 3, 5),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.post(
            "/assistant/response",
            json={
                "question": "Which savings scenario should I try first?",
                "history": [],
                "mode": "balanced",
                "account_id": self.chequing_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertIn("simulator recommendation", payload["answer"].lower())
        self.assertEqual(payload["suggested_actions"][0]["page"], "simulator")
        self.assertLess(payload["suggested_actions"][0]["expense_adjustment"], 0)

    def test_assistant_suggestions_include_recurring_prompt_when_patterns_exist(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=50.0,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 1, 9),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 2, 9),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    Transaction(
                        amount=50.0,
                        category="Entertainment",
                        description="Spotify Premium",
                        date=date(2026, 3, 9),
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/assistant/suggestions",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("What subscriptions or recurring charges do I have?", suggestions)
        self.assertIn("What happens if I cancel my biggest subscription?", suggestions)
        self.assertIn("Which savings scenario should I try first?", suggestions)

    def test_assistant_suggestions_include_saved_scenario_prompt(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    SavedScenario(
                        name="Base Plan",
                        months=3,
                        income_adjustment=100.0,
                        expense_adjustment=0.0,
                        target_balance=None,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                    SavedScenario(
                        name="Stretch Plan",
                        months=3,
                        income_adjustment=400.0,
                        expense_adjustment=0.0,
                        target_balance=9000.0,
                        event_month_offset=None,
                        event_amount=None,
                        event_label=None,
                        owner_id=self.user_id,
                        account_id=self.chequing_account_id,
                    ),
                ]
            )
            session.commit()

        response = self.client.get(
            "/assistant/suggestions",
            params={"account_id": self.chequing_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Which saved scenario looks strongest?", suggestions)
        self.assertIn("Which saved scenario is safest?", suggestions)
        self.assertIn("Which saved scenario has the best monthly cash flow?", suggestions)
        self.assertIn("Which saved scenario gets me closest to my goal?", suggestions)


if __name__ == "__main__":
    unittest.main()
