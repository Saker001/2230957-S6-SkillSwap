from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from admin import router as admin_router
from audit import record_admin_action
from auth import User, router as auth_router
from authorization import (
    GroupAccess,
    require_group_capability,
    require_group_access,
    require_group_owner,
    require_permission,
)
from database import create_db_and_tables, get_session
from models import (
    GroupMemberRead,
    GroupMembership,
    GroupMembershipCreate,
    GroupMembershipUpdate,
    GroupSkillAssignment,
    SkillGroup,
    SkillGroupCreate,
    SkillGroupRead,
    SkillGroupUpdate,
    SessionRequest,
    SessionRequestCreate,
    SessionRequestRead,
    SessionRequestUpdate,
    SkillListing,
    SkillListingCreate,
    SkillListingRead,
    SkillListingUpdate,
)
from permissions import (
    PERMISSION_REQUESTS_CREATE,
    PERMISSION_REQUESTS_DELETE_PARTICIPANT,
    PERMISSION_REQUESTS_READ_PARTICIPANT,
    PERMISSION_REQUESTS_UPDATE_PARTICIPANT,
    PERMISSION_SKILLS_CREATE,
    PERMISSION_SKILLS_DELETE_OWN,
    PERMISSION_SKILLS_READ,
    PERMISSION_SKILLS_UPDATE_OWN,
)

