import argparse
import os
import sys
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.exc import SQLAlchemyError


CONFIRMATION = "CREATE_OR_REUSE_SKILLSWAP_DEMO_DATA"
GROUP_NAME_DEFAULT = "SkillSwap final demo group"
SAMPLE_SKILL_TITLE = "Demo: Introduction to Python"


@dataclass(frozen=True)
class DemoAccount:
    email: str
    display_name: str
    role: str
    password: str | None = field(default=None, repr=False)


def _read_configuration() -> tuple[list[DemoAccount], str]:
    from pydantic import ValidationError

    from auth import SignUpInput

    account_specs = (
        ("DEMO_ADMIN_1", "Admin Demo One", "admin"),
        ("DEMO_ADMIN_2", "Admin Demo Two", "admin"),
        ("DEMO_MEMBER_1", "Member Demo One", "user"),
        ("DEMO_MEMBER_2", "Member Demo Two", "user"),
        ("DEMO_MEMBER_3", "Member Demo Three", "user"),
    )
    accounts = []
    for prefix, display_name, role in account_specs:
        raw_email = os.getenv(f"{prefix}_EMAIL", "").strip()
        if not raw_email:
            raise ValueError(f"Set {prefix}_EMAIL in the process environment.")
        password = os.getenv(f"{prefix}_PASSWORD") or None
        try:
            account = SignUpInput(
                email=raw_email,
                display_name=display_name,
                password=password or "unused-placeholder-password",
            )
        except ValidationError as error:
            fields = {str(issue["loc"][0]) for issue in error.errors()}
            if "password" in fields:
                raise ValueError(
                    f"{prefix}_PASSWORD must be between 12 and 128 characters."
                ) from None
            raise ValueError(f"{prefix}_EMAIL must be a valid email address.") from None
        accounts.append(
            DemoAccount(
                email=account.email,
                display_name=display_name,
                role=role,
                password=password,
            )
        )

    if len({account.email for account in accounts}) != len(accounts):
        raise ValueError("Each demo account must use a distinct email address.")
    group_name = os.getenv("DEMO_GROUP_NAME", GROUP_NAME_DEFAULT).strip()
    if not group_name or len(group_name) > 100:
        raise ValueError("DEMO_GROUP_NAME must be between 1 and 100 characters.")
    return accounts, group_name


def _validate_environment(apply: bool) -> None:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url or urlsplit(database_url).scheme not in {
        "postgres",
        "postgresql",
        "postgresql+psycopg",
    }:
        raise ValueError("Set DATABASE_URL to the persistent PostgreSQL database.")

    for name in ("JWT_SECRET_KEY", "PASSWORD_PEPPER"):
        value = os.getenv(name, "")
        if len(value) < 32:
            raise ValueError(f"Set {name} to the matching deployment secret (at least 32 characters).")

    if apply and os.getenv("DEMO_SEED_CONFIRM") != CONFIRMATION:
        raise ValueError(
            f"Set DEMO_SEED_CONFIRM={CONFIRMATION} to confirm database writes."
        )


