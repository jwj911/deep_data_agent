import asyncio
import logging
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path

import httpx
import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers
from starlette.datastructures import UploadFile as StarletteUploadFile

from data_agent import agent_server
from data_agent.config.config import Config, ConfigurationError, config
from data_agent.config.database import get_db
from data_agent.config.logger import RedactingFormatter, file_logger
from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import Base, User, UserRole, utc_now
from data_agent.security.upload_limit_middleware import \
    FileUploadBodyLimitMiddleware
from data_agent.services.auth_service import get_current_user
from data_agent.services.authorization_service import AuthorizationDeniedError
from data_agent.services.managed_file_service import (ManagedFileError,
                                                      ManagedFileService)
from data_agent.tools import document_analysis


class _CaptureHandler(logging.StreamHandler):
    def __init__(self) -> None:
        self.stream = StringIO()
        super().__init__(self.stream)
        self.setFormatter(RedactingFormatter())


@pytest.fixture
def file_context(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(config, "FILE_STORAGE_ROOT", str(tmp_path / "files"))
    monkeypatch.setattr(config, "FILE_UPLOAD_MAX_BYTES", 64)
    monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_BYTES", 128)
    monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_COUNT", 5)
    monkeypatch.setattr(config, "FILE_USER_QUOTA_BYTES", 256)
    monkeypatch.setattr(config, "FILE_USER_MAX_COUNT", 10)
    monkeypatch.setattr(config, "FILE_RETENTION_HOURS", 24)
    monkeypatch.setattr(config, "FILE_ANALYSIS_MAX_CHARS", 12)
    with factory() as db:
        users = [
            User(
                username="file-user-a",
                email="file-a@example.test",
                hashed_password="hash",
                role=UserRole.USER.value,
            ),
            User(
                username="file-user-b",
                email="file-b@example.test",
                hashed_password="hash",
                role=UserRole.USER.value,
            ),
            User(
                username="file-admin",
                email="file-admin@example.test",
                hashed_password="hash",
                role=UserRole.ADMIN.value,
            ),
        ]
        db.add_all(users)
        db.commit()
        for user in users:
            db.refresh(user)
            db.expunge(user)
    try:
        yield factory, users, ManagedFileService()
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _upload(
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
) -> StarletteUploadFile:
    return StarletteUploadFile(
        file=BytesIO(content),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


def _store(service, db, actor, *uploads):
    return asyncio.run(
        service.upload_files(db, actor, list(uploads))
    )


def test_file_config_defaults_and_relationships(monkeypatch) -> None:
    variables = (
        "FILE_STORAGE_ROOT",
        "FILE_UPLOAD_MAX_BYTES",
        "FILE_UPLOAD_BATCH_MAX_BYTES",
        "FILE_UPLOAD_REQUEST_MAX_BYTES",
        "FILE_UPLOAD_BATCH_MAX_COUNT",
        "FILE_USER_QUOTA_BYTES",
        "FILE_USER_MAX_COUNT",
        "FILE_RETENTION_HOURS",
        "FILE_ANALYSIS_MAX_CHARS",
    )
    for variable in variables:
        monkeypatch.delenv(variable, raising=False)

    runtime = Config()

    assert runtime.FILE_STORAGE_ROOT == "var/managed_files"
    assert runtime.FILE_UPLOAD_MAX_BYTES == 5 * 1024 * 1024
    assert runtime.FILE_UPLOAD_BATCH_MAX_BYTES == 10 * 1024 * 1024
    assert runtime.FILE_UPLOAD_REQUEST_MAX_BYTES == 11 * 1024 * 1024
    assert runtime.FILE_UPLOAD_BATCH_MAX_COUNT == 5
    assert runtime.FILE_USER_QUOTA_BYTES == 100 * 1024 * 1024
    assert runtime.FILE_USER_MAX_COUNT == 100
    assert runtime.FILE_RETENTION_HOURS == 168
    assert runtime.FILE_ANALYSIS_MAX_CHARS == 20000

    monkeypatch.setenv("FILE_UPLOAD_MAX_BYTES", "10")
    monkeypatch.setenv("FILE_UPLOAD_BATCH_MAX_BYTES", "9")
    with pytest.raises(
        ConfigurationError,
        match="FILE_UPLOAD_BATCH_MAX_BYTES",
    ):
        Config()


def test_upload_list_analyze_and_delete(file_context) -> None:
    factory, users, service = file_context
    actor = users[0]
    with factory() as db:
        records = _store(
            service,
            db,
            actor,
            _upload("notes.txt", b"hello managed file"),
        )

        assert len(records) == 1
        record = records[0]
        assert record.user_id == actor.id
        assert record.media_type == "text/plain"
        assert record.storage_key != record.original_name
        assert service.list_files(db, actor)[0].file_id == record.file_id

        analysis = service.analyze_file(db, actor, record.file_id)
        assert analysis["content"] == "hello manage"
        assert analysis["content_truncated"] is True
        assert analysis["filename"] == "notes.txt"

        assert service.delete_file(db, actor, record.file_id) is True
        assert service.get_file(db, actor, record.file_id) is None
        assert service.delete_file(db, actor, record.file_id) is False
        assert not (
            Path(config.FILE_STORAGE_ROOT) / record.storage_key
        ).exists()


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "code"),
    [
        ("bad.pdf", b"%PDF-1.7", "application/pdf", "unsupported_file_type"),
        ("double.csv.txt", b"safe", "text/plain", "unsupported_file_type"),
        ("bad.txt", b"\xff", "text/plain", "invalid_file_content"),
        ("nul.txt", b"a\x00b", "text/plain", "invalid_file_content"),
        ("bad.json", b"{", "application/json", "invalid_file_content"),
        (
            "formula.csv",
            b"name,value\nsafe,=cmd()\n",
            "text/csv",
            "unsafe_csv_formula",
        ),
        (
            "wrong.json",
            b'{"safe": true}',
            "text/csv",
            "unsupported_file_type",
        ),
        ("../escape.txt", b"safe", "text/plain", "invalid_filename"),
    ],
)
def test_invalid_uploads_fail_without_partial_state(
    file_context,
    filename,
    content,
    content_type,
    code,
) -> None:
    factory, users, service = file_context
    with factory() as db:
        with pytest.raises(ManagedFileError) as caught:
            _store(
                service,
                db,
                users[0],
                _upload("safe.txt", b"safe"),
                _upload(filename, content, content_type),
            )

        assert caught.value.code == code
        assert db.query(ManagedFile).count() == 0
        storage_root = config.FILE_STORAGE_ROOT
        assert not any(
            path.is_file()
            for path in Path(storage_root).rglob("*")
        )


