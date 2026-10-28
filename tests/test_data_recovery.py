"""Malformed backups must fail before any restore side effect."""

import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import data_recovery
from verify_container_smoke import SmokeError

LOCK = "a" * 64


def _tar(path, *, entry="canary.txt", kind=tarfile.REGTYPE):
    with tarfile.open(path, "w") as archive:
        item = tarfile.TarInfo(entry)
        item.type = kind
        item.size = 6 if kind == tarfile.REGTYPE else 0
        item.linkname = "/etc/passwd" if kind == tarfile.SYMTYPE else ""
        archive.addfile(item, io.BytesIO(b"canary") if item.size else None)


def _manifest(bundle):
    manifest = {
        "format": 1, "quiesced": True, "lock_sha256": LOCK,
        "revision": "b6f4e8c2a9d1",
        "artifacts": {
            name: {
                "size": (bundle / name).stat().st_size,
                "sha256": data_recovery.digest(bundle / name),
            } for name in data_recovery.ARTIFACTS
        },
    }
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


@pytest.fixture
def bundle(tmp_path):
    (tmp_path / "mysql.sql").write_bytes(b"-- offline canary\n")
    _tar(tmp_path / "langgraph.tar")
    _tar(tmp_path / "managed-files.tar")
    _manifest(tmp_path)
    return tmp_path


def test_complete_quiesced_bundle_validates(bundle):
    assert data_recovery.validate_bundle(bundle, lock_sha256=LOCK)["quiesced"]


def test_optimized_python_still_refuses_nonquiesced_backup(bundle):
    manifest = _manifest(bundle)
    manifest["quiesced"] = False
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    script = (
        "from pathlib import Path\n"
        f"import sys; sys.path.insert(0, {str(Path(data_recovery.__file__).parent)!r})\n"
        "from data_recovery import validate_bundle, SmokeError\n"
        "try:\n"
        f" validate_bundle(Path({str(bundle)!r}), lock_sha256={LOCK!r})\n"
        "except SmokeError as exc:\n print(str(exc))\n"
        "else:\n print('accepted')\n"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-B", "-c", script],
        capture_output=True, text=True, timeout=30, check=True,
    )
    assert result.stdout.strip() == "recovery_bundle_invalid"


@pytest.mark.parametrize("domain", data_recovery.ARTIFACTS)
@pytest.mark.parametrize("mutation", ["missing", "tamper", "truncate"])
def test_any_missing_or_changed_domain_refuses_before_docker(
    bundle, domain, mutation, monkeypatch,
):
    path = bundle / domain
    if mutation == "missing":
        path.unlink()
    elif mutation == "tamper":
        path.write_bytes(path.read_bytes() + b"changed")
    else:
        path.write_bytes(b"")
    monkeypatch.setattr(data_recovery, "_require_writers_stopped", lambda _: pytest.fail("restore wrote early"))
    monkeypatch.setattr(data_recovery, "digest", lambda path: LOCK if path.name == "requirements.txt" else "b" * 64)
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.restore(None, bundle, bundle)


@pytest.mark.parametrize("entry,kind", [
    ("../../outside", tarfile.REGTYPE),
    ("/absolute", tarfile.REGTYPE),
    ("C:/windows", tarfile.REGTYPE),
    ("..\\outside", tarfile.REGTYPE),
    ("link", tarfile.SYMTYPE),
    ("link", tarfile.LNKTYPE),
    ("pipe", tarfile.FIFOTYPE),
])
def test_recomputed_archive_hash_does_not_allow_unsafe_entries(bundle, entry, kind):
    _tar(bundle / "langgraph.tar", entry=entry, kind=kind)
    _manifest(bundle)
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


@pytest.mark.parametrize("field,value", [
    ("quiesced", False), ("format", 2), ("lock_sha256", "b" * 64),
    ("artifacts", {}), ("artifacts", []),
])
def test_incompatible_manifest_refuses(bundle, field, value):
    manifest = _manifest(bundle)
    manifest[field] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_existing_database_is_not_overwritten(bundle, monkeypatch):
    original_digest = data_recovery.digest
    monkeypatch.setattr(
        data_recovery, "digest",
        lambda path: LOCK if path.name == "requirements.txt" else original_digest(path),
    )
    monkeypatch.setattr(data_recovery, "_require_writers_stopped", lambda _: None)
    monkeypatch.setattr(data_recovery, "resolve_migration_head", lambda _: "b6f4e8c2a9d1")
    monkeypatch.setattr(data_recovery, "_mysql", lambda *args: "users\n")
    monkeypatch.setattr(data_recovery, "_binary", lambda *args, **kwargs: pytest.fail("occupied database was written"))
    with pytest.raises(SmokeError, match="recovery_target_database_not_empty"):
        data_recovery.restore(None, bundle, bundle)


def test_existing_file_volume_is_not_overwritten(bundle, monkeypatch):
    original_digest = data_recovery.digest
    monkeypatch.setattr(
        data_recovery, "digest",
        lambda path: LOCK if path.name == "requirements.txt" else original_digest(path),
    )
    monkeypatch.setattr(data_recovery, "_require_writers_stopped", lambda _: None)
    monkeypatch.setattr(data_recovery, "resolve_migration_head", lambda _: "b6f4e8c2a9d1")
    monkeypatch.setattr(data_recovery, "_mysql", lambda *args: "")
    monkeypatch.setattr(data_recovery, "_volume", lambda *args: ("occupied-volume", "image"))

    def read_only(command, **kwargs):
        assert "find" in command
        assert any(argument.endswith(":/snapshot:ro") for argument in command)
        return b"existing-private-file"

    monkeypatch.setattr(data_recovery, "_binary", read_only)
    with pytest.raises(SmokeError, match="recovery_target_volume_not_empty"):
        data_recovery.restore(None, bundle, bundle)


def test_active_writer_prevents_backup_directory_creation(tmp_path, monkeypatch):
    monkeypatch.setattr(data_recovery, "_container", lambda *args: "private-source")
    monkeypatch.setattr(
        data_recovery, "_inspect",
        lambda _: {"State": {"Running": True, "ExitCode": 0}},
    )
    destination = tmp_path / "backup"
    with pytest.raises(SmokeError, match="recovery_writers_not_cleanly_stopped"):
        data_recovery.backup(None, destination, tmp_path)
    assert not destination.exists()


def test_restore_refuses_actual_target_runtime_drift_before_writing(bundle, monkeypatch):
    original_digest = data_recovery.digest
    monkeypatch.setattr(
        data_recovery, "digest",
        lambda path: LOCK if path.name == "requirements.txt" else original_digest(path),
    )
    monkeypatch.setattr(data_recovery, "_require_writers_stopped", lambda _: None)
    monkeypatch.setattr(data_recovery, "resolve_migration_head", lambda _: "b6f4e8c2a9d1")
    monkeypatch.setattr(data_recovery, "_mysql", lambda *args: "")
    monkeypatch.setattr(data_recovery, "_volume", lambda *args: ("empty-volume", "image"))
    monkeypatch.setattr(data_recovery, "_container", lambda *args: "empty-target")
    monkeypatch.setattr(data_recovery, "_binary", lambda *args, **kwargs: b"")

    def drift(*args):
        raise SmokeError("recovery_domain_command_failed")

    monkeypatch.setattr(data_recovery, "_source_runtime", drift)
    with pytest.raises(SmokeError, match="recovery_domain_command_failed"):
        data_recovery.restore(None, bundle, bundle)