def provision_demo(
    session: Any,
    accounts: list[DemoAccount],
    group_name: str,
    *,
    apply: bool,
) -> dict[str, Any]:
    from auth import User, hash_password
    from models import (
        GroupMembership,
        GroupSkillAssignment,
        SkillGroup,
        SkillListing,
    )
    from permissions import ROLE_ADMIN
    from sqlmodel import select

    users: list[User | None] = []
    for account in accounts:
        user = session.exec(select(User).where(User.email == account.email)).first()
        if user is not None and (
            user.role != account.role or not user.is_active or user.is_banned
        ):
            raise ValueError(
                "A configured demo account already exists with a different role or inactive status."
            )
        users.append(user)

    missing_accounts = [
        account for account, user in zip(accounts, users) if user is None
    ]
    if apply and any(not account.password for account in missing_accounts):
        raise ValueError(
            "Set a password environment variable for each demo account that does not exist yet."
        )

    if apply:
        for index, (account, user) in enumerate(zip(accounts, users)):
            if user is None:
                user = User(
                    email=account.email,
                    display_name=account.display_name,
                    password_hash=hash_password(account.password or ""),
                    role=account.role,
                )
                session.add(user)
                users[index] = user
        session.flush()

    admin = users[0]
    group: SkillGroup | None = None
    skill: SkillListing | None = None
    membership_specs = (
        (True, False, False),
        (False, True, False),
        (False, False, True),
    )

    if admin is not None:
        if admin.role != ROLE_ADMIN:
            raise ValueError("The first configured demo account must be an administrator.")
        groups = list(
            session.exec(
                select(SkillGroup).where(
                    SkillGroup.owner_id == admin.id,
                    SkillGroup.name == group_name,
                )
            ).all()
        )
        if len(groups) > 1:
            raise ValueError("Multiple groups match the configured demo group; no changes made.")
        group = groups[0] if groups else None
        if apply and group is None:
            group = SkillGroup(name=group_name, owner_id=admin.id)
            session.add(group)
            session.flush()

        if group is not None:
            for account, user, capabilities in zip(
                accounts[2:], users[2:], membership_specs
            ):
                if user is None:
                    continue
                membership = session.exec(
                    select(GroupMembership).where(
                        GroupMembership.group_id == group.id,
                        GroupMembership.user_id == user.id,
                    )
                ).first()
                expected = dict(
                    zip(("can_create", "can_edit", "can_assign"), capabilities)
                )
                if membership is not None and any(
                    getattr(membership, name) != enabled
                    for name, enabled in expected.items()
                ):
                    raise ValueError(
                        "A configured demo group member already has different permissions; no changes made."
                    )
                if apply and membership is None:
                    session.add(
                        GroupMembership(
                            group_id=group.id,
                            user_id=user.id,
                            **expected,
                        )
                    )

            skills = list(
                session.exec(
                    select(SkillListing).where(
                        SkillListing.owner_id == admin.id,
                        SkillListing.title == SAMPLE_SKILL_TITLE,
                    )
                ).all()
            )
            if len(skills) > 1:
                raise ValueError("Multiple sample listings match; no changes made.")
            skill = skills[0] if skills else None
            if skill is not None:
                assignment = session.get(GroupSkillAssignment, skill.id)
                if assignment is None or assignment.group_id != group.id:
                    raise ValueError(
                        "The sample listing already exists outside the configured group; no changes made."
                    )
            elif apply:
                skill = SkillListing(
                    owner_id=admin.id,
                    teacher_name=admin.display_name,
                    title=SAMPLE_SKILL_TITLE,
                    description="A sample listing for the final demonstration.",
                    category="Technology",
                )
                session.add(skill)
                session.flush()
                session.add(
                    GroupSkillAssignment(
                        skill_listing_id=skill.id,
                        group_id=group.id,
                        assigned_by_user_id=admin.id,
                    )
                )

    return {
        "users": [
            {"id": user.id if user is not None else None, "role": account.role}
            for account, user in zip(accounts, users)
        ],
        "group_id": group.id if group is not None else None,
        "group_name": group_name,
        "sample_skill_id": skill.id if skill is not None else None,
        "missing_users": len(missing_accounts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or reuse SkillSwap demo accounts and mixed-permission sample data."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Without this flag the command only inspects and reports.",
    )
    args = parser.parse_args()

    try:
        _validate_environment(args.apply)
        accounts, group_name = _read_configuration()
        from database import create_db_and_tables, engine
        from sqlmodel import Session

        if args.apply:
            create_db_and_tables()
        with Session(engine) as session:
            result = provision_demo(session, accounts, group_name, apply=args.apply)
            if args.apply:
                session.commit()
        print("Demo accounts (IDs and roles only):")
        for account in result["users"]:
            value = account["id"] if account["id"] is not None else "created on apply"
            print(f"  ID {value} - {account['role']}")
        group_id = result["group_id"] if result["group_id"] is not None else "created on apply"
        skill_id = (
            result["sample_skill_id"]
            if result["sample_skill_id"] is not None
            else "created on apply"
        )
        print(f"Group: {result['group_name']} (ID {group_id})")
        print(f"Sample listing: {SAMPLE_SKILL_TITLE} (ID {skill_id})")
        print("Permissions: member 1=create, member 2=edit, member 3=assign.")
        if args.apply:
            print("Demo data provisioned; existing accounts and matching demo data were reused.")
        else:
            print("Dry run only; no database changes were made.")
            print(f"Supply --apply and DEMO_SEED_CONFIRM={CONFIRMATION} to write.")
        return 0
    except (ValueError, RuntimeError) as error:
        print(f"Demo provisioning stopped: {error}", file=sys.stderr)
        return 2
    except SQLAlchemyError:
        print(
            "Demo provisioning stopped because the database operation failed. "
            "Check the environment and database availability; error details are suppressed "
            "to avoid exposing connection credentials.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
