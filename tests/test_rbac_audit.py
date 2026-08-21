import json
import logging
import re
from io import StringIO

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_agent.config.config import config
from data_agent.config.logger import RedactingFormatter, audit_logger
from data_agent.models.user import Base, User, UserRole
from data_agent.observability.audit import audit_identity_ref, emit_audit_event
from data_agent.observability.context import bind_request_id
from data_agent.services.admin_service import AdminService
from data_agent.services.authorization_service import (
    AuthorizationDeniedError, Permission, ensure_permission)

TEST_JWT_SECRET = "audit-test-secret-with-at-least-32-characters"
VALID_REQUEST_ID = "c" * 32


class _JsonCapture(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.stream = StringIO()
        self.setFormatter(RedactingFormatter())

    def emit(self, record: logging.LogRecord) -> None:
        self.stream.write(self.format(record) + "\n")

    def events(self) -> list[dict[str, object]]:
        return [
            json.loads(line)
            for line in self.stream.getvalue().splitlines()
            if line
        ]


@pytest.fixture
def audit_capture(monkeypatch):
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    capture = _JsonCapture()
    previous_level = audit_logger.level
    audit_logger.setLevel(logging.INFO)
    audit_logger.addHandler(capture)
    try:
        yield capture
    finally:
        audit_logger.removeHandler(capture)
        audit_logger.setLevel(previous_level)


def test_audit_identity_reference_is_stable_and_keyed(audit_capture) -> None:
    first = audit_identity_ref(1)
    second = audit_identity_ref(1)
    other = audit_identity_ref(2)

    assert first == second
    assert first != other
    assert re.fullmatch(r"[0-9a-f]{64}", first)
    assert first != "1"

    with pytest.raises(ValueError):
        audit_identity_ref(0)


def test_role_change_audit_is_bounded_and_correlated(
    audit_capture,
) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with session_factory() as db:
            admin = User(
                username="audit-admin",
                email="audit-admin@example.test",
                hashed_password="private-admin-hash",
                role=UserRole.ADMIN.value,
            )
            target = User(
                username="audit-target",
                email="audit-target@example.test",
                hashed_password="private-target-hash",
                role=UserRole.USER.value,
            )
            db.add_all([admin, target])
            db.commit()
            db.refresh(admin)
            db.refresh(target)

            with bind_request_id(VALID_REQUEST_ID):
                AdminService().change_user_role(
                    db,
                    admin,
                    target_user_id=target.id,
                    role=UserRole.ADMIN,
                )

            actor_ref = audit_identity_ref(admin.id)
            target_ref = audit_identity_ref(target.id)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()

    event = audit_capture.events()[-1]
    assert event["event"] == "admin.role.changed"
    assert event["request_id"] == VALID_REQUEST_ID
    assert event["actor_ref"] == actor_ref
    assert event["target_ref"] == target_ref
    assert event["previous_role"] == "user"
    assert event["role"] == "admin"
    assert event["permission"] == "admin.roles_write"

    rendered = json.dumps(event)
    for forbidden in (
        "audit-admin",
        "audit-target",
        "example.test",
        "private-admin-hash",
        "private-target-hash",
        "user_id",
        "username",
        "email",
        "password",
        "token",
    ):
        assert forbidden not in rendered.lower()


def test_denied_event_does_not_include_target_data(
    audit_capture,
) -> None:
    actor = User(id=5, role=UserRole.USER.value)
    with bind_request_id(VALID_REQUEST_ID):
        with pytest.raises(AuthorizationDeniedError):
            ensure_permission(actor, Permission.ADMIN_USERS_LIST)

    denied = audit_capture.events()[-1]
    assert denied["event"] == "authorization.denied"
    assert denied["decision"] == "denied"
    assert denied["permission"] == "admin.users_list"
    assert "target_ref" not in denied


def test_audit_event_drops_unapproved_fields(audit_capture) -> None:
    emit_audit_event(
        "admin.users.listed",
        operation="users.list",
        outcome="success",
        actor_kind="system",
        event_count=2,
    )

    event = audit_capture.events()[-1]
    assert event["event_count"] == 2
    assert set(event) >= {
        "timestamp",
        "event",
        "operation",
        "outcome",
        "actor_kind",
    }
