import hashlib
import hmac
import os
import secrets
import uuid
import warnings
from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_validator, model_validator
from sqlalchemy import DateTime, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Field, Session, SQLModel, select

from database import get_session

ACCESS_TOKEN_MINUTES = 15
REFRESH_TOKEN_DAYS = 14
REFRESH_COOKIE = "skillswap_refresh"
REFRESH_COOKIE_PATH = "/api"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCK_MINUTES = 15
JWT_ISSUER = "skillswap-api"


def _secret_from_environment(name: str) -> str:
    value = os.getenv(name)
    if value:
        if len(value) < 32:
            raise RuntimeError(f"{name} must be at least 32 characters long.")
        return value
    if os.getenv("VERCEL"):
        raise RuntimeError(f"Set {name} in the Vercel environment before deployment.")
    warnings.warn(
        f"{name} is not set; a temporary development secret is being used.",
        RuntimeWarning,
        stacklevel=2,
    )
    return secrets.token_urlsafe(48)


JWT_SECRET_KEY = _secret_from_environment("JWT_SECRET_KEY")
PASSWORD_PEPPER = _secret_from_environment("PASSWORD_PEPPER")
password_hasher = PasswordHasher()
bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_future(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > utc_now()


def _peppered_password(password: str) -> str:
    return hmac.new(
        PASSWORD_PEPPER.encode("utf-8"),
        password.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_password(password: str) -> str:
    return password_hasher.hash(_peppered_password(password))


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, _peppered_password(password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


DUMMY_PASSWORD_HASH = password_hasher.hash(_peppered_password(secrets.token_urlsafe(32)))


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)
    display_name: str = Field(max_length=80)
    password_hash: str
    role: str = Field(default="user", max_length=20, index=True)
    is_active: bool = Field(default=True, index=True)
    failed_login_attempts: int = Field(default=0)
    locked_until: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))


class RefreshSession(SQLModel, table=True):
    __tablename__ = "refresh_sessions"

    id: str = Field(primary_key=True, max_length=36)
    user_id: int = Field(foreign_key="users.id", index=True, ondelete="CASCADE")
    token_hash: str = Field(index=True, unique=True, max_length=64)
    created_at: datetime = Field(default_factory=utc_now, sa_type=DateTime(timezone=True))
    expires_at: datetime = Field(sa_type=DateTime(timezone=True))
    revoked_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    replaced_by: str | None = Field(default=None, max_length=36)
    user_agent: str | None = Field(default=None, max_length=500)
    ip_address: str | None = Field(default=None, max_length=64)


