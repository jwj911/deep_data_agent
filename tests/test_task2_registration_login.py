import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from data_agent.config.config import config
from data_agent.routes import auth as auth_routes
from data_agent.routes.auth import UserCreate, UserResponse
from data_agent.services import auth_service
from data_agent.services.auth_service import UserAlreadyExistsError


def _login_form(
    username: str = "alice",
    password: str = "correct-password",
) -> OAuth2PasswordRequestForm:
    return OAuth2PasswordRequestForm(
        username=username,
        password=password,
    )


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        (
            {
                "username": "ab",
                "email": "alice@example.com",
                "password": "correct-password",
            },
            "username",
        ),
        (
            {
                "username": "alice",
                "email": "not-an-email",
                "password": "correct-password",
            },
            "email",
        ),
        (
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": "short",
            },
            "password",
        ),
    ],
)
def test_registration_input_validation(payload: dict, field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        UserCreate.model_validate(payload)

    assert field in str(caught.value)


def test_registration_normalizes_username_and_public_response() -> None:
    request = UserCreate(
        username="  alice  ",
        email="alice@example.com",
        password="correct-password",
    )
    user = SimpleNamespace(
        id=1,
        username=request.username,
        email=str(request.email),
        hashed_password="private-hash",
        role="user",
    )

    response = UserResponse.model_validate(user).model_dump()

    assert request.username == "alice"
    assert response == {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
        "role": "user",
    }
    assert "hashed_password" not in response


@pytest.mark.parametrize("conflict_field", ["username", "email"])
def test_registration_precheck_returns_stable_409(
    monkeypatch,
    conflict_field: str,
) -> None:
    existing_user = object()
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        Mock(
            return_value=existing_user
            if conflict_field == "username"
            else None
        ),
    )
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_email",
        Mock(
            return_value=existing_user
            if conflict_field == "email"
            else None
        ),
    )
    create_user = Mock()
    monkeypatch.setattr(auth_routes, "create_user", create_user)

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            auth_routes.register(
                UserCreate(
                    username="alice",
                    email="alice@example.com",
                    password="correct-password",
                ),
                db=Mock(),
            )
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == {
        "code": "registration_conflict",
        "message": "Username or email is already registered",
    }
    create_user.assert_not_called()


def test_registration_integrity_race_rolls_back(monkeypatch) -> None:
    db = Mock()
    db.commit.side_effect = IntegrityError(
        "INSERT INTO users",
        {},
        RuntimeError("duplicate"),
    )
    monkeypatch.setattr(
        auth_service,
        "get_password_hash",
        Mock(return_value="hashed"),
    )

    with pytest.raises(UserAlreadyExistsError):
        auth_service.create_user(
            db,
            "alice",
            "alice@example.com",
            "correct-password",
        )

    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def test_registration_integrity_race_returns_stable_409(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_email",
        Mock(return_value=None),
    )
    monkeypatch.setattr(
        auth_routes,
        "create_user",
        Mock(side_effect=UserAlreadyExistsError("private database detail")),
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(
            auth_routes.register(
                UserCreate(
                    username="alice",
                    email="alice@example.com",
                    password="correct-password",
                ),
                db=Mock(),
            )
        )

    assert caught.value.status_code == 409
    assert "private database detail" not in str(caught.value.detail)


def test_login_returns_user_id_token_and_expiry(monkeypatch) -> None:
    user = SimpleNamespace(id=7, hashed_password="hashed")
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        Mock(return_value=user),
    )
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        Mock(return_value=True),
    )
    create_access_token = Mock(return_value="signed-token")
    monkeypatch.setattr(
        auth_routes,
        "create_access_token",
        create_access_token,
    )
    monkeypatch.setattr(config, "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 45)

    response = asyncio.run(
        auth_routes.login(
            _login_form(username="  alice  "),
            db=Mock(),
        )
    )

    assert response == {
        "access_token": "signed-token",
        "token_type": "bearer",
        "expires_in": 2700,
    }
    create_access_token.assert_called_once()
    assert create_access_token.call_args.kwargs["user_id"] == 7
    assert (
        create_access_token.call_args.kwargs[
            "expires_delta"
        ].total_seconds()
        == 2700
    )


@pytest.mark.parametrize(
    ("user", "password_valid"),
    [(None, False), (SimpleNamespace(hashed_password="hashed"), False)],
)
def test_login_failure_is_uniform_401(
    monkeypatch,
    user,
    password_valid: bool,
) -> None:
    monkeypatch.setattr(
        auth_routes,
        "get_user_by_username",
        Mock(return_value=user),
    )
    monkeypatch.setattr(
        auth_routes,
        "verify_password",
        Mock(return_value=password_valid),
    )

    with pytest.raises(HTTPException) as caught:
        asyncio.run(auth_routes.login(_login_form(), db=Mock()))

    assert caught.value.status_code == 401
    assert caught.value.detail == {
        "code": "invalid_credentials",
        "message": "Incorrect username or password",
    }
    assert caught.value.headers == {"WWW-Authenticate": "Bearer"}
