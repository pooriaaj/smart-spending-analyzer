from __future__ import annotations

import unittest
from collections.abc import Generator
from datetime import datetime, timezone

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import MerchantCategoryProfile, MerchantLookupCache, User, UserLearningPreference
from app.routes.user_routes import change_my_password, delete_my_account, router as user_router
from app.schemas import ChangePasswordRequest, DeleteAccountRequest
from app.auth import hash_password


class UserRouteTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
