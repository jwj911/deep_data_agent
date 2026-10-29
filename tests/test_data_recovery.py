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
import verify_data_recovery
from verify_container_smoke import SmokeError

LOCK = "a" * 64


@pytest.mark.parametrize("memory_source", [True, False])
@pytest.mark.parametrize("file_target", [True, False])
def test_binary_command_preserves_memory_and_file_input(tmp_path, memory_source, file_target):
    content = b"binary canary\x00\xff\n"
    path = tmp_path / "input.bin"
    path.write_bytes(content)
    output_path = tmp_path / "output.bin"
    command = [
        sys.executable, "-B", "-c",
        "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
    ]
    with io.BytesIO(content) if memory_source else path.open("rb") as source:
        if file_target:
            with output_path.open("wb") as target:
                data_recovery._binary(command, source=source, target=target)
            actual = output_path.read_bytes()
        else:
            actual = data_recovery._binary(command, source=source)
    assert actual == content


@pytest.mark.parametrize(
    ("bindings", "accepted"),
    [
        ([{"HostIp": "0.0.0.0", "HostPort": "32777"},
          {"HostIp": "::", "HostPort": "32777"}], True),
        ([{"HostIp": "127.0.0.1", "HostPort": "32777"}], True),
        ([{"HostIp": "0.0.0.0", "HostPort": "32777"},
          {"HostIp": "::", "HostPort": "32778"}], False),
        ([{"HostIp": "::1", "HostPort": "32777"}], False),
        ([{"HostIp": "192.0.2.1", "HostPort": "32777"}], False),
    ],
)
def test_recovery_drill_resolves_only_unambiguous_ipv4_ports(monkeypatch, bindings, accepted):
    monkeypatch.setattr(data_recovery, "_container", lambda *args: "private-container")
    monkeypatch.setattr(data_recovery, "_inspect", lambda *args: {
        "NetworkSettings": {"Ports": {"8000/tcp": bindings}},
    })
    if accepted:
        assert verify_data_recovery._base(None, "fastapi", 8000) == "http://127.0.0.1:32777"
    else:
        with pytest.raises(SmokeError, match="recovery_drill_port_invalid"):
            verify_data_recovery._base(None, "fastapi", 8000)


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


@pytest.mark.parametrize("entries", [
    [("same", b"first"), ("same", b"last")],
    [("./same", b"first"), ("same", b"last")],
    [("parent", b"file"), ("parent/child", b"child")],
    [("parent/child", b"child"), ("parent", b"file")],
])
def test_ambiguous_tar_refused_before_any_restore_call(bundle, entries, monkeypatch):
    with tarfile.open(bundle / "langgraph.tar", "w") as archive:
        for name, content in entries:
            item = tarfile.TarInfo(name)
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
    _manifest(bundle)
    original_digest = data_recovery.digest
    monkeypatch.setattr(
        data_recovery, "digest",
        lambda path: LOCK if path.name == "requirements.txt" else original_digest(path),
    )
    monkeypatch.setattr(
        data_recovery, "_require_writers_stopped",
        lambda _: pytest.fail("invalid archive reached Docker"),
    )
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.restore(None, bundle, Path(__file__).resolve().parents[1])


def test_duplicate_manifest_field_refused(bundle):
    text = (bundle / "manifest.json").read_text(encoding="utf-8")
    text = text.replace('"quiesced": true', '"quiesced": false, "quiesced": true')
    (bundle / "manifest.json").write_text(text, encoding="utf-8")
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_manifest_format_requires_integer(bundle, value):
    manifest = _manifest(bundle)
    manifest["format"] = value
    (bundle / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_manifest_size_bound_before_parsing(bundle, monkeypatch):
    monkeypatch.setattr(data_recovery, "MAX_MANIFEST_BYTES", 8)
    monkeypatch.setattr(data_recovery.json, "loads", lambda *a, **k: pytest.fail("oversized JSON parsed"))
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_bundle_size_bound_before_hashing(bundle, monkeypatch):
    monkeypatch.setattr(data_recovery, "MAX_BUNDLE_BYTES", 1)
    monkeypatch.setattr(data_recovery, "digest", lambda _: pytest.fail("oversized artifact read"))
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_all_artifact_sizes_checked_before_hashing(bundle, monkeypatch):
    (bundle / "managed-files.tar").write_bytes(b"wrong-size")
    monkeypatch.setattr(data_recovery, "digest", lambda _: pytest.fail("artifact read before size checks"))
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_archive_member_bound(bundle, monkeypatch):
    with tarfile.open(bundle / "langgraph.tar", "w") as archive:
        for name in ("a", "b"):
            archive.addfile(tarfile.TarInfo(name), io.BytesIO())
    _manifest(bundle)
    monkeypatch.setattr(data_recovery, "MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_unrelated_bundle_file_refused(bundle):
    (bundle / "unexpected.txt").write_bytes(b"unrelated")
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


def test_compressed_tar_refused(bundle):
    with tarfile.open(bundle / "langgraph.tar", "w:gz") as archive:
        item = tarfile.TarInfo("canary")
        item.size = 6
        archive.addfile(item, io.BytesIO(b"canary"))
    _manifest(bundle)
    with pytest.raises(SmokeError, match="recovery_bundle_invalid"):
        data_recovery.validate_bundle(bundle, lock_sha256=LOCK)


@pytest.mark.parametrize("directories_first", [True, False])
def test_archive_root_and_implicit_directories_remain_compatible(bundle, directories_first):
    entries = [(".", True), ("./nested", True), ("nested/child.txt", False)]
    if not directories_first:
        entries.reverse()
    with tarfile.open(bundle / "langgraph.tar", "w") as archive:
        for name, directory in entries:
            item = tarfile.TarInfo(name)
            item.type = tarfile.DIRTYPE if directory else tarfile.REGTYPE
            item.size = 0 if directory else 6
            archive.addfile(item, None if directory else io.BytesIO(b"canary"))
    _manifest(bundle)
    assert data_recovery.validate_bundle(bundle, lock_sha256=LOCK)["quiesced"] is True
