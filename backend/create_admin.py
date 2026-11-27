import argparse
import os
import sys
from dataclasses import dataclass, field
from urllib.parse import urlsplit


CONFIRMATION = "CREATE_SKILLSWAP_ADMIN_ACCOUNT"


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "Admin bootstrap refused: invalid command-line arguments.\n")


@dataclass(frozen=True)
class AdminAccount:
    email: str = field(repr=False)
    display_name: str = field(repr=False)
    password: str = field(repr=False)


def _validate_environment(*, apply: bool) -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    try:
        parsed_url = urlsplit(database_url)
        is_postgres = (
            parsed_url.scheme in {"postgres", "postgresql", "postgresql+psycopg"}
            and parsed_url.hostname is not None
            and parsed_url.path not in {"", "/"}
        )
    except ValueError:
        is_postgres = False
    if not is_postgres:
        raise ValueError("Set DATABASE_URL to a valid persistent PostgreSQL database.")

    for name in ("JWT_SECRET_KEY", "PASSWORD_PEPPER"):
        if len(os.getenv(name, "")) < 32:
            raise ValueError(f"Set {name} to the matching deployment secret (at least 32 characters).")

    if apply and os.getenv("ADMIN_BOOTSTRAP_CONFIRM") != CONFIRMATION:
        raise ValueError(
            f"Set ADMIN_BOOTSTRAP_CONFIRM={CONFIRMATION} to confirm database writes."
        )


def _read_configuration() -> AdminAccount:
    values = {
        "email": os.getenv("ADMIN_EMAIL", ""),
        "display_name": os.getenv("ADMIN_DISPLAY_NAME", ""),
        "password": os.getenv("ADMIN_PASSWORD", ""),
    }
    if not all(values.values()):
        raise ValueError("Set ADMIN_EMAIL, ADMIN_DISPLAY_NAME, and ADMIN_PASSWORD in the process environment.")
    if len(os.getenv("JWT_SECRET_KEY", "")) < 32 or len(os.getenv("PASSWORD_PEPPER", "")) < 32:
        raise ValueError("Set JWT_SECRET_KEY and PASSWORD_PEPPER before validating admin credentials.")

    from pydantic import ValidationError

    from auth import SignUpInput

    try:
        validated = SignUpInput(**values)
    except ValidationError:
        raise ValueError(
            "ADMIN_EMAIL, ADMIN_DISPLAY_NAME, or ADMIN_PASSWORD failed signup validation."
        ) from None
    return AdminAccount(
        email=validated.email,
        display_name=validated.display_name,
        password=validated.password,
    )


def _normalized_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def provision_admin(session, account: AdminAccount, *, apply: bool) -> str:
    from sqlalchemy import func
    from sqlmodel import select

    from auth import User, hash_password
    from permissions import ROLE_ADMIN

    matches = list(
        session.exec(select(User).where(func.lower(User.email) == account.email)).all()
    )
    if len(matches) > 1:
        raise ValueError("Multiple accounts match this email; no changes made.")
    existing = matches[0] if matches else None
    if existing is not None:
        if existing.role != ROLE_ADMIN or not existing.is_active or existing.is_banned:
            raise ValueError(
                "An account already exists for this email but is not an active, unbanned administrator; no changes made."
            )
        return "reused"

    if not apply:
        return "would_create"

    session.add(
        User(
            email=account.email,
            display_name=account.display_name,
            password_hash=hash_password(account.password),
            role=ROLE_ADMIN,
            is_active=True,
            is_banned=False,
        )
    )
    session.flush()
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = _SafeArgumentParser(
        description="Safely create or reuse one SkillSwap administrator account."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write changes (also requires ADMIN_BOOTSTRAP_CONFIRM)",
    )
    args, unexpected_args = parser.parse_known_args(argv)
    if unexpected_args:
        print(
            "Admin bootstrap refused: unexpected command-line arguments; provide credentials through environment variables.",
            file=sys.stderr,
        )
        return 2

    try:
        _validate_environment(apply=args.apply)
        account = _read_configuration()

        from sqlalchemy import create_engine
        from sqlalchemy.exc import SQLAlchemyError
        from sqlmodel import Session

        database_url = _normalized_database_url(os.environ["DATABASE_URL"].strip())
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with Session(engine) as session:
                with session.begin():
                    outcome = provision_admin(session, account, apply=args.apply)
        finally:
            engine.dispose()
    except ValueError as error:
        print(f"Admin bootstrap refused: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print("Database operation failed; no changes were committed.", file=sys.stderr)
        return 1

    if outcome == "created":
        print("Administrator account created.")
    elif outcome == "reused":
        print("Existing administrator account reused; no changes made.")
    else:
        print("Dry run: an administrator account would be created; no changes made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
