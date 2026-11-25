import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, SQLModel, create_engine, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-key-not-for-deployments")
os.environ.setdefault("PASSWORD_PEPPER", "test-only-password-pepper-not-for-deployments")

from auth import User  # noqa: E402
from models import GroupMembership, SkillGroup, SkillListing  # noqa: E402
from seed_demo import DemoAccount, _read_configuration, _validate_environment, provision_demo  # noqa: E402


class DemoSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.accounts = [
            DemoAccount("admin1@example.com", "Admin Demo One", "admin", "test-password-one"),
            DemoAccount("admin2@example.com", "Admin Demo Two", "admin", "test-password-two"),
            DemoAccount("member1@example.com", "Member Demo One", "user", "test-password-three"),
            DemoAccount("member2@example.com", "Member Demo Two", "user", "test-password-four"),
            DemoAccount("member3@example.com", "Member Demo Three", "user", "test-password-five"),
        ]

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_dry_run_does_not_create_any_data(self) -> None:
        with Session(self.engine) as session:
            result = provision_demo(
                session,
                self.accounts,
                "Demo group",
                apply=False,
            )
            self.assertEqual(result["missing_users"], 5)
            self.assertEqual(session.exec(select(User)).all(), [])

    def test_apply_and_repeat_reuses_accounts_group_and_sample_data(self) -> None:
        with patch("auth.hash_password", return_value="test-hash"):
            with Session(self.engine) as session:
                first = provision_demo(
                    session,
                    self.accounts,
                    "Demo group",
                    apply=True,
                )
                session.commit()
            with Session(self.engine) as session:
                second = provision_demo(
                    session,
                    self.accounts,
                    "Demo group",
                    apply=True,
                )
                session.commit()
                self.assertEqual(first["users"], second["users"])
                self.assertEqual(first["group_id"], second["group_id"])
                self.assertEqual(first["sample_skill_id"], second["sample_skill_id"])
                self.assertEqual(len(session.exec(select(User)).all()), 5)
                self.assertEqual(len(session.exec(select(SkillGroup)).all()), 1)
                self.assertEqual(len(session.exec(select(SkillListing)).all()), 1)
                memberships = session.exec(select(GroupMembership)).all()
                self.assertEqual(
                    [
                        (item.can_create, item.can_edit, item.can_assign)
                        for item in memberships
                    ],
                    [(True, False, False), (False, True, False), (False, False, True)],
                )

    def test_existing_account_with_wrong_role_is_not_modified(self) -> None:
        with Session(self.engine) as session:
            existing = User(
                email="admin1@example.com",
                display_name="Existing account",
                password_hash="unchanged",
                role="user",
            )
            session.add(existing)
            session.commit()
            with self.assertRaisesRegex(ValueError, "different role"):
                provision_demo(
                    session,
                    self.accounts,
                    "Demo group",
                    apply=True,
                )
            session.refresh(existing)
            self.assertEqual(existing.role, "user")
            self.assertEqual(existing.password_hash, "unchanged")
            self.assertEqual(len(session.exec(select(User)).all()), 1)

    def test_seed_requires_postgres_and_confirmation_for_writes(self) -> None:
        settings = {
            "DATABASE_URL": "sqlite:///local.db",
            "JWT_SECRET_KEY": "test-only-jwt-secret-key-not-for-deployments",
            "PASSWORD_PEPPER": "test-only-password-pepper-not-for-deployments",
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "persistent PostgreSQL"):
                _validate_environment(apply=False)

        settings["DATABASE_URL"] = "postgresql://test.invalid/database"
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "DEMO_SEED_CONFIRM"):
                _validate_environment(apply=True)

    def test_invalid_password_is_not_in_configuration_error(self) -> None:
        settings = {
            "DEMO_ADMIN_1_EMAIL": "admin1@example.com",
            "DEMO_ADMIN_1_PASSWORD": "do-not-print-this-password",
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaises(ValueError) as raised:
                _read_configuration()
        self.assertNotIn("do-not-print-this-password", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
