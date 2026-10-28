"""Create a quiesced three-domain snapshot or restore it into empty resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from verify_container_smoke import (ComposeContext, SmokeError,
                                    _compose_output, _mysql,
                                    resolve_migration_head)

ARTIFACTS = ("mysql.sql", "langgraph.tar", "managed-files.tar")
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


def validate_bundle(bundle: Path, *, lock_sha256: str) -> dict:
    """Reject all missing, changed or unsafe domains before restoring anything."""
    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise SmokeError("recovery_manifest_missing")

    def require(condition):
        if not condition:
            raise ValueError("recovery_bundle_invalid")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        require(manifest["format"] == 1)
        require(manifest["quiesced"] is True)
        require(manifest["lock_sha256"] == lock_sha256)
        require(set(manifest["artifacts"]) == set(ARTIFACTS))
        for name in ARTIFACTS:
            path = bundle / name
            require(path.is_file() and not path.is_symlink())
            expected = manifest["artifacts"][name]
            require(path.stat().st_size == expected["size"] > 0)
            require(digest(path) == expected["sha256"])
            if name.endswith(".tar"):
                with tarfile.open(path) as archive:
                    members = archive.getmembers()
                    require(bool(members))
                    for member in members:
                        entry = PurePosixPath(member.name)
                        require(not entry.is_absolute())
                        require(".." not in entry.parts)
                        require("\\" not in member.name and ":" not in member.name)
                        require(member.isfile() or member.isdir())
        return manifest
    except (AssertionError, KeyError, TypeError, ValueError, OSError, tarfile.TarError) as exc:
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
    result = subprocess.run(
        command, stdin=source, stdout=target or subprocess.PIPE,
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
    import io

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
