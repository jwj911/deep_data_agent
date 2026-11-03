"""Isolated host browser acceptance for the real managed-file chat path.

Default preparation never sends a statistics run. Use --mode full only after
the integrating agent authorizes final validation. No Compose or real .env.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import queue
import re
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.metadata import version
from pathlib import Path
from urllib import error, request
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
PREFIX = ".dda-controlled-analysis-chat-"
TOOL = "analyze_file_statistics"
MARKER = "__managed_file_v1__:"
READY_TIMEOUT = 120
UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


def canonical(value):
    """Independent encoding of the documented version-one hash contract."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def decimal_text(value: Fraction) -> str:
    """Render a terminating rational using integer arithmetic, never Decimal."""
    sign = "-" if value < 0 else ""
    numerator, denominator = abs(value.numerator), value.denominator
    whole, remainder = divmod(numerator, denominator)
    digits = []
    while remainder:
        remainder *= 10
        digit, remainder = divmod(remainder, denominator)
        digits.append(str(digit))
        if len(digits) > 100:
            raise AssertionError("reference_is_not_a_bounded_decimal")
    return sign + str(whole) + ("." + "".join(digits) if digits else "")


def fixtures(scratch):
    result = []
    for kind in ("csv", "json"):
        rows = [
            {"amount": "0.1", "note": f"public-{kind}-{index:04d}-" + "x" * 24}
            for index in range(1200)
        ]
        rows[1]["amount"] = ""
        rows[-1]["amount"] = "12345678901234567890.123456789012345678"
        rows.append(dict(rows[0]))
        if kind == "csv":
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=["amount", "note"])
            writer.writeheader()
            writer.writerows(rows)
            content = stream.getvalue().encode("utf-8")
        else:
            content = json.dumps(rows, ensure_ascii=True).encode("ascii")
        assert content.index(rows[-2]["amount"].encode()) > 20_000
        path = scratch / f"public-tail-{kind}.{kind}"
        path.write_bytes(content)
        values = [Fraction(row["amount"]) for row in rows if row["amount"]]
        result.append({
            "name": path.name, "path": str(path), "column": "amount",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content), "row_count": len(rows),
            "valid_count": len(values), "missing_count": len(rows) - len(values),
            "duplicate_row_count": 1,
            "value": decimal_text(sum(values, Fraction(0))),
            "minimum": decimal_text(min(values)), "maximum": decimal_text(max(values)),
        })
    # Independent files for destructive lifecycle checks avoid upload deduplication.
    for action in ("delete", "expire", "drift"):
        source = result[0]
        content = Path(source["path"]).read_bytes().replace(b"public-csv", action.encode())
        path = scratch / f"public-{action}.csv"
        path.write_bytes(content)
        result.append({
            **source, "name": path.name, "path": str(path), "lifecycle": action,
            "sha256": hashlib.sha256(content).hexdigest(), "size_bytes": len(content),
        })
    content = Path(result[0]["path"]).read_bytes().replace(b"public-csv", b"unselected-csv")
    path = scratch / "public-unselected.csv"
    path.write_bytes(content)
    result[1]["alternative"] = {
        "name": path.name, "path": str(path), "size_bytes": len(content),
    }
    return result


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block["text"] for block in content
            if isinstance(block, dict) and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        )
    return ""


