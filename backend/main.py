from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import or_
from sqlmodel import Session, select

from auth import User, router as auth_router
from authorization import require_permission
from database import create_db_and_tables, get_session
from models import (
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


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/hello")
def hello(name: str = "World") -> dict[str, str]:
    return {"message": f"Hello, {name}!"}


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
    current_user: SkillDeleter,
    session: Session = Depends(get_session),
) -> Response:
    skill = session.exec(
        select(SkillListing).where(
            SkillListing.id == skill_id,
            SkillListing.owner_id == current_user.id,
        )
    ).first()
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    session.delete(skill)
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
    if listing is None or listing.owner_id is None:
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
    current_user: RequestDeleter,
    session: Session = Depends(get_session),
) -> Response:
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
    session.delete(request)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
