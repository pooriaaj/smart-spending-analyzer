from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import (
    Account,
    AssistantChatMessage,
    AssistantLearningExample,
    AssistantUsageEvent,
    BudgetPlan,
    CategoryLearningEvent,
    CategoryMemory,
    MerchantCategoryProfile,
    MerchantLookupCache,
    SavedScenario,
    Transaction,
    User,
    UserLearningPreference,
)
from app.routes.user_routes import change_my_password, delete_my_account, export_my_data, router as user_router
from app.schemas import ChangePasswordRequest, DeleteAccountRequest, UserDataExportRequest
from app.auth import hash_password


def collect_export_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(collect_export_keys(item))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for item in value:
            keys.update(collect_export_keys(item))
        return keys
    return set()


class UserRouteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )

        @event.listens_for(cls.engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        cls.session_local = sessionmaker(bind=cls.engine, autocommit=False, autoflush=False, future=True)
        Base.metadata.create_all(bind=cls.engine)

        with cls.session_local() as session:
            user = User(email="profile@example.com", password_hash="hashed")
            session.add(user)
            session.commit()
            cls.user_id = user.id

        app = FastAPI()
        app.include_router(user_router)

        def override_get_db() -> Generator[Session, None, None]:
            session = cls.session_local()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user() -> User:
            return User(id=cls.user_id, email="profile@example.com", password_hash="hashed")

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
            session.query(MerchantLookupCache).delete()
            session.query(MerchantCategoryProfile).delete()
            session.query(UserLearningPreference).delete()
            session.query(User).filter(User.id != self.user_id).delete()
            session.commit()

    def test_profile_returns_community_learning_enabled_by_default(self) -> None:
        response = self.client.get("/users/me")

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["email"], "profile@example.com")
        self.assertTrue(payload["community_learning_enabled"])

    def test_user_can_disable_anonymous_community_learning(self) -> None:
        response = self.client.put(
            "/users/me/learning",
            json={"community_learning_enabled": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["community_learning_enabled"])

        with self.session_local() as session:
            preference = (
                session.query(UserLearningPreference)
                .filter(UserLearningPreference.owner_id == self.user_id)
                .one()
            )

        self.assertFalse(preference.community_learning_enabled)

    def test_disabling_community_learning_removes_user_from_global_consensus(self) -> None:
        with self.session_local() as session:
            other_user = User(email="learning-peer@example.com", password_hash="hashed")
            session.add(other_user)
            session.flush()
            session.add_all(
                [
                    MerchantCategoryProfile(
                        merchant_key="glimmerbox",
                        display_name="Glimmerbox",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=18.0,
                        owner_id=self.user_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="glimmerbox",
                        display_name="Glimmerbox",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=19.0,
                        owner_id=other_user.id,
                    ),
                    MerchantLookupCache(
                        merchant_key="glimmerbox",
                        display_name="Glimmerbox",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.9,
                        matched_signal="glimmerbox",
                        provider="community",
                    ),
                ]
            )
            session.commit()

        response = self.client.put(
            "/users/me/learning",
            json={"community_learning_enabled": False},
        )

        self.assertEqual(response.status_code, 200, response.text)
        with self.session_local() as session:
            cached = (
                session.query(MerchantLookupCache)
                .filter(
                    MerchantLookupCache.merchant_key == "glimmerbox",
                    MerchantLookupCache.transaction_type == "expense",
                    MerchantLookupCache.provider == "community",
                )
                .one_or_none()
            )

        self.assertIsNone(cached)

    def test_enabling_community_learning_rebuilds_allowed_consensus(self) -> None:
        with self.session_local() as session:
            other_user = User(email="learning-peer-rebuild@example.com", password_hash="hashed")
            session.add(other_user)
            session.flush()
            session.add(
                UserLearningPreference(
                    owner_id=self.user_id,
                    community_learning_enabled=False,
                )
            )
            session.add_all(
                [
                    MerchantCategoryProfile(
                        merchant_key="glimmerbox",
                        display_name="Glimmerbox",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=18.0,
                        owner_id=self.user_id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="glimmerbox",
                        display_name="Glimmerbox",
                        category="entertainment",
                        transaction_type="expense",
                        confidence=0.97,
                        confirmation_count=3,
                        last_amount=19.0,
                        owner_id=other_user.id,
                    ),
                ]
            )
            session.commit()

        response = self.client.put(
            "/users/me/learning",
            json={"community_learning_enabled": True},
        )

        self.assertEqual(response.status_code, 200, response.text)
        with self.session_local() as session:
            cached = (
                session.query(MerchantLookupCache)
                .filter(
                    MerchantLookupCache.merchant_key == "glimmerbox",
                    MerchantLookupCache.transaction_type == "expense",
                    MerchantLookupCache.provider == "community",
                )
                .one_or_none()
            )

        self.assertIsNotNone(cached)
        self.assertEqual(cached.category, "entertainment")

    def test_password_change_marks_password_changed_at(self) -> None:
        with self.session_local() as session:
            user = session.get(User, self.user_id)
            assert user is not None
            user.password_hash = hash_password("StrongPass1")
            user.password_changed_at = None
            session.commit()

        before_change = datetime.now(timezone.utc)
        with self.session_local() as session:
            user = session.get(User, self.user_id)
            assert user is not None
            cookie_response = Response()
            response = change_my_password(
                ChangePasswordRequest(
                    current_password="StrongPass1",
                    new_password="BetterPass1",
                ),
                response=cookie_response,
                db=session,
                current_user=user,
            )
            self.assertEqual(response.message, "Password changed successfully")
            self.assertIn("access_token=", cookie_response.headers.get("set-cookie", ""))
            self.assertIsNotNone(user.password_changed_at)
            changed_at = user.password_changed_at
            if changed_at.tzinfo is None:
                changed_at = changed_at.replace(tzinfo=timezone.utc)
            self.assertGreaterEqual(changed_at, before_change)

    def test_delete_account_clears_auth_cookie(self) -> None:
        with self.session_local() as session:
            user = User(
                email="delete-cookie@example.com",
                password_hash=hash_password("StrongPass1"),
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            cookie_response = Response()
            response = delete_my_account(
                DeleteAccountRequest(password="StrongPass1"),
                response=cookie_response,
                db=session,
                current_user=user,
            )

            self.assertEqual(response.message, "Account deleted successfully")
            set_cookie = cookie_response.headers.get("set-cookie", "").lower()
            self.assertIn("access_token=", set_cookie)
            self.assertIn("max-age=0", set_cookie)

    def test_delete_account_rejects_wrong_password_without_deleting_user(self) -> None:
        with self.session_local() as session:
            user = User(
                email="delete-wrong-password@example.com",
                password_hash=hash_password("StrongPass1"),
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            with self.assertRaises(HTTPException) as exc:
                delete_my_account(
                    DeleteAccountRequest(password="WrongPass1"),
                    response=Response(),
                    db=session,
                    current_user=user,
                )

            self.assertEqual(exc.exception.status_code, 400)
            self.assertEqual(exc.exception.detail, "Password is incorrect")
            self.assertIsNotNone(session.get(User, user.id))

    def test_delete_account_removes_user_owned_rows(self) -> None:
        with self.session_local() as session:
            user = User(
                email="delete-owned-rows@example.com",
                password_hash=hash_password("StrongPass1"),
            )
            session.add(user)
            session.flush()

            account = Account(
                name="Chequing",
                type="chequing",
                owner_id=user.id,
            )
            session.add(account)
            session.flush()

            session.add_all(
                [
                    Transaction(
                        amount=42.5,
                        category="groceries",
                        description="Sample grocery transaction",
                        date=date(2026, 5, 1),
                        type="expense",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    CategoryMemory(
                        keyword="sample grocery",
                        category="groceries",
                        transaction_type="expense",
                        owner_id=user.id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="sample-grocery",
                        display_name="Sample Grocery",
                        category="groceries",
                        transaction_type="expense",
                        owner_id=user.id,
                    ),
                    UserLearningPreference(
                        owner_id=user.id,
                        community_learning_enabled=False,
                    ),
                    AssistantChatMessage(
                        role="user",
                        content="How much did I spend on groceries?",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    AssistantUsageEvent(
                        provider="test",
                        request_chars=12,
                        response_chars=34,
                        owner_id=user.id,
                    ),
                    AssistantLearningExample(
                        question="What changed?",
                        answer="Groceries increased.",
                        intent="spending_summary",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    CategoryLearningEvent(
                        merchant_key="sample-grocery",
                        display_name="Sample Grocery",
                        category="groceries",
                        transaction_type="expense",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    BudgetPlan(
                        month="2026-05",
                        category="groceries",
                        amount=300.0,
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    SavedScenario(
                        name="Tighter grocery plan",
                        months=3,
                        income_adjustment=0.0,
                        expense_adjustment=-50.0,
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                ]
            )
            session.commit()
            user_id = user.id

            response = delete_my_account(
                DeleteAccountRequest(password="StrongPass1"),
                response=Response(),
                db=session,
                current_user=user,
            )

            self.assertEqual(response.message, "Account deleted successfully")
            self.assertIsNone(session.get(User, user_id))

            owner_models = [
                Account,
                Transaction,
                CategoryMemory,
                MerchantCategoryProfile,
                UserLearningPreference,
                AssistantChatMessage,
                AssistantUsageEvent,
                AssistantLearningExample,
                CategoryLearningEvent,
                BudgetPlan,
                SavedScenario,
            ]
            for model in owner_models:
                with self.subTest(model=model.__name__):
                    self.assertEqual(
                        session.query(model).filter(model.owner_id == user_id).count(),
                        0,
                    )

    def test_export_my_data_rejects_wrong_password_without_writing(self) -> None:
        with self.session_local() as session:
            user = User(
                email="export-wrong-password@example.com",
                password_hash=hash_password("StrongPass1"),
            )
            session.add(user)
            session.commit()
            session.refresh(user)

            with self.assertRaises(HTTPException) as exc:
                export_my_data(
                    UserDataExportRequest(password="WrongPass1"),
                    db=session,
                    current_user=user,
                )

            self.assertEqual(exc.exception.status_code, 400)
            self.assertEqual(exc.exception.detail, "Password is incorrect")
            self.assertIsNotNone(session.get(User, user.id))

    def test_export_my_data_includes_current_user_rows_without_sensitive_fields(self) -> None:
        with self.session_local() as session:
            user = User(
                email="export-owner@example.com",
                password_hash=hash_password("StrongPass1"),
                reset_token_hash="hashed-reset-token",
                reset_token_expires_at=datetime(2026, 5, 28, tzinfo=timezone.utc),
            )
            other_user = User(
                email="export-other@example.com",
                password_hash=hash_password("StrongPass1"),
            )
            session.add_all([user, other_user])
            session.flush()

            account = Account(name="Chequing", type="chequing", owner_id=user.id)
            other_account = Account(name="Other", type="savings", owner_id=other_user.id)
            session.add_all([account, other_account])
            session.flush()

            session.add_all(
                [
                    Transaction(
                        amount=25.0,
                        category="transport",
                        description="Current user bus pass",
                        date=date(2026, 5, 2),
                        type="expense",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    Transaction(
                        amount=99.0,
                        category="other",
                        description="Other user hidden transaction",
                        date=date(2026, 5, 3),
                        type="expense",
                        owner_id=other_user.id,
                        account_id=other_account.id,
                    ),
                    CategoryMemory(
                        keyword="bus pass",
                        category="transport",
                        transaction_type="expense",
                        owner_id=user.id,
                    ),
                    MerchantCategoryProfile(
                        merchant_key="bus-pass",
                        display_name="Bus Pass",
                        category="transport",
                        transaction_type="expense",
                        owner_id=user.id,
                    ),
                    UserLearningPreference(
                        owner_id=user.id,
                        community_learning_enabled=True,
                    ),
                    AssistantChatMessage(
                        role="assistant",
                        content="You spent $25 on transport.",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    AssistantUsageEvent(
                        provider="test",
                        request_chars=10,
                        response_chars=20,
                        owner_id=user.id,
                    ),
                    AssistantLearningExample(
                        question="Transport summary?",
                        answer="Bus pass was the only item.",
                        intent="category_summary",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    CategoryLearningEvent(
                        merchant_key="bus-pass",
                        display_name="Bus Pass",
                        category="transport",
                        transaction_type="expense",
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    MerchantLookupCache(
                        merchant_key="bus-pass",
                        display_name="Bus Pass",
                        category="transport",
                        transaction_type="expense",
                        provider="community",
                    ),
                    BudgetPlan(
                        month="2026-05",
                        category="transport",
                        amount=100.0,
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                    SavedScenario(
                        name="Transit plan",
                        months=2,
                        income_adjustment=0.0,
                        expense_adjustment=-10.0,
                        owner_id=user.id,
                        account_id=account.id,
                    ),
                ]
            )
            session.commit()
            session.refresh(user)

            response = export_my_data(
                UserDataExportRequest(password="StrongPass1"),
                db=session,
                current_user=user,
            )
            payload = response.model_dump()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["user"]["email"], "export-owner@example.com")
        self.assertEqual(len(payload["accounts"]), 1)
        self.assertEqual(payload["accounts"][0]["name"], "Chequing")
        self.assertEqual(len(payload["transactions"]), 1)
        self.assertEqual(payload["transactions"][0]["description"], "Current user bus pass")
        self.assertEqual(payload["transactions"][0]["date"], "2026-05-02")
        self.assertEqual(len(payload["category_memories"]), 1)
        self.assertEqual(len(payload["merchant_category_profiles"]), 1)
        self.assertEqual(len(payload["user_learning_preferences"]), 1)
        self.assertEqual(len(payload["assistant_chat_messages"]), 1)
        self.assertEqual(len(payload["assistant_usage_events"]), 1)
        self.assertEqual(len(payload["assistant_learning_examples"]), 1)
        self.assertEqual(len(payload["category_learning_events"]), 1)
        self.assertEqual(len(payload["budget_plans"]), 1)
        self.assertEqual(len(payload["saved_scenarios"]), 1)
        self.assertNotIn("Other user hidden transaction", str(payload))
        self.assertNotIn("merchant_lookup_cache", payload)

        exported_keys = collect_export_keys(payload)
        self.assertNotIn("password_hash", exported_keys)
        self.assertNotIn("reset_token_hash", exported_keys)
        self.assertNotIn("reset_token_expires_at", exported_keys)


if __name__ == "__main__":
    unittest.main()
