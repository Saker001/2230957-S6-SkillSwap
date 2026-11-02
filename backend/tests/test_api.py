import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
TEST_DATABASE_DIR = tempfile.TemporaryDirectory()
TEST_DATABASE_PATH = Path(TEST_DATABASE_DIR.name) / "skillswap-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE_PATH.as_posix()}"

from database import engine  # noqa: E402
from main import app  # noqa: E402


class SkillSwapApiTests(unittest.TestCase):
    def setUp(self) -> None:
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)
        self.client = TestClient(app)

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
            response = client.get(f"/api/skills/{skill['id']}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Beginner guitar")


def tearDownModule() -> None:
    engine.dispose()
    TEST_DATABASE_DIR.cleanup()


if __name__ == "__main__":
    unittest.main()
