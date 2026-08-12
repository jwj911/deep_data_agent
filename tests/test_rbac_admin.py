import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from data_agent.agent_server import app
from data_agent.config.config import config
from data_agent.config.database import get_db
from data_agent.models.user import Base, User, UserRole
from data_agent.services.admin_service import global_admin_service
from data_agent.services.auth_service import create_access_token
from data_agent.services.authorization_service import (
    ROLE_PERMISSIONS, AuthorizationDeniedError, Permission, ensure_permission,
    has_permission)

TEST_JWT_SECRET = "rbac-test-secret-with-at-least-32-characters"


@pytest.fixture
def rbac_api(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)

    with session_factory() as db:
        admin = User(
            username="rbac-admin",
            email="rbac-admin@example.test",
            hashed_password="unused",
            role=UserRole.ADMIN.value,
        )
        user = User(
            username="rbac-user",
            email="rbac-user@example.test",
            hashed_password="unused",
            role=UserRole.USER.value,
        )
        target = User(
            username="rbac-target",
            email="rbac-target@example.test",
            hashed_password="unused",
            role=UserRole.USER.value,
        )
        db.add_all([admin, user, target])
        db.commit()
        db.refresh(admin)
        db.refresh(user)
        db.refresh(target)
        ids = {
            "admin": admin.id,
            "user": user.id,
            "target": target.id,
        }

    previous_overrides = app.dependency_overrides.copy()

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    def request(
        method: str,
        path: str,
        *,
        token: str | None = None,
        **kwargs,
    ) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token is not None:
            headers = {
                **headers,
                "Authorization": f"Bearer {token}",
            }

        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(
                    method,
                    path,
                    headers=headers,
                    **kwargs,
                )

        return asyncio.run(send())

    try:
        yield SimpleNamespace(
            request=request,
            session_factory=session_factory,
            admin_id=ids["admin"],
            user_id=ids["user"],
            target_id=ids["target"],
            admin_token=create_access_token(ids["admin"]),
            user_token=create_access_token(ids["user"]),
            target_token=create_access_token(ids["target"]),
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_role_matrix_is_explicit_and_default_deny() -> None:
    assert set(ROLE_PERMISSIONS) == {"user", "admin"}
    assert has_permission(
        UserRole.USER, Permission.SESSION_READ_OWN
    )
    assert not has_permission(
        UserRole.USER, Permission.ADMIN_USERS_LIST
    )
    assert has_permission(
        UserRole.ADMIN, Permission.ADMIN_ROLES_WRITE
    )
    assert not has_permission("owner", Permission.ADMIN_ROLES_WRITE)
    assert not has_permission(UserRole.ADMIN, "admin.roles_write")

    unknown = User(id=99, role="owner")
    with pytest.raises(AuthorizationDeniedError):
        ensure_permission(unknown, Permission.ADMIN_USERS_LIST)


def test_admin_service_rejects_before_query() -> None:
    db = Mock()
    actor = User(id=7, role=UserRole.USER.value)

    with pytest.raises(AuthorizationDeniedError):
        global_admin_service.list_users(
            db,
            actor,
            offset=0,
            limit=50,
        )

    db.query.assert_not_called()

    admin = User(id=8, role=UserRole.ADMIN.value)
    with pytest.raises(ValueError, match="pagination"):
        global_admin_service.list_users(
            db,
            admin,
            offset=0,
            limit=101,
        )
    with pytest.raises(ValueError, match="invalid role"):
        global_admin_service.change_user_role(
            db,
            admin,
            target_user_id=9,
            role="owner",
        )
    db.query.assert_not_called()


def test_admin_api_authorization_and_role_refresh(rbac_api) -> None:
    assert rbac_api.request(
        "GET", "/api/admin/users"
    ).status_code == 401

    forbidden = rbac_api.request(
        "PATCH",
        "/api/admin/users/999/role",
        token=rbac_api.user_token,
        json={"role": "admin"},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["detail"]["code"] == "forbidden"

    listed = rbac_api.request(
        "GET",
        "/api/admin/users?offset=1&limit=2",
        token=rbac_api.admin_token,
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [
        rbac_api.user_id,
        rbac_api.target_id,
    ]
    assert all("hashed_password" not in item for item in listed.json())
    assert all(item["role"] == "user" for item in listed.json())

    for path in (
        "/api/admin/users?offset=-1",
        "/api/admin/users?limit=0",
        "/api/admin/users?limit=101",
    ):
        assert rbac_api.request(
            "GET",
            path,
            token=rbac_api.admin_token,
        ).status_code == 422

    promoted = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.target_id}/role",
        token=rbac_api.admin_token,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    promoted_again = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.target_id}/role",
        token=rbac_api.admin_token,
        json={"role": "admin"},
    )
    assert promoted_again.status_code == 200
    assert rbac_api.request(
        "GET",
        "/api/admin/users",
        token=rbac_api.target_token,
    ).status_code == 200

    demoted = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.target_id}/role",
        token=rbac_api.admin_token,
        json={"role": "user"},
    )
    assert demoted.status_code == 200
    assert rbac_api.request(
        "GET",
        "/api/admin/users",
        token=rbac_api.target_token,
    ).status_code == 403

    self_change = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.admin_id}/role",
        token=rbac_api.admin_token,
        json={"role": "user"},
    )
    assert self_change.status_code == 409
    assert (
        self_change.json()["detail"]["code"]
        == "self_role_change_forbidden"
    )

    missing = rbac_api.request(
        "PATCH",
        "/api/admin/users/999/role",
        token=rbac_api.admin_token,
        json={"role": "admin"},
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "user_not_found"

    invalid = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.user_id}/role",
        token=rbac_api.admin_token,
        json={"role": "owner"},
    )
    assert invalid.status_code == 422


