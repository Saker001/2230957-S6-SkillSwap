from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlmodel import Session, select

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
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = SkillListing.model_validate(payload)
    session.add(skill)
    session.commit()
    session.refresh(skill)
    return skill


@app.get("/api/skills", response_model=list[SkillListingRead])
def list_skills(
    session: Session = Depends(get_session),
) -> list[SkillListing]:
    return list(session.exec(select(SkillListing).order_by(SkillListing.id.desc())).all())


@app.get("/api/skills/{skill_id}", response_model=SkillListingRead)
def read_skill(
    skill_id: int,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = session.get(SkillListing, skill_id)
    if skill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    return skill


@app.patch("/api/skills/{skill_id}", response_model=SkillListingRead)
def update_skill(
    skill_id: int,
    payload: SkillListingUpdate,
    session: Session = Depends(get_session),
) -> SkillListing:
    skill = session.get(SkillListing, skill_id)
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
    session: Session = Depends(get_session),
) -> Response:
    skill = session.get(SkillListing, skill_id)
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
    session: Session = Depends(get_session),
) -> SessionRequest:
    if session.get(SkillListing, payload.skill_listing_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
    request = SessionRequest.model_validate(payload, update={"status": "pending"})
    session.add(request)
    session.commit()
    session.refresh(request)
    return request


@app.get("/api/session-requests", response_model=list[SessionRequestRead])
def list_session_requests(
    session: Session = Depends(get_session),
) -> list[SessionRequest]:
    return list(
        session.exec(select(SessionRequest).order_by(SessionRequest.id.desc())).all()
    )


@app.get("/api/session-requests/{request_id}", response_model=SessionRequestRead)
def read_session_request(
    request_id: int,
    session: Session = Depends(get_session),
) -> SessionRequest:
    request = session.get(SessionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    return request


@app.patch("/api/session-requests/{request_id}", response_model=SessionRequestRead)
def update_session_request(
    request_id: int,
    payload: SessionRequestUpdate,
    session: Session = Depends(get_session),
) -> SessionRequest:
    request = session.get(SessionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    update_data = payload.model_dump(exclude_unset=True)
    skill_listing_id = update_data.get("skill_listing_id")
    if skill_listing_id is not None and session.get(SkillListing, skill_listing_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill listing not found")
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
    session: Session = Depends(get_session),
) -> Response:
    request = session.get(SessionRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session request not found")
    session.delete(request)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if FRONTEND_DIR.is_dir():
    app.frontend("/", directory=FRONTEND_DIR)