SkillReader = Annotated[User, Depends(require_permission(PERMISSION_SKILLS_READ))]
SkillCreator = Annotated[User, Depends(require_permission(PERMISSION_SKILLS_CREATE))]
SkillUpdater = Annotated[User, Depends(require_permission(PERMISSION_SKILLS_UPDATE_OWN))]
SkillDeleter = Annotated[User, Depends(require_permission(PERMISSION_SKILLS_DELETE_OWN))]
GroupOwner = Annotated[GroupAccess, Depends(require_group_owner)]
GroupReader = Annotated[GroupAccess, Depends(require_group_access)]
GroupCreator = Annotated[GroupAccess, Depends(require_group_capability("can_create"))]
GroupEditor = Annotated[GroupAccess, Depends(require_group_capability("can_edit"))]
GroupAssigner = Annotated[GroupAccess, Depends(require_group_capability("can_assign"))]
RequestCreator = Annotated[User, Depends(require_permission(PERMISSION_REQUESTS_CREATE))]
RequestReader = Annotated[
    User, Depends(require_permission(PERMISSION_REQUESTS_READ_PARTICIPANT))
]
RequestUpdater = Annotated[
    User, Depends(require_permission(PERMISSION_REQUESTS_UPDATE_PARTICIPANT))
]
RequestDeleter = Annotated[
    User, Depends(require_permission(PERMISSION_REQUESTS_DELETE_PARTICIPANT))
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="SkillSwap API",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)
app.include_router(auth_router)
app.include_router(admin_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hello")
def hello(name: str = "World") -> dict[str, str]:
    return {"message": f"Hello, {name}!"}


def _group_member_read(
    user_id: int,
    display_name: str,
    *,
    is_owner: bool = False,
    can_create: bool = False,
    can_edit: bool = False,
    can_assign: bool = False,
) -> GroupMemberRead:
    return GroupMemberRead(
        user_id=user_id,
        display_name=display_name,
        is_owner=is_owner,
        can_create=can_create,
        can_edit=can_edit,
        can_assign=can_assign,
    )


@app.post(
    "/api/groups",
    response_model=SkillGroupRead,
    status_code=status.HTTP_201_CREATED,
)
def create_group(
    payload: SkillGroupCreate,
    current_user: SkillCreator,
    session: Session = Depends(get_session),
) -> SkillGroup:
    group = SkillGroup.model_validate(payload, update={"owner_id": current_user.id})
    session.add(group)
    session.commit()
    session.refresh(group)
    return group


@app.get("/api/groups", response_model=list[SkillGroupRead])
def list_groups(
    current_user: User = Depends(require_permission(PERMISSION_SKILLS_READ)),
    session: Session = Depends(get_session),
) -> list[SkillGroup]:
    return list(
        session.exec(
            select(SkillGroup)
            .outerjoin(
                GroupMembership,
                GroupMembership.group_id == SkillGroup.id,
            )
            .where(
                (SkillGroup.owner_id == current_user.id)
                | (GroupMembership.user_id == current_user.id)
            )
            .distinct()
            .order_by(SkillGroup.id.desc())
        ).all()
    )


@app.get("/api/groups/{group_id}", response_model=SkillGroupRead)
def read_group(access: GroupReader) -> SkillGroup:
    return access.group


@app.patch("/api/groups/{group_id}", response_model=SkillGroupRead)
def update_group(
    payload: SkillGroupUpdate,
    access: GroupOwner,
    session: Session = Depends(get_session),
) -> SkillGroup:
    access.group.name = payload.name
    session.add(access.group)
    session.commit()
    session.refresh(access.group)
    return access.group


@app.delete("/api/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(
    request: Request,
    access: GroupOwner,
    session: Session = Depends(get_session),
) -> Response:
    session.delete(access.group)
    record_admin_action(
        session,
        access.group.owner_id,
        "content.deleted",
        "group",
        access.group.id,
        request=request,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/groups/{group_id}/members", response_model=list[GroupMemberRead])
def list_group_members(
    access: GroupReader,
    session: Session = Depends(get_session),
) -> list[GroupMemberRead]:
    owner = session.get(User, access.group.owner_id)
    members = list(
        session.exec(
            select(GroupMembership, User)
            .join(User, User.id == GroupMembership.user_id)
            .where(GroupMembership.group_id == access.group.id)
            .order_by(User.display_name)
        ).all()
    )
    results = [
        _group_member_read(
            owner.id,
            owner.display_name,
            is_owner=True,
            can_create=True,
            can_edit=True,
            can_assign=True,
        )
    ] if owner is not None else []
    results.extend(
        _group_member_read(
            membership.user_id,
            user.display_name,
            can_create=membership.can_create,
            can_edit=membership.can_edit,
            can_assign=membership.can_assign,
        )
        for membership, user in members
    )
    return results


@app.post(
    "/api/groups/{group_id}/members",
    response_model=GroupMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_group_member(
    payload: GroupMembershipCreate,
    access: GroupOwner,
    session: Session = Depends(get_session),
) -> GroupMemberRead:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if user.id == access.group.owner_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The group owner is already a member.")
    existing = session.exec(
        select(GroupMembership).where(
            GroupMembership.group_id == access.group.id,
            GroupMembership.user_id == user.id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a group member.")
    membership = GroupMembership(
        group_id=access.group.id,
        user_id=user.id,
        can_create=payload.can_create,
        can_edit=payload.can_edit,
        can_assign=payload.can_assign,
    )
    session.add(membership)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a group member.",
        ) from error
    return _group_member_read(
        user.id,
        user.display_name,
        can_create=membership.can_create,
        can_edit=membership.can_edit,
        can_assign=membership.can_assign,
    )


@app.patch(
    "/api/groups/{group_id}/members/{user_id}",
    response_model=GroupMemberRead,
)
def update_group_member(
    user_id: int,
    payload: GroupMembershipUpdate,
    access: GroupOwner,
    session: Session = Depends(get_session),
) -> GroupMemberRead:
    membership = session.exec(
        select(GroupMembership).where(
            GroupMembership.group_id == access.group.id,
            GroupMembership.user_id == user_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found.")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found.")
    membership.sqlmodel_update(payload.model_dump(exclude_unset=True))
    session.add(membership)
    session.commit()
    return _group_member_read(
        user.id,
        user.display_name,
        can_create=membership.can_create,
        can_edit=membership.can_edit,
        can_assign=membership.can_assign,
    )


@app.delete(
    "/api/groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_group_member(
    user_id: int,
    access: GroupOwner,
    session: Session = Depends(get_session),
) -> Response:
    membership = session.exec(
        select(GroupMembership).where(
            GroupMembership.group_id == access.group.id,
            GroupMembership.user_id == user_id,
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found.")
    session.delete(membership)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get(
    "/api/groups/{group_id}/skills",
    response_model=list[SkillListingRead],
)
def list_group_skills(
    access: GroupReader,
    session: Session = Depends(get_session),
) -> list[SkillListing]:
    return list(
        session.exec(
            select(SkillListing)
            .join(
                GroupSkillAssignment,
                GroupSkillAssignment.skill_listing_id == SkillListing.id,
            )
            .where(GroupSkillAssignment.group_id == access.group.id)
            .order_by(SkillListing.id.desc())
        ).all()
    )


@app.post(
    "/api/groups/{group_id}/skills",
    response_model=SkillListingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_group_skill(
    payload: SkillListingCreate,
    access: GroupCreator,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = SkillListing.model_validate(payload, update={"owner_id": access.user.id})
    session.add(skill)
    session.flush()
    session.add(
        GroupSkillAssignment(
            skill_listing_id=skill.id,
            group_id=access.group.id,
            assigned_by_user_id=access.user.id,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Skill listing is already assigned to a group.",
        ) from error
    session.refresh(skill)
    return skill


@app.post(
    "/api/groups/{group_id}/skills/{skill_id}/assignment",
    response_model=SkillListingRead,
)
def assign_group_skill(
    skill_id: int,
    access: GroupAssigner,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = session.get(SkillListing, skill_id)
    if skill is None or skill.owner_id != access.user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found.")
    if session.get(GroupSkillAssignment, skill_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Skill listing is already assigned to a group.")
    session.add(
        GroupSkillAssignment(
            skill_listing_id=skill_id,
            group_id=access.group.id,
            assigned_by_user_id=access.user.id,
        )
    )
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Skill listing is already assigned to a group.",
        ) from error
    return skill


@app.patch(
    "/api/groups/{group_id}/skills/{skill_id}",
    response_model=SkillListingRead,
)
def update_group_skill(
    skill_id: int,
    payload: SkillListingUpdate,
    access: GroupEditor,
    session: Session = Depends(get_session),
) -> SkillListing:
    assignment = session.get(GroupSkillAssignment, skill_id)
    if assignment is None or assignment.group_id != access.group.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group skill listing not found.")
    skill = session.get(SkillListing, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group skill listing not found.")
    skill.sqlmodel_update(payload.model_dump(exclude_unset=True))
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


@app.delete(
    "/api/groups/{group_id}/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unassign_group_skill(
    skill_id: int,
    access: GroupAssigner,
    session: Session = Depends(get_session),
) -> Response:
    assignment = session.get(GroupSkillAssignment, skill_id)
    if assignment is None or assignment.group_id != access.group.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group skill listing not found.")
    session.delete(assignment)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/skills",
    response_model=SkillListingRead,
    status_code=status.HTTP_201_CREATED,
)
def create_skill(
    payload: SkillListingCreate,
    current_user: SkillCreator,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = SkillListing.model_validate(payload, update={"owner_id": current_user.id})
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


@app.get("/api/skills", response_model=list[SkillListingRead])
def list_skills(
    current_user: SkillReader,
    session: Session = Depends(get_session),
) -> list[SkillListing]:
    return list(
        session.exec(
            select(SkillListing)
            .where(SkillListing.owner_id.is_not(None))
            .where(SkillListing.id.not_in(select(GroupSkillAssignment.skill_listing_id)))
            .order_by(SkillListing.id.desc())
        ).all()
    )


@app.get("/api/skills/{skill_id}", response_model=SkillListingRead)
def read_skill(
    skill_id: int,
    current_user: SkillReader,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = session.exec(
        select(SkillListing).where(
            SkillListing.id == skill_id,
            SkillListing.owner_id.is_not(None),
            SkillListing.id.not_in(select(GroupSkillAssignment.skill_listing_id)),
        )
    ).first()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    return skill


@app.patch("/api/skills/{skill_id}", response_model=SkillListingRead)
def update_skill(
    skill_id: int,
    payload: SkillListingUpdate,
    current_user: SkillUpdater,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = session.exec(
        select(SkillListing).where(
            SkillListing.id == skill_id,
            SkillListing.owner_id == current_user.id,
            SkillListing.id.not_in(select(GroupSkillAssignment.skill_listing_id)),
        )
    ).first()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    skill.sqlmodel_update(payload.model_dump(exclude_unset=True))
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


@app.delete("/api/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(
    skill_id: int,
    request: Request,
    current_user: SkillDeleter,
    session: Session = Depends(get_session),
) -> Response:
    skill = session.exec(
        select(SkillListing).where(
            SkillListing.id == skill_id,
            SkillListing.owner_id == current_user.id,
            SkillListing.id.not_in(select(GroupSkillAssignment.skill_listing_id)),
        )
    ).first()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    session.delete(skill)
    record_admin_action(
        session,
        current_user.id,
        "content.deleted",
        "listing",
        skill_id,
        request=request,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/session-requests",
    response_model=SessionRequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_session_request(
    payload: SessionRequestCreate,
    current_user: RequestCreator,
    session: Session = Depends(get_session),
) -> SessionRequest:
    listing = session.get(SkillListing, payload.skill_listing_id)
    if (
        listing is None
        or listing.owner_id is None
        or session.get(GroupSkillAssignment, listing.id) is not None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    if listing.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot request a session for your own listing.",
        )
    request = SessionRequest.model_validate(
        payload,
        update={
            "learner_id": current_user.id,
            "learner_name": current_user.display_name,
            "status": "pending",
        },
    )
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


@app.get("/api/session-requests", response_model=list[SessionRequestRead])
def list_session_requests(
    current_user: RequestReader,
    session: Session = Depends(get_session),
) -> list[SessionRequest]:
    return list(
        session.exec(
            select(SessionRequest)
            .join(SkillListing)
            .where(
                or_(
                    SessionRequest.learner_id == current_user.id,
                    SkillListing.owner_id == current_user.id,
                )
            )
            .order_by(SessionRequest.id.desc())
        ).all()
    )


@app.get("/api/session-requests/{request_id}", response_model=SessionRequestRead)
def read_session_request(
    request_id: int,
    current_user: RequestReader,
    session: Session = Depends(get_session),
) -> SessionRequest:
    request = session.exec(
        select(SessionRequest)
        .join(SkillListing)
        .where(
            SessionRequest.id == request_id,
            or_(
                SessionRequest.learner_id == current_user.id,
                SkillListing.owner_id == current_user.id,
            ),
        )
    ).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    return request


@app.patch("/api/session-requests/{request_id}", response_model=SessionRequestRead)
def update_session_request(
    request_id: int,
    payload: SessionRequestUpdate,
    current_user: RequestUpdater,
    session: Session = Depends(get_session),
) -> SessionRequest:
    request = session.exec(
        select(SessionRequest)
        .join(SkillListing)
        .where(
            SessionRequest.id == request_id,
            or_(
                SessionRequest.learner_id == current_user.id,
                SkillListing.owner_id == current_user.id,
            ),
        )
    ).first()
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    update_data = payload.model_dump(exclude_unset=True)
    listing = session.get(SkillListing, request.skill_listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    if current_user.id == listing.owner_id:
        if set(update_data) != {"status"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Listing owners may only update request status.",
            )
    elif current_user.id == request.learner_id:
        if set(update_data) != {"message"}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Learners may only update their request message.",
            )
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    request.sqlmodel_update(update_data)
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


@app.delete(
    "/api/session-requests/{request_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_session_request(
    request_id: int,
    request: Request,
    current_user: RequestDeleter,
    session: Session = Depends(get_session),
) -> Response:
    session_request = session.exec(
        select(SessionRequest)
        .join(SkillListing)
        .where(
            SessionRequest.id == request_id,
            or_(
                SessionRequest.learner_id == current_user.id,
                SkillListing.owner_id == current_user.id,
            ),
        )
    ).first()
    if session_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    session.delete(session_request)
    record_admin_action(
        session,
        current_user.id,
        "content.deleted",
        "session_request",
        request_id,
        request=request,
    )
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