def test_registration_cannot_assign_role(rbac_api) -> None:
    response = rbac_api.request(
        "POST",
        "/api/auth/register",
        json={
            "username": "role-injection",
            "email": "role-injection@example.test",
            "password": "correct-password",
            "role": "admin",
        },
    )

    assert response.status_code == 422
    with rbac_api.session_factory() as db:
        assert (
            db.query(User)
            .filter(User.username == "role-injection")
            .first()
            is None
        )


def test_admin_role_does_not_bypass_session_ownership(rbac_api) -> None:
    created = rbac_api.request(
        "POST",
        "/api/sessions/",
        token=rbac_api.target_token,
        json={"title": "Target session"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    assert rbac_api.request(
        "GET",
        f"/api/sessions/{session_id}",
        token=rbac_api.user_token,
    ).status_code == 404
    promoted = rbac_api.request(
        "PATCH",
        f"/api/admin/users/{rbac_api.user_id}/role",
        token=rbac_api.admin_token,
        json={"role": "admin"},
    )
    assert promoted.status_code == 200

    responses = (
        rbac_api.request(
            "GET",
            f"/api/sessions/{session_id}",
            token=rbac_api.user_token,
        ),
        rbac_api.request(
            "POST",
            f"/api/sessions/{session_id}/messages",
            token=rbac_api.user_token,
            json={"role": "user", "content": "Unauthorized"},
        ),
        rbac_api.request(
            "DELETE",
            f"/api/sessions/{session_id}",
            token=rbac_api.user_token,
        ),
    )
    assert all(response.status_code == 404 for response in responses)
    assert rbac_api.request(
        "GET",
        f"/api/sessions/{session_id}",
        token=rbac_api.target_token,
    ).status_code == 200


def test_cors_allows_patch_only_for_allowlisted_origin(rbac_api) -> None:
    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "PATCH",
        "Access-Control-Request-Headers": "Authorization,X-Request-ID",
    }
    allowed = rbac_api.request(
        "OPTIONS",
        f"/api/admin/users/{rbac_api.target_id}/role",
        headers=headers,
    )
    denied = rbac_api.request(
        "OPTIONS",
        f"/api/admin/users/{rbac_api.target_id}/role",
        headers={**headers, "Origin": "https://evil.example"},
    )

    assert allowed.status_code == 200
    assert "PATCH" in allowed.headers["access-control-allow-methods"]
    assert allowed.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
    assert "access-control-allow-origin" not in denied.headers
