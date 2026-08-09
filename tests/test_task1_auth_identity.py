import asyncio
from datetime import timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException
from jose import jwt

from data_agent.config.config import Config, ConfigurationError, config
from data_agent.config.database import get_db
from data_agent.models.user import User
from data_agent.services.auth_service import (ALGORITHM, create_access_token,
                                              decode_access_token,
                                              get_current_user,
                                              require_auth_configured)

TEST_JWT_SECRET = "task-1-test-secret-with-at-least-32-characters"


def _run_request(
    method: str,
    path: str,
    **kwargs,
) -> httpx.Response:
    from data_agent.agent_server import app

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(request())


def test_auth_config_rejects_missing_short_and_placeholder_secrets(
    monkeypatch,
) -> None:
    for value in ("", "too-short", "your_jwt_secret_key_here"):
        monkeypatch.setenv("JWT_SECRET_KEY", value)
        runtime_config = Config()

        with pytest.raises(ConfigurationError, match="at least 32"):
            runtime_config.require_jwt_secret_key()


def test_auth_config_parses_expiry_cors_and_rest_url(monkeypatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000, https://app.example.com/",
    )
    monkeypatch.setenv(
        "NEXT_PUBLIC_REST_API_URL",
        "https://api.example.com/",
    )

    runtime_config = Config()

    assert runtime_config.require_jwt_secret_key() == TEST_JWT_SECRET
    assert runtime_config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES == 45
    assert runtime_config.CORS_ALLOWED_ORIGINS == (
        "http://localhost:3000",
        "https://app.example.com",
    )
    assert runtime_config.NEXT_PUBLIC_REST_API_URL == "https://api.example.com"


def test_auth_config_rejects_wildcard_cors_with_credentials(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")

    with pytest.raises(ConfigurationError, match="cannot contain"):
        Config()


def test_missing_auth_config_keeps_health_available(monkeypatch) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", None)

    health = _run_request("GET", "/api/health")
    auth = _run_request(
        "POST",
        "/api/auth/register",
        json={
            "username": "task1user",
            "email": "task1@example.com",
            "password": "password",
        },
    )
    sessions = _run_request("GET", "/api/sessions/")

    assert health.status_code == 200
    for response in (auth, sessions):
        assert response.status_code == 503
        assert response.json()["detail"] == {
            "code": "auth_not_configured",
            "message": "Authentication is not configured",
        }


def test_access_token_uses_positive_user_id_subject_and_utc_expiry(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)

    token = create_access_token(42, expires_delta=timedelta(minutes=5))
    payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=[ALGORITHM])

    assert payload["sub"] == "42"
    assert isinstance(payload["exp"], int)
    assert decode_access_token(token) == 42


@pytest.mark.parametrize(
    "token",
    (
        "not-a-jwt",
        jwt.encode(
            {"sub": "1"},
            "another-test-secret-with-at-least-32-characters",
            algorithm=ALGORITHM,
        ),
        jwt.encode(
            {"sub": "0"},
            TEST_JWT_SECRET,
            algorithm=ALGORITHM,
        ),
        jwt.encode(
            {"sub": "-1"},
            TEST_JWT_SECRET,
            algorithm=ALGORITHM,
        ),
        jwt.encode(
            {"sub": "01"},
            TEST_JWT_SECRET,
            algorithm=ALGORITHM,
        ),
        jwt.encode(
            {"sub": "user"},
            TEST_JWT_SECRET,
            algorithm=ALGORITHM,
        ),
        jwt.encode(
            {"sub": "1"},
            TEST_JWT_SECRET,
            algorithm=ALGORITHM,
        ),
    ),
)
def test_decode_access_token_rejects_invalid_credentials(
    monkeypatch,
    token: str,
) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)

    with pytest.raises(HTTPException) as caught:
        decode_access_token(token)

    assert caught.value.status_code == 401
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}
    assert caught.value.detail["code"] == "invalid_credentials"


def test_decode_access_token_rejects_expired_token(monkeypatch) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    token = create_access_token(1, expires_delta=timedelta(seconds=-1))

    with pytest.raises(HTTPException) as caught:
        decode_access_token(token)

    assert caught.value.status_code == 401
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}


def test_get_current_user_rejects_missing_and_deleted_user(
    monkeypatch,
) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as missing:
        get_current_user(token=None, db=db)
    assert missing.value.status_code == 401

    token = create_access_token(99)
    with pytest.raises(HTTPException) as deleted:
        get_current_user(token=token, db=db)
    assert deleted.value.status_code == 401
    assert deleted.value.detail == missing.value.detail


def test_me_returns_only_public_user_fields(monkeypatch) -> None:
    from data_agent.agent_server import app

    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
    user = User(
        id=7,
        username="public-user",
        email="public@example.com",
        hashed_password="must-not-be-returned",
    )
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = user

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        response = _run_request(
            "GET",
            "/api/auth/me",
            headers={"Authorization": f"Bearer {create_access_token(7)}"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "username": "public-user",
        "email": "public@example.com",
    }


def test_cors_allows_configured_origin_and_rejects_other_origin() -> None:
    allowed = _run_request(
        "OPTIONS",
        "/api/auth/me",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    rejected = _run_request(
        "OPTIONS",
        "/api/auth/me",
        headers={
            "Origin": "https://untrusted.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert allowed.status_code == 200
    assert (
        allowed.headers["access-control-allow-origin"]
        == "http://localhost:3000"
    )
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_require_auth_configured_uses_stable_503(monkeypatch) -> None:
    monkeypatch.setattr(config, "JWT_SECRET_KEY", None)

    with pytest.raises(HTTPException) as caught:
        require_auth_configured()

    assert caught.value.status_code == 503
    assert caught.value.detail == {
        "code": "auth_not_configured",
        "message": "Authentication is not configured",
    }
