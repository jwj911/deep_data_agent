import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from fractions import Fraction
from io import BytesIO
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers, UploadFile

from data_agent import agent_server
from data_agent.config.config import config
from data_agent.config.database import get_db
from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import Base, User, utc_now
from data_agent.services import file_statistics as statistics
from data_agent.services.auth_service import get_current_user
from data_agent.services.authorization_service import AuthorizationDeniedError
from data_agent.services.file_statistics import (StatisticsError,
                                                 calculate_statistics)
from data_agent.services.managed_file_service import (ManagedFileError,
                                                      ManagedFileService)


def test_complete_csv_tail_and_exact_independent_reference():
    values = ["0.1", "0.2"] * 6000 + ["999.123456789012345678"]
    content = ("amount\n" + "\n".join(values)).encode()
    assert len(content) > 20_000
    result = calculate_statistics(content, "text/csv", "amount")
    expected = sum(map(Fraction, values))
    assert Fraction(result["result"]["value"]) == expected
    assert result["row_count"] == len(values)
    assert result["duplicate_row_count"] == len(values) - 3
    assert result["result"]["value"] in result["summary"]


def test_json_quality_precision_and_typed_duplicates():
    content = b"""[
        {"amount": 0.1, "label": true},
        {"label": true, "amount": 0.10},
        {"amount": -0.2, "label": "a"},
        {"amount": null, "label": "a"},
        {"amount": "", "label": "a"},
        {"amount": 0, "label": null}
    ]"""
    result = calculate_statistics(content, "application/json", "amount")
    assert result["result"] == {
        "value": "0", "unit": "unspecified", "valid_count": 4,
        "missing_count": 2, "minimum": "-0.2", "maximum": "0.1",
    }
    assert result["duplicate_row_count"] == 1
    assert result["columns"] == [
        {"name": "amount", "types": ["number"], "missing_count": 2},
        {"name": "label", "types": ["boolean", "string"], "missing_count": 1},
    ]
    assert set(result["warnings"]) == {
        "unit_unspecified", "missing_values_excluded", "duplicate_rows_included",
    }


def test_large_decimal_sum_never_rounds_or_uses_float():
    number = "99999999999999999999999999999999999999"
    result = calculate_statistics(
        f'amount\n{number}\n{number}\n0.000000000000000001'.encode(),
        "text/csv", "amount",
    )
    assert Fraction(result["result"]["value"]) == (
        Fraction(number) * 2 + Fraction(1, 10**18)
    )


@pytest.mark.parametrize(
    ("media_type", "content", "code"),
    [
        ("text/plain", b"amount\n1", "analysis_unsupported_type"),
        ("text/csv", b"amount,amount\n1,2", "analysis_invalid_columns"),
        ("text/csv", b",amount\n1,2", "analysis_invalid_columns"),
        ("text/csv", b"amount\n", "analysis_invalid_table"),
        ("text/csv", b"amount,other\n1", "analysis_invalid_table"),
        ("text/csv", b'amount\n"1', "analysis_invalid_table"),
        ("text/csv", b"amount\n\xff", "analysis_invalid_table"),
        ("text/csv", b"amount\n=1+2", "unsafe_csv_formula"),
        ("text/csv", b"amount\n-1", "unsafe_csv_formula"),
        ("text/csv", b"amount\n 1", "analysis_non_numeric"),
        ("text/csv", b"amount\nNA", "analysis_non_numeric"),
        ("text/csv", b'amount\n""', "analysis_no_numeric_values"),
        ("application/json", b'{"amount":1}', "analysis_invalid_table"),
        ("application/json", b"[]", "analysis_invalid_table"),
        ("application/json", b'[{"amount":1,"amount":2}]', "analysis_duplicate_key"),
        ("application/json", b'[{"amount":NaN}]', "analysis_non_finite"),
        ("application/json", b'[{"amount":Infinity}]', "analysis_non_finite"),
        ("application/json", b'[{"amount":true}]', "analysis_non_numeric"),
        ("application/json", b'[{"amount":null}]', "analysis_no_numeric_values"),
        ("application/json", b'[{"amount":1},{"other":2}]', "analysis_invalid_table"),
        ("application/json", b'[{"amount":1},2]', "analysis_invalid_table"),
        ("application/json", b'[{"amount":[1]}]', "analysis_invalid_table"),
        ("application/json", b'[{"amount":1,"other":{}}]', "analysis_invalid_table"),
        ("application/json", b'[{"amount":1e999}]', "analysis_numeric_range"),
        ("application/json", b'[{"amount":1e-19}]', "analysis_numeric_range"),
        ("text/csv", b"amount\n" + b"9" * 39, "analysis_numeric_range"),
    ],
)
def test_ambiguous_or_unsafe_data_has_no_partial_result(media_type, content, code):
    with pytest.raises(StatisticsError, match=f"^{code}$"):
        calculate_statistics(content, media_type, "amount")


