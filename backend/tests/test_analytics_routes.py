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
from app.models import Account, BudgetPlan, SavedScenario, Transaction, User
from app.routes.analytics_routes import router as analytics_router


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
        self.assertEqual(payload["top_category"]["category"], "Entertainment")
        self.assertEqual(payload["account_comparison"], [])
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
        self.assertEqual(len(payload["timeline"]), 3)
        self.assertEqual(payload["timeline"][0]["month"], "2026-05")
        self.assertEqual(payload["timeline"][0]["baseline_ending_balance"], 5600.0)
        self.assertEqual(payload["timeline"][0]["balance_delta"], 150.0)

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
            "/analytics/assistant-suggestions",
            params={"account_id": self.savings_account_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Why is Entertainment my top expense category?", suggestions)
        self.assertIn("How can I reduce Entertainment spending?", suggestions)
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
            "/analytics/assistant-suggestions",
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
                "/analytics/assistant-suggestions",
                params={"account_id": self.chequing_account_id},
            )

        self.assertEqual(response.status_code, 200, response.text)
        suggestions = response.json()["suggestions"]

        self.assertIn("Which budget is projected to go over?", suggestions)

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

    def test_assistant_response_reports_budget_status_for_focused_category(self) -> None:
        self.seed_transactions()
        self.seed_budget(
            month="2026-02",
            category="groceries",
            amount=120.0,
            account_id=self.chequing_account_id,
        )

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
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

            with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
                response = self.client.post(
                    "/analytics/assistant-response",
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

            with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
                response = self.client.post(
                    "/analytics/assistant-response",
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

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
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

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
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

        with patch("app.services.analytics_service.generate_llm_assistant_response", return_value=None):
            response = self.client.post(
                "/analytics/assistant-response",
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
            "/analytics/assistant-response",
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
            "/analytics/assistant-response",
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


if __name__ == "__main__":
    unittest.main()
