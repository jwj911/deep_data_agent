import logging
from enum import StrEnum

from fastapi import Depends, HTTPException, status

from data_agent.models.user import User, UserRole
from data_agent.observability.audit import emit_audit_event
from data_agent.services.auth_service import get_current_user


class Permission(StrEnum):
    """Permissions enforced by the application service boundary."""

    SESSION_READ_OWN = "session.read_own"
    SESSION_WRITE_OWN = "session.write_own"
    SESSION_DELETE_OWN = "session.delete_own"
    AGENT_INVOKE_OWN = "agent.invoke_own"
    ADMIN_USERS_LIST = "admin.users_list"
    ADMIN_ROLES_WRITE = "admin.roles_write"


_SESSION_PERMISSIONS = frozenset(
    {
        Permission.SESSION_READ_OWN,
        Permission.SESSION_WRITE_OWN,
        Permission.SESSION_DELETE_OWN,
        Permission.AGENT_INVOKE_OWN,
    }
)
ROLE_PERMISSIONS: dict[str, frozenset[Permission]] = {
    UserRole.USER.value: _SESSION_PERMISSIONS,
    UserRole.ADMIN.value: frozenset(
        {
            *_SESSION_PERMISSIONS,
            Permission.ADMIN_USERS_LIST,
            Permission.ADMIN_ROLES_WRITE,
        }
    ),
}


class AuthorizationDeniedError(PermissionError):
    """Raised when a service caller lacks a required permission."""


def has_permission(role: object, permission: Permission) -> bool:
    """Return whether a known role explicitly grants a permission."""
    role_value = role.value if isinstance(role, UserRole) else role
    if not isinstance(role_value, str) or not isinstance(
        permission, Permission
    ):
        return False
    return permission in ROLE_PERMISSIONS.get(role_value, frozenset())


def ensure_permission(actor: User, permission: Permission) -> None:
    """Enforce a service-layer permission using default-deny semantics."""
    if has_permission(getattr(actor, "role", None), permission):
        return

    actor_id = getattr(actor, "id", None)
    if (
        isinstance(actor_id, int)
        and not isinstance(actor_id, bool)
        and actor_id > 0
    ):
        emit_audit_event(
            "authorization.denied",
            operation="permission.check",
            outcome="rejected",
            actor_kind="user",
            actor_user_id=actor_id,
            permission=permission.value,
            decision="denied",
            level=logging.WARNING,
        )
    raise AuthorizationDeniedError("permission denied")


def require_permission(permission: Permission):
    """Build a FastAPI dependency that enforces one permission."""

    def dependency(
        current_user: User = Depends(get_current_user),
    ) -> User:
        try:
            ensure_permission(current_user, permission)
        except AuthorizationDeniedError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "forbidden",
                    "message": "Insufficient permissions",
                },
            ) from exc
        return current_user

    return dependency
