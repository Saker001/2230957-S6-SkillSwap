import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
TEST_DATABASE_PATH = Path(TEST_DATABASE_DIR.name) / "skillswap-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-key-not-for-deployments"
os.environ["PASSWORD_PEPPER"] = "test-only-password-pepper-not-for-deployments"

from database import engine  # noqa: E402
from auth import JWT_ISSUER, JWT_SECRET_KEY, RefreshSession, User  # noqa: E402
from main import app  # noqa: E402


class SkillSwapApiTests(unittest.TestCase):
    def setUp(self) -> None:
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        self.client = TestClient(app)
        self.user_email = f"member-{uuid.uuid4()}@example.com"
        signup = self.client.post(
            "/api/auth/signup",
            json={
                "email": self.user_email,
                "display_name": "Ari",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(signup.status_code, 201, signup.text)
        login = self.client.post(
            "/api/auth/login",
            json={
                "email": self.user_email,
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.access_token = login.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

    def tearDown(self) -> None:
        self.client.close()

    def create_skill(self) -> dict:
        response = self.client.post(
            "/api/skills",
            json={
                "teacher_name": "Ari",
                "title": "Beginner guitar",
                "description": "Learn basic chords.",
                "category": "Music",
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_skill_listing_crud(self) -> None:
        skill = self.create_skill()
        skill_id = skill["id"]

        self.assertEqual(self.client.get("/api/skills").json()[0]["id"], skill_id)
        self.assertEqual(self.client.get(f"/api/skills/{skill_id}").json()["title"], "Beginner guitar")

        updated = self.client.patch(
            f"/api/skills/{skill_id}",
            json={"title": "Acoustic guitar"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["title"], "Acoustic guitar")

        deleted = self.client.delete(f"/api/skills/{skill_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(f"/api/skills/{skill_id}").status_code, 404)

    def test_skill_create_validates_required_fields(self) -> None:
        response = self.client.post(
            "/api/skills",
            json={
                "teacher_name": "Ari",
                "title": " ",
                "description": "A skill",
                "category": "Music",
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_api_docs_include_crud_endpoints(self) -> None:
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        for path in ("/api/skills", "/api/skills/{skill_id}"):
            self.assertIn(path, paths)
        for method in ("get", "post"):
            self.assertIn(method, paths["/api/skills"])
        for method in ("get", "patch", "delete"):
            self.assertIn(method, paths["/api/skills/{skill_id}"])
        for method in ("get", "post"):
            self.assertIn(method, paths["/api/session-requests"])
        for method in ("get", "patch", "delete"):
            self.assertIn(method, paths["/api/session-requests/{request_id}"])
        self.assertIn("/api/auth/login", paths)
        self.assertIn("/api/auth/refresh", paths)
        self.assertIn("/api/users/me", paths)

    def test_authentication_rejects_missing_or_invalid_tokens(self) -> None:
        anonymous = TestClient(app)
        self.assertEqual(anonymous.get("/api/skills").status_code, 401)
        invalid = anonymous.get(
            "/api/skills",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        self.assertEqual(invalid.status_code, 401)
        tampered = anonymous.get(
            "/api/skills",
            headers={"Authorization": f"Bearer {self.access_token}tampered"},
        )
        self.assertEqual(tampered.status_code, 401)
        now = datetime.now(timezone.utc)
        expired_token = jwt.encode(
            {
                "iss": JWT_ISSUER,
                "sub": "1",
                "role": "user",
                "sid": str(uuid.uuid4()),
                "iat": now - timedelta(minutes=2),
                "exp": now - timedelta(minutes=1),
            },
            JWT_SECRET_KEY,
            algorithm="HS256",
        )
        expired = anonymous.get(
            "/api/skills",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(expired.status_code, 401)
        anonymous.close()

    def test_password_is_hashed_and_sessions_can_be_revoked(self) -> None:
        with Session(engine) as database_session:
            user = database_session.exec(
                select(User).where(User.email == self.user_email)
            ).one()
            self.assertNotEqual(user.password_hash, "correct horse battery staple")
            self.assertTrue(user.password_hash.startswith("$argon2id$"))

        sessions = self.client.get("/api/users/me/sessions")
        self.assertEqual(sessions.status_code, 200)
        self.assertEqual(len(sessions.json()), 1)
        session_id = sessions.json()[0]["id"]
        revoked = self.client.delete(f"/api/users/me/sessions/{session_id}")
        self.assertEqual(revoked.status_code, 204)
        self.assertEqual(self.client.get("/api/users/me").status_code, 401)

    def test_signup_cannot_assign_admin_role_and_repeated_login_failures_lock_account(self) -> None:
        email = f"role-{uuid.uuid4()}@example.com"
        signup = self.client.post(
            "/api/auth/signup",
            json={
                "email": email,
                "display_name": "Role test",
                "password": "correct horse battery staple",
                "role": "admin",
            },
        )
        self.assertEqual(signup.status_code, 201)
        self.assertEqual(signup.json()["role"], "user")

        for _ in range(5):
            failed_login = self.client.post(
                "/api/auth/login",
                json={"email": email, "password": "wrong password"},
            )
            self.assertEqual(failed_login.status_code, 401)
        locked_login = self.client.post(
            "/api/auth/login",
            json={
                "email": email,
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(locked_login.status_code, 401)

    def test_refresh_rotation_and_logout_revoke_access(self) -> None:
        anonymous = TestClient(app)
        signup = anonymous.post(
            "/api/auth/signup",
            json={
                "email": f"refresh-{uuid.uuid4()}@example.com",
                "display_name": "Refresh test",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(signup.status_code, 201)
        login = anonymous.post(
            "/api/auth/login",
            json={
                "email": signup.json()["email"],
                "password": "correct horse battery staple",
            },
        )
        old_access_token = login.json()["access_token"]
        old_refresh_cookie = anonymous.cookies.get("skillswap_refresh")

        rotated = anonymous.post("/api/auth/refresh")
        self.assertEqual(rotated.status_code, 200, rotated.text)
        new_refresh_cookie = anonymous.cookies.get("skillswap_refresh")
        self.assertNotEqual(new_refresh_cookie, old_refresh_cookie)
        anonymous.cookies.set("skillswap_refresh", old_refresh_cookie)
        reused_refresh = anonymous.post("/api/auth/refresh")
        self.assertEqual(reused_refresh.status_code, 401)
        anonymous.cookies.set("skillswap_refresh", new_refresh_cookie)
        self.assertEqual(
            anonymous.get(
                "/api/users/me",
                headers={"Authorization": f"Bearer {old_access_token}"},
            ).status_code,
            401,
        )
        active_access_token = rotated.json()["access_token"]
        self.assertEqual(
            anonymous.get(
                "/api/users/me",
                headers={"Authorization": f"Bearer {active_access_token}"},
            ).status_code,
            200,
        )

        self.assertEqual(anonymous.post("/api/auth/logout").status_code, 204)
        self.assertEqual(
            anonymous.get(
                "/api/users/me",
                headers={"Authorization": f"Bearer {active_access_token}"},
            ).status_code,
            401,
        )
        anonymous.close()

    def test_profile_update_password_change_and_duplicate_signup(self) -> None:
        duplicate = self.client.post(
            "/api/auth/signup",
            json={
                "email": self.user_email,
                "display_name": "Duplicate",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.patch(
            "/api/users/me",
            json={"display_name": "Ari Updated"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["display_name"], "Ari Updated")

        wrong_current_password = self.client.post(
            "/api/users/me/password",
            json={
                "current_password": "not the current password",
                "new_password": "new correct horse battery",
            },
        )
        self.assertEqual(wrong_current_password.status_code, 400)

        password_change = self.client.post(
            "/api/users/me/password",
            json={
                "current_password": "correct horse battery staple",
                "new_password": "new correct horse battery",
            },
        )
        self.assertEqual(password_change.status_code, 204)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={
                    "email": self.user_email,
                    "password": "correct horse battery staple",
                },
            ).status_code,
            401,
        )
        new_login = self.client.post(
            "/api/auth/login",
            json={
                "email": self.user_email,
                "password": "new correct horse battery",
            },
        )
        self.assertEqual(new_login.status_code, 200)

    def test_session_request_crud_and_skill_delete_cascade(self) -> None:
        skill = self.create_skill()
        response = self.client.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
                "learner_name": "Sam",
                "message": "I want to learn chords.",
            },
        )
        self.assertEqual(response.status_code, 201)
        request_id = response.json()["id"]
        self.assertEqual(response.json()["status"], "pending")

        self.assertEqual(self.client.get("/api/session-requests").json()[0]["id"], request_id)
        self.assertEqual(
            self.client.get(f"/api/session-requests/{request_id}").json()["learner_name"],
            "Sam",
        )

        updated = self.client.patch(
            f"/api/session-requests/{request_id}",
            json={"status": "accepted", "message": "I am available weekends."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "accepted")
        self.assertEqual(updated.json()["message"], "I am available weekends.")

        self.assertEqual(self.client.delete(f"/api/session-requests/{request_id}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/session-requests/{request_id}").status_code, 404)

        another_request = self.client.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
                "learner_name": "Jamie",
                "message": "I want to learn.",
            },
        )
        self.assertEqual(another_request.status_code, 201)
        self.assertEqual(self.client.delete(f"/api/skills/{skill['id']}").status_code, 204)
        self.assertEqual(
            self.client.get(
                f"/api/session-requests/{another_request.json()['id']}"
            ).status_code,
            404,
        )

    def test_request_rejects_missing_skill_and_invalid_status(self) -> None:
        missing_skill = self.client.post(
            "/api/session-requests",
            json={
                "skill_listing_id": 9999,
                "learner_name": "Sam",
                "message": "I want to learn.",
            },
        )
        self.assertEqual(missing_skill.status_code, 404)

        skill = self.create_skill()
        created = self.client.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
                "learner_name": "Sam",
                "message": "I want to learn.",
            },
        )
        invalid_status = self.client.patch(
            f"/api/session-requests/{created.json()['id']}",
            json={"status": "scheduled"},
        )
        self.assertEqual(invalid_status.status_code, 422)

    def test_records_persist_across_app_restart(self) -> None:
        skill = self.create_skill()
        self.client.close()
        with TestClient(app) as client:
            response = client.get(
                f"/api/skills/{skill['id']}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Beginner guitar")


def tearDownModule() -> None:
    engine.dispose()
    TEST_DATABASE_DIR.cleanup()


if __name__ == "__main__":
    unittest.main()
