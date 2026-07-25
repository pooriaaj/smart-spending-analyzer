from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import hash_password
from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import (
    Account,
    BudgetPlan,
    CategoryLearningEvent,
    CategoryMemory,
    MerchantCategoryProfile,
    Transaction,
    User,
)
from app.routes import auth_routes
from app.routes.transaction_routes import router as transaction_router
from app.security import RequestIdMiddleware
from app.services.transaction_service import (
    normalize_category_name,
    normalize_typed_category_name,
    unify_stored_categories_for_user,
)


class CategoryNameNormalizationTest(unittest.TestCase):
    def test_spelling_variants_collapse_to_one_canonical_category(self) -> None:
        for variant in ("grocery", "Grocery", "GROCERIES", "groceries", "  Groceries  ", "Super Market"):
            with self.subTest(variant=variant):
                self.assertEqual(normalize_category_name(variant), "groceries")

    def test_typed_typos_are_corrected_to_the_closest_known_category(self) -> None:
        cases = {
            "gorcery": "groceries",
            "grocerys": "groceries",
            "resturant": "restaurant",
            "transprot": "transport",
            "utilites": "utilities",
            "entertainmnet": "entertainment",
        }

        for typed, expected in cases.items():
            with self.subTest(typed=typed):
                self.assertEqual(normalize_typed_category_name(typed), expected)

    def test_custom_category_names_are_left_alone(self) -> None:
        # Typo repair must never hijack a category the user meant to create.
        for custom in ("gym", "vet", "yoga", "daycare", "haircut", "parking", "side hustle"):
            with self.subTest(custom=custom):
                self.assertEqual(normalize_typed_category_name(custom), custom)

    def test_words_needing_more_than_two_edits_are_not_corrected(self) -> None:
        # Similar-looking is not enough: only genuine keystroke slips are fixed.
        # A word within two edits of a real category (say "educator") is still
        # treated as a typo, which is what editing a transaction overrides.
        for custom in ("investors", "education fund", "traveller insurance"):
            with self.subTest(custom=custom):
                self.assertEqual(normalize_typed_category_name(custom), custom)

    def test_plain_normalization_never_guesses_at_typos(self) -> None:
        # Everything except quick entry stays deterministic, so no guessed
        # correction can be applied silently or in bulk.
        self.assertEqual(normalize_category_name("gorcery"), "gorcery")
        self.assertEqual(normalize_category_name("Grocery"), "groceries")


