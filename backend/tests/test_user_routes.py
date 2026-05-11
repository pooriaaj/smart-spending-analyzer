from __future__ import annotations

import unittest
from collections.abc import Generator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import get_current_user, get_db
from app.models import User, UserLearningPreference
from app.routes.user_routes import router as user_router


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
            session.query(UserLearningPreference).delete()
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


if __name__ == "__main__":
    unittest.main()
