import csv
import io
import json
from datetime import datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_validator
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select

from audit import AuditEvent, record_admin_action
from auth import (
    RefreshSession,
    SessionRead,
    User,
    UserRead,
    utc_now,
)
from database import get_session
from models import (
    GroupMembership,
    SessionRequest,
    SessionRequestRead,
    SkillGroup,
    SkillGroupRead,
    SkillListing,
    SkillListingRead,
)
from authorization import require_permission
from permissions import PERMISSION_ADMIN, ROLE_ADMIN

router = APIRouter(prefix="/api/admin", tags=["admin"])
DatabaseSession = Annotated[Session, Depends(get_session)]
AdminActor = Annotated[User, Depends(require_permission(PERMISSION_ADMIN))]


class AdminAuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: int | None
    action: str
    target_type: str
    target_id: str
    details: dict[str, Any]
    ip_address: str | None
    user_agent: str | None
    created_at: datetime


class FailedLoginInsight(BaseModel):
    value: str
    count: int
    last_seen: datetime


class FailedLoginSummary(BaseModel):
    by_ip: list[FailedLoginInsight]
    by_account: list[FailedLoginInsight]


class AdminOverview(BaseModel):
    users: int
    banned_users: int
    records: int
    groups: int
    recent_activity: list[AdminAuditRead]


T = TypeVar("T")


class AdminPage(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class AdminUserRead(UserRead):
    is_active: bool
    is_banned: bool
    ban_reason: str | None
    banned_at: datetime | None


class AdminUserDetail(BaseModel):
    user: AdminUserRead
    records: list[SkillListingRead]
    session_requests: list[SessionRequestRead]
    groups: list[SkillGroupRead]
    sessions: list[SessionRead]
    recent_activity: list[AdminAuditRead]


class RoleUpdate(BaseModel):
    role: Literal["user", "admin"]


class BanInput(BaseModel):
    reason: str = PydanticField(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A ban reason is required.")
        return value


class BulkUserAction(BanInput):
    user_ids: list[int] = PydanticField(min_length=1, max_length=100)

    @field_validator("user_ids")
    @classmethod
    def unique_user_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("User IDs must be unique.")
        return value


class BulkDeleteInput(BaseModel):
    ids: list[int] = PydanticField(min_length=1, max_length=100)

    @field_validator("ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("IDs must be unique.")
        return value


class BulkActionResult(BaseModel):
    affected: int


class CategoryCreate(BaseModel):
    name: str = PydanticField(min_length=1, max_length=60)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category name cannot be empty.")
        return value


class SkillCategory(SQLModel, table=True):
    __tablename__ = "skill_categories"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=60, unique=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime


def _read_event(event: AuditEvent) -> AdminAuditRead:
    return AdminAuditRead(
        id=event.id,
        actor_id=event.actor_id,
        action=event.action,
        target_type=event.target_type,
        target_id=event.target_id,
        details=json.loads(event.details),
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        created_at=event.created_at,
    )


def _recent_events(session: Session, limit: int = 10) -> list[AdminAuditRead]:
    events = session.exec(
        select(AuditEvent).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit)
    ).all()
    return [_read_event(event) for event in events]


def _user_conditions(
    q: str | None,
    role: Literal["user", "admin"] | None,
    banned: bool | None,
) -> list[Any]:
    conditions = []
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions.append(or_(User.email.ilike(term), User.display_name.ilike(term)))
    if role is not None:
        conditions.append(User.role == role)
    if banned is not None:
        conditions.append(User.is_banned.is_(banned))
    return conditions


def _listing_conditions(q: str | None, category: str | None) -> list[Any]:
    conditions = []
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                SkillListing.title.ilike(term),
                SkillListing.teacher_name.ilike(term),
                SkillListing.description.ilike(term),
            )
        )
    if category and category.strip():
        conditions.append(SkillListing.category.ilike(category.strip()))
    return conditions


def _activity_conditions(
    q: str | None,
    action: str | None,
    actor_id: int | None,
    target_type: str | None,
    since: datetime | None,
    until: datetime | None,
) -> list[Any]:
    conditions = []
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions.append(
            or_(
                AuditEvent.action.ilike(term),
                AuditEvent.target_type.ilike(term),
                AuditEvent.target_id.ilike(term),
                AuditEvent.ip_address.ilike(term),
                AuditEvent.user_agent.ilike(term),
            )
        )
    if action:
        conditions.append(AuditEvent.action == action)
    if actor_id is not None:
        conditions.append(AuditEvent.actor_id == actor_id)
    if target_type:
        conditions.append(AuditEvent.target_type == target_type)
    if since is not None:
        conditions.append(AuditEvent.created_at >= since)
    if until is not None:
        conditions.append(AuditEvent.created_at <= until)
    return conditions


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    text_value = str(value)
    if text_value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return f"'{text_value}"
    return text_value


