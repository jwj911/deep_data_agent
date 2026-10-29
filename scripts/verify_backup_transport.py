"""Validate and transport the existing format-1 recovery bundle using restic.

This is a transport helper, not a production snapshot producer or a scheduler.
It never loads .env, initializes repositories, stops applications, or prunes data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit
from uuid import uuid4


class TransportError(RuntimeError):
    pass


@contextmanager
def temporary_directory(parent, prefix):
    """Retry name collisions only; never spin on Windows permission failures."""
    directory = None
    for _ in range(8):
        candidate = Path(parent) / (prefix + uuid4().hex)
        try:
            candidate.mkdir(mode=0o700)
        except FileExistsError:
            continue
        except OSError as exc:
            raise TransportError("private_staging_creation_failed") from exc
        directory = candidate
        break
    if directory is None:
        raise TransportError("private_staging_name_collisions")
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest()


def source_fingerprint(root):
    expected = {
        path.relative_to(root).as_posix(): digest(path)
        for folder in ("data_agent", "migrations")
        for path in (root / folder).rglob("*.py")
    }
    expected["requirements.txt"] = digest(root / "requirements.txt")
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


def validate(bundle, root, manifest_sha, *, recent=False):
    if not re.fullmatch(r"[a-f0-9]{64}", manifest_sha or ""):
        raise TransportError("authoritative_manifest_hash_required")
    if bundle.is_symlink() or bundle.is_junction() or not bundle.is_dir():
        raise TransportError("bundle_directory_invalid")
    manifest_path = bundle / "manifest.json"
    if manifest_path.is_symlink() or manifest_path.is_junction() or not manifest_path.is_file():
        raise TransportError("manifest_missing")
    if not 0 < manifest_path.stat().st_size <= 64 * 1024:
        raise TransportError("manifest_size_invalid")
    if digest(manifest_path) != manifest_sha:
        raise TransportError("manifest_hash_mismatch")
    expected_names = {"manifest.json", "mysql.sql", "langgraph.tar", "managed-files.tar"}
    if {entry.name for entry in bundle.iterdir()} != expected_names:
        raise TransportError("bundle_extra_or_missing_file")
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from data_recovery import validate_bundle
    from verify_container_smoke import resolve_migration_head

    manifest = validate_bundle(bundle, lock_sha256=digest(root / "requirements.txt"))
    if manifest.get("revision") != resolve_migration_head(root):
        raise TransportError("bundle_revision_incompatible")
    if manifest.get("runtime", {}).get("source_sha256") != source_fingerprint(root):
        raise TransportError("bundle_source_incompatible")
    if recent:
        completed = datetime.fromisoformat(manifest["completed_at"].replace("Z", "+00:00"))
        if completed.tzinfo is None:
            raise TransportError("bundle_timestamp_timezone_missing")
        age = (datetime.now(timezone.utc) - completed).total_seconds()
        if not 0 <= age <= 3600:
            raise TransportError("bundle_not_fresh")
    return manifest


def remote_configuration():
    repo = os.environ.get("RESTIC_REPOSITORY", "")
    if not repo.startswith("s3:https://"):
        return False
    url = urlsplit(repo[len("s3:"):])
    try:
        if (
            not url.hostname or url.username or url.password
            or url.port not in (None, 443) or not url.path.strip("/")
            or url.query or url.fragment
        ):
            return False
    except ValueError:
        return False
    return not any(os.environ.get(name) for name in (
        "RESTIC_REPOSITORY_FILE", "RESTIC_PASSWORD_COMMAND",
    ))


def preflight(restic):
    executable = shutil.which(str(restic))
    return {
        "restic_available": executable is not None,
        "remote_s3_https_configuration_present": remote_configuration(),
        "repository_password_configuration_present": bool(
            os.environ.get("RESTIC_PASSWORD") or os.environ.get("RESTIC_PASSWORD_FILE")
        ),
        "explicit_aws_credentials_present": bool(
            os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY")
        ),
        "runtime_format_supported": "format1_langgraph_dev",
        "production_snapshot_producer": "absent",
        "automatic_schedule": "not_installed",
        "offsite_independence_verified": False,
    }


def run_restic(
    restic, args, *, work_dir, cwd=None, environment=None,
    max_output_bytes=256 * 1024, output_file=None, timeout_seconds=300,
):
    """Bound subprocess output while streaming artifacts into private staging."""
    environment = dict(os.environ if environment is None else environment)
    for name in ("TMP", "TEMP", "TMPDIR"):
        environment[name] = str(work_dir)
    if type(max_output_bytes) is not int or max_output_bytes < 0 or timeout_seconds <= 0:
        raise TransportError("restic_command_budget_invalid")
    errors = []
    chunks = []

    def consume(pipe):
        size = 0
        try:
            while chunk := pipe.read(64 * 1024):
                size += len(chunk)
                if size > max_output_bytes:
                    raise TransportError("restic_output_limit_exceeded")
                if output_file is None:
                    chunks.append(chunk)
                else:
                    output_file.write(chunk)
        except Exception:
            errors.append("restic_output_limit_or_write_failure")
            process.kill()

    try:
        process = subprocess.Popen(
            [str(restic), "--no-cache", "--json", *args],
            cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise TransportError("restic_command_unavailable") from exc
    reader = threading.Thread(target=consume, args=(process.stdout,), daemon=True)
    reader.start()
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        raise TransportError("restic_command_timeout") from exc
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        reader.join(timeout=5)
        if not reader.is_alive():
            process.stdout.close()
    if reader.is_alive() or errors:
        raise TransportError("restic_output_limit_or_write_failure")
    if process.returncode:
        raise TransportError(f"restic_{args[0]}_failed_exit_{process.returncode}")
    return b"".join(chunks)


def _snapshot_files(raw, snapshot, max_bytes):
    """Inspect the entire snapshot before downloading any artifact bytes."""
    nodes = {}
    headers = 0
    for line in raw.splitlines():
        row = json.loads(line)
        if row.get("struct_type") == "snapshot":
            headers += 1
            if row.get("id") != snapshot:
                raise TransportError("snapshot_listing_identity_invalid")
            continue
        name = row.get("path")
        if not isinstance(name, str) or not name or len(name) > 4096:
            raise TransportError("snapshot_path_invalid")
        path = PurePosixPath(name)
        if (
            row.get("struct_type") != "node" or not path.is_absolute()
            or ".." in path.parts or "\\" in name or "\x00" in name
            or str(path) != name or path in nodes
            or row.get("type") not in ("file", "dir")
        ):
            raise TransportError("snapshot_node_invalid")
        nodes[path] = row
        if len(nodes) > 132:
            raise TransportError("snapshot_node_limit_exceeded")
    files = {path: row for path, row in nodes.items() if row["type"] == "file"}
    expected = {"manifest.json", "mysql.sql", "langgraph.tar", "managed-files.tar"}
    if (
        headers != 1 or len(files) != 4 or {path.name for path in files} != expected
        or len({path.parent for path in files}) != 1
    ):
        raise TransportError("snapshot_file_set_invalid")
    ancestors = {parent for path in files for parent in path.parents}
    if any(path not in ancestors for path, row in nodes.items() if row["type"] == "dir"):
        raise TransportError("snapshot_unrelated_directory")
    sizes = [row.get("size") for row in files.values()]
    if any(type(size) is not int or size <= 0 for size in sizes) or sum(sizes) > max_bytes:
        raise TransportError("snapshot_file_size_invalid")
    return {path.name: (str(path), row["size"]) for path, row in files.items()}


def _private_directory(path):
    return path.is_dir() and all(
        not entry.is_symlink() and not entry.is_junction()
        for entry in (path, *path.parents)
    )


def _promote(source, target):
    """Same-filesystem, no-replacement directory publication on Windows/Linux."""
    if os.name == "nt":
        os.rename(source, target)  # Windows refuses every existing destination.
    elif sys.platform == "linux":
        import ctypes
        import errno

        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise TransportError("exclusive_publish_unsupported")
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(target), 1):
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                raise TransportError("retrieve_target_already_exists")
            raise TransportError("exclusive_publish_failed")
    else:
        raise TransportError("exclusive_publish_unsupported")


def retrieve(restic, snapshot, target, root, manifest_sha, work_dir, max_bytes=1024 ** 3):
    if not re.fullmatch(r"[a-f0-9]{64}", snapshot or ""):
        raise TransportError("exact_snapshot_id_required")
    if not re.fullmatch(r"[a-f0-9]{64}", manifest_sha or ""):
        raise TransportError("authoritative_manifest_hash_required")
    if type(max_bytes) is not int or not 0 < max_bytes <= 1024 ** 3:
        raise TransportError("transport_byte_cap_invalid")
    if (
        target.exists() or target.is_symlink() or target.is_junction()
        or not _private_directory(target.parent) or not _private_directory(work_dir)
    ):
        raise TransportError("retrieve_target_must_be_new")
    deadline = time.monotonic() + 300

    def run(arguments, **kwargs):
        return run_restic(
            restic, arguments, work_dir=work_dir,
            timeout_seconds=max(0, deadline - time.monotonic()), **kwargs,
        )

    metadata = json.loads(run(["snapshots", snapshot]))
    if (
        not isinstance(metadata, list) or len(metadata) != 1
        or metadata[0].get("id") != snapshot
    ):
        raise TransportError("snapshot_metadata_invalid")
    size = metadata[0].get("summary", {}).get("total_bytes_processed")
    if type(size) is not int or not 0 < size <= max_bytes:
        raise TransportError("snapshot_size_unknown_or_exceeded")
    files = _snapshot_files(run(["ls", snapshot]), snapshot, max_bytes)
    if sum(item[1] for item in files.values()) != size:
        raise TransportError("snapshot_summary_size_mismatch")
    manifest_path, manifest_size = files["manifest.json"]
    if manifest_size > 64 * 1024:
        raise TransportError("snapshot_manifest_too_large")
    raw = run(["dump", snapshot, manifest_path], max_output_bytes=manifest_size)
    if len(raw) != manifest_size or hashlib.sha256(raw).hexdigest() != manifest_sha:
        raise TransportError("manifest_hash_mismatch")
    scripts = str(root / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from data_recovery import parse_manifest

    manifest = parse_manifest(raw, lock_sha256=digest(root / "requirements.txt"))
    for name, expected in manifest["artifacts"].items():
        if files[name][1] != expected["size"]:
            raise TransportError("snapshot_artifact_size_mismatch")
    # Stage beside the target for atomic same-filesystem publication. All names
    # written here are fixed local names, never paths supplied by the snapshot.
    with temporary_directory(target.parent, ".dda-retrieval-") as temporary:
        stage = temporary / "bundle"
        stage.mkdir(mode=0o700)
        (stage / "manifest.json").write_bytes(raw)
        for name, expected in manifest["artifacts"].items():
            with (stage / name).open("xb") as output:
                run(
                    ["dump", snapshot, files[name][0]],
                    max_output_bytes=expected["size"], output_file=output,
                )
        validate(stage, root, manifest_sha)
        _promote(stage, target)
    return target, manifest


def publish(args):
    manifest = validate(
        args.bundle, args.repo_root, args.expected_manifest_sha256, recent=True,
    )
    total = sum(entry.stat().st_size for entry in args.bundle.iterdir())
    if total > args.max_bytes:
        raise TransportError("transport_byte_cap_exceeded")
    # Explicit filenames prevent unrelated staging files from being uploaded.
    raw = run_restic(
        args.restic, [
            "backup", "--host", "deep-data-agent", "--tag", "dda-format1",
            "mysql.sql", "langgraph.tar", "managed-files.tar", "manifest.json",
        ], work_dir=args.work_dir, cwd=args.bundle,
    )
    summaries = [
        row for line in raw.splitlines()
        if isinstance(row := json.loads(line), dict) and row.get("message_type") == "summary"
    ]
    if len(summaries) != 1:
        raise TransportError("restic_summary_invalid")
    snapshot = summaries[0].get("snapshot_id", "")
    with temporary_directory(args.work_dir, "dda-readback-") as temporary:
        _, downloaded = retrieve(
            args.restic, snapshot, Path(temporary) / "restore",
            args.repo_root, args.expected_manifest_sha256, args.work_dir, args.max_bytes,
        )
        if downloaded != manifest:
            raise TransportError("remote_manifest_mismatch")
    return {
        "snapshot_id": snapshot, "bundle_bytes": total,
        "manifest_sha256": args.expected_manifest_sha256,
        "remote_readback_hashes": "passed",
        "transport_outcome": "passed",
        "production_backup_gate": "not_evaluated",
        "independent_host_restore": "not_evaluated",
    }


def save(path, report):
    if path.exists() or not path.parent.is_dir():
        raise TransportError("evidence_destination_must_be_new")
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "validate", "publish", "retrieve"))
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--restic", default="restic")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--snapshot-id")
    parser.add_argument("--target", type=Path)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--max-bytes", type=int, default=1024 * 1024 * 1024)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or not args.output.parent.is_dir():
        parser.error("output must be a new file in an existing directory")
    report = {
        "format": 1, "gate": "existing_bundle_encrypted_transport",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "operation": args.operation, "preflight": preflight(args.restic),
        "outcome": "blocked",
        "production_backup_gate": "not_evaluated",
    }
    code = 2
    try:
        if args.operation == "preflight":
            report["blockers"] = [
                name for name in (
                    "restic_available", "remote_s3_https_configuration_present",
                    "repository_password_configuration_present",
                ) if not report["preflight"][name]
            ]
            report["blockers"].extend([
                "production_snapshot_producer_absent",
                "automatic_schedule_and_offsite_restore_not_verified",
            ])
        else:
            if not 0 < args.max_bytes <= 1024 * 1024 * 1024:
                raise TransportError("byte_cap_invalid")
            if args.operation == "validate":
                if args.bundle is None:
                    raise TransportError("bundle_required")
                validate(args.bundle, args.repo_root, args.expected_manifest_sha256)
                report.update(outcome="passed", validation_scope="format1_archive_and_source_only")
            else:
                if not args.execute:
                    raise TransportError("explicit_execute_flag_required")
                if not all(report["preflight"][name] for name in (
                    "restic_available", "remote_s3_https_configuration_present",
                    "repository_password_configuration_present",
                )):
                    raise TransportError("remote_transport_configuration_missing")
                if args.work_dir is None or not args.work_dir.is_dir():
                    raise TransportError("existing_private_work_directory_required")
                if args.operation == "publish":
                    if args.bundle is None:
                        raise TransportError("bundle_required")
                    report.update(publish(args))
                else:
                    if args.target is None:
                        raise TransportError("new_target_required")
                    retrieve(
                        args.restic, args.snapshot_id, args.target, args.repo_root,
                        args.expected_manifest_sha256, args.work_dir, args.max_bytes,
                    )
                    report["transport_outcome"] = "passed"
                report["outcome"] = "passed"
            code = 0
    except Exception as exc:
        report["outcome"] = "failed"
        report["failure_code"] = (
            str(exc) if isinstance(exc, TransportError) else "bundle_or_transport_invalid"
        )
        code = 1
    save(args.output, report)
    print(json.dumps({
        "gate": report["gate"], "outcome": report["outcome"],
        "blockers": report.get("blockers", []),
        "failure_code": report.get("failure_code"),
    }))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
