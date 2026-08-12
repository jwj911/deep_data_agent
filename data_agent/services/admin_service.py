import logging

from sqlalchemy.orm import Session

from data_agent.models.user import User, UserRole
from data_agent.observability.audit import emit_audit_event
from data_agent.services.authorization_service import (Permission,
                                                       ensure_permission)


class UserNotFoundError(LookupError):
    """Raised when an authorized administrator targets a missing user."""


class SelfRoleChangeError(ValueError):
    """Raised when an administrator attempts to change their own role."""


class AdminService:
    """Authorized user listing and role management."""

    def list_users(
        self,
        db: Session,
        actor: User,
        *,
        offset: int,
        limit: int,
    ) -> list[User]:
        ensure_permission(actor, Permission.ADMIN_USERS_LIST)
        if offset < 0 or not 1 <= limit <= 100:
            raise ValueError("invalid pagination bounds")
        users = (
            db.query(User)
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
            .all()
        )
        emit_audit_event(
            "admin.users.listed",
            operation="users.list",
            outcome="success",
            actor_kind="user",
            actor_user_id=actor.id,
            permission=Permission.ADMIN_USERS_LIST.value,
            decision="allowed",
            event_count=len(users),
        )
        return users

    def change_user_role(
        self,
        db: Session,
        actor: User,
        *,
        target_user_id: int,
        role: UserRole,
    ) -> User:
        ensure_permission(actor, Permission.ADMIN_ROLES_WRITE)
        if (
            not isinstance(target_user_id, int)
            or isinstance(target_user_id, bool)
            or target_user_id <= 0
        ):
            raise UserNotFoundError("user not found")
        if not isinstance(role, UserRole):
            raise ValueError("invalid role")
        if actor.id == target_user_id:
            emit_audit_event(
                "admin.role_change.rejected",
                operation="users.role_change",
                outcome="rejected",
                actor_kind="user",
                actor_user_id=actor.id,
                target_user_id=target_user_id,
                permission=Permission.ADMIN_ROLES_WRITE.value,
                decision="allowed",
                previous_role=actor.role,
                role=role.value,
                level=logging.WARNING,
            )
            raise SelfRoleChangeError("administrators cannot change own role")

        target = db.query(User).filter(User.id == target_user_id).first()
        if target is None:
            emit_audit_event(
                "admin.role_change.rejected",
                operation="users.role_change",
                outcome="rejected",
                actor_kind="user",
                actor_user_id=actor.id,
                permission=Permission.ADMIN_ROLES_WRITE.value,
                decision="allowed",
                level=logging.WARNING,
            )
            raise UserNotFoundError("user not found")

        previous_role = target.role
        if previous_role != role.value:
            target.role = role.value
            try:
                db.commit()
            except Exception:
                db.rollback()
                raise
            db.refresh(target)

        emit_audit_event(
            "admin.role.changed",
            operation="users.role_change",
            outcome="success",
            actor_kind="user",
            actor_user_id=actor.id,
            target_user_id=target.id,
            permission=Permission.ADMIN_ROLES_WRITE.value,
            decision="allowed",
            previous_role=previous_role,
            role=role.value,
        )
        return target


global_admin_service = AdminService()
