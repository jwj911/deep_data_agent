"""Create a quiesced three-domain snapshot or restore it into empty resources."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from verify_container_smoke import (ComposeContext, SmokeError,
                                    _compose_output, _mysql,
                                    resolve_migration_head)

ARTIFACTS = ("mysql.sql", "langgraph.tar", "managed-files.tar")
MAX_MANIFEST_BYTES = 64 * 1024
MAX_BUNDLE_BYTES = 1024 ** 3
MAX_ARCHIVE_MEMBERS = 100_000
VOLUME_PATHS = {
    "langgraph.tar": "/app/.langgraph_api",
    "managed-files.tar": "/data/managed-files",
}


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def _require(condition):
    if not condition:
        raise ValueError("recovery_bundle_invalid")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result)
        result[key] = value
    return result


def parse_manifest(raw: bytes, *, lock_sha256: str) -> dict:
    """Bound and validate metadata before any artifact is consumed."""
    try:
        _require(0 < len(raw) <= MAX_MANIFEST_BYTES)
        manifest = json.loads(raw, object_pairs_hook=_unique_object)
        _require(isinstance(manifest, dict))
        _require(type(manifest["format"]) is int and manifest["format"] == 1)
        _require(manifest["quiesced"] is True)
        _require(manifest["lock_sha256"] == lock_sha256)
        artifacts = manifest["artifacts"]
        _require(isinstance(artifacts, dict) and set(artifacts) == set(ARTIFACTS))
        size = 0
        for expected in artifacts.values():
            _require(isinstance(expected, dict))
            _require(type(expected["size"]) is int and expected["size"] > 0)
            _require(isinstance(expected["sha256"], str))
            _require(re.fullmatch(r"[0-9a-f]{64}", expected["sha256"]) is not None)
            size += expected["size"]
        _require(size <= MAX_BUNDLE_BYTES)
        return manifest
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise SmokeError("recovery_bundle_invalid") from exc


def _archive_bytes(path: Path) -> int:
    """Reject ambiguous extraction, including implicit directory conflicts."""
    declared = set()
    directories = set()
    files = set()
    expanded = 0
    # The producer uses tar -cf. Reject compressed archives and expansion bombs.
    with tarfile.open(path, mode="r:") as archive:
        for index, member in enumerate(archive, 1):
            _require(index <= MAX_ARCHIVE_MEMBERS)
            _require(len(member.name) <= 4096)
            entry = PurePosixPath(member.name)
            _require(not entry.is_absolute() and ".." not in entry.parts)
            _require("\\" not in member.name and ":" not in member.name)
            _require(member.isfile() or member.isdir())
            _require(not member.issparse())
            _require(entry not in declared)
            _require(not files.intersection(entry.parents))
            declared.add(entry)
            if member.isdir():
                _require(entry not in files and member.size == 0)
                directories.add(entry)
            else:
                _require(entry != PurePosixPath(".") and entry not in directories)
                _require(member.size >= 0)
                files.add(entry)
                expanded += member.size
                _require(expanded <= MAX_BUNDLE_BYTES)
            directories.update(entry.parents)
    _require(bool(declared))
    return expanded


def _ordinary(path: Path) -> bool:
    return not path.is_symlink() and not path.is_junction()


def validate_bundle(bundle: Path, *, lock_sha256: str) -> dict:
    """Reject all missing, changed or unsafe domains before restoring anything."""
    manifest_path = bundle / "manifest.json"
    if not _ordinary(manifest_path) or not manifest_path.is_file():
        raise SmokeError("recovery_manifest_missing")
    try:
        _require(bundle.is_dir() and _ordinary(bundle))
        _require({path.name for path in bundle.iterdir()} == {"manifest.json", *ARTIFACTS})
        _require(manifest_path.stat().st_size <= MAX_MANIFEST_BYTES)
        with manifest_path.open("rb") as source:
            manifest = parse_manifest(source.read(MAX_MANIFEST_BYTES + 1), lock_sha256=lock_sha256)
        # Validate every physical size before hashing or parsing an artifact.
        for name in ARTIFACTS:
            path = bundle / name
            _require(path.is_file() and _ordinary(path))
            _require(path.stat().st_size == manifest["artifacts"][name]["size"])
        expanded = 0
        for name in ARTIFACTS:
            path = bundle / name
            _require(digest(path) == manifest["artifacts"][name]["sha256"])
            if name.endswith(".tar"):
                expanded += _archive_bytes(path)
                _require(expanded <= MAX_BUNDLE_BYTES)
        return manifest
    except (KeyError, TypeError, ValueError, OSError, tarfile.TarError) as exc:
        raise SmokeError("recovery_bundle_invalid") from exc


def _container(context, service):
    output = _compose_output(
        context, "ps", "--all", "-q", service, operation="container identity",
    )
    ids = output.split()
    if len(ids) != 1:
        raise SmokeError("recovery_service_identity_invalid")
    return ids[0]


def _inspect(container):
    result = subprocess.run(
        ["docker", "inspect", container], capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise SmokeError("recovery_inspection_failed")
    return json.loads(result.stdout)[0]


def _require_writers_stopped(context):
    for service in ("fastapi", "langgraph", "frontend"):
        state = _inspect(_container(context, service))["State"]
        if state["Running"] or state.get("ExitCode", 0) != 0:
            raise SmokeError("recovery_writers_not_cleanly_stopped")


def _volume(context, domain):
    service = "langgraph" if domain == "langgraph.tar" else "fastapi"
    inspection = _inspect(_container(context, service))
    mounts = [
        mount for mount in inspection["Mounts"]
        if mount["Destination"] == VOLUME_PATHS[domain] and mount["Type"] == "volume"
    ]
    if len(mounts) != 1:
        raise SmokeError("recovery_persistent_volume_missing")
    return mounts[0]["Name"], inspection["Image"]


def _binary(command, *, source=None, target=None):
    input_options = {"stdin": source}
    if source is not None:
        try:
            source.fileno()
        except io.UnsupportedOperation:
            input_options = {"input": source.read()}
    result = subprocess.run(
        command, **input_options, stdout=target or subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=180,
    )
    if result.returncode:
        raise SmokeError("recovery_domain_command_failed")
    return result.stdout


def _source_runtime(context, root):
    """Record the actual deployed source/lock; do not infer them from the host."""
    expected = {
        path.relative_to(root).as_posix(): digest(path)
        for folder in ("data_agent", "migrations")
        for path in (root / folder).rglob("*.py")
    }
    expected["requirements.txt"] = digest(root / "requirements.txt")

    script = (
        "import hashlib,json\nfrom pathlib import Path\n"
        f"expected={expected!r}\n"
        "actual={name:hashlib.sha256(Path('/app',name).read_bytes()).hexdigest() for name in expected}\n"
        "assert actual == expected\n"
    )
    verifier = (root / "scripts/verify_runtime_lock.py").read_bytes()
    images = set()
    for service in ("fastapi", "langgraph"):
        image = _inspect(_container(context, service))["Image"]
        if image in images:
            continue
        images.add(image)
        _binary([
            "docker", "run", "--rm", "-i", "--network", "none",
            image, "python", "-B", "-",
        ], source=io.BytesIO(script.encode()))
        _binary([
            "docker", "run", "--rm", "-i", "--network", "none",
            image, "python", "-B", "-", "--requirements", "/app/requirements.txt",
        ], source=io.BytesIO(verifier))
    return {
        "images": sorted(images),
        "source_sha256": hashlib.sha256(
            json.dumps(expected, sort_keys=True).encode(),
        ).hexdigest(),
    }


def backup(context: ComposeContext, bundle: Path, root: Path):
    """Caller drains runs and stops all writers; a stopped writer is enforced."""
    _require_writers_stopped(context)
    runtime = _source_runtime(context, root)
    if bundle.exists():
        raise SmokeError("recovery_bundle_destination_exists")
    bundle.mkdir(parents=True, mode=0o700)
    started = datetime.now(timezone.utc).isoformat()
    revision = _mysql(
        context, "SELECT version_num FROM alembic_version", "backup revision",
    ).strip()
    if revision != resolve_migration_head(root):
        raise SmokeError("recovery_source_revision_unknown")
    mysql_id = _container(context, "mysql")
    with (bundle / "mysql.sql").open("wb") as output:
        _binary([
            "docker", "exec", mysql_id, "sh", "-c",
            'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
            'exec mysqldump --single-transaction --routines --triggers '
            '--no-tablespaces --set-gtid-purged=OFF --hex-blob -uroot "$MYSQL_DATABASE"',
        ], target=output)
    for domain in VOLUME_PATHS:
        volume, image = _volume(context, domain)
        with (bundle / domain).open("wb") as output:
            _binary([
                "docker", "run", "--rm", "--network", "none",
                "-v", f"{volume}:/snapshot:ro", image,
                "tar", "-C", "/snapshot", "-cf", "-", ".",
            ], target=output)
    manifest = {
        "format": 1,
        "quiesced": True,
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "revision": revision,
        "lock_sha256": digest(root / "requirements.txt"),
        "runtime": runtime,
        "artifacts": {
            name: {"sha256": digest(bundle / name), "size": (bundle / name).stat().st_size}
            for name in ARTIFACTS
        },
    }
    (bundle / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
    )
    validate_bundle(bundle, lock_sha256=manifest["lock_sha256"])
    return manifest


def restore(context: ComposeContext, bundle: Path, root: Path):
    """Verify the whole bundle and target emptiness before the first write."""
    manifest = validate_bundle(bundle, lock_sha256=digest(root / "requirements.txt"))
    if manifest["revision"] != resolve_migration_head(root):
        raise SmokeError("recovery_revision_incompatible")
    _require_writers_stopped(context)
    table_count = _mysql(context, "SHOW TABLES", "restore target emptiness")
    if table_count.strip():
        raise SmokeError("recovery_target_database_not_empty")
    volumes = {domain: _volume(context, domain) for domain in VOLUME_PATHS}
    for volume, image in volumes.values():
        output = _binary([
            "docker", "run", "--rm", "--network", "none",
            "-v", f"{volume}:/snapshot:ro", image,
            "find", "/snapshot", "-mindepth", "1", "-print", "-quit",
        ])
        if output.strip():
            raise SmokeError("recovery_target_volume_not_empty")
    target_runtime = _source_runtime(context, root)
    if target_runtime["source_sha256"] != manifest.get("runtime", {}).get("source_sha256"):
        raise SmokeError("recovery_source_incompatible")
    with (bundle / "mysql.sql").open("rb") as source:
        _binary([
            "docker", "exec", "-i", _container(context, "mysql"), "sh", "-c",
            'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; '
            'exec mysql --binary-mode -uroot "$MYSQL_DATABASE"',
        ], source=source)
    for domain, (volume, image) in volumes.items():
        with (bundle / domain).open("rb") as source:
            _binary([
                "docker", "run", "--rm", "-i", "--network", "none",
                "-v", f"{volume}:/snapshot", image,
                "tar", "-C", "/snapshot", "-xf", "-",
            ], source=source)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", action="append", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("operation", choices=("backup", "restore", "validate"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    context = ComposeContext(tuple(args.compose_file), args.env_file, args.project_name)
    try:
        if args.operation == "validate":
            validate_bundle(args.bundle, lock_sha256=digest(root / "requirements.txt"))
        else:
            operation = backup if args.operation == "backup" else restore
            operation(context, args.bundle, root)
    except SmokeError as exc:
        print(str(exc))
        return 1
    print(json.dumps({"gate": "data_recovery", "operation": args.operation, "outcome": "passed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
