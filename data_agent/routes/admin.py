from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from data_agent.config.database import get_db
from data_agent.models.user import User, UserRole
from data_agent.routes.auth import UserResponse
from data_agent.services.admin_service import (SelfRoleChangeError,
                                               UserNotFoundError,
                                               global_admin_service)
from data_agent.services.auth_service import require_auth_configured
from data_agent.services.authorization_service import (Permission,
                                                       require_permission)

router = APIRouter(dependencies=[Depends(require_auth_configured)])


class RoleUpdate(BaseModel):
    role: UserRole


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.ADMIN_USERS_LIST)
    ),
):
    """Return a bounded, stable user list to authorized administrators."""
    return global_admin_service.list_users(
        db,
        current_user,
        offset=offset,
        limit=limit,
    )


@router.patch("/users/{user_id}/role", response_model=UserResponse)
async def change_user_role(
    user_id: int,
    update: RoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.ADMIN_ROLES_WRITE)
    ),
):
    """Change another user's fixed role."""
    if user_id <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "user_not_found",
                "message": "User not found",
            },
        )
    try:
        return global_admin_service.change_user_role(
            db,
            current_user,
            target_user_id=user_id,
            role=update.role,
        )
    except SelfRoleChangeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "self_role_change_forbidden",
                "message": "Administrators cannot change their own role",
            },
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "user_not_found",
                "message": "User not found",
            },
        ) from exc
