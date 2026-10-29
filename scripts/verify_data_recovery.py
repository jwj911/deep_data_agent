"""Exercise a quiesced backup and fresh three-domain restore with private canaries."""

from __future__ import annotations

import argparse
import io
import json
import secrets
import subprocess
import tempfile
import time
from pathlib import Path

import data_recovery as recovery
from verify_container_smoke import (ComposeContext, SmokeError, _json_request,
                                    _login_tenant_user, _managed_file_id,
                                    _multipart_file_request, _mysql,
                                    _register_tenant_user)


def _compose(context, *args, timeout=180):
    result = subprocess.run(
        context.command(*args), capture_output=True, timeout=timeout,
    )
    if result.returncode:
        raise SmokeError("recovery_drill_compose_failed")


def _base(context, service, port):
    inspection = recovery._inspect(recovery._container(context, service))
    bindings = inspection["NetworkSettings"]["Ports"][f"{port}/tcp"] or []
    ports = {binding.get("HostPort") for binding in bindings}
    addresses = {binding.get("HostIp") for binding in bindings}
    if (
        len(ports) != 1
        or not addresses.intersection({"127.0.0.1", "0.0.0.0"})
        or not addresses.issubset({"127.0.0.1", "0.0.0.0", "::1", "::"})
    ):
        raise SmokeError("recovery_drill_port_invalid")
    host_port = ports.pop()
    if not isinstance(host_port, str) or not host_port.isdigit() or not 1 <= int(host_port) <= 65535:
        raise SmokeError("recovery_drill_port_invalid")
    return f"http://127.0.0.1:{host_port}"


def _request(method, base, path, token, body=None, expected=200):
    status, payload = _json_request(method, base + path, body=body, token=token)
    if status != expected:
        raise SmokeError(f"recovery_drill_http_{method}_{expected}_received_{status}")
    return payload


def _upload(base, token, label):
    status, payload = _multipart_file_request(
        base + "/api/files", token=token, filename=label + ".txt",
        content=("recovery-" + label).encode(), content_type="text/plain",
    )
    if status != 201:
        raise SmokeError("recovery_drill_upload_failed")
    return _managed_file_id(payload)


def _business_snapshot(context):
    # This stays in process memory and is never written to logs or reports.
    return [
        _mysql(context, f"SELECT * FROM `{table}` ORDER BY id", "domain comparison")
        for table in ("users", "sessions", "messages", "managed_files")
    ]


def _store_canary(context, owner, *, write=False):
    volume, image = recovery._volume(context, "langgraph.tar")
    script = (
        "import logging; logging.disable(logging.CRITICAL)\n"
        "from langgraph_runtime_inmem.store import STORE\n"
        "from langgraph_runtime_inmem._persistence import stop_flush_loop\n"
        f"namespace=({str(owner)!r}, 'recovery-canary')\n"
        "try:\n"
        + (
            " STORE.put(namespace, 'version', {'version': 1, 'content': 'store-canary'})\n"
            if write else
            " assert STORE.get(namespace, 'version').value == {'version': 1, 'content': 'store-canary'}\n"
        )
        + "finally:\n STORE.close()\n stop_flush_loop()\n"
    )
    recovery._binary([
        "docker", "run", "--rm", "-i", "--network", "none",
        "-v", f"{volume}:/app/.langgraph_api", image, "python", "-B", "-",
    ], source=io.BytesIO(script.encode()))


def _tamper_file(context, file_id):
    script = (
        "import logging; logging.disable(logging.CRITICAL)\n"
        "from pathlib import Path\n"
        "from sqlalchemy import text\n"
        "from data_agent.config.database import get_engine\n"
        "from data_agent.config.config import config\n"
        "with get_engine().connect() as db:\n"
        f" key=db.execute(text('SELECT storage_key FROM managed_files WHERE file_id=:id'), {{'id':{file_id!r}}}).scalar_one()\n"
        "p=Path(config.FILE_STORAGE_ROOT)/key\n"
        "content=p.read_bytes(); p.write_bytes(b'X'+content[1:])\n"
    )
    recovery._binary(
        context.command("exec", "-T", "fastapi", "python", "-B", "-"),
        source=io.BytesIO(script.encode()),
    )


