import contextlib
import io
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

from auth import User, verify_password  # noqa: E402
from create_admin import (  # noqa: E402
    AdminAccount,
    CONFIRMATION,
    _read_configuration,
    _validate_environment,
    main,
    provision_admin,
)


class AdminBootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite://")
        SQLModel.metadata.create_all(self.engine)
        self.account = AdminAccount(
            email="admin@example.com",
            display_name="SkillSwap Admin",
            password="secure-test-password-123",
        )

    def tearDown(self) -> None:
        self.engine.dispose()

    def test_dry_run_does_not_write(self) -> None:
        with Session(self.engine) as session:
            self.assertEqual(provision_admin(session, self.account, apply=False), "would_create")
            self.assertEqual(session.exec(select(User)).all(), [])

    def test_apply_creates_active_admin_with_argon2_password(self) -> None:
        with Session(self.engine) as session:
            self.assertEqual(provision_admin(session, self.account, apply=True), "created")
            session.commit()
            user = session.exec(select(User)).one()
            self.assertEqual(user.role, "admin")
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_banned)
            self.assertTrue(user.password_hash.startswith("$argon2id$"))
            self.assertTrue(verify_password(self.account.password, user.password_hash))

    def test_repeat_run_reuses_admin_without_changing_password(self) -> None:
        with Session(self.engine) as session:
            provision_admin(session, self.account, apply=True)
            session.commit()
            original_hash = session.exec(select(User)).one().password_hash

        with Session(self.engine) as session:
            self.assertEqual(provision_admin(session, self.account, apply=True), "reused")
            session.commit()
            user = session.exec(select(User)).one()
            self.assertEqual(user.password_hash, original_hash)
            self.assertEqual(len(session.exec(select(User)).all()), 1)

    def test_existing_regular_account_is_not_promoted_or_modified(self) -> None:
        with Session(self.engine) as session:
            existing = User(
                email=self.account.email,
                display_name="Existing member",
                password_hash="unchanged-hash",
                role="user",
            )
            session.add(existing)
            session.commit()
            with self.assertRaisesRegex(ValueError, "not an active, unbanned administrator"):
                provision_admin(session, self.account, apply=True)
            session.refresh(existing)
            self.assertEqual(existing.role, "user")
            self.assertEqual(existing.password_hash, "unchanged-hash")

    def test_non_postgres_database_and_missing_confirmation_are_rejected(self) -> None:
        settings = {
            "DATABASE_URL": "sqlite:///local.db",
            "JWT_SECRET_KEY": "test-only-jwt-secret-key-not-for-deployments",
            "PASSWORD_PEPPER": "test-only-password-pepper-not-for-deployments",
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "PostgreSQL"):
                _validate_environment(apply=False)

        settings["DATABASE_URL"] = "postgresql://user:pass@example.com/skillswap"
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaisesRegex(ValueError, "ADMIN_BOOTSTRAP_CONFIRM"):
                _validate_environment(apply=True)

    def test_invalid_password_is_not_in_cli_error_output(self) -> None:
        secret_password = "no-leak"
        settings = {
            "DATABASE_URL": "postgresql://user:db-secret@example.com/skillswap",
            "JWT_SECRET_KEY": "test-only-jwt-secret-key-not-for-deployments",
            "PASSWORD_PEPPER": "test-only-password-pepper-not-for-deployments",
            "ADMIN_BOOTSTRAP_CONFIRM": CONFIRMATION,
            "ADMIN_EMAIL": "admin@example.com",
            "ADMIN_DISPLAY_NAME": "Admin",
            "ADMIN_PASSWORD": secret_password,
        }
        stderr = io.StringIO()
        with patch.dict(os.environ, settings, clear=True), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["--apply"]), 2)
        self.assertNotIn(secret_password, stderr.getvalue())
        self.assertNotIn("db-secret", stderr.getvalue())

    def test_command_line_credentials_are_not_echoed(self) -> None:
        secret_password = "must-not-appear-in-arguments-output"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["--password", secret_password]), 2)
        self.assertNotIn(secret_password, stderr.getvalue())

    def test_invalid_signup_fields_are_not_echoed_by_configuration_error(self) -> None:
        secret_password = "no-leak"
        settings = {
            "JWT_SECRET_KEY": "test-only-jwt-secret-key-not-for-deployments",
            "PASSWORD_PEPPER": "test-only-password-pepper-not-for-deployments",
            "ADMIN_EMAIL": "not-an-email",
            "ADMIN_DISPLAY_NAME": " ",
            "ADMIN_PASSWORD": secret_password,
        }
        with patch.dict(os.environ, settings, clear=True):
            with self.assertRaises(ValueError) as raised:
                _read_configuration()
        self.assertNotIn(secret_password, str(raised.exception))


if __name__ == "__main__":
    unittest.main()
