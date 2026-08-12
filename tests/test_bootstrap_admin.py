from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from data_agent.models.user import Base, User, UserRole
from scripts import bootstrap_admin


@pytest.fixture
def bootstrap_db(monkeypatch):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    with session_factory() as db:
        user = User(
            username="bootstrap-user",
            email="bootstrap-user@example.test",
            hashed_password="private-hash",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

    audit = Mock()
    monkeypatch.setattr(bootstrap_admin, "init_db", lambda: None)
    monkeypatch.setattr(
        bootstrap_admin,
        "get_session_factory",
        lambda: session_factory,
    )
    monkeypatch.setattr(bootstrap_admin, "emit_audit_event", audit)
    try:
        yield session_factory, user_id, audit
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_bootstrap_promotes_existing_user_idempotently(
    bootstrap_db,
    capsys,
) -> None:
    session_factory, user_id, audit = bootstrap_db

    assert bootstrap_admin.main(["--user-id", str(user_id)]) == 0
    first_output = capsys.readouterr()
    assert first_output.out == "Administrator role is active.\n"
    assert first_output.err == ""
    assert str(user_id) not in first_output.out

    with session_factory() as db:
        assert db.get(User, user_id).role == UserRole.ADMIN.value

    assert bootstrap_admin.main(["--user-id", str(user_id)]) == 0
    second_output = capsys.readouterr()
    assert second_output.out == "Administrator role is active.\n"
    assert second_output.err == ""

    assert audit.call_count == 2
    assert audit.call_args.kwargs["previous_role"] == "admin"
    assert audit.call_args.kwargs["role"] == "admin"


def test_bootstrap_missing_user_is_generic(
    bootstrap_db,
    capsys,
) -> None:
    _, _, audit = bootstrap_db

    assert bootstrap_admin.main(["--user-id", "999"]) == 3
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "Unable to activate administrator role.\n"
    assert "999" not in output.err
    audit.assert_not_called()


def test_bootstrap_invalid_input_does_not_echo_value(
    bootstrap_db,
    capsys,
) -> None:
    _, _, audit = bootstrap_db
    sensitive_input = "mistaken-email@example.test"

    with pytest.raises(SystemExit) as exc_info:
        bootstrap_admin.main(["--user-id", sensitive_input])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert sensitive_input not in output.err
    assert "Invalid administrator bootstrap arguments." in output.err
    audit.assert_not_called()


def test_bootstrap_rejects_unsupported_identity_selector(
    bootstrap_db,
    capsys,
) -> None:
    _, _, audit = bootstrap_db

    with pytest.raises(SystemExit) as exc_info:
        bootstrap_admin.main(["--email", "user@example.test"])

    assert exc_info.value.code == 2
    output = capsys.readouterr()
    assert "user@example.test" not in output.err
    audit.assert_not_called()
