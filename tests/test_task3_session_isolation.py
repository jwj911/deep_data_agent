import asyncio
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from data_agent.agent_server import app
from data_agent.config.config import config
from data_agent.config.database import get_db
from data_agent.models.session import Message
from data_agent.models.session import Session as ChatSession
from data_agent.models.user import Base, User
from data_agent.services.auth_service import create_access_token
from data_agent.services.session_service import global_session_service

TEST_JWT_SECRET = "task-3-test-secret-with-at-least-32-characters"


@pytest.fixture
def session_api(monkeypatch):
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

    with session_factory() as db:
        user_a = User(
            username="task3-user-a",
            email="task3-a@example.com",
            hashed_password="unused",
        )
        user_b = User(
            username="task3-user-b",
            email="task3-b@example.com",
            hashed_password="unused",
        )
        db.add_all([user_a, user_b])
        db.commit()
        db.refresh(user_a)
        db.refresh(user_b)
        user_a_id = user_a.id
        user_b_id = user_b.id

    monkeypatch.setattr(config, "JWT_SECRET_KEY", TEST_JWT_SECRET)
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
        if token:
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
            token_a=create_access_token(user_a_id),
            token_b=create_access_token(user_b_id),
            user_a_id=user_a_id,
            user_b_id=user_b_id,
        )
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("POST", "/api/sessions/", {"json": {"title": "Session"}}),
        ("GET", "/api/sessions/", {}),
        ("GET", "/api/sessions/missing", {}),
        (
            "POST",
            "/api/sessions/missing/messages",
            {"json": {"role": "user", "content": "Message"}},
        ),
        ("DELETE", "/api/sessions/missing", {}),
    ],
)
def test_all_session_routes_require_current_user(
    session_api,
    method: str,
    path: str,
    kwargs: dict,
) -> None:
    response = session_api.request(method, path, **kwargs)

    assert response.status_code == 401


def test_session_crud_is_scoped_to_current_user(session_api) -> None:
    created_a = session_api.request(
        "POST",
        "/api/sessions/",
        token=session_api.token_a,
        json={"title": "  User A session  "},
    )
    created_b = session_api.request(
        "POST",
        "/api/sessions/",
        token=session_api.token_b,
        json={"title": "User B session"},
    )

    assert created_a.status_code == 200
    assert created_a.json()["title"] == "User A session"
    assert created_b.status_code == 200
    session_a_id = created_a.json()["session_id"]
    session_b_id = created_b.json()["session_id"]

    list_a = session_api.request(
        "GET",
        "/api/sessions/",
        token=session_api.token_a,
    )
    list_b = session_api.request(
        "GET",
        "/api/sessions/",
        token=session_api.token_b,
    )

    assert [item["session_id"] for item in list_a.json()] == [session_a_id]
    assert [item["session_id"] for item in list_b.json()] == [session_b_id]

    added = session_api.request(
        "POST",
        f"/api/sessions/{session_b_id}/messages",
        token=session_api.token_b,
        json={"role": "assistant", "content": "  Private message  "},
    )

    assert added.status_code == 200
    assert added.json()["content"] == "Private message"

    with session_api.session_factory() as db:
        user_a = db.get(User, session_api.user_a_id)
        user_b = db.get(User, session_api.user_b_id)
        assert user_a is not None
        assert user_b is not None
        owner_session = global_session_service.get_session(
            db,
            session_b_id,
            user_b,
        )
        assert owner_session is not None
        owner_session_id = owner_session.id
        original_updated_at = owner_session.updated_at
        original_message_count = (
            db.query(Message)
            .filter(Message.session_id == owner_session_id)
            .count()
        )
        assert (
            global_session_service.get_session(
                db,
                session_b_id,
                user_a,
            )
            is None
        )
        with pytest.raises(ValueError, match="Session not found"):
            global_session_service.get_messages(
                db,
                session_b_id,
                user_a,
            )

    forbidden_responses = [
        session_api.request(
            "GET",
            f"/api/sessions/{session_b_id}",
            token=session_api.token_a,
        ),
        session_api.request(
            "GET",
            "/api/sessions/does-not-exist",
            token=session_api.token_a,
        ),
        session_api.request(
            "POST",
            f"/api/sessions/{session_b_id}/messages",
            token=session_api.token_a,
            json={"role": "user", "content": "Unauthorized write"},
        ),
        session_api.request(
            "POST",
            "/api/sessions/does-not-exist/messages",
            token=session_api.token_a,
            json={"role": "user", "content": "Missing write"},
        ),
        session_api.request(
            "DELETE",
            f"/api/sessions/{session_b_id}",
            token=session_api.token_a,
        ),
        session_api.request(
            "DELETE",
            "/api/sessions/does-not-exist",
            token=session_api.token_a,
        ),
    ]

    for response in forbidden_responses:
        assert response.status_code == 404
        assert response.json()["detail"] == "Session not found"

    with session_api.session_factory() as db:
        unchanged_session = (
            db.query(ChatSession)
            .filter(ChatSession.id == owner_session_id)
            .one()
        )
        assert unchanged_session.updated_at == original_updated_at
        assert (
            db.query(Message)
            .filter(Message.session_id == owner_session_id)
            .count()
            == original_message_count
        )

    owner_read = session_api.request(
        "GET",
        f"/api/sessions/{session_b_id}",
        token=session_api.token_b,
    )
    owner_delete = session_api.request(
        "DELETE",
        f"/api/sessions/{session_b_id}",
        token=session_api.token_b,
    )

    assert owner_read.status_code == 200
    assert owner_read.json()["messages"][0]["content"] == "Private message"
    assert owner_delete.status_code == 200

    with session_api.session_factory() as db:
        assert (
            db.query(ChatSession)
            .filter(ChatSession.id == owner_session_id)
            .first()
            is None
        )
        assert (
            db.query(Message)
            .filter(Message.session_id == owner_session_id)
            .count()
            == 0
        )


def test_invalid_session_and_message_input_does_not_write(
    session_api,
) -> None:
    invalid_titles = ("   ", "x" * 256)
    for title in invalid_titles:
        response = session_api.request(
            "POST",
            "/api/sessions/",
            token=session_api.token_a,
            json={"title": title},
        )
        assert response.status_code == 422

    created = session_api.request(
        "POST",
        "/api/sessions/",
        token=session_api.token_a,
        json={"title": "Validation session"},
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    with session_api.session_factory() as db:
        chat_session = (
            db.query(ChatSession)
            .filter(ChatSession.session_id == session_id)
            .one()
        )
        chat_session_id = chat_session.id
        original_updated_at = chat_session.updated_at
        assert db.query(ChatSession).count() == 1

    invalid_messages = (
        {"role": "system", "content": "Message"},
        {"role": "user", "content": "   "},
        {"role": "assistant", "content": "x" * 20001},
    )
    for message in invalid_messages:
        response = session_api.request(
            "POST",
            f"/api/sessions/{session_id}/messages",
            token=session_api.token_a,
            json=message,
        )
        assert response.status_code == 422

    with session_api.session_factory() as db:
        unchanged_session = (
            db.query(ChatSession)
            .filter(ChatSession.id == chat_session_id)
            .one()
        )
        assert unchanged_session.updated_at == original_updated_at
        assert (
            db.query(Message)
            .filter(Message.session_id == chat_session_id)
            .count()
            == 0
        )

    for role in ("user", "assistant"):
        response = session_api.request(
            "POST",
            f"/api/sessions/{session_id}/messages",
            token=session_api.token_a,
            json={"role": role, "content": f"  {role} message  "},
        )
        assert response.status_code == 200
        assert response.json()["content"] == f"{role} message"