@pytest.mark.parametrize("column", ["", "missing", "x" * 129, 1])
def test_invalid_column_is_rejected(column):
    with pytest.raises(StatisticsError):
        calculate_statistics(b"amount\n1", "text/csv", column)


@pytest.mark.parametrize("dimension", ["MAX_BYTES", "MAX_ROWS", "MAX_COLUMNS", "MAX_CELLS"])
def test_table_resource_limits(dimension, monkeypatch):
    monkeypatch.setattr(statistics, dimension, 1)
    with pytest.raises(StatisticsError, match="analysis_table_limit") as caught:
        calculate_statistics(b"amount,label\n1,a\n2,b", "text/csv", "amount")
    assert caught.value.status_code == 413


def test_deadline_rejects_instead_of_returning_partial_statistics(monkeypatch):
    ticks = iter([0, 0, 0, 6])
    monkeypatch.setattr(statistics, "perf_counter", lambda: next(ticks))
    with pytest.raises(StatisticsError, match="analysis_timeout"):
        calculate_statistics(b"amount\n1\n2", "text/csv", "amount")


def test_parallel_calculations_do_not_share_accumulators():
    def compute(value):
        return calculate_statistics(
            f"amount\n{value}\n{value}".encode(), "text/csv", "amount",
        )["result"]["value"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(compute, range(20))) == [str(n * 2) for n in range(20)]


@pytest.fixture
def files(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(config, "FILE_STORAGE_ROOT", str(tmp_path / "files"))
    monkeypatch.setattr(config, "FILE_ANALYSIS_MAX_CHARS", 5)
    with factory() as db:
        users = [
            User(username=f"stat-{index}", email=f"stat-{index}@example.test",
                 hashed_password="test-hash", role=role)
            for index, role in enumerate(["user", "user", "admin"])
        ]
        db.add_all(users)
        db.commit()
        for user in users:
            db.expunge(user)
    service = ManagedFileService()

    def store(content=b"amount,label\n0.1,a\n0.2,b\n"):
        with factory() as db:
            return asyncio.run(service.upload_files(db, users[0], [
                UploadFile(file=BytesIO(content), filename="sample.csv",
                           headers=Headers({"content-type": "text/csv"})),
            ]))[0]

    yield factory, users, service, store
    engine.dispose()


def test_service_verifies_complete_bytes_owner_and_source(files):
    factory, users, service, store = files
    record = store()
    with factory() as db:
        result = service.file_statistics(db, users[0], record.file_id, "amount")
        assert result["result"]["value"] == "0.3"
        assert result["source"] == {
            "file_id": record.file_id, "sha256": record.sha256,
            "size_bytes": record.size_bytes, "semantics": "current_file_at_read",
        }
        for other in users[1:]:
            assert service.file_statistics(db, other, record.file_id, "amount") is None
        denied = User(id=users[0].id, role="unknown")
        with pytest.raises(AuthorizationDeniedError):
            service.file_statistics(db, denied, record.file_id, "amount")
        with pytest.raises(ManagedFileError, match="invalid_file_id"):
            service.file_statistics(db, users[0], "../../outside", "amount")
    assert record.storage_key not in json.dumps(result)
    assert "sample.csv" not in json.dumps(result)


@pytest.fixture
def api(files):
    factory, users, service, store = files
    actor = {"value": users[0]}

    def override_db():
        with factory() as db:
            yield db

    previous = agent_server.app.dependency_overrides.copy()
    agent_server.app.dependency_overrides[get_db] = override_db
    agent_server.app.dependency_overrides[get_current_user] = lambda: actor["value"]

    def request(path, body=None):
        async def send():
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=agent_server.app), base_url="http://test",
            ) as client:
                return await client.post(path, json=body or {"column": "amount"})
        return asyncio.run(send())

    try:
        yield actor, request
    finally:
        agent_server.app.dependency_overrides.clear()
        agent_server.app.dependency_overrides.update(previous)