def test_file_batch_and_quota_limits_are_enforced(
    file_context,
    monkeypatch,
) -> None:
    factory, users, service = file_context
    actor = users[0]
    with factory() as db:
        monkeypatch.setattr(config, "FILE_UPLOAD_MAX_BYTES", 3)
        with pytest.raises(ManagedFileError, match="file_too_large"):
            _store(service, db, actor, _upload("large.txt", b"1234"))

        monkeypatch.setattr(config, "FILE_UPLOAD_MAX_BYTES", 64)
        monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_COUNT", 1)
        with pytest.raises(ManagedFileError, match="file_count_exceeded"):
            _store(
                service,
                db,
                actor,
                _upload("one.txt", b"one"),
                _upload("two.txt", b"two"),
            )

        monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_COUNT", 5)
        monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_BYTES", 5)
        with pytest.raises(ManagedFileError, match="file_batch_too_large"):
            _store(
                service,
                db,
                actor,
                _upload("one.txt", b"one"),
                _upload("two.txt", b"two"),
            )

        monkeypatch.setattr(config, "FILE_UPLOAD_BATCH_MAX_BYTES", 128)
        _store(service, db, actor, _upload("kept.txt", b"kept"))
        with pytest.raises(ManagedFileError, match="duplicate_file"):
            _store(service, db, actor, _upload("copy.txt", b"kept"))

        monkeypatch.setattr(config, "FILE_USER_MAX_COUNT", 1)
        with pytest.raises(ManagedFileError, match="file_quota_exceeded"):
            _store(service, db, actor, _upload("second.txt", b"other"))


def test_storage_failure_rolls_back_the_entire_batch(
    file_context,
    monkeypatch,
) -> None:
    factory, users, service = file_context
    original = service._write_file
    call_count = 0

    def fail_second(user_id, file_id, suffix, content):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ManagedFileError("file_storage_unavailable", 503)
        return original(user_id, file_id, suffix, content)

    monkeypatch.setattr(service, "_write_file", fail_second)
    with factory() as db:
        with pytest.raises(
            ManagedFileError,
            match="file_storage_unavailable",
        ):
            _store(
                service,
                db,
                users[0],
                _upload("first.txt", b"first"),
                _upload("second.txt", b"second"),
            )

        assert db.query(ManagedFile).count() == 0
        assert not any(
            path.is_file()
            for path in Path(config.FILE_STORAGE_ROOT).rglob("*")
        )


