import os
import sys
import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
TEST_DATABASE_PATH = Path(TEST_DATABASE_DIR.name) / "skillswap-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"
os.environ["JWT_SECRET_KEY"] = "test-only-jwt-secret-key-not-for-deployments"
os.environ["PASSWORD_PEPPER"] = "test-only-password-pepper-not-for-deployments"

from database import engine  # noqa: E402
from auth import JWT_ISSUER, JWT_SECRET_KEY, RefreshSession, User  # noqa: E402
from migrations import migrate_resource_ownership  # noqa: E402
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
        self.user_id = login.json()["user"]["id"]
        self.client.headers.update({"Authorization": f"Bearer {self.access_token}"})

    def tearDown(self) -> None:
        self.client.close()

    def create_member(self) -> tuple[TestClient, dict]:
        client = TestClient(app)
        email = f"member-{uuid.uuid4()}@example.com"
        signup = client.post(
            "/api/auth/signup",
            json={
                "email": email,
                "display_name": "Casey",
                "password": "correct horse battery staple",
            },
        )
        self.assertEqual(signup.status_code, 201, signup.text)
        login = client.post(
            "/api/auth/login",
            json={"email": email, "password": "correct horse battery staple"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        client.headers.update({"Authorization": f"Bearer {login.json()['access_token']}"})
        return client, login.json()["user"]

    def create_skill(self, client: TestClient | None = None, **extra) -> dict:
        response = (client or self.client).post(
            "/api/skills",
            json={
                "teacher_name": "Ari",
                "title": "Beginner guitar",
                "description": "Learn basic chords.",
                "category": "Music",
                **extra,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def create_group(self, name: str = "Study group", client: TestClient | None = None) -> dict:
        response = (client or self.client).post("/api/groups", json={"name": name})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def add_group_member(
        self,
        group_id: int,
        user: dict,
        *,
        client: TestClient | None = None,
        can_create: bool = False,
        can_edit: bool = False,
        can_assign: bool = False,
    ) -> dict:
        response = (client or self.client).post(
            f"/api/groups/{group_id}/members",
            json={
                "email": user["email"],
                "can_create": can_create,
                "can_edit": can_edit,
                "can_assign": can_assign,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
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

    def test_skill_listing_reads_are_shared_but_writes_are_owner_only(self) -> None:
        skill = self.create_skill(owner_id=99999)
        self.assertEqual(skill["owner_id"], self.user_id)
        other_client, _other_user = self.create_member()
        try:
            self.assertEqual(other_client.get("/api/skills").json()[0]["id"], skill["id"])
            self.assertEqual(other_client.get(f"/api/skills/{skill['id']}").status_code, 200)
            self.assertEqual(
                other_client.patch(
                    f"/api/skills/{skill['id']}",
                    json={"title": "Hijacked listing"},
                ).status_code,
                404,
            )
            self.assertEqual(
                other_client.delete(f"/api/skills/{skill['id']}").status_code,
                404,
            )
        finally:
            other_client.close()

    def test_group_settings_and_membership_are_owner_only(self) -> None:
        group = self.create_group("  Guitar circle  ")
        self.assertEqual(group["name"], "Guitar circle")
        member_client, member = self.create_member()
        outsider_client, _outsider = self.create_member()
        try:
            self.assertEqual(member_client.get("/api/groups").json(), [])
            membership = self.add_group_member(group["id"], member)
            self.assertEqual(membership["display_name"], "Casey")
            self.assertFalse(membership["can_create"])
            self.assertFalse(membership["can_edit"])
            self.assertFalse(membership["can_assign"])
            group_skill = self.client.post(
                f"/api/groups/{group['id']}/skills",
                json={
                    "teacher_name": "Ari",
                    "title": "Shared guitar",
                    "description": "A group-owned listing.",
                    "category": "Music",
                },
            )
            self.assertEqual(group_skill.status_code, 201, group_skill.text)

            visible_groups = member_client.get("/api/groups").json()
            self.assertEqual([item["id"] for item in visible_groups], [group["id"]])
            self.assertEqual(
                member_client.get(f"/api/groups/{group['id']}").status_code,
                200,
            )
            member_rows = member_client.get(f"/api/groups/{group['id']}/members").json()
            self.assertEqual({row["user_id"] for row in member_rows}, {self.user_id, member["id"]})
            self.assertNotIn("email", member_rows[0])

            self.assertEqual(outsider_client.get("/api/groups").json(), [])
            self.assertEqual(
                outsider_client.get(f"/api/groups/{group['id']}").status_code,
                404,
            )
            self.assertEqual(
                outsider_client.get(f"/api/groups/{group['id']}/members").status_code,
                404,
            )
            self.assertEqual(
                member_client.patch(
                    f"/api/groups/{group['id']}",
                    json={"name": "Member rename"},
                ).status_code,
                403,
            )
            self.assertEqual(
                member_client.post(
                    f"/api/groups/{group['id']}/members",
                    json={"email": self.user_email},
                ).status_code,
                403,
            )
            self.assertEqual(
                member_client.delete(
                    f"/api/groups/{group['id']}/members/{self.user_id}"
                ).status_code,
                403,
            )
            self.assertEqual(
                member_client.delete(f"/api/groups/{group['id']}").status_code,
                403,
            )
            renamed = self.client.patch(
                f"/api/groups/{group['id']}",
                json={"name": "Owner rename"},
            )
            self.assertEqual(renamed.status_code, 200)
            self.assertEqual(renamed.json()["name"], "Owner rename")
            self.assertEqual(
                self.client.patch(
                    f"/api/groups/{group['id']}/members/{member['id']}",
                    json={"can_create": True, "can_edit": False, "can_assign": False},
                ).status_code,
                200,
            )
            self.assertEqual(
                self.client.delete(
                    f"/api/groups/{group['id']}/members/{member['id']}"
                ).status_code,
                204,
            )
            self.assertEqual(
                member_client.get(f"/api/groups/{group['id']}").status_code,
                404,
            )
            self.assertEqual(
                self.client.delete(f"/api/groups/{group['id']}").status_code,
                204,
            )
            self.assertEqual(
                self.client.get(f"/api/skills/{group_skill.json()['id']}").status_code,
                200,
            )
        finally:
            member_client.close()
            outsider_client.close()

    def test_group_capabilities_and_group_resource_isolation(self) -> None:
        group = self.create_group("Shared skills")
        member_client, member = self.create_member()
        outsider_client, _outsider = self.create_member()
        try:
            self.add_group_member(group["id"], member, can_assign=True)
            personal_skill = self.create_skill(member_client)
            owner_skill = self.create_skill()

            self.assertEqual(
                member_client.post(
                    f"/api/groups/{group['id']}/skills",
                    json={
                        "teacher_name": "Casey",
                        "title": "Should be denied",
                        "description": "No create capability.",
                        "category": "Music",
                    },
                ).status_code,
                403,
            )
            self.assertEqual(
                member_client.patch(
                    f"/api/groups/{group['id']}/skills/{personal_skill['id']}",
                    json={"title": "Should be denied"},
                ).status_code,
                403,
            )
            self.assertEqual(
                member_client.post(
                    f"/api/groups/{group['id']}/skills/{owner_skill['id']}/assignment"
                ).status_code,
                404,
            )
            assigned = member_client.post(
                f"/api/groups/{group['id']}/skills/{personal_skill['id']}/assignment"
            )
            self.assertEqual(assigned.status_code, 200, assigned.text)
            self.assertEqual(
                [row["id"] for row in member_client.get(f"/api/groups/{group['id']}/skills").json()],
                [personal_skill["id"]],
            )
            self.assertEqual(
                self.client.get(f"/api/skills/{personal_skill['id']}").status_code,
                404,
            )
            self.assertNotIn(
                personal_skill["id"],
                [row["id"] for row in self.client.get("/api/skills").json()],
            )
            self.assertEqual(
                self.client.post(
                    "/api/session-requests",
                    json={
                        "skill_listing_id": personal_skill["id"],
                        "message": "Try to reach a private listing.",
                    },
                ).status_code,
                404,
            )
            self.assertEqual(
                outsider_client.get(f"/api/groups/{group['id']}/skills").status_code,
                404,
            )
            self.assertEqual(
                outsider_client.patch(
                    f"/api/groups/{group['id']}/skills/{personal_skill['id']}",
                    json={"title": "Outsider edit"},
                ).status_code,
                404,
            )

            self.assertEqual(
                self.client.patch(
                    f"/api/groups/{group['id']}/members/{member['id']}",
                    json={"can_create": False, "can_edit": True, "can_assign": True},
                ).status_code,
                200,
            )
            updated = member_client.patch(
                f"/api/groups/{group['id']}/skills/{personal_skill['id']}",
                json={"title": "Group guitar"},
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(updated.json()["title"], "Group guitar")

            second_group_owner, second_owner = self.create_member()
            try:
                second_group = self.create_group("Private group", client=second_group_owner)
                private_listing = second_group_owner.post(
                    f"/api/groups/{second_group['id']}/skills",
                    json={
                        "teacher_name": "Jordan",
                        "title": "Private piano",
                        "description": "Visible only in the private group.",
                        "category": "Music",
                    },
                )
                self.assertEqual(private_listing.status_code, 201, private_listing.text)
                private_skill_id = private_listing.json()["id"]
                self.assertNotIn(
                    second_group["id"],
                    [item["id"] for item in self.client.get("/api/groups").json()],
                )
                self.assertEqual(
                    self.client.get(f"/api/groups/{second_group['id']}/skills").status_code,
                    404,
                )
                self.assertEqual(
                    member_client.get(f"/api/groups/{second_group['id']}/skills").status_code,
                    404,
                )
                self.assertEqual(
                    self.client.get(f"/api/skills/{private_skill_id}").status_code,
                    404,
                )
                self.assertEqual(
                    member_client.patch(
                        f"/api/groups/{group['id']}/skills/{private_skill_id}",
                        json={"title": "Cross-group modification"},
                    ).status_code,
                    404,
                )
            finally:
                second_group_owner.close()
        finally:
            member_client.close()
            outsider_client.close()

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
        for path in (
            "/api/groups",
            "/api/groups/{group_id}",
            "/api/groups/{group_id}/members",
            "/api/groups/{group_id}/members/{user_id}",
            "/api/groups/{group_id}/skills",
            "/api/groups/{group_id}/skills/{skill_id}",
            "/api/groups/{group_id}/skills/{skill_id}/assignment",
        ):
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
        learner, learner_user = self.create_member()
        response = learner.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
                "learner_name": "Impersonated name",
                "learner_id": self.user_id,
                "message": "I want to learn chords.",
            },
        )
        self.assertEqual(response.status_code, 201)
        request_id = response.json()["id"]
        self.assertEqual(response.json()["status"], "pending")
        self.assertEqual(response.json()["learner_id"], learner_user["id"])
        self.assertEqual(response.json()["learner_name"], "Casey")

        self.assertEqual(self.client.get("/api/session-requests").json()[0]["id"], request_id)
        self.assertEqual(learner.get("/api/session-requests").json()[0]["id"], request_id)
        self.assertEqual(
            learner.get(f"/api/session-requests/{request_id}").json()["learner_name"],
            "Casey",
        )

        updated = learner.patch(
            f"/api/session-requests/{request_id}",
            json={"message": "I am available weekends."},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["message"], "I am available weekends.")
        self.assertEqual(
            learner.patch(
                f"/api/session-requests/{request_id}",
                json={"status": "accepted"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/session-requests/{request_id}",
                json={"message": "Owner cannot change learner message."},
            ).status_code,
            403,
        )
        owner_update = self.client.patch(
            f"/api/session-requests/{request_id}",
            json={"status": "accepted"},
        )
        self.assertEqual(owner_update.status_code, 200)
        self.assertEqual(owner_update.json()["status"], "accepted")

        outsider, _ = self.create_member()
        try:
            self.assertEqual(outsider.get("/api/session-requests").json(), [])
            self.assertEqual(
                outsider.get(f"/api/session-requests/{request_id}").status_code,
                404,
            )
            self.assertEqual(
                outsider.delete(f"/api/session-requests/{request_id}").status_code,
                404,
            )
        finally:
            outsider.close()

        self.assertEqual(learner.delete(f"/api/session-requests/{request_id}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/session-requests/{request_id}").status_code, 404)

        another_request = learner.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
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
        learner.close()

    def test_legacy_records_migrate_without_being_claimed(self) -> None:
        legacy_engine = create_engine("sqlite://")
        try:
            with legacy_engine.begin() as connection:
                connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
                connection.execute(
                    text(
                        "CREATE TABLE skill_listings ("
                        "id INTEGER PRIMARY KEY, teacher_name TEXT NOT NULL, "
                        "title TEXT NOT NULL, description TEXT NOT NULL, "
                        "category TEXT NOT NULL, created_at DATETIME NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "CREATE TABLE session_requests ("
                        "id INTEGER PRIMARY KEY, skill_listing_id INTEGER NOT NULL, "
                        "learner_name TEXT NOT NULL, message TEXT NOT NULL, "
                        "status TEXT NOT NULL, created_at DATETIME NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO skill_listings VALUES "
                        "(1, 'Legacy teacher', 'Legacy skill', 'Description', 'Music', '2025-01-01')"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO session_requests VALUES "
                        "(1, 1, 'Legacy learner', 'Message', 'pending', '2025-01-02')"
                    )
                )

            migrate_resource_ownership(legacy_engine)
            migrate_resource_ownership(legacy_engine)
            with legacy_engine.connect() as connection:
                skill = connection.execute(
                    text("SELECT title, owner_id FROM skill_listings WHERE id = 1")
                ).one()
                request = connection.execute(
                    text("SELECT message, learner_id FROM session_requests WHERE id = 1")
                ).one()
            self.assertEqual(skill, ("Legacy skill", None))
            self.assertEqual(request, ("Message", None))
        finally:
            legacy_engine.dispose()

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

        own_skill = self.create_skill()
        self.assertEqual(
            self.client.post(
                "/api/session-requests",
                json={
                    "skill_listing_id": own_skill["id"],
                    "message": "I want to learn.",
                },
            ).status_code,
            403,
        )

        owner, _owner_user = self.create_member()
        skill = self.create_skill(owner)
        created = self.client.post(
            "/api/session-requests",
            json={
                "skill_listing_id": skill["id"],
                "learner_name": "Sam",
                "message": "I want to learn.",
            },
        )
        owner.close()
        invalid_status = self.client.patch(
            f"/api/session-requests/{created.json()['id']}",
            json={"status": "scheduled"},
        )
        self.assertEqual(invalid_status.status_code, 422)

    def test_records_persist_across_app_restart(self) -> None:
        group = self.create_group("Persistent group")
        member_client, member = self.create_member()
        self.add_group_member(group["id"], member)
        group_skill = self.client.post(
            f"/api/groups/{group['id']}/skills",
            json={
                "teacher_name": "Ari",
                "title": "Persistent group skill",
                "description": "Stored in the local database.",
                "category": "Music",
            },
        )
        self.assertEqual(group_skill.status_code, 201, group_skill.text)
        member_headers = {"Authorization": member_client.headers["authorization"]}
        member_client.close()
        self.client.close()
        with TestClient(app) as client:
            group_response = client.get(
                f"/api/groups/{group['id']}",
                headers={"Authorization": f"Bearer {self.access_token}"},
            )
            listings_response = client.get(
                f"/api/groups/{group['id']}/skills",
                headers=member_headers,
            )
        self.assertEqual(group_response.status_code, 200)
        self.assertEqual(group_response.json()["name"], "Persistent group")
        self.assertEqual(listings_response.status_code, 200)
        self.assertEqual(listings_response.json()[0]["title"], "Persistent group skill")


def tearDownModule() -> None:
    engine.dispose()
    TEST_DATABASE_DIR.cleanup()


if __name__ == "__main__":
    unittest.main()
