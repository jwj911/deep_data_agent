import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from data_agent.config.config import config
from data_agent.models.user import Base, User, UserRole
from data_agent.security import langgraph_auth
from data_agent.services.auth_service import create_access_token

TEST_JWT_SECRET = "langgraph-auth-test-secret-with-at-least-32-characters"


@pytest.fixture
def auth_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )
    Base.metadata.create_all(engine)
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setattr(
        langgraph_auth,
        "get_session_factory",
        lambda: session_factory,
    )
    try:
        yield session_factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _create_user(
    session_factory,
    *,
    username: str = "tenant-user",
    role: UserRole = UserRole.USER,
) -> User:
    with session_factory() as db:
        user = User(
            username=username,
            email=f"{username}@example.test",
            hashed_password="hash",
            role=role.value,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
        return user


def _authorization(user_id: int) -> str:
    return f"Bearer {create_access_token(user_id=user_id)}"


def _auth_error_status(authorization: str | None) -> int:
    with pytest.raises(
        langgraph_auth.Auth.exceptions.HTTPException
    ) as caught:
        langgraph_auth.authenticate(authorization)
    return caught.value.status_code


def test_authenticate_returns_stable_identity_and_current_permissions(
    auth_db,
) -> None:
    user = _create_user(auth_db)
    authorization = _authorization(user.id)

    authenticated = langgraph_auth.authenticate(authorization)

    assert authenticated["identity"] == str(user.id)
    assert authenticated["is_authenticated"] is True
    assert authenticated["permissions"] == [
        "agent.invoke_own",
        "session.delete_own",
        "session.read_own",
        "session.write_own",
    ]
    assert "username" not in authenticated
    assert "email" not in authenticated


def test_authenticate_reads_role_from_database_on_every_request(
    auth_db,
) -> None:
    user = _create_user(auth_db)
    authorization = _authorization(user.id)

    before = langgraph_auth.authenticate(authorization)
    with auth_db() as db:
        stored = db.get(User, user.id)
        stored.role = UserRole.ADMIN.value
        db.commit()
    after = langgraph_auth.authenticate(authorization)

    assert "admin.users_list" not in before["permissions"]
    assert "admin.users_list" in after["permissions"]


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Basic abc",
        "Bearer",
        "Bearer not-a-jwt",
        "Bearer token with-spaces",
    ],
)
def test_authenticate_rejects_missing_or_invalid_credentials(
    auth_db,
    authorization,
) -> None:
    assert _auth_error_status(authorization) == 401


def test_authenticate_rejects_token_for_deleted_user(auth_db) -> None:
    user = _create_user(auth_db)
    authorization = _authorization(user.id)
    with auth_db() as db:
        db.delete(db.get(User, user.id))
        db.commit()

    assert _auth_error_status(authorization) == 401


def test_authenticate_reports_missing_server_configuration(
    auth_db,
    monkeypatch,
) -> None:
    user = _create_user(auth_db)
    authorization = _authorization(user.id)
    monkeypatch.setattr(config, "JWT_SECRET_KEY", None)

    assert _auth_error_status(authorization) == 503


def test_thread_authorization_overwrites_forged_owner() -> None:
    ctx = SimpleNamespace(user=SimpleNamespace(identity="17"))
    value = {"metadata": {"owner": "other-user", "safe": "value"}}

    filters = asyncio.run(
        langgraph_auth.authorize_thread_owner(ctx, value)
    )

    assert filters == {"owner": "17"}
    assert value["metadata"] == {"owner": "17", "safe": "value"}


def test_thread_authorization_adds_missing_metadata() -> None:
    ctx = SimpleNamespace(user=SimpleNamespace(identity="23"))
    value = {"thread_id": "thread"}

    filters = asyncio.run(
        langgraph_auth.authorize_thread_owner(ctx, value)
    )

    assert filters == {"owner": "23"}
    assert value["metadata"] == {"owner": "23"}


def test_unhandled_resources_are_denied() -> None:
    assert (
        asyncio.run(
            langgraph_auth.deny_unhandled(
                SimpleNamespace(),
                {},
            )
        )
        is False
    )


def test_assistant_search_is_forced_to_application_graph() -> None:
    value = {"graph_id": "forged", "metadata": {"safe": "value"}}

    allowed = asyncio.run(
        langgraph_auth.allow_agent_assistant_search(
            SimpleNamespace(),
            value,
        )
    )

    assert allowed == {"graph_id": langgraph_auth.AGENT_GRAPH_ID}
    assert value["graph_id"] == langgraph_auth.AGENT_GRAPH_ID


def test_assistant_read_is_filtered_to_application_graph() -> None:
    filters = asyncio.run(
        langgraph_auth.allow_agent_assistant_read(
            SimpleNamespace(),
            {"assistant_id": "existing"},
        )
    )

    assert filters == {"graph_id": langgraph_auth.AGENT_GRAPH_ID}