def test_owner_and_admin_cannot_cross_file_boundary(file_context) -> None:
    factory, users, service = file_context
    owner, other, admin = users
    with factory() as db:
        record = _store(
            service,
            db,
            owner,
            _upload("private.txt", b"private"),
        )[0]

        for actor in (other, admin):
            assert service.get_file(db, actor, record.file_id) is None
            assert service.analyze_file(db, actor, record.file_id) is None
            assert service.delete_file(db, actor, record.file_id) is False

        assert service.analyze_file(db, owner, record.file_id)["content"] == (
            "private"
        )


def test_unknown_role_is_denied_before_storage_access(file_context) -> None:
    factory, _, service = file_context
    unknown = User(id=999, role="unknown")
    with factory() as db:
        with pytest.raises(AuthorizationDeniedError):
            _store(service, db, unknown, _upload("safe.txt", b"safe"))
        assert db.query(ManagedFile).count() == 0


def test_expired_file_is_removed_for_only_its_owner(file_context) -> None:
    factory, users, service = file_context
    owner, other, _ = users
    with factory() as db:
        owner_record = _store(
            service,
            db,
            owner,
            _upload("owner.txt", b"owner"),
        )[0]
        other_record = _store(
            service,
            db,
            other,
            _upload("other.txt", b"other"),
        )[0]
        db.query(ManagedFile).filter(
            ManagedFile.file_id == owner_record.file_id
        ).update({"expires_at": utc_now() - timedelta(seconds=1)})
        db.commit()

        assert service.list_files(db, owner) == []
        assert service.get_file(db, other, other_record.file_id) is not None
        assert (
            db.query(ManagedFile)
            .filter(ManagedFile.file_id == owner_record.file_id)
            .first()
            is None
        )


def test_hash_drift_is_rejected(file_context) -> None:
    factory, users, service = file_context
    with factory() as db:
        record = _store(
            service,
            db,
            users[0],
            _upload("drift.txt", b"original"),
        )[0]
        path = service._record_path(record, require_exists=True)
        path.write_bytes(b"tampered")

        with pytest.raises(ManagedFileError, match="file_storage_invalid"):
            service.analyze_file(db, users[0], record.file_id)


def test_storage_key_traversal_and_non_regular_file_are_rejected(
    file_context,
) -> None:
    factory, users, service = file_context
    with factory() as db:
        traversal = _store(
            service,
            db,
            users[0],
            _upload("traversal.txt", b"safe"),
        )[0]
        traversal.storage_key = "../outside.txt"
        db.commit()
        with pytest.raises(ManagedFileError, match="file_storage_invalid"):
            service.analyze_file(db, users[0], traversal.file_id)

        regular = _store(
            service,
            db,
            users[0],
            _upload("directory.txt", b"safe directory"),
        )[0]
        path = service._record_path(regular, require_exists=True)
        path.unlink()
        path.mkdir()
        with pytest.raises(ManagedFileError, match="file_storage_invalid"):
            service.analyze_file(db, users[0], regular.file_id)


def test_symbolic_link_is_rejected(file_context, monkeypatch) -> None:
    factory, users, service = file_context
    with factory() as db:
        record = _store(
            service,
            db,
            users[0],
            _upload("link.txt", b"safe link"),
        )[0]
        path = service._record_path(record, require_exists=True)
        original = Path.is_symlink

        def report_candidate_as_link(candidate: Path) -> bool:
            if candidate == path:
                return True
            return original(candidate)

        monkeypatch.setattr(Path, "is_symlink", report_candidate_as_link)

        with pytest.raises(ManagedFileError, match="file_storage_invalid"):
            service.analyze_file(db, users[0], record.file_id)


def test_file_events_do_not_leak_name_content_path_or_identifier(
    file_context,
) -> None:
    factory, users, service = file_context
    capture = _CaptureHandler()
    file_logger.addHandler(capture)
    try:
        with factory() as db:
            record = _store(
                service,
                db,
                users[0],
                _upload("private-name.txt", b"private-content"),
            )[0]
            service.analyze_file(db, users[0], record.file_id)
            service.delete_file(db, users[0], record.file_id)
    finally:
        file_logger.removeHandler(capture)

    output = capture.stream.getvalue()
    assert "private-name" not in output
    assert "private-content" not in output
    assert record.file_id not in output
    assert record.storage_key not in output
    assert str(config.FILE_STORAGE_ROOT) not in output


