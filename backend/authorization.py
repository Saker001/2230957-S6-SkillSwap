from typing import Annotated

from fastapi import Depends, HTTPException, status

from auth import User, get_current_user
from permissions import ROLE_PERMISSIONS


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