def _csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> Response:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows([_csv_value(value) for value in row] for row in rows)
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _ensure_not_admin_target(user: User) -> None:
    if user.role == ROLE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Administrator accounts cannot be banned.",
        )


def _ensure_ban_targets_safe(actor: User, users: list[User]) -> None:
    for user in users:
        if user.id == actor.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You cannot ban your own account.",
            )
        _ensure_not_admin_target(user)


@router.get("/overview", response_model=AdminOverview)
def get_overview(
    _actor: AdminActor,
    session: DatabaseSession,
) -> AdminOverview:
    return AdminOverview(
        users=session.exec(select(func.count()).select_from(User)).one(),
        banned_users=session.exec(
            select(func.count()).select_from(User).where(User.is_banned.is_(True))
        ).one(),
        records=session.exec(select(func.count()).select_from(SkillListing)).one(),
        groups=session.exec(select(func.count()).select_from(SkillGroup)).one(),
        recent_activity=_recent_events(session),
    )


@router.get("/users", response_model=AdminPage[AdminUserRead])
def list_users(
    _actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    role: Literal["user", "admin"] | None = None,
    banned: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPage[AdminUserRead]:
    query = select(User)
    count_query = select(func.count()).select_from(User)
    conditions = _user_conditions(q, role, banned)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    users = session.exec(
        query.order_by(User.created_at.desc(), User.id.desc()).offset(offset).limit(limit)
    ).all()
    return AdminPage[AdminUserRead](
        items=[AdminUserRead.model_validate(user) for user in users],
        total=session.exec(count_query).one(),
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
def get_user_detail(
    user_id: int,
    _actor: AdminActor,
    session: DatabaseSession,
) -> AdminUserDetail:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    records = session.exec(
        select(SkillListing).where(SkillListing.owner_id == user_id).order_by(SkillListing.id.desc())
    ).all()
    requests = session.exec(
        select(SessionRequest)
        .where(SessionRequest.learner_id == user_id)
        .order_by(SessionRequest.id.desc())
    ).all()
    groups = session.exec(
        select(SkillGroup)
        .outerjoin(GroupMembership, GroupMembership.group_id == SkillGroup.id)
        .where((SkillGroup.owner_id == user_id) | (GroupMembership.user_id == user_id))
        .distinct()
        .order_by(SkillGroup.id.desc())
    ).all()
    sessions = session.exec(
        select(RefreshSession)
        .where(RefreshSession.user_id == user_id)
        .order_by(RefreshSession.created_at.desc())
    ).all()
    activity = session.exec(
        select(AuditEvent)
        .where(
            (AuditEvent.target_type == "user")
            & (AuditEvent.target_id == str(user_id))
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(10)
    ).all()
    return AdminUserDetail(
        user=AdminUserRead.model_validate(user),
        records=[SkillListingRead.model_validate(record) for record in records],
        session_requests=[SessionRequestRead.model_validate(request) for request in requests],
        groups=[SkillGroupRead.model_validate(group) for group in groups],
        sessions=[SessionRead.model_validate(item) for item in sessions],
        recent_activity=[_read_event(event) for event in activity],
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserRead)
def update_user_role(
    request: Request,
    user_id: int,
    payload: RoleUpdate,
    actor: AdminActor,
    session: DatabaseSession,
) -> User:
    if user_id == actor.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You cannot change your own administrator role.",
        )
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if payload.role == ROLE_ADMIN and user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Banned accounts cannot be promoted to administrator.",
        )
    if user.role == ROLE_ADMIN and payload.role != ROLE_ADMIN:
        active_admins = session.exec(
            select(User)
            .where(User.role == ROLE_ADMIN, User.is_active.is_(True), User.is_banned.is_(False))
            .order_by(User.id)
            .with_for_update()
        ).all()
        if user.is_active and not user.is_banned and len(active_admins) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The last active administrator cannot be demoted.",
            )
    previous_role = user.role
    user.role = payload.role
    session.add(user)
    record_admin_action(
        session,
        actor.id,
        "user.role_changed",
        "user",
        user_id,
        {"from": previous_role, "to": payload.role},
        request=request,
    )
    session.commit()
    session.refresh(user)
    return user


