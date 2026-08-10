import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import DateTime, create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from data_agent.models.session import Message
from data_agent.models.session import Session as ChatSession
from data_agent.models.user import Base, User, utc_now
from data_agent.routes.session import MessageResponse, SessionResponse
from data_agent.services.session_service import SessionService


@pytest.fixture
def db_session():
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
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _create_user(db_session, suffix: str = "primary") -> User:
    user = User(
        username=f"orm-{suffix}",
        email=f"orm-{suffix}@example.test",
        hashed_password="unused",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_models_share_metadata_and_use_timezone_less_datetime_columns():
    assert User.metadata is Base.metadata
    assert ChatSession.metadata is Base.metadata
    assert Message.metadata is Base.metadata

    datetime_columns = (
        User.created_at,
        User.updated_at,
        ChatSession.created_at,
        ChatSession.updated_at,
        Message.created_at,
    )
    for column in datetime_columns:
        assert isinstance(column.type, DateTime)
        assert column.type.timezone is False


def test_utc_now_returns_current_naive_utc():
    before = datetime.now(UTC).replace(tzinfo=None)
    value = utc_now()
    after = datetime.now(UTC).replace(tzinfo=None)

    assert value.tzinfo is None
    assert before <= value <= after


def test_created_timestamps_are_compatible_with_response_iso_json(db_session):
    service = SessionService()
    user = _create_user(db_session)
    chat_session = service.create_session(db_session, user.id, "UTC test")
    message = service.add_message(
        db_session,
        chat_session.session_id,
        user.id,
        "user",
        "hello",
    )

    timestamps = (
        user.created_at,
        user.updated_at,
        chat_session.created_at,
        chat_session.updated_at,
        message.created_at,
    )
    assert all(value is not None and value.tzinfo is None for value in timestamps)

    session_json = json.loads(
        SessionResponse.model_validate(chat_session).model_dump_json()
    )
    message_json = json.loads(
        MessageResponse.model_validate(message).model_dump_json()
    )
    assert session_json["created_at"] == chat_session.created_at.isoformat()
    assert session_json["updated_at"] == chat_session.updated_at.isoformat()
    assert message_json["created_at"] == message.created_at.isoformat()


def test_updates_refresh_user_and_session_ordering(db_session):
    service = SessionService()
    user = _create_user(db_session, "ordering")

    old_user_update = utc_now() - timedelta(days=3)
    user.updated_at = old_user_update
    db_session.commit()
    user.email = "orm-ordering-updated@example.test"
    db_session.commit()
    db_session.refresh(user)
    assert user.updated_at > old_user_update

    first = service.create_session(db_session, user.id, "First")
    second = service.create_session(db_session, user.id, "Second")
    first.updated_at = utc_now() - timedelta(days=2)
    second.updated_at = utc_now() - timedelta(days=1)
    db_session.commit()

    assert service.get_sessions(db_session, user.id) == [second, first]
    previous_first_update = first.updated_at

    service.add_message(
        db_session,
        first.session_id,
        user.id,
        "assistant",
        "new activity",
    )
    db_session.refresh(first)

    assert first.updated_at > previous_first_update
    assert service.get_sessions(db_session, user.id) == [first, second]
