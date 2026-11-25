from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, HTTPException, status

from auth import User, get_current_user
from database import get_session
from models import GroupMembership, SkillGroup
from permissions import ROLE_PERMISSIONS
from sqlmodel import Session, select


def require_permission(permission: str):
    def dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if permission not in ROLE_PERMISSIONS.get(current_user.role, frozenset()):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return dependency


@dataclass(frozen=True)
class GroupAccess:
    group: SkillGroup
    user: User
    membership: GroupMembership | None

    @property
    def is_owner(self) -> bool:
        return self.group.owner_id == self.user.id


GroupCapability = Literal["can_create", "can_edit", "can_assign"]


def require_group_access(
    group_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> GroupAccess:
    group = session.get(SkillGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    membership = session.exec(
        select(GroupMembership).where(
            GroupMembership.group_id == group_id,
            GroupMembership.user_id == current_user.id,
        )
    ).first()
    if group.owner_id != current_user.id and membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    return GroupAccess(group=group, user=current_user, membership=membership)


def require_group_owner(access: Annotated[GroupAccess, Depends(require_group_access)]) -> GroupAccess:
    if not access.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the group owner can manage group settings and membership.",
        )
    return access


def require_group_capability(capability: GroupCapability):
    def dependency(
        access: Annotated[GroupAccess, Depends(require_group_access)],
    ) -> GroupAccess:
        if not access.is_owner and (
            access.membership is None or not getattr(access.membership, capability)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This group does not grant the {capability.removeprefix('can_')} capability.",
            )
        return access

    return dependency