def test_document_tool_uses_hidden_authenticated_identity(
    file_context,
    monkeypatch,
) -> None:
    factory, users, service = file_context
    with factory() as db:
        record = _store(
            service,
            db,
            users[0],
            _upload("tool.txt", b"tool content"),
        )[0]
    monkeypatch.setattr(
        document_analysis,
        "get_session_factory",
        lambda: factory,
    )

    tool = StructuredTool.from_function(
        document_analysis.analyze_document,
    )
    schema = tool.args_schema.model_json_schema()
    assert set(schema["properties"]) == {"file_id"}

    result = tool.invoke(
        {"file_id": record.file_id},
        config={
            "configurable": {
                "langgraph_auth_user_id": str(users[0].id),
            }
        },
    )
    assert result["content"] == "tool content"

    cross_user = tool.invoke(
        {"file_id": record.file_id},
        config={
            "configurable": {
                "langgraph_auth_user_id": str(users[1].id),
            }
        },
    )
    assert cross_user == {"error": "managed_file_not_found"}
    assert document_analysis.analyze_document(
        "../../.env",
        {"configurable": {"langgraph_auth_user_id": str(users[0].id)}},
    ) == {"error": "invalid_file_id"}
    assert document_analysis.analyze_document(
        record.file_id,
        {"configurable": {"langgraph_auth_user_id": "forged"}},
    ) == {"error": "managed_file_auth_required"}


def _request(method: str, path: str, **kwargs) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=agent_server.app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_file_api_is_owner_scoped_and_hides_storage_fields(
    file_context,
) -> None:
    factory, users, _ = file_context
    actor = {"value": users[0]}

    def override_db():
        with factory() as db:
            yield db

    previous = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_db] = override_db
    agent_server.app.dependency_overrides[get_current_user] = (
        lambda: actor["value"]
    )
    try:
        response = _request(
            "POST",
            "/api/files",
            files=[
                (
                    "files",
                    ("api.txt", b"api managed content", "text/plain"),
                )
            ],
        )
        assert response.status_code == 201
        payload = response.json()[0]
        assert set(payload) == {
            "file_id",
            "original_name",
            "media_type",
            "size_bytes",
            "created_at",
            "expires_at",
        }
        file_id = payload["file_id"]

        analysis = _request("GET", f"/api/files/{file_id}/analysis")
        assert analysis.status_code == 200
        assert analysis.json()["content"] == "api managed "

        actor["value"] = users[1]
        assert _request("GET", f"/api/files/{file_id}").status_code == 404
        assert _request(
            "GET",
            f"/api/files/{file_id}/analysis",
        ).status_code == 404
        assert _request("DELETE", f"/api/files/{file_id}").status_code == 404

        actor["value"] = users[2]
        assert _request("GET", f"/api/files/{file_id}").status_code == 404

        actor["value"] = users[0]
        assert _request("DELETE", f"/api/files/{file_id}").status_code == 204
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous)


def test_file_upload_body_limit_rejects_before_route(
    file_context,
    monkeypatch,
) -> None:
    factory, users, _ = file_context

    def override_db():
        with factory() as db:
            yield db

    previous = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_db] = override_db
    agent_server.app.dependency_overrides[get_current_user] = lambda: users[0]
    monkeypatch.setattr(config, "FILE_UPLOAD_REQUEST_MAX_BYTES", 16)
    try:
        response = _request(
            "POST",
            "/api/files",
            content=b"x" * 17,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": "17",
            },
        )
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous)

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "upload_request_too_large"


def test_file_api_rejects_anonymous_upload(file_context) -> None:
    factory, _, _ = file_context

    def override_db():
        with factory() as db:
            yield db

    previous = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_db] = override_db
    agent_server.app.dependency_overrides.pop(get_current_user, None)
    try:
        response = _request(
            "POST",
            "/api/files",
            files=[("files", ("safe.txt", b"safe", "text/plain"))],
        )
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous)

    assert response.status_code == 401


def test_chunked_upload_body_limit_is_bounded(monkeypatch) -> None:
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    middleware = FileUploadBodyLimitMiddleware(downstream)
    monkeypatch.setattr(config, "FILE_UPLOAD_REQUEST_MAX_BYTES", 5)
    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/files",
                "headers": [],
            },
            receive,
            send,
        )
    )

    assert called is False
    assert sent[0]["status"] == 413


@pytest.mark.parametrize(
    "headers",
    [
        [(b"content-length", b"invalid")],
        [
            (b"content-length", b"1"),
            (b"content-length", b"1"),
        ],
    ],
)
def test_invalid_content_length_is_rejected(monkeypatch, headers) -> None:
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    middleware = FileUploadBodyLimitMiddleware(downstream)
    monkeypatch.setattr(config, "FILE_UPLOAD_REQUEST_MAX_BYTES", 5)
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(
        middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/files",
                "headers": headers,
            },
            receive,
            send,
        )
    )

    assert called is False
    assert sent[0]["status"] == 400