def test_api_download_is_same_canonical_result_and_cannot_override_identity(files, api):
    _, users, _, store = files
    actor, request = api
    record = store()
    path = f"/api/files/{record.file_id}/statistics"
    response = request(path)
    download = request(path + "?download=true")
    assert response.status_code == download.status_code == 200
    assert response.json() == download.json()
    assert response.headers["cache-control"] == "no-store"
    assert download.headers["content-disposition"] == (
        f'attachment; filename="analysis-{record.file_id}.json"'
    )
    payload = response.json()
    digest = payload.pop("result_sha256")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(encoded.encode("ascii")).hexdigest() == digest
    for body in [
        {"column": 1}, {"column": "amount", "owner": users[0].id},
        {"column": "amount", "metric": "eval"}, {"column": "amount", "path": "/tmp/a"},
    ]:
        assert request(path, body).status_code == 422
    for other in users[1:]:
        actor["value"] = other
        assert request(path).status_code == 404
        assert request(path + "?download=true").status_code == 404
    actor["value"] = users[0]
    assert request(path).json() == response.json()


@pytest.mark.parametrize("change", ["delete", "expire", "tamper", "path", "directory", "missing"])
def test_repeated_api_request_revalidates_lifecycle(files, api, change):
    factory, users, service, store = files
    _, request = api
    record = store()
    path = f"/api/files/{record.file_id}/statistics"
    assert request(path).status_code == 200
    with factory() as db:
        stored = db.query(ManagedFile).filter_by(file_id=record.file_id).one()
        disk = Path(config.FILE_STORAGE_ROOT) / stored.storage_key
        if change == "delete":
            service.delete_file(db, users[0], record.file_id)
        elif change == "expire":
            stored.expires_at = utc_now() - timedelta(seconds=1)
            db.commit()
        elif change == "tamper":
            disk.write_bytes(b"amount,label\n9.1,a\n9.2,b\n")
        elif change == "path":
            stored.storage_key = "../outside.csv"
            db.commit()
        else:
            disk.unlink()
            if change == "directory":
                disk.mkdir()
    retry = request(path + "?download=true")
    assert retry.status_code == (404 if change in {"delete", "expire"} else 503)
    assert "result" not in retry.json()


def test_statistics_anonymous_request_is_rejected(files):
    _, _, _, store = files
    record = store()

    async def send():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=agent_server.app), base_url="http://test",
        ) as client:
            return await client.post(
                f"/api/files/{record.file_id}/statistics", json={"column": "amount"},
            )
    assert asyncio.run(send()).status_code == 401


def test_statistics_limit_rejects_before_reading_oversized_storage(files, monkeypatch):
    factory, users, service, store = files
    record = store()
    with factory() as db:
        stored = db.query(ManagedFile).filter_by(file_id=record.file_id).one()
        stored.size_bytes = statistics.MAX_BYTES + 1
        db.commit()

        def unexpected_read(_record):
            pytest.fail("Oversized statistics source was read")

        monkeypatch.setattr(service, "_read_bytes", unexpected_read)
        with pytest.raises(ManagedFileError, match="analysis_table_limit"):
            service.file_statistics(db, users[0], record.file_id, "amount")


def test_api_numeric_error_has_stable_code_without_input_echo(files, api):
    _, _, _, store = files
    _, request = api
    record = store(b"amount,label\nprivate-invalid-value,a\n")
    response = request(f"/api/files/{record.file_id}/statistics")
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "analysis_non_numeric"
    assert "private-invalid-value" not in response.text
