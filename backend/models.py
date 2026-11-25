from datetime import datetime, timezone

from pydantic import ConfigDict, field_validator, model_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class SkillListingBase(SQLModel):
    teacher_name: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    category: str = Field(min_length=1, max_length=60)

    @field_validator("teacher_name", "title", "description", "category", mode="before")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class SkillListingCreate(SkillListingBase):
    pass


class SkillListingUpdate(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    teacher_name: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    category: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("teacher_name", "title", "description", "category", mode="before")
    @classmethod
    def strip_update_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        return self


class SkillListingRead(SkillListingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int | None
    created_at: datetime


class SkillListing(SkillListingBase, table=True):
    __tablename__ = "skill_listings"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        ondelete="SET NULL",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkillGroupBase(SQLModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class SkillGroupCreate(SkillGroupBase):
    pass


class SkillGroupUpdate(SkillGroupBase):
    pass


class SkillGroupRead(SkillGroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    created_at: datetime


class SkillGroup(SkillGroupBase, table=True):
    __tablename__ = "skill_groups"

    id: int | None = Field(default=None, primary_key=True)
    owner_id: int = Field(
        foreign_key="users.id",
        index=True,
        ondelete="CASCADE",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GroupMembershipCreate(SQLModel):
    email: str = Field(min_length=1, max_length=254)
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value


class GroupMembershipUpdate(SQLModel):
    can_create: bool | None = None
    can_edit: bool | None = None
    can_assign: bool | None = None

    @model_validator(mode="after")
    def require_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one capability must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Capability values cannot be null")
        return self


class GroupMembership(SQLModel, table=True):
    __tablename__ = "group_memberships"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_membership_user"),
    )

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(
        foreign_key="skill_groups.id",
        index=True,
        ondelete="CASCADE",
    )
    user_id: int = Field(
        foreign_key="users.id",
        index=True,
        ondelete="CASCADE",
    )
    can_create: bool = Field(default=False)
    can_edit: bool = Field(default=False)
    can_assign: bool = Field(default=False)


class GroupMemberRead(SQLModel):
    user_id: int
    display_name: str
    is_owner: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_assign: bool = False


class GroupSkillAssignment(SQLModel, table=True):
    __tablename__ = "group_skill_assignments"

    skill_listing_id: int = Field(
        foreign_key="skill_listings.id",
        primary_key=True,
        ondelete="CASCADE",
    )
    group_id: int = Field(
        foreign_key="skill_groups.id",
        index=True,
        ondelete="CASCADE",
    )
    assigned_by_user_id: int = Field(foreign_key="users.id", ondelete="CASCADE")


class SessionRequestBase(SQLModel):
    skill_listing_id: int = Field(foreign_key="skill_listings.id", ondelete="CASCADE")
    learner_name: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=1000)
    status: str = Field(default="pending", max_length=20)


class SessionRequestCreate(SQLModel):
    skill_listing_id: int
    message: str = Field(min_length=1, max_length=1000)

    @field_validator("message", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class SessionRequestUpdate(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    message: str | None = Field(default=None, min_length=1, max_length=1000)
    status: str | None = Field(default=None, max_length=20)

    @field_validator("message", mode="before")
    @classmethod
    def strip_update_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_update_fields(self):
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("Updated fields cannot be null")
        if self.status is not None and self.status not in {"pending", "accepted", "declined"}:
            raise ValueError("Status must be pending, accepted, or declined")
        return self


class SessionRequestRead(SessionRequestBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    learner_id: int | None
    created_at: datetime


class SessionRequest(SessionRequestBase, table=True):
    __tablename__ = "session_requests"

    id: int | None = Field(default=None, primary_key=True)
    learner_id: int | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        ondelete="SET NULL",
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
