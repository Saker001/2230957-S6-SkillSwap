import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Field, Session, SQLModel


class AuditEvent(SQLModel, table=True):
    __tablename__ = "audit_events"

    id: int | None = Field(default=None, primary_key=True)
    actor_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        ondelete="SET NULL",
    )
    action: str = Field(max_length=80, index=True)
    target_type: str = Field(max_length=40, index=True)
    target_id: str = Field(max_length=80, index=True)
    details: str = Field(default="{}", max_length=4000)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True,
    )


def record_admin_action(
    session: Session,
    actor_id: int,
    action: str,
    target_type: str,
    target_id: int | str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id),
            details=json.dumps(details or {}, separators=(",", ":"), sort_keys=True),
        )
    )