class SignUpInput(BaseModel):
    email: str
    display_name: str = PydanticField(min_length=1, max_length=80)
    password: str = PydanticField(min_length=12, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        try:
            return validate_email(value.strip(), check_deliverability=False).normalized.lower()
        except EmailNotValidError as error:
            raise ValueError("Enter a valid email address.") from error

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be empty.")
        return value


class LoginInput(BaseModel):
    email: str
    password: str = PydanticField(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class ProfileUpdateInput(BaseModel):
    display_name: str = PydanticField(min_length=1, max_length=80)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Display name cannot be empty.")
        return value


class PasswordChangeInput(BaseModel):
    current_password: str = PydanticField(min_length=1, max_length=128)
    new_password: str = PydanticField(min_length=12, max_length=128)

    @model_validator(mode="after")
    def passwords_must_differ(self):
        if self.current_password == self.new_password:
            raise ValueError("New password must differ from current password.")
        return self


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    session_id: str
    user: UserRead


class SessionRead(BaseModel):
    id: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip_address: str | None


def _new_access_token(user: User, session_id: str) -> str:
    now = utc_now()
    return jwt.encode(
        {
            "iss": JWT_ISSUER,
            "sub": str(user.id),
            "role": user.role,
            "sid": session_id,
            "iat": now,
            "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
            "jti": str(uuid.uuid4()),
        },
        JWT_SECRET_KEY,
        algorithm="HS256",
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=bool(os.getenv("VERCEL")),
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
        max_age=REFRESH_TOKEN_DAYS * 24 * 60 * 60,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=bool(os.getenv("VERCEL")),
        samesite="lax",
    )


def _create_refresh_session(
    session: Session,
    user: User,
    request: Request,
    response: Response,
) -> AuthResponse:
    raw_token = secrets.token_urlsafe(48)
    refresh_session = RefreshSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        expires_at=utc_now() + timedelta(days=REFRESH_TOKEN_DAYS),
        user_agent=request.headers.get("user-agent", "")[:500] or None,
        ip_address=request.client.host if request.client else None,
    )
    session.add(refresh_session)
    session.commit()
    _set_refresh_cookie(response, raw_token)
    return AuthResponse(
        access_token=_new_access_token(user, refresh_session.id),
        expires_in=ACCESS_TOKEN_MINUTES * 60,
        session_id=refresh_session.id,
        user=UserRead.model_validate(user),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required or session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()
    try:
        payload = jwt.decode(
            credentials.credentials,
            JWT_SECRET_KEY,
            algorithms=["HS256"],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "sid", "role"]},
        )
        user_id = int(payload["sub"])
        session_id = str(payload["sid"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise _unauthorized() from None

    user = session.get(User, user_id)
    refresh_session = session.get(RefreshSession, session_id)
    if (
        user is None
        or not user.is_active
        or refresh_session is None
        or refresh_session.user_id != user_id
        or refresh_session.revoked_at is not None
        or not _is_future(refresh_session.expires_at)
    ):
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DatabaseSession = Annotated[Session, Depends(get_session)]


@router.post("/api/auth/signup", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def sign_up(payload: SignUpInput, session: DatabaseSession) -> User:
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.") from error
    session.refresh(user)
    return user


@router.post("/api/auth/login", response_model=AuthResponse)
def log_in(
    payload: LoginInput,
    request: Request,
    response: Response,
    session: DatabaseSession,
) -> AuthResponse:
    user = session.exec(select(User).where(User.email == payload.email)).first()
    now = utc_now()
    valid_password = verify_password(
        payload.password,
        user.password_hash if user is not None else DUMMY_PASSWORD_HASH,
    )
    if (
        user is None
        or not valid_password
        or not user.is_active
        or (user.locked_until is not None and _is_future(user.locked_until))
    ):
        if user is not None and user.is_active:
            if user.locked_until is None or not _is_future(user.locked_until):
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= MAX_LOGIN_ATTEMPTS:
                    user.failed_login_attempts = 0
                    user.locked_until = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
                session.add(user)
                session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    user.failed_login_attempts = 0
    user.locked_until = None
    session.add(user)
    session.commit()
    return _create_refresh_session(session, user, request, response)


@router.post("/api/auth/refresh", response_model=AuthResponse)
def refresh_access_token(
    request: Request,
    response: Response,
    session: DatabaseSession,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> AuthResponse:
    if not refresh_token:
        _clear_refresh_cookie(response)
        raise _unauthorized()

    current = session.exec(
        select(RefreshSession).where(RefreshSession.token_hash == _token_hash(refresh_token))
    ).first()
    if current is None or current.revoked_at is not None or not _is_future(current.expires_at):
        _clear_refresh_cookie(response)
        raise _unauthorized()

    user = session.get(User, current.user_id)
    if user is None or not user.is_active:
        _clear_refresh_cookie(response)
        raise _unauthorized()

    new_id = str(uuid.uuid4())
    now = utc_now()
    result = session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == current.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=now, replaced_by=new_id)
    )
    if result.rowcount != 1:
        session.rollback()
        _clear_refresh_cookie(response)
        raise _unauthorized()

    raw_token = secrets.token_urlsafe(48)
    replacement = RefreshSession(
        id=new_id,
        user_id=user.id,
        token_hash=_token_hash(raw_token),
        expires_at=now + timedelta(days=REFRESH_TOKEN_DAYS),
        user_agent=request.headers.get("user-agent", "")[:500] or None,
        ip_address=request.client.host if request.client else None,
    )
    session.add(replacement)
    session.commit()
    _set_refresh_cookie(response, raw_token)
    return AuthResponse(
        access_token=_new_access_token(user, replacement.id),
        expires_in=ACCESS_TOKEN_MINUTES * 60,
        session_id=replacement.id,
        user=UserRead.model_validate(user),
    )


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    response: Response,
    session: DatabaseSession,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> Response:
    if refresh_token:
        session.execute(
            update(RefreshSession)
            .where(
                RefreshSession.token_hash == _token_hash(refresh_token),
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=utc_now())
        )
        session.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/api/users/me", response_model=UserRead)
def read_profile(current_user: CurrentUser) -> User:
    return current_user


@router.patch("/api/users/me", response_model=UserRead)
def update_profile(payload: ProfileUpdateInput, current_user: CurrentUser, session: DatabaseSession) -> User:
    current_user.display_name = payload.display_name
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.post("/api/users/me/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeInput,
    response: Response,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect.")
    current_user.password_hash = hash_password(payload.new_password)
    current_user.failed_login_attempts = 0
    current_user.locked_until = None
    session.add(current_user)
    session.execute(
        update(RefreshSession)
        .where(RefreshSession.user_id == current_user.id, RefreshSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    session.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/api/users/me/sessions", response_model=list[SessionRead])
def list_my_sessions(current_user: CurrentUser, session: DatabaseSession) -> list[RefreshSession]:
    return list(
        session.exec(
            select(RefreshSession)
            .where(RefreshSession.user_id == current_user.id)
            .order_by(RefreshSession.created_at.desc())
        ).all()
    )


@router.delete("/api/users/me/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_my_session(
    session_id: str,
    current_user: CurrentUser,
    session: DatabaseSession,
) -> Response:
    result = session.execute(
        update(RefreshSession)
        .where(
            RefreshSession.id == session_id,
            RefreshSession.user_id == current_user.id,
            RefreshSession.revoked_at.is_(None),
        )
        .values(revoked_at=utc_now())
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