class StoredCategoryUnificationTest(unittest.TestCase):
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
            user = User(email="unify@example.com", password_hash="hashed")
            session.add(user)
            session.flush()

            first_account = Account(name="Chequing", type="chequing", owner_id=user.id, is_active=True)
            second_account = Account(name="Visa", type="credit", owner_id=user.id, is_active=True)
            session.add_all([first_account, second_account])
            session.commit()

            cls.user_id = user.id
            cls.first_account_id = first_account.id
            cls.second_account_id = second_account.id

        app = FastAPI()
        app.add_middleware(RequestIdMiddleware)
        app.include_router(transaction_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="unify@example.com", password_hash="hashed")

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
            session.query(CategoryMemory).delete()
            session.query(MerchantCategoryProfile).delete()
            session.query(CategoryLearningEvent).delete()
            session.commit()

    def add_transaction(self, category: str, account_id: int, description: str) -> None:
        with self.session_local() as session:
            session.add(
                Transaction(
                    amount=25.0,
                    category=category,
                    description=description,
                    date=date(2026, 6, 1),
                    type="expense",
                    owner_id=self.user_id,
                    account_id=account_id,
                )
            )
            session.commit()

    def test_legacy_spellings_are_unified_across_every_account(self) -> None:
        self.add_transaction("grocery", self.first_account_id, "Food Basics")
        self.add_transaction("Grocery", self.first_account_id, "T&T Supermarket")
        self.add_transaction("groceries", self.second_account_id, "Ambrosia")
        self.add_transaction("gym", self.second_account_id, "Bodies In Progress")

        with self.session_local() as session:
            stats = unify_stored_categories_for_user(session, self.user_id)

        self.assertEqual(stats["transactions_updated"], 2)

        with self.session_local() as session:
            stored = {row[0] for row in session.query(Transaction.category).distinct().all()}

        # One grocery category left, and the custom category survived untouched.
        self.assertEqual(stored, {"groceries", "gym"})

    def test_unification_does_not_recategorize_transactions(self) -> None:
        self.add_transaction("Grocery", self.first_account_id, "AIR CANADA FLIGHT")

        with self.session_local() as session:
            unify_stored_categories_for_user(session, self.user_id)
            transaction = session.query(Transaction).one()

            self.assertEqual(transaction.category, "groceries")
            self.assertEqual(transaction.description, "AIR CANADA FLIGHT")

    def test_learned_signals_follow_the_canonical_category(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    CategoryMemory(
                        keyword="foodbasics",
                        category="Grocery",
                        transaction_type="expense",
                        owner_id=self.user_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="foodbasics",
                        display_name="Food Basics",
                        category="grocery",
                        transaction_type="expense",
                        confidence=0.9,
                        confirmation_count=2,
                        owner_id=self.user_id,
                    ),
                    CategoryLearningEvent(
                        merchant_key="foodbasics",
                        display_name="Food Basics",
                        category="GROCERY",
                        transaction_type="expense",
                        signal_source="manual_edit",
                        owner_id=self.user_id,
                    ),
                ]
            )
            session.commit()

        with self.session_local() as session:
            stats = unify_stored_categories_for_user(session, self.user_id)

        self.assertEqual(stats["learning_rows_updated"], 3)

        with self.session_local() as session:
            self.assertEqual(session.query(CategoryMemory).one().category, "groceries")
            self.assertEqual(session.query(MerchantCategoryProfile).one().category, "groceries")
            self.assertEqual(session.query(CategoryLearningEvent).one().category, "groceries")

    def seed_duplicate_budget_rows(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    BudgetPlan(
                        month="2026-06",
                        category="grocery",
                        amount=400.0,
                        owner_id=self.user_id,
                        account_id=self.first_account_id,
                    ),
                    BudgetPlan(
                        month="2026-06",
                        category="groceries",
                        amount=550.0,
                        owner_id=self.user_id,
                        account_id=self.first_account_id,
                    ),
                    BudgetPlan(
                        month="2026-06",
                        category="gym",
                        amount=60.0,
                        owner_id=self.user_id,
                        account_id=self.first_account_id,
                    ),
                ]
            )
            session.commit()

    def test_duplicate_budget_rows_are_never_deleted_automatically(self) -> None:
        self.seed_duplicate_budget_rows()

        with self.session_local() as session:
            stats = unify_stored_categories_for_user(session, self.user_id)

        # Renaming "grocery" would collide with the existing "groceries" row, so
        # the automatic pass reports it instead of deleting a budget the user set.
        self.assertEqual(stats["budget_plans_merged"], 0)
        self.assertEqual(stats["budget_plans_needing_merge"], 1)

        with self.session_local() as session:
            plans = {plan.category: plan.amount for plan in session.query(BudgetPlan).all()}

        self.assertEqual(plans, {"grocery": 400.0, "groceries": 550.0, "gym": 60.0})

    def test_explicit_cleanup_merges_duplicates_and_keeps_the_larger_limit(self) -> None:
        self.seed_duplicate_budget_rows()

        with self.session_local() as session:
            stats = unify_stored_categories_for_user(
                session,
                self.user_id,
                merge_budget_duplicates=True,
            )

        self.assertEqual(stats["budget_plans_merged"], 1)

        with self.session_local() as session:
            plans = {plan.category: plan.amount for plan in session.query(BudgetPlan).all()}

        self.assertEqual(plans, {"groceries": 550.0, "gym": 60.0})

    def test_automatic_pass_does_not_repair_typos_in_stored_rows(self) -> None:
        self.add_transaction("gorcery", self.first_account_id, "Food Basics")

        with self.session_local() as session:
            stats = unify_stored_categories_for_user(session, self.user_id)

        self.assertEqual(stats["transactions_updated"], 0)

        with self.session_local() as session:
            self.assertEqual(session.query(Transaction).one().category, "gorcery")

    def test_explicit_cleanup_repairs_typos_in_stored_rows(self) -> None:
        self.add_transaction("gorcery", self.first_account_id, "Food Basics")

        with self.session_local() as session:
            unify_stored_categories_for_user(session, self.user_id, repair_typos=True)

        with self.session_local() as session:
            self.assertEqual(session.query(Transaction).one().category, "groceries")

    def test_unification_is_idempotent(self) -> None:
        self.add_transaction("Grocery", self.first_account_id, "Food Basics")

        with self.session_local() as session:
            unify_stored_categories_for_user(session, self.user_id)

        with self.session_local() as session:
            second_run = unify_stored_categories_for_user(session, self.user_id)

        self.assertEqual(
            second_run,
            {
                "transactions_updated": 0,
                "learning_rows_updated": 0,
                "budget_plans_updated": 0,
                "budget_plans_merged": 0,
                "budget_plans_needing_merge": 0,
            },
        )

    def create_transaction(self, category: str, description: str) -> dict:
        response = self.client.post(
            "/transactions/",
            json={
                "amount": 42.5,
                "category": category,
                "description": description,
                "date": "2026-06-02",
                "type": "expense",
                "account_id": self.first_account_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_saving_a_mistyped_category_stores_the_canonical_name(self) -> None:
        self.assertEqual(self.create_transaction("gorcery", "Food Basics")["category"], "groceries")

    def test_a_category_the_owner_already_uses_is_never_corrected(self) -> None:
        # Once a custom name exists in the user's data it counts as intentional,
        # even if it looks like a typo of a built-in category.
        self.add_transaction("grocerys", self.second_account_id, "Corner Store")

        created = self.create_transaction("grocerys", "Food Basics")

        self.assertEqual(created["category"], "grocerys")

    def test_editing_a_transaction_keeps_the_category_exactly_as_typed(self) -> None:
        created = self.create_transaction("gorcery", "Food Basics")
        self.assertEqual(created["category"], "groceries")

        # The escape hatch: an edit is deliberate, so quick entry's guess loses.
        response = self.client.put(
            f"/transactions/{created['id']}",
            json={
                "amount": 42.5,
                "category": "gorcery",
                "description": "Food Basics",
                "date": "2026-06-02",
                "type": "expense",
                "account_id": self.first_account_id,
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["category"], "gorcery")


class CategoryDrilldownTest(StoredCategoryUnificationTest):
    """A chart total and the list behind it must cover the same transactions."""

    def seed_grocery_history(self) -> None:
        with self.session_local() as session:
            session.add_all(
                [
                    Transaction(
                        amount=amount,
                        category="groceries",
                        description=description,
                        date=day,
                        type="expense",
                        owner_id=self.user_id,
                        account_id=self.first_account_id,
                    )
                    for amount, description, day in (
                        (40.17, "longos", date(2026, 6, 30)),
                        (73.48, "food basics", date(2026, 6, 29)),
                        (58.94, "older purchase", date(2026, 3, 2)),
                        (65.03, "much older purchase", date(2026, 2, 18)),
                    )
                ]
            )
            session.commit()

    def test_date_range_narrows_the_transaction_list(self) -> None:
        self.seed_grocery_history()

        response = self.client.get(
            "/transactions/page",
            params={"category": "groceries", "start": "2026-06-26", "end": "2026-07-25"},
        )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()

        self.assertEqual(payload["total"], 2)
        self.assertEqual(
            round(sum(item["amount"] for item in payload["items"]), 2),
            113.65,
        )

    def test_list_without_a_range_still_returns_the_full_history(self) -> None:
        self.seed_grocery_history()

        response = self.client.get("/transactions/page", params={"category": "groceries"})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["total"], 4)

    def test_reversed_date_range_is_rejected(self) -> None:
        response = self.client.get(
            "/transactions/page",
            params={"start": "2026-07-25", "end": "2026-06-26"},
        )

        self.assertEqual(response.status_code, 400, response.text)

    def test_merge_similar_categories_route_collapses_typo_variants(self) -> None:
        # The exact shape reported from production: three grocery spellings.
        self.add_transaction("groceries", self.first_account_id, "food basics")
        self.add_transaction("groccery", self.first_account_id, "longos")
        self.add_transaction("grocerry", self.second_account_id, "t&t")

        response = self.client.post("/transactions/merge-similar-categories")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["transactions_updated"], 2)

        with self.session_local() as session:
            stored = {row[0] for row in session.query(Transaction.category).distinct().all()}

        self.assertEqual(stored, {"groceries"})


class LoginCategoryUnificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.session_local = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)

        def override_get_db() -> Generator[Session, None, None]:
            session = self.session_local()
            try:
                yield session
            finally:
                session.close()

        app = FastAPI()
        app.include_router(auth_routes.router)
        app.dependency_overrides[auth_routes.get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def seed_user_with_legacy_categories(self) -> None:
        with self.session_local() as session:
            user = User(email="login-unify@example.com", password_hash=hash_password("StrongPass1"))
            session.add(user)
            session.flush()

            account = Account(name="Chequing", type="chequing", owner_id=user.id, is_active=True)
            session.add(account)
            session.flush()

            session.add_all(
                [
                    Transaction(
                        amount=30.0,
                        category=category,
                        description=description,
                        date=date(2026, 6, 1),
                        type="expense",
                        owner_id=user.id,
                        account_id=account.id,
                    )
                    for category, description in (
                        ("grocery", "Food Basics"),
                        ("Grocery", "T&T Supermarket"),
                        ("groceries", "Ambrosia"),
                    )
                ]
            )
            session.commit()

    def test_successful_login_unifies_legacy_categories(self) -> None:
        self.seed_user_with_legacy_categories()

        response = self.client.post(
            "/auth/login",
            data={"username": "login-unify@example.com", "password": "StrongPass1"},
        )

        self.assertEqual(response.status_code, 200, response.text)

        with self.session_local() as session:
            stored = {row[0] for row in session.query(Transaction.category).distinct().all()}

        self.assertEqual(stored, {"groceries"})

    def test_login_still_succeeds_when_unification_fails(self) -> None:
        self.seed_user_with_legacy_categories()

        with patch.object(
            auth_routes,
            "unify_stored_categories_for_user",
            side_effect=SQLAlchemyError("boom"),
        ):
            response = self.client.post(
                "/auth/login",
                data={"username": "login-unify@example.com", "password": "StrongPass1"},
            )

        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()
