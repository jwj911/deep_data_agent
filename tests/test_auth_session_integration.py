import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from data_agent.agent_server import app
from data_agent.config.config import config
from data_agent.config.database import get_db
from data_agent.models.session import Message
from data_agent.models.session import Session as ChatSession
from data_agent.models.user import Base, User
from data_agent.routes import auth as auth_routes
from data_agent.services.auth_service import ALGORITHM, verify_password

TEST_JWT_SECRET = "test-suite-jwt-secret-with-at-least-32-characters"


@pytest.fixture
def api(monkeypatch):
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
    monkeypatch.setattr(config, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    previous_overrides = app.dependency_overrides.copy()

    def override_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    def request(method: str, path: str, **kwargs) -> httpx.Response:
        async def send() -> httpx.Response:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.request(method, path, **kwargs)

        return asyncio.run(send())

    try:
        yield SimpleNamespace(
            request=request,
            session_factory=session_factory,
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        Base.metadata.drop_all(engine)
        engine.dispose()


def _register(
    api,
    username: str,
    email: str,
    password: str = "correct-password",
) -> httpx.Response:
    return api.request(
        "POST",
        "/api/auth/register",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
    )


def _login(
    api,
    username: str,
    password: str = "correct-password",
) -> httpx.Response:
    return api.request(
        "POST",
        "/api/auth/login",
        data={"username": username, "password": password},
    )


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _signed_token(subject: str, *, expired: bool = False) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=-5 if expired else 5
    )
    return jwt.encode(
        {"sub": subject, "exp": expires_at},
        TEST_JWT_SECRET,
        algorithm=ALGORITHM,
    )


def test_register_login_and_me_use_only_sqlite(api) -> None:
    registered = _register(api, "alice", "alice@example.com")

    assert registered.status_code == 200
    assert registered.json() == {
        "id": registered.json()["id"],
        "username": "alice",
        "email": "alice@example.com",
    }

    with api.session_factory() as db:
        user = db.query(User).filter(User.username == "alice").one()
        assert user.hashed_password != "correct-password"
        assert verify_password("correct-password", user.hashed_password)
        user_id = user.id

    logged_in = _login(api, "alice")

    assert logged_in.status_code == 200
    body = logged_in.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 1800
    payload = jwt.decode(
        body["access_token"],
        TEST_JWT_SECRET,
        algorithms=[ALGORITHM],
    )
    assert payload["sub"] == str(user_id)

    me = api.request(
        "GET",
        "/api/auth/me",
        headers=_auth(body["access_token"]),
    )

    assert me.status_code == 200
    assert me.json() == {
        "id": user_id,
        "username": "alice",
        "email": "alice@example.com",
    }
    assert "hashed_password" not in me.text
    assert "access_token" not in me.text


@pytest.mark.parametrize(
    "headers",
    [
        {},
        _auth("not-a-jwt"),
        _auth(
            jwt.encode(
                {
                    "sub": "1",
                    "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                },
                "wrong-signing-secret-with-at-least-32-characters",
                algorithm=ALGORITHM,
            )
        ),
        _auth(_signed_token("1", expired=True)),
        _auth(_signed_token("not-a-user-id")),
    ],
)
def test_me_rejects_missing_and_invalid_tokens(api, headers) -> None:
    response = api.request("GET", "/api/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == {
        "code": "invalid_credentials",
        "message": "Could not validate credentials",
    }


def test_me_rejects_token_for_deleted_user(api) -> None:
    registered = _register(api, "deleted", "deleted@example.com")
    token = _login(api, "deleted").json()["access_token"]

    with api.session_factory() as db:
        user = db.get(User, registered.json()["id"])
        db.delete(user)
        db.commit()

    response = api.request(
        "GET",
        "/api/auth/me",
        headers=_auth(token),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_missing_jwt_configuration_keeps_health_available(
    api,
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", None)

    health = api.request("GET", "/api/health")
    responses = [
        _register(api, "missing-key", "missing-key@example.com"),
        _login(api, "missing-key"),
        api.request("GET", "/api/auth/me"),
        api.request("GET", "/api/sessions/"),
    ]

    assert health.status_code == 200
    for response in responses:
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "auth_not_configured",
            "message": "Authentication is not configured",
        }


def test_duplicate_registration_and_integrity_race_return_409(
    api,
    monkeypatch,
) -> None:
    assert _register(api, "duplicate", "duplicate@example.com").status_code == 200

    duplicate_username = _register(
        api,
        "duplicate",
        "other@example.com",
    )
    duplicate_email = _register(
        api,
        "other-user",
        "duplicate@example.com",
    )

    assert duplicate_username.status_code == 409
    assert duplicate_email.status_code == 409

    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_email",
        lambda *args, **kwargs: None,
    )
    integrity_race = _register(
        api,
        "duplicate",
        "duplicate@example.com",
    )

    assert integrity_race.status_code == 409
    assert integrity_race.json()["detail"] == {
        "code": "registration_conflict",
        "message": "Username or email is already registered",
    }
    assert "integrity" not in integrity_race.text.lower()

    with api.session_factory() as db:
        assert db.query(User).count() == 1


def test_cors_allows_whitelist_and_rejects_other_origin(api) -> None:
    allowed = api.request(
        "OPTIONS",
        "/api/auth/me",
        headers={
            "Origin": "https://app.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    rejected = api.request(
        "OPTIONS",
        "/api/auth/me",
        headers={
            "Origin": "https://untrusted.example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert allowed.status_code == 200
    assert (
        allowed.headers["access-control-allow-origin"]
        == "https://app.example.test"
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_two_users_are_isolated_for_session_read_write_and_delete(api) -> None:
    user_a = _register(api, "user-a", "user-a@example.com").json()
    user_b = _register(api, "user-b", "user-b@example.com").json()
    token_a = _login(api, "user-a").json()["access_token"]
    token_b = _login(api, "user-b").json()["access_token"]

    session_a = api.request(
        "POST",
        "/api/sessions/",
        headers=_auth(token_a),
        json={"title": "A session"},
    ).json()
    session_b = api.request(
        "POST",
        "/api/sessions/",
        headers=_auth(token_b),
        json={"title": "B session"},
    ).json()
    own_message = api.request(
        "POST",
        f"/api/sessions/{session_b['session_id']}/messages",
        headers=_auth(token_b),
        json={"role": "user", "content": "Private"},
    )
    assert own_message.status_code == 200

    list_a = api.request(
        "GET",
        "/api/sessions/",
        headers=_auth(token_a),
    )
    list_b = api.request(
        "GET",
        "/api/sessions/",
        headers=_auth(token_b),
    )
    assert [item["id"] for item in list_a.json()] == [session_a["id"]]
    assert [item["id"] for item in list_b.json()] == [session_b["id"]]

    with api.session_factory() as db:
        stored_b = db.get(ChatSession, session_b["id"])
        original_updated_at = stored_b.updated_at
        original_message_count = (
            db.query(Message)
            .filter(Message.session_id == stored_b.id)
            .count()
        )

    forbidden = [
        api.request(
            "GET",
            f"/api/sessions/{session_b['session_id']}",
            headers=_auth(token_a),
        ),
        api.request(
            "POST",
            f"/api/sessions/{session_b['session_id']}/messages",
            headers=_auth(token_a),
            json={"role": "assistant", "content": "Unauthorized"},
        ),
        api.request(
            "DELETE",
            f"/api/sessions/{session_b['session_id']}",
            headers=_auth(token_a),
        ),
    ]

    for response in forbidden:
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    with api.session_factory() as db:
        stored_b = db.get(ChatSession, session_b["id"])
        assert stored_b.user_id == user_b["id"]
        assert stored_b.user_id != user_a["id"]
        assert stored_b.updated_at == original_updated_at
        assert (
            db.query(Message)
            .filter(Message.session_id == stored_b.id)
            .count()
            == original_message_count
        )


def test_invalid_session_input_has_no_partial_writes(api) -> None:
    _register(api, "validation", "validation@example.com")
    token = _login(api, "validation").json()["access_token"]

    for title in ("   ", "x" * 256):
        response = api.request(
            "POST",
            "/api/sessions/",
            headers=_auth(token),
            json={"title": title},
        )
        assert response.status_code == 422

    with api.session_factory() as db:
        assert db.query(ChatSession).count() == 0

    created = api.request(
        "POST",
        "/api/sessions/",
        headers=_auth(token),
        json={"title": "Validation"},
    ).json()

    with api.session_factory() as db:
        stored = db.get(ChatSession, created["id"])
        original_updated_at = stored.updated_at

    invalid_messages = [
        {"role": "system", "content": "Message"},
        {"role": "user", "content": "   "},
        {"role": "assistant", "content": "x" * 20001},
    ]
    for message in invalid_messages:
        response = api.request(
            "POST",
            f"/api/sessions/{created['session_id']}/messages",
            headers=_auth(token),
            json=message,
        )
        assert response.status_code == 422

    with api.session_factory() as db:
        stored = db.get(ChatSession, created["id"])
        assert stored.updated_at == original_updated_at
        assert db.query(Message).count() == 0