class ControlledProvider:
    """Select only the latest user's explicit file/column; never compute data."""

    def __init__(self):
        self.lock = threading.Lock()
        self.requests = 0
        self.calls = {}
        self.completed = []
        self.clarifications = []

    def completion(self, payload):
        with self.lock:
            self.requests += 1
            attempt = self.requests
            messages = payload.get("messages", [])
            user_index = next(
                (index for index in range(len(messages) - 1, -1, -1)
                 if messages[index].get("role") == "user"), None,
            )
            if user_index is None:
                raise ValueError("provider_requires_latest_user")
            text = content_text(messages[user_index].get("content"))
            refs = []
            for match in re.finditer(re.escape(MARKER), text):
                value, _ = json.JSONDecoder().raw_decode(text[match.end():])
                file_id = value.get("file_id", "")
                if not UUID_PATTERN.fullmatch(file_id) or str(UUID(file_id)) != file_id:
                    raise ValueError("provider_requires_canonical_file_id")
                refs.append(file_id)
            column_match = re.findall(r'(?m)^column=("(?:[^"\\]|\\.)*")\s*$', text)
            message = {"role": "assistant", "content": "Please specify one file and column."}
            if len(refs) == 1 and len(column_match) == 1:
                column = json.loads(column_match[0])
                if not isinstance(column, str) or not 1 <= len(column) <= 128:
                    raise ValueError("provider_requires_bounded_column")
                # Only a call issued after this user can authorize completion.
                issued = {}
                for item in messages[user_index + 1:]:
                    if item.get("role") == "assistant":
                        for call in item.get("tool_calls", []):
                            if call["function"]["name"] == TOOL:
                                issued[call["id"]] = call
                results = [
                    item for item in messages[user_index + 1:]
                    if item.get("role") == "tool" and item.get("tool_call_id") in issued
                ]
                if results:
                    tool_result = results[-1]
                    call_id = tool_result["tool_call_id"]
                    if self.calls.get(call_id) != {"file_id": refs[0], "column": column}:
                        raise ValueError("provider_received_unissued_tool_result")
                    envelope = json.loads(content_text(tool_result["content"]))
                    if (
                        envelope.get("type") != "managed_file_statistics"
                        or envelope.get("version") != 1
                        or envelope.get("status") not in ("success", "error")
                    ):
                        raise ValueError("provider_received_invalid_tool_result")
                    if envelope["status"] == "success" and not isinstance(envelope.get("data"), dict):
                        raise ValueError("provider_received_success_without_data")
                    if envelope["status"] == "error" and "data" in envelope:
                        raise ValueError("provider_received_error_with_data")
                    self.completed.append({"call_id": call_id, "status": envelope["status"]})
                    message["content"] = "Controlled provider observed the actual tool result."
                elif issued:
                    raise ValueError("provider_refuses_missing_tool_result")
                else:
                    names = {item.get("function", {}).get("name") for item in payload.get("tools", [])}
                    if TOOL not in names:
                        raise ValueError("statistics_tool_not_registered")
                    call_id = "call_" + uuid4().hex
                    arguments = {"file_id": refs[0], "column": column}
                    self.calls[call_id] = arguments
                    message.update(content="", tool_calls=[{
                        "id": call_id, "type": "function",
                        "function": {"name": TOOL, "arguments": json.dumps(arguments)},
                    }])
            else:
                self.clarifications.append({
                    "reason": "multiple_files" if len(refs) > 1 else "missing_column",
                    "file_refs": len(refs), "explicit_columns": len(column_match),
                })
            return {
                "id": f"controlled-{attempt}", "object": "chat.completion",
                "model": "isolated-analysis-provider", "created": 1,
                "choices": [{
                    "index": 0, "message": message,
                    "finish_reason": "tool_calls" if message.get("tool_calls") else "stop",
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }


def clean_env(scratch):
    allowed = {
        "SYSTEMROOT", "WINDIR", "PATH", "APPDATA", "LOCALAPPDATA", "COMSPEC",
        "PATHEXT", "USERPROFILE", "PROGRAMFILES", "PROGRAMFILES(X86)",
    }
    env = {key.upper(): value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(
        TEMP=str(scratch), TMP=str(scratch), PYTHONDONTWRITEBYTECODE="1",
        PYTHON_DOTENV_DISABLED="1", PYTHONUTF8="1",
        LANGSMITH_TRACING="false", LANGCHAIN_TRACING_V2="false",
        LANGSMITH_API_KEY="", LANGCHAIN_API_KEY="", OPENAI_API_KEY="",
        LANGSMITH_CONTROL_PLANE_API_KEY="", LANGGRAPH_CLOUD_LICENSE_KEY="",
        LANGCHAIN_TRACING="false", OTEL_ENABLED="false", OTEL_SDK_DISABLED="true",
        ANONYMIZED_TELEMETRY="false", NEXT_TELEMETRY_DISABLED="1",
        DO_NOT_TRACK="1", HF_HUB_OFFLINE="1", NO_PROXY="127.0.0.1,localhost,::1",
        TAVILY_API_KEY="", REDIS_URL="redis://127.0.0.1:1/0",
        RATE_LIMIT_ENABLED="false", LOG_FILE_PATH="",
        AGENT_MODEL_CALL_LIMIT="8", AGENT_TOOL_CALL_LIMIT="12",
    )
    return env


def assert_private_scratch(path):
    resolved = path.resolve()
    if resolved.parent != WORKSPACE or not resolved.name.startswith(PREFIX):
        raise ValueError("requires_owned_outer_workspace_scratch")
    return resolved


def serve():
    """Real app imports and real graph factory, with recording lease storage only."""
    scratch = assert_private_scratch(Path.cwd())
    boot = json.loads(sys.stdin.readline())
    config_path = scratch / "langgraph.json"
    graph_config = json.loads(config_path.read_text("utf-8"))
    if graph_config["env"] != {} or (scratch / ".langgraph_api").exists():
        raise ValueError("requires_fresh_inmem_and_empty_config_env")
    env = clean_env(scratch)
    env.update(boot["env"])
    os.environ.clear()
    os.environ.update(env)
    sys.path.insert(0, str(ROOT))
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False
    outbound = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def require_loopback(address):
        if isinstance(address, tuple) and address[0] not in ("127.0.0.1", "::1", "localhost"):
            outbound.append(True)
            raise RuntimeError("external_network_disabled")

    def connect(connection, address):
        require_loopback(address)
        return original_connect(connection, address)

    def connect_ex(connection, address):
        require_loopback(address)
        return original_connect_ex(connection, address)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    provider = ControlledProvider()
    leases = {}
    events = []
    lease_lock = threading.Lock()
    mutations = []
    samples = {item["sha256"] for item in boot["fixtures"]}
    errors = []

    def diagnostics():
        return {
            "provider_requests": provider.requests, "issued_calls": provider.calls,
            "clarifications": provider.clarifications,
            "completed": provider.completed, "acquired": events.count("acquire"),
            "released": events.count("release"), "active": len(leases),
            "outbound_attempts": len(outbound), "provider_errors": errors,
            "mutations": mutations,
        }

    def mutate(body):
        action, file_id = body["action"], body["file_id"]
        if action not in ("expire", "drift") or not UUID_PATTERN.fullmatch(file_id):
            raise ValueError("invalid_private_mutation")
        db_path = scratch / "identity.sqlite"
        with sqlite3.connect(db_path) as db:
            row = db.execute(
                "SELECT sha256, storage_key FROM managed_files WHERE file_id = ?", (file_id,),
            ).fetchone()
            if not row or row[0] not in samples:
                raise ValueError("mutation_requires_own_synthetic_fixture")
            if action == "expire":
                expired = datetime.now(timezone.utc) - timedelta(days=1)
                db.execute(
                    "UPDATE managed_files SET expires_at = ? WHERE file_id = ?",
                    (expired.replace(tzinfo=None).isoformat(" "), file_id),
                )
            else:
                target = (scratch / "managed" / row[1]).resolve()
                if not target.is_relative_to(scratch / "managed") or not target.is_file():
                    raise ValueError("mutation_outside_managed_root")
                content = target.read_bytes()
                changed = content.replace(b"0.1", b"0.2", 1)
                if changed == content or len(changed) != len(content):
                    raise ValueError("drift_fixture_not_mutated")
                target.write_bytes(changed)
            mutations.append(action)
        return {"mutated": action}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != "/diagnostics" or self.headers.get("X-Harness-Key") != boot["control_key"]:
                self.send_error(404)
                return
            self.respond(200, diagnostics())

        def respond(self, status, body, stream=False):
            if stream:
                delta = dict(body["choices"][0]["message"])
                if "tool_calls" in delta:
                    delta["tool_calls"] = [
                        {"index": index, **call} for index, call in enumerate(delta["tool_calls"])
                    ]
                chunk = {**body, "object": "chat.completion.chunk"}
                chunk["choices"] = [{"index": 0, "delta": delta, "finish_reason": None}]
                final = {**chunk, "choices": [{
                    "index": 0, "delta": {},
                    "finish_reason": body["choices"][0]["finish_reason"],
                }]}
                content = (
                    f"data: {json.dumps(chunk)}\n\ndata: {json.dumps(final)}\n\ndata: [DONE]\n\n"
                ).encode()
            else:
                content = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream" if stream else "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4 * 1024 * 1024:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(size))
                if self.path == "/mutate" and self.headers.get("X-Harness-Key") == boot["control_key"]:
                    self.respond(200, mutate(body))
                elif self.path == "/v1/chat/completions":
                    self.respond(200, provider.completion(body), body.get("stream", False))
                else:
                    self.send_error(404)
            except (ValueError, KeyError) as exc:
                # Only fixed provider error identifiers, never request bodies.
                code = str(exc) if re.fullmatch("[a-z_]+", str(exc)) else "invalid_provider_request"
                errors.append(code)
                self.respond(400, {"error": {"message": code, "type": "invalid_request_error"}})

    provider_server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    provider_thread = threading.Thread(target=provider_server.serve_forever, daemon=True)
    provider_thread.start()
    os.environ.update(
        MODEL_BASE_URL=f"http://127.0.0.1:{provider_server.server_port}/v1",
        MODEL_NAME="isolated-analysis-provider", MOONSHOT_API_KEY="isolated-no-paid-provider",
        LANGGRAPH_RUNTIME_EDITION="inmem", LANGGRAPH_ALLOW_BLOCKING="true",
        LANGSMITH_LANGGRAPH_API_VARIANT="local_dev", LANGGRAPH_DISABLE_FILE_PERSISTENCE="true",
        LANGGRAPH_AUTH_TYPE="noop", LANGGRAPH_AUTH=json.dumps(graph_config["auth"]),
        LANGSERVE_GRAPHS=json.dumps(graph_config["graphs"]),
        LANGGRAPH_HTTP=json.dumps(graph_config["http"]), DATABASE_URI=":memory:",
        REDIS_URI="redis://127.0.0.1:1/0", FF_CRONS_ENABLED="false",
        N_JOBS_PER_WORKER="1", DISABLE_TRUSTSTORE="true",
    )
    import logging

    import structlog
    import uvicorn

    __import__("numpy")
    logging.disable(logging.CRITICAL)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    from data_agent.config import database
    from data_agent.services import agent_service
    from data_agent.services.agent_lease import AgentLease, AgentLeaseManager

    class RecordingLeaseManager(AgentLeaseManager):
        # Preserve production hold/hold_async and their identity/reset semantics.
        def acquire(self, subject):
            with lease_lock:
                lease = AgentLease(
                    uuid4().hex, self.subject_digest(subject),
                    int(time.time() * 1000) + 75000,
                )
                leases[lease.lease_id] = subject
                events.append("acquire")
                return lease

        async def acquire_async(self, subject):
            return self.acquire(subject)

        def release(self, lease):
            with lease_lock:
                if lease.lease_id not in leases:
                    raise RuntimeError("duplicate_or_unknown_lease_release")
                del leases[lease.lease_id]
                events.append("release")
            return True

    agent_service.global_agent_lease_manager = RecordingLeaseManager()
    from langgraph_api import metadata, metrics_collector

    async def no_background_collection():
        return None

    # Disable optional background collectors, not the real run queue or API.
    metadata.metadata_loop = no_background_collection
    metrics_collector.collector_loop = no_background_collection
    from langgraph_api.server import app as graph_app

    from data_agent.agent_server import app as rest_app

    servers = []
    threads = []
    listeners = []
    try:
        for app, port in ((rest_app, boot["rest_port"]), (graph_app, boot["graph_port"])):
            listener = socket.socket()
            listener.bind(("127.0.0.1", port))
            listener.listen(128)
            listeners.append(listener)
            server = uvicorn.Server(uvicorn.Config(
                app, host="127.0.0.1", port=port, access_log=False,
                log_config=None, timeout_graceful_shutdown=5,
            ))
            worker = threading.Thread(
                target=lambda s=server, sock=listener: asyncio.run(s.serve(sockets=[sock])),
                daemon=True,
            )
            worker.start()
            servers.append(server)
            threads.append(worker)
            deadline = time.monotonic() + READY_TIMEOUT
            while not server.started:
                if not worker.is_alive() or time.monotonic() > deadline:
                    raise RuntimeError("real_api_startup_failed")
                time.sleep(0.05)
        print(json.dumps({
            "ready": True, "control": f"http://127.0.0.1:{provider_server.server_port}",
            "versions": {name: version(name) for name in (
                "langgraph-api", "langchain-openai", "fastapi", "langgraph",
            )},
        }), flush=True)
        sys.stdin.readline()
    finally:
        for server in servers:
            server.should_exit = True
        for worker in threads:
            worker.join(timeout=10)
        for listener in listeners:
            listener.close()
        provider_server.shutdown()
        provider_server.server_close()
        provider_thread.join(timeout=5)
        if database._engine is not None:
            database._engine.dispose()
    if any(worker.is_alive() for worker in threads):
        raise RuntimeError("real_api_shutdown_incomplete")


def http_json(url, *, key=None):
    headers = {"X-Harness-Key": key} if key else {}
    opener = request.build_opener(request.ProxyHandler({}))
    with opener.open(request.Request(url, headers=headers), timeout=3) as response:
        return json.load(response)


def stop_process(process, graceful=False):
    if process.poll() is None and graceful:
        try:
            process.stdin.write("stop\n")
            process.stdin.flush()
            process.wait(timeout=25)
        except (OSError, subprocess.TimeoutExpired):
            pass
    if process.poll() is None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                check=False,
            )
        else:
            process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def check_result(result, samples):
    references = {sample["name"]: sample for sample in samples}
    for case in result.get("statistics", []):
        reference = references[case["fixture"]]
        tool = case["tool"]
        assert tool == case["rest"] == case["download"], "chat_rest_download_mismatch"
        assert tool["parameters"] == {"metric": "sum", "column": reference["column"]}
        for field in ("value", "minimum", "maximum", "valid_count", "missing_count"):
            assert tool["result"][field] == reference[field], f"reference_{field}_mismatch"
        assert tool["row_count"] == reference["row_count"]
        assert tool["duplicate_row_count"] == reference["duplicate_row_count"]
        assert tool["source"]["sha256"] == reference["sha256"]
        assert tool["source"]["size_bytes"] == reference["size_bytes"]
        assert set(tool["warnings"]) == {
            "unit_unspecified", "missing_values_excluded", "duplicate_rows_included",
        }
        unhashed = {key: value for key, value in tool.items() if key != "result_sha256"}
        assert hashlib.sha256(canonical(unhashed)).hexdigest() == tool["result_sha256"]


def source_fingerprint(directory, suffixes):
    files = {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file() and path.suffix in suffixes
        and not any(part in ("node_modules", ".next", "out", ".git") for part in path.parts)
    }
    return {"files": len(files), "sha256": hashlib.sha256(canonical(files)).hexdigest()}


def preflight(args):
    node = Path(args.node).resolve()
    pnpm = Path(args.pnpm).resolve()
    playwright = Path(args.playwright).resolve()
    for path in (node, pnpm, playwright, ROOT / "agent_chatui/node_modules/next/package.json"):
        if not path.is_file():
            raise ValueError("missing_explicit_local_toolchain")
    node_version = subprocess.check_output([str(node), "--version"], text=True).strip()
    if not re.fullmatch(r"v22\.(?:1[1-9]|[2-9]\d)\.\d+", node_version):
        raise ValueError("requires_node_22_at_least_22_11")
    pnpm_version = json.loads((pnpm.parent.parent / "package.json").read_text("utf-8"))["version"]
    if pnpm_version != "10.5.1":
        raise ValueError("requires_pnpm_10_5_1")
    for port in (args.frontend_port, args.rest_port, args.graph_port):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    if len({args.frontend_port, args.rest_port, args.graph_port}) != 3:
        raise ValueError("ports_must_be_distinct")
    return node, pnpm, playwright, node_version, pnpm_version


def run(args):
    node, pnpm, playwright, node_version, pnpm_version = preflight(args)
    report = {
        "gate": "controlled_analysis_chat", "mode": args.mode,
        "execution_id": uuid4().hex,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "outcome": "failed", "statistics": "not_verified",
        "lease_storage": "recording substitute, NOT Redis evidence",
        "model": "loopback OpenAI JSON/SSE, real ChatOpenAI SDK",
        "node": node_version, "pnpm": pnpm_version,
        "deployment": "host development /, NOT production /data_copilot",
    }
    stage = "prepare_scratch"
    with tempfile.TemporaryDirectory(prefix=PREFIX, dir=WORKSPACE) as directory:
        scratch = assert_private_scratch(Path(directory))
        samples = fixtures(scratch)
        control_key = secrets.token_hex(32)
        env = clean_env(scratch)
        origins = {
            "frontend": f"http://127.0.0.1:{args.frontend_port}",
            "rest": f"http://127.0.0.1:{args.rest_port}",
            "graph": f"http://127.0.0.1:{args.graph_port}",
        }
        env.update(
            DATABASE_URL="sqlite:///" + (scratch / "identity.sqlite").as_posix(),
            FILE_STORAGE_ROOT=str(scratch / "managed"), JWT_SECRET_KEY=secrets.token_hex(32),
            CORS_ALLOWED_ORIGINS=origins["frontend"],
        )
        (scratch / "langgraph.json").write_text(json.dumps({
            "env": {}, "graphs": {"agent": "data_agent.agent_graph:agent"},
            "auth": {"path": "data_agent.security.langgraph_auth:auth", "disable_studio_auth": True},
            "http": {"disable_mcp": True, "disable_a2a": True},
        }), encoding="utf-8")
        frontend = scratch / "frontend"
        shutil.copytree(ROOT / "agent_chatui", frontend, ignore=shutil.ignore_patterns(
            "node_modules", ".next", "out", ".env*", "*.tsbuildinfo", ".git",
        ))
        report["frontend_snapshot"] = source_fingerprint(frontend, {".ts", ".tsx", ".mjs", ".css", ".json", ".yaml"})
        report["backend_snapshot"] = source_fingerprint(ROOT / "data_agent", {".py"})
        modules = ROOT / "agent_chatui/node_modules"
        frontend_env = {
            **clean_env(scratch),
            "PATH": os.pathsep.join((str(node.parent), str(modules / ".bin"), os.environ.get("PATH", ""))),
            "NODE_PATH": str(modules),
            "NODE_OPTIONS": '--require "' + (ROOT / "scripts/verify_controlled_analysis_chat_network.cjs").as_posix() + '"',
            "NPM_CONFIG_OFFLINE": "true",
            "COREPACK_ENABLE_NETWORK": "0",
            "NEXT_PUBLIC_API_URL": origins["graph"],
            "NEXT_PUBLIC_REST_API_URL": origins["rest"],
            "NEXT_PUBLIC_ASSISTANT_ID": "agent",
            "NODE_ENV": "development",
        }
        cli_probe = subprocess.run(
            [str(node), str(pnpm), "dev", "--help"], cwd=frontend,
            env=frontend_env, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        if args.preflight_only or cli_probe.returncode:
            print(json.dumps({
                "gate": "isolated_frontend_cli_probe",
                "outcome": "passed" if cli_probe.returncode == 0 else "failed",
                "exit_code": cli_probe.returncode,
                "diagnostic": (cli_probe.stdout + cli_probe.stderr)[-3000:],
                "business_evidence": False,
            }))
            return 0 if cli_probe.returncode == 0 else 1
        with ExitStack() as stack:
            backend_log = stack.enter_context((scratch / "backend.log").open("w+", encoding="utf-8"))
            frontend_log = stack.enter_context((scratch / "frontend.log").open("w+", encoding="utf-8"))
            backend = subprocess.Popen(
                [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--server"],
                cwd=scratch, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=backend_log, text=True, encoding="utf-8",
            )
            stack.callback(stop_process, backend, True)
            try:
                stage = "backend_startup"
                backend.stdin.write(json.dumps({
                    "env": env, "fixtures": samples, "control_key": control_key,
                    "rest_port": args.rest_port, "graph_port": args.graph_port,
                }) + "\n")
                backend.stdin.flush()
                ready_queue = queue.Queue()

                def read_ready():
                    for line in backend.stdout:
                        try:
                            value = json.loads(line)
                            if value.get("ready"):
                                ready_queue.put(value)
                                return
                        except (ValueError, AttributeError):
                            pass
                    ready_queue.put(None)

                threading.Thread(target=read_ready, daemon=True).start()
                ready = ready_queue.get(timeout=READY_TIMEOUT)
                if not ready:
                    raise RuntimeError("backend_exited_before_ready")
                report["backend_versions"] = ready["versions"]
                assert http_json(origins["rest"] + "/api/live") == {"status": "healthy"}
                stage = "frontend_startup"
                web = subprocess.Popen(
                    [str(node), str(pnpm), "dev", "--hostname", "127.0.0.1",
                     "--port", str(args.frontend_port)],
                    cwd=frontend, env=frontend_env,
                    stdout=frontend_log, stderr=subprocess.STDOUT,
                )
                stack.callback(stop_process, web)
                deadline = time.monotonic() + READY_TIMEOUT
                while True:
                    if web.poll() is not None:
                        raise RuntimeError("frontend_exited_before_ready")
                    try:
                        opener = request.build_opener(request.ProxyHandler({}))
                        with opener.open(origins["frontend"] + "/login/", timeout=5) as response:
                            content = response.read()
                            if response.status == 200 and b"Deep Data" in content:
                                break
                    except (OSError, error.URLError, TimeoutError):
                        pass
                    if time.monotonic() > deadline:
                        raise RuntimeError("frontend_readiness_timeout")
                    time.sleep(0.2)
                stage = "browser_" + args.mode
                browser_env = {**clean_env(scratch), "DDA_PLAYWRIGHT_MODULE": str(playwright)}
                browser_process = subprocess.Popen(
                    [str(node), str(ROOT / "scripts/verify_controlled_analysis_chat.mjs")],
                    cwd=scratch, env=browser_env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding="utf-8",
                )
                stack.callback(stop_process, browser_process)
                browser_stdout, browser_stderr = browser_process.communicate(input=json.dumps({
                        "origins": origins, "fixtures": samples, "mode": args.mode,
                        "control": ready["control"], "controlKey": control_key,
                        "headed": args.headed,
                    }), timeout=600)
                report["browser_exit_code"] = browser_process.returncode
                report["browser_error_types"] = sorted(set(re.findall(
                    r"\b(?:[A-Z][A-Za-z]*Error|ERR_[A-Z_]+)\b", browser_stderr,
                )))
                report["browser_error_locations"] = re.findall(
                    r"verify_controlled_analysis_chat\.mjs:\d+:\d+", browser_stderr,
                )[-5:]
                lines = [line for line in browser_stdout.splitlines() if line.startswith("{")]
                browser_result = json.loads(lines[-1]) if lines else {
                    "outcome": "failed", "stage": "browser_no_report",
                }
                report["browser"] = browser_result
                stage = browser_result.get("stage", "independent_reference")
                check_result(browser_result, samples)
                diagnostics = http_json(ready["control"] + "/diagnostics", key=control_key)
                report["diagnostics"] = diagnostics
                assert diagnostics["acquired"] == diagnostics["released"] and not diagnostics["active"]
                assert not diagnostics["outbound_attempts"] and not diagnostics["provider_errors"]
                assert browser_process.returncode == 0 and browser_result["outcome"] == "passed", "browser_gate_failed"
                if args.mode == "prepare":
                    assert diagnostics["provider_requests"] == 0
                else:
                    assert len(browser_result["statistics"]) == 5
                    assert {case["fixture"] for case in browser_result["statistics"]} == {
                        sample["name"] for sample in samples
                    }
                    assert len(diagnostics["completed"]) >= 5
                    assert len(browser_result["clarifications"]) == 2
                    assert diagnostics["clarifications"] == [
                        {"reason": "missing_column", "file_refs": 1, "explicit_columns": 0},
                        {"reason": "multiple_files", "file_refs": 2, "explicit_columns": 1},
                    ]
                    assert diagnostics["provider_requests"] == 14
                    assert len(diagnostics["issued_calls"]) == len(diagnostics["completed"]) == 6
                    assert diagnostics["acquired"] == diagnostics["released"] == 8
                    report["statistics"] = "real_tool_rest_download_fraction_reference_passed"
                report["outcome"] = "prepared" if args.mode == "prepare" else "passed"
            except Exception as exc:
                report["failure_stage"] = stage
                # Assertion messages are fixed identifiers; never print browser tokens/logs.
                report["failure_type"] = type(exc).__name__
                for name, log in (("backend", backend_log), ("frontend", frontend_log)):
                    log.flush()
                    log.seek(0)
                    lines = log.read().splitlines()
                    diagnostic = [
                        re.sub(r"\beyJ[\w-]*\.[\w-]+\.[\w-]+", "<REDACTED>", line)[:240]
                        for line in lines[-20:]
                        if name == "frontend" or any(
                            word in line.lower() for word in ("error", "exception", "failed", "traceback")
                        )
                    ]
                    report[name + "_errors"] = diagnostic
        report["backend_unchanged_during_run"] = (
            report["backend_snapshot"] == source_fingerprint(ROOT / "data_agent", {".py"})
        )
        if not report["backend_unchanged_during_run"]:
            report["outcome"] = "failed"
            report["failure_stage"] = "backend_source_changed"
    report["owned_resources_cleaned"] = True
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, ensure_ascii=True))
    return 0 if report["outcome"] in ("prepared", "passed") else 1


def self_test():
    with tempfile.TemporaryDirectory(prefix=PREFIX, dir=WORKSPACE) as directory:
        samples = fixtures(Path(directory))
        assert samples[0]["value"] == "12345678901234568010.023456789012345678"
        provider = ControlledProvider()
        user = {"role": "user", "content": [
            {"type": "text", "text": 'column="amount"'},
            {"type": "text", "text": MARKER + json.dumps({"file_id": str(uuid4())})},
        ]}
        payload = {"messages": [user], "tools": [{"function": {"name": TOOL}}]}
        first = provider.completion(payload)["choices"][0]["message"]
        assert first["tool_calls"][0]["function"]["name"] == TOOL
        try:
            provider.completion({**payload, "messages": [user, first]})
        except ValueError as exc:
            assert str(exc) == "provider_refuses_missing_tool_result"
        else:
            raise AssertionError("missing_tool_result_was_accepted")
        latest = {"role": "user", "content": "No file and no column in this new turn."}
        second = provider.completion({**payload, "messages": [user, first, latest]})
        assert "tool_calls" not in second["choices"][0]["message"]
        for ambiguous, expected in (
            ({"role": "user", "content": [user["content"][1]]}, "missing_column"),
            ({"role": "user", "content": [
                *user["content"],
                {"type": "text", "text": MARKER + json.dumps({"file_id": str(uuid4())})},
            ]}, "multiple_files"),
        ):
            issued_before = len(provider.calls)
            clarification = provider.completion({**payload, "messages": [ambiguous]})
            assert "tool_calls" not in clarification["choices"][0]["message"]
            assert len(provider.calls) == issued_before
            assert provider.clarifications[-1]["reason"] == expected
            explicit = provider.completion({**payload, "messages": [ambiguous, user]})
            assert explicit["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == TOOL
        assert all(sample["size_bytes"] > 20_000 for sample in samples)
    print(json.dumps({"gate": "harness_self_test", "outcome": "passed", "business_evidence": False}))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--mode", choices=("prepare", "full"), default="prepare")
    parser.add_argument("--node", default=os.environ.get("DDA_NODE"))
    parser.add_argument("--pnpm", default=os.environ.get("DDA_PNPM"))
    parser.add_argument("--playwright", default=os.environ.get("DDA_PLAYWRIGHT_MODULE"))
    parser.add_argument("--frontend-port", type=int, default=3317)
    parser.add_argument("--rest-port", type=int, default=8317)
    parser.add_argument("--graph-port", type=int, default=2317)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if args.server:
        serve()
        return 0
    if args.self_test:
        return self_test()
    if not all((args.node, args.pnpm, args.playwright)):
        parser.error("Supply --node, --pnpm and --playwright (or DDA_* equivalents).")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