def verify(context, *, scratch_root=None):
    if not context.project_name.startswith("dda-"):
        raise SmokeError("recovery_drill_requires_isolated_dda_project")
    root = Path(__file__).resolve().parents[1]
    fastapi = _base(context, "fastapi", 8000)
    langgraph = _base(context, "langgraph", 2024)
    suffix = secrets.token_hex(6)
    usernames = [f"recovery-{suffix}-{label}" for label in ("a", "b", "admin")]
    users = [
        _register_tenant_user(fastapi, name, name + "@example.com")
        for name in usernames
    ]
    _mysql(context, f"UPDATE users SET role='admin' WHERE id={users[2][0]}", "canary RBAC")
    token = users[0][1]
    session = _request("POST", fastapi, "/api/sessions/", token, {"title": "recovery canary"})
    session_path = f"/api/sessions/{session['session_id']}"
    _request(
        "POST", fastapi, session_path + "/messages", token,
        {"role": "user", "content": "REST recovery canary"},
    )
    files = {label: _upload(fastapi, token, label) for label in ("live", "deleted", "expired", "tampered")}
    _request("DELETE", fastapi, "/api/files/" + files["deleted"], token, expected=204)
    _mysql(
        context,
        f"UPDATE managed_files SET expires_at='2020-01-01' WHERE file_id='{files['expired']}'",
        "canary expiration",
    )
    _tamper_file(context, files["tampered"])
    live_metadata = _request("GET", fastapi, "/api/files/" + files["live"], token)
    reference = {
        "type": "text",
        "text": "__managed_file_v1__:" + json.dumps({
            "file_id": files["live"], "name": live_metadata["original_name"],
            "media_type": live_metadata["media_type"], "size_bytes": live_metadata["size_bytes"],
        }),
    }
    virtual_file = {
        "content": ["virtual checkpoint canary"],
        "created_at": "2026-01-02T03:04:05+00:00",
        "modified_at": "2026-01-02T03:04:05+00:00",
    }
    thread = _request("POST", langgraph, "/threads", token, {"metadata": {"graph_id": "agent"}})
    thread_path = "/threads/" + thread["thread_id"]
    _request(
        "POST", langgraph, thread_path + "/state", token,
        {"assistant_id": "agent", "values": {"messages": [{
            "id": "recovery-managed-reference", "role": "user",
            "content": [reference],
        }], "files": {"/recovery.txt": virtual_file}}},
    )
    _request(
        "POST", langgraph, thread_path + "/state", token,
        {"assistant_id": "agent", "values": {"messages": [{
            "id": "recovery-answer", "role": "assistant", "content": "checkpoint canary",
        }]}},
    )
    state = _request("GET", langgraph, thread_path + "/state", token)
    history = _request("GET", langgraph, thread_path + "/history", token)
    rest = _request("GET", fastapi, session_path, token)
    business = _business_snapshot(context)
    for _id, actor_token in users:
        running = _request(
            "POST", langgraph, "/threads/search", actor_token,
            {"status": "busy", "limit": 1},
        )
        if running:
            raise SmokeError("recovery_drill_has_active_runs")
    last_write_confirmed = time.monotonic()
    target_name = context.project_name + "-restore-" + suffix
    target = None
    try:
        with tempfile.TemporaryDirectory(prefix="dda-recovery-", dir=scratch_root) as scratch:
            scratch = Path(scratch)
            bundle = scratch / "bundle"
            _compose(context, "stop", "--timeout", "30", "frontend", "fastapi", "langgraph")
            _store_canary(context, users[0][0], write=True)
            manifest = recovery.backup(context, bundle, root)
            snapshot_elapsed = time.monotonic() - last_write_confirmed
            override = scratch / "restore.yml"
            override.write_text(
                "services:\n" + "".join(
                    f"  {service}:\n    ports: !override\n      - '127.0.0.1::{port}'\n"
                    for service, port in (
                        ("mysql", 3306), ("redis", 6379), ("fastapi", 8000),
                        ("langgraph", 2024), ("frontend", 80),
                    )
                ), encoding="utf-8",
            )
            target = ComposeContext(
                (*context.compose_files, override), context.env_file, target_name,
            )
            recovery_started = time.monotonic()
            _compose(target, "create")
            _compose(target, "up", "-d", "--wait", "--wait-timeout", "120", "mysql", "redis")
            # Negative controls use the actual restore entry point; no target
            # domain may change when one component is missing or corrupted.
            for domain in recovery.ARTIFACTS:
                path = bundle / domain
                intact = path.read_bytes()
                for mutation in ("missing", "tampered"):
                    if mutation == "missing":
                        path.unlink()
                    else:
                        path.write_bytes(intact + b"tampered")
                    try:
                        recovery.restore(target, bundle, root)
                    except SmokeError as exc:
                        if str(exc) != "recovery_bundle_invalid":
                            raise
                    else:
                        raise SmokeError("recovery_drill_corrupt_bundle_accepted")
                    path.write_bytes(intact)
                    if _mysql(target, "SHOW TABLES", "negative target unchanged").strip():
                        raise SmokeError("recovery_drill_negative_wrote_database")
            recovery.restore(target, bundle, root)
            if _business_snapshot(target) != business:
                raise SmokeError("recovery_drill_business_data_changed")
            try:
                recovery.restore(target, bundle, root)
            except SmokeError as exc:
                if str(exc) != "recovery_target_database_not_empty":
                    raise
            else:
                raise SmokeError("recovery_drill_overwrote_occupied_target")
            if _business_snapshot(target) != business:
                raise SmokeError("recovery_drill_occupied_target_changed")
            _store_canary(target, users[0][0])
            _compose(target, "up", "-d", "--wait", "--wait-timeout", "120")
            restored_api = _base(target, "fastapi", 8000)
            restored_graph = _base(target, "langgraph", 2024)
            tokens = [_login_tenant_user(restored_api, name) for name in usernames]
            # Login helper returns a token string, not user records.
            restored_token = tokens[0]
            assert _request("GET", restored_api, session_path, restored_token) == rest
            assert _request("GET", restored_graph, thread_path + "/state", restored_token) == state
            assert _request("GET", restored_graph, thread_path + "/history", restored_token) == history
            live = _request(
                "GET", restored_api, "/api/files/" + files["live"] + "/analysis", restored_token,
            )
            assert live["content"] == "recovery-live"
            me = _request("GET", restored_api, "/api/auth/me", tokens[2])
            assert me["role"] == "admin"
            for actor_token in tokens[1:]:
                for path in (session_path, "/api/files/" + files["live"] + "/analysis"):
                    _request("GET", restored_api, path, actor_token, expected=404)
                for path in (thread_path, thread_path + "/state", thread_path + "/history"):
                    _request("GET", restored_graph, path, actor_token, expected=404)
            for label, status in (("deleted", 404), ("expired", 404), ("tampered", 503)):
                _request(
                    "GET", restored_api, "/api/files/" + files[label] + "/analysis",
                    restored_token, expected=status,
                )
            for actor_token in tokens:
                _request(
                    "POST", restored_graph, "/store/items/search", actor_token,
                    {"namespace_prefix": [str(users[0][0])]}, expected=403,
                )
            return {
                "gate": "data_recovery", "outcome": "passed",
                "domains": ["mysql_identity_rbac_rest_file_metadata", "langgraph_thread_checkpoint_store", "managed_bytes_versions"],
                "bundle_negative_controls": 6, "occupied_target_refused": True,
                "confirmed_writes_lost": 0,
                "snapshot_elapsed_seconds": round(snapshot_elapsed, 3),
                "restore_elapsed_seconds": round(time.monotonic() - recovery_started, 3),
                "revision": manifest["revision"],
                "independent_target": True,
                "checks": ["fresh login and RBAC", "REST exact rows", "state and history exact values", "canonical managed UUID reference", "checkpoint virtual file", "persistent store value", "file bytes and hash", "owner/admin refusal", "deleted/expired/tampered refusal", "store API remains denied"],
                "scope": "manual quiesced snapshot; dev runtime; synthetic canaries",
            }
    finally:
        try:
            if target is not None:
                # Teardown only needs the project and original service set;
                # the temporary port override has already been removed.
                cleanup = ComposeContext(
                    context.compose_files, context.env_file, target_name,
                )
                _compose(cleanup, "down", "--volumes", "--remove-orphans", "--timeout", "10")
        finally:
            _compose(context, "up", "-d", "--wait", "--wait-timeout", "120")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", action="append", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project-name", required=True)
    parser.add_argument("--scratch-root", type=Path)
    args = parser.parse_args()
    context = ComposeContext(tuple(args.compose_file), args.env_file, args.project_name)
    try:
        print(json.dumps(verify(context, scratch_root=args.scratch_root)))
    except (SmokeError, AssertionError) as exc:
        print(json.dumps({"gate": "data_recovery", "outcome": "failed", "code": str(exc) if isinstance(exc, SmokeError) else "canary_mismatch"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