def _ban_user(
    session: Session,
    actor: User,
    user: User,
    reason: str,
    request: Request,
) -> None:
    _ensure_ban_targets_safe(actor, [user])
    if user.is_banned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User {user.id} is already banned.",
        )
    user.is_banned = True
    user.ban_reason = reason
    user.banned_at = utc_now()
    session.add(user)
    session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    record_admin_action(
        session,
        actor.id,
        "user.banned",
        "user",
        user.id,
        {"reason": reason},
        request=request,
    )


@router.post("/users/{user_id}/ban", response_model=AdminUserRead)
def ban_user(
    request: Request,
    user_id: int,
    payload: BanInput,
    actor: AdminActor,
    session: DatabaseSession,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _ban_user(session, actor, user, payload.reason, request)
    session.commit()
    session.refresh(user)
    return user


@router.post("/users/{user_id}/unban", response_model=AdminUserRead)
def unban_user(
    request: Request,
    user_id: int,
    actor: AdminActor,
    session: DatabaseSession,
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if not user.is_banned:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is not banned.")
    user.is_banned = False
    user.ban_reason = None
    user.banned_at = None
    session.add(user)
    record_admin_action(session, actor.id, "user.unbanned", "user", user_id, request=request)
    session.commit()
    session.refresh(user)
    return user


@router.post("/users/bulk-ban", response_model=BulkActionResult)
def bulk_ban_users(
    request: Request,
    payload: BulkUserAction,
    actor: AdminActor,
    session: DatabaseSession,
) -> BulkActionResult:
    users = session.exec(select(User).where(User.id.in_(payload.user_ids))).all()
    if len(users) != len(payload.user_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more users were not found.")
    _ensure_ban_targets_safe(actor, users)
    already_banned = [user.id for user in users if user.is_banned]
    if already_banned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Users are already banned: {', '.join(map(str, already_banned))}.",
        )
    for user in users:
        _ban_user(session, actor, user, payload.reason, request)
    session.commit()
    return BulkActionResult(affected=len(users))


@router.post("/users/bulk-unban", response_model=BulkActionResult)
def bulk_unban_users(
    request: Request,
    payload: BulkDeleteInput,
    actor: AdminActor,
    session: DatabaseSession,
) -> BulkActionResult:
    users = session.exec(select(User).where(User.id.in_(payload.ids))).all()
    if len(users) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more users were not found.")
    if any(not user.is_banned for user in users):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="All selected users must be banned.")
    for user in users:
        user.is_banned = False
        user.ban_reason = None
        user.banned_at = None
        session.add(user)
        record_admin_action(session, actor.id, "user.unbanned", "user", user.id, request=request)
    session.commit()
    return BulkActionResult(affected=len(users))


@router.post("/users/{user_id}/revoke-sessions", response_model=BulkActionResult)
def revoke_user_sessions(
    request: Request,
    user_id: int,
    actor: AdminActor,
    session: DatabaseSession,
) -> BulkActionResult:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    result = session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    count = result.rowcount or 0
    record_admin_action(
        session,
        actor.id,
        "user.sessions_revoked",
        "user",
        user_id,
        {"count": count},
        request=request,
    )
    session.commit()
    return BulkActionResult(affected=count)


@router.post(
    "/users/{user_id}/sessions/{session_id}/revoke",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_user_session(
    request: Request,
    user_id: int,
    session_id: str,
    actor: AdminActor,
    session: DatabaseSession,
) -> Response:
    result = session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == user_id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active session not found.")
    record_admin_action(
        session,
        actor.id,
        "user.session_revoked",
        "user",
        user_id,
        {"session_id": session_id},
        request=request,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/listings", response_model=AdminPage[SkillListingRead])
def list_all_listings(
    _actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    category: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPage[SkillListingRead]:
    query = select(SkillListing)
    count_query = select(func.count()).select_from(SkillListing)
    conditions = _listing_conditions(q, category)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)
    items = session.exec(
        query.order_by(SkillListing.created_at.desc(), SkillListing.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return AdminPage[SkillListingRead](
        items=[SkillListingRead.model_validate(item) for item in items],
        total=session.exec(count_query).one(),
        limit=limit,
        offset=offset,
    )


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    request: Request,
    listing_id: int,
    actor: AdminActor,
    session: DatabaseSession,
) -> Response:
    listing = session.get(SkillListing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    session.delete(listing)
    record_admin_action(session, actor.id, "listing.deleted", "listing", listing_id, request=request)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/listings/bulk-delete", response_model=BulkActionResult)
def bulk_delete_listings(
    request: Request,
    payload: BulkDeleteInput,
    actor: AdminActor,
    session: DatabaseSession,
) -> BulkActionResult:
    listings = session.exec(select(SkillListing).where(SkillListing.id.in_(payload.ids))).all()
    if len(listings) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more listings were not found.")
    for listing in listings:
        session.delete(listing)
        record_admin_action(session, actor.id, "listing.deleted", "listing", listing.id, request=request)
    session.commit()
    return BulkActionResult(affected=len(listings))


@router.get("/groups", response_model=AdminPage[SkillGroupRead])
def list_all_groups(
    _actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AdminPage[SkillGroupRead]:
    query = select(SkillGroup).join(User, User.id == SkillGroup.owner_id)
    count_query = select(func.count()).select_from(SkillGroup).join(User, User.id == SkillGroup.owner_id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        condition = or_(SkillGroup.name.ilike(term), User.email.ilike(term), User.display_name.ilike(term))
        query = query.where(condition)
        count_query = count_query.where(condition)
    items = session.exec(
        query.order_by(SkillGroup.created_at.desc(), SkillGroup.id.desc()).offset(offset).limit(limit)
    ).all()
    return AdminPage[SkillGroupRead](
        items=[SkillGroupRead.model_validate(item) for item in items],
        total=session.exec(count_query).one(),
        limit=limit,
        offset=offset,
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    request: Request,
    group_id: int,
    actor: AdminActor,
    session: DatabaseSession,
) -> Response:
    group = session.get(SkillGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    session.delete(group)
    record_admin_action(session, actor.id, "group.deleted", "group", group_id, request=request)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/groups/bulk-delete", response_model=BulkActionResult)
def bulk_delete_groups(
    request: Request,
    payload: BulkDeleteInput,
    actor: AdminActor,
    session: DatabaseSession,
) -> BulkActionResult:
    groups = session.exec(select(SkillGroup).where(SkillGroup.id.in_(payload.ids))).all()
    if len(groups) != len(payload.ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more groups were not found.")
    for group in groups:
        session.delete(group)
        record_admin_action(session, actor.id, "group.deleted", "group", group.id, request=request)
    session.commit()
    return BulkActionResult(affected=len(groups))


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    _actor: AdminActor,
    session: DatabaseSession,
) -> list[SkillCategory]:
    return list(session.exec(select(SkillCategory).order_by(SkillCategory.name)).all())


@router.post(
    "/categories",
    response_model=CategoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    request: Request,
    payload: CategoryCreate,
    actor: AdminActor,
    session: DatabaseSession,
) -> SkillCategory:
    category = SkillCategory(name=payload.name)
    session.add(category)
    record_admin_action(session, actor.id, "category.created", "category", payload.name, request=request)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists.") from error
    session.refresh(category)
    return category


@router.patch("/categories/{category_id}", response_model=CategoryRead)
def rename_category(
    request: Request,
    category_id: int,
    payload: CategoryCreate,
    actor: AdminActor,
    session: DatabaseSession,
) -> SkillCategory:
    category = session.get(SkillCategory, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    previous_name = category.name
    category.name = payload.name
    session.exec(
        update(SkillListing)
        .where(func.lower(SkillListing.category) == previous_name.lower())
        .values(category=payload.name)
    )
    session.add(category)
    record_admin_action(
        session,
        actor.id,
        "category.renamed",
        "category",
        category_id,
        {"from": previous_name, "to": payload.name},
        request=request,
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists.") from error
    session.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    request: Request,
    category_id: int,
    actor: AdminActor,
    session: DatabaseSession,
) -> Response:
    category = session.get(SkillCategory, category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found.")
    usage_count = session.exec(
        select(func.count())
        .select_from(SkillListing)
        .where(func.lower(SkillListing.category) == category.name.lower())
    ).one()
    if usage_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Category is in use by skill listings.",
        )
    session.delete(category)
    record_admin_action(
        session,
        actor.id,
        "category.deleted",
        "category",
        category_id,
        {"name": category.name},
        request=request,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/activity", response_model=list[AdminAuditRead])
def list_recent_activity(
    _actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    action: str | None = None,
    actor_id: int | None = Query(default=None, ge=1),
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AdminAuditRead]:
    conditions = _activity_conditions(q, action, actor_id, target_type, since, until)
    events = session.exec(
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_read_event(event) for event in events]


@router.get("/security/failed-logins", response_model=FailedLoginSummary)
def get_failed_login_insights(
    _actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    since: datetime | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> FailedLoginSummary:
    conditions: list[Any] = [AuditEvent.action == "auth.login_failed"]
    if since is not None:
        conditions.append(AuditEvent.created_at >= since)
    if q and q.strip():
        term = f"%{q.strip()}%"
        conditions.append(
            or_(AuditEvent.ip_address.ilike(term), AuditEvent.target_id.ilike(term))
        )

    def grouped_insights(column: Any) -> list[FailedLoginInsight]:
        value = func.coalesce(column, "Unknown")
        rows = session.exec(
            select(
                value.label("value"),
                func.count(AuditEvent.id).label("count"),
                func.max(AuditEvent.created_at).label("last_seen"),
            )
            .where(*conditions)
            .group_by(value)
            .order_by(func.count(AuditEvent.id).desc(), func.max(AuditEvent.created_at).desc())
            .limit(limit)
        ).all()
        return [
            FailedLoginInsight(value=row[0], count=row[1], last_seen=row[2])
            for row in rows
        ]

    return FailedLoginSummary(
        by_ip=grouped_insights(AuditEvent.ip_address),
        by_account=grouped_insights(AuditEvent.target_id),
    )


@router.get("/exports/users.csv")
def export_users_csv(
    request: Request,
    actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    role: Literal["user", "admin"] | None = None,
    banned: bool | None = None,
) -> Response:
    conditions = _user_conditions(q, role, banned)
    users = session.exec(
        select(User).where(*conditions).order_by(User.created_at.desc(), User.id.desc())
    ).all()
    record_admin_action(
        session,
        actor.id,
        "export.users",
        "export",
        "users",
        {"role": role, "banned": banned},
        request=request,
    )
    session.commit()
    return _csv_response(
        "skillswap-users.csv",
        ["id", "email", "display_name", "role", "is_active", "is_banned", "created_at"],
        [
            [
                user.id,
                user.email,
                user.display_name,
                user.role,
                user.is_active,
                user.is_banned,
                user.created_at,
            ]
            for user in users
        ],
    )


@router.get("/exports/records.csv")
def export_records_csv(
    request: Request,
    actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    category: str | None = None,
) -> Response:
    conditions = _listing_conditions(q, category)
    records = session.exec(
        select(SkillListing)
        .where(*conditions)
        .order_by(SkillListing.created_at.desc(), SkillListing.id.desc())
    ).all()
    record_admin_action(
        session,
        actor.id,
        "export.records",
        "export",
        "records",
        {"category": category},
        request=request,
    )
    session.commit()
    return _csv_response(
        "skillswap-records.csv",
        [
            "id",
            "owner_id",
            "teacher_name",
            "title",
            "description",
            "category",
            "created_at",
        ],
        [
            [
                record.id,
                record.owner_id,
                record.teacher_name,
                record.title,
                record.description,
                record.category,
                record.created_at,
            ]
            for record in records
        ],
    )


@router.get("/exports/activity.csv")
def export_activity_csv(
    request: Request,
    actor: AdminActor,
    session: DatabaseSession,
    q: str | None = None,
    action: str | None = None,
    actor_id: int | None = Query(default=None, ge=1),
    target_type: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> Response:
    record_admin_action(
        session,
        actor.id,
        "export.activity",
        "export",
        "activity",
        {"action": action, "target_type": target_type, "actor_id": actor_id},
        request=request,
    )
    session.flush()
    conditions = _activity_conditions(q, action, actor_id, target_type, since, until)
    events = session.exec(
        select(AuditEvent)
        .where(*conditions)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    ).all()
    session.commit()
    return _csv_response(
        "skillswap-activity.csv",
        [
            "id",
            "actor_id",
            "action",
            "target_type",
            "target_id",
            "ip_address",
            "user_agent",
            "created_at",
        ],
        [
            [
                event.id,
                event.actor_id,
                event.action,
                event.target_type,
                event.target_id,
                event.ip_address,
                event.user_agent,
                event.created_at,
            ]
            for event in events
        ],
    )
