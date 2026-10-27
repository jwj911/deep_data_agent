"""Exercise installed LangGraph HTTP routes using isolated synthetic services."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 30


def _request(base, path, token=None, body=None, *, method=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with request.urlopen(req, timeout=TIMEOUT) as response:
            expired = threading.Event()
            response_socket = response.fp.raw._sock

            def stop_read():
                expired.set()
                try:
                    response_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

            timer = threading.Timer(TIMEOUT, stop_read)
            timer.start()
            try:
                payload = response.read().decode()
                if expired.is_set():
                    raise TimeoutError("HTTP response exceeded its total deadline")
                return response.status, payload
            finally:
                timer.cancel()
    except error.HTTPError as exc:
        return exc.code, exc.read().decode()


def _expect(status, payload, expected, label):
    if status != expected:
        raise RuntimeError(f"{label}: expected HTTP {expected}, received {status}")
    decoded = json.loads(payload) if payload else None
    if isinstance(decoded, dict) and "__error__" in decoded:
        raise RuntimeError(f"{label}: graph execution returned an error")
    return decoded


def _server():
    """Run the real API app; substitute only model, lease and identity storage."""
    scratch = Path.cwd()
    if not scratch.name.startswith("dda-graph-http-") or (
        scratch / ".langgraph_api"
    ).exists():
        raise RuntimeError("Server mode requires a fresh private temporary directory")
    sys.path.insert(0, str(ROOT))
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1",
        LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false",
        LANGSMITH_API_KEY="",
        LANGCHAIN_API_KEY="",
        LANGSMITH_CONTROL_PLANE_API_KEY="",
        LANGGRAPH_CLOUD_LICENSE_KEY="",
        LANGGRAPH_RUNTIME_EDITION="inmem",
        LANGGRAPH_ALLOW_BLOCKING="true",
        LANGSMITH_LANGGRAPH_API_VARIANT="local_dev",
        LANGGRAPH_DISABLE_FILE_PERSISTENCE="true",
        LANGGRAPH_AUTH_TYPE="noop",
        LANGGRAPH_AUTH=json.dumps({
            "path": "data_agent.security.langgraph_auth:auth",
            "disable_studio_auth": True,
        }),
        LANGSERVE_GRAPHS=json.dumps({"agent": "data_agent.agent_graph:agent"}),
        LANGGRAPH_HTTP=json.dumps({"disable_mcp": True, "disable_a2a": True}),
        DATABASE_URI=":memory:",
        REDIS_URI="redis://127.0.0.1:1/0",
        DATABASE_URL="sqlite://",
        REDIS_URL="redis://127.0.0.1:1/0",
        MOONSHOT_API_KEY="http-regression-model-placeholder",
        TAVILY_API_KEY="your_tavily_api_key_here",
        MODEL_BASE_URL="http://127.0.0.1:9/v1",
        JWT_SECRET_KEY=secrets.token_hex(32),
        LOG_FILE_PATH="",
        FF_CRONS_ENABLED="false",
        N_JOBS_PER_WORKER="1",
        DISABLE_TRUSTSTORE="true",
        OTEL_ENABLED="false",
    )
    import dotenv

    dotenv.load_dotenv = lambda *args, **kwargs: False

    import logging

    # orjson's NumPy support initializes a native module on its first use.
    # Initialize it on the process main thread before API executor threads.
    __import__("numpy")
    import structlog

    logging.disable(logging.CRITICAL)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    import uvicorn
    from langchain_core.language_models.fake_chat_models import \
        FakeListChatModel
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool

    from data_agent.config import database
    from data_agent.models.user import Base, User
    from data_agent.services import agent_service
    from data_agent.services.auth_service import create_access_token

    outbound_attempts = []
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def require_loopback(address):
        if isinstance(address, tuple) and address[0] not in (
            "127.0.0.1", "::1", "localhost",
        ):
            outbound_attempts.append(True)
            raise RuntimeError("External network is disabled in HTTP verification")

    def loopback_connect(connection, address):
        require_loopback(address)
        return original_connect(connection, address)

    def loopback_connect_ex(connection, address):
        require_loopback(address)
        return original_connect_ex(connection, address)

    socket.socket.connect = loopback_connect
    socket.socket.connect_ex = loopback_connect_ex
    database._engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    database._session_factory = None
    Base.metadata.create_all(database._engine)
    with database.get_session_factory()() as db:
        for user_id in (17, 18, 19):
            db.add(User(
                id=user_id,
                username=f"http-regression-{user_id}",
                email=f"http-{user_id}@example.invalid",
                hashed_password="unused-synthetic-password-hash",
                role="admin" if user_id == 19 else "user",
            ))
        db.commit()

    events = []

    class RecordingLeaseManager:
        @asynccontextmanager
        async def hold_async(self, subject):
            events.append(("acquire", subject))
            try:
                yield
            finally:
                events.append(("release", subject))

    class OfflineModel(FakeListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        async def _agenerate(self, messages, **kwargs):
            if any(message.content == "wait-for-cancel" for message in messages):
                await asyncio.Event().wait()
            return await super()._agenerate(messages, **kwargs)

    agent_service.global_agent_lease_manager = RecordingLeaseManager()
    agent_service.ChatOpenAI = lambda **kwargs: OfflineModel(
        responses=["http-copy-ok"]
    )

    from langgraph_api.server import app
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    copies = []
    installed_copy = agent_service.ResourceBoundedAgentGraph.copy

    def observe_copy(self, update=None):
        graph = installed_copy(self, update=update)
        copies.append({
            "manager_preserved": (
                graph._agent_lease_manager is
                agent_service.global_agent_lease_manager
            ),
            "checkpoint_injected": graph.checkpointer is not None,
            "store_injected": graph.store is not None,
        })
        return graph

    # Delegate to the installed copy; API routes and execution stay untouched.
    agent_service.ResourceBoundedAgentGraph.copy = observe_copy

    async def diagnostics(_request):
        return JSONResponse({
            "acquired": sum(event[0] == "acquire" for event in events),
            "released": sum(event[0] == "release" for event in events),
            "subjects": sorted({event[1] for event in events}),
            "copies": copies,
            "outbound_attempts": len(outbound_attempts),
        })

    app.routes.insert(0, Route("/__verification", diagnostics))
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(128)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=listener.getsockname()[1],
        access_log=False, log_config=None, timeout_graceful_shutdown=5,
    ))
    worker = threading.Thread(
        target=lambda: asyncio.run(server.serve(sockets=[listener])),
        daemon=True,
    )
    worker.start()
    deadline = time.monotonic() + TIMEOUT
    while not server.started:
        if not worker.is_alive() or time.monotonic() >= deadline:
            raise RuntimeError("LangGraph HTTP server did not become ready")
        time.sleep(0.01)
    print(json.dumps({
        "port": listener.getsockname()[1],
        "tokens": [create_access_token(user_id) for user_id in (17, 18, 19)],
    }), flush=True)
    try:
        sys.stdin.readline()
    finally:
        server.should_exit = True
        worker.join(timeout=10)
        listener.close()
        database._engine.dispose()
    if worker.is_alive():
        raise RuntimeError("HTTP server did not stop")


def _verify(base, tokens):
    first, second, admin = tokens
    status, payload = _request(base, "/threads/search", body={})
    if status not in (401, 403):
        raise RuntimeError("Anonymous thread search was not rejected")
    thread = _expect(*_request(base, "/threads", first, {}), 200, "Create thread")
    print("HTTP startup and anonymous rejection passed.", file=sys.stderr)
    thread_id = thread["thread_id"]
    for token in (second, admin):
        status, _ = _request(base, f"/threads/{thread_id}", token)
        if status not in (403, 404):
            raise RuntimeError("Cross-owner thread read was not rejected")
    body = {
        "assistant_id": "agent",
        "input": {"messages": [{"role": "user", "content": "http regression"}]},
        "config": {"configurable": {"request_id": "a" * 32}},
    }
    forged_body = dict(
        body, config={"configurable": {"langgraph_auth_user_id": "999"}}
    )
    status, _ = _request(
        base, f"/threads/{thread_id}/runs/wait", first, forged_body
    )
    if status != 422:
        raise RuntimeError("Reserved HTTP identity input was not rejected")
    for token in (second, admin):
        status, _ = _request(
            base, f"/threads/{thread_id}/runs/wait", token, body
        )
        if status not in (403, 404):
            raise RuntimeError("Cross-owner run creation was not rejected")
    print("HTTP identity and owner rejection passed.", file=sys.stderr)
    result = _expect(
        *_request(base, f"/threads/{thread_id}/runs/wait", first, body),
        200, "Wait run",
    )
    if result["messages"][-1]["content"] != "http-copy-ok":
        raise RuntimeError("Wait run returned an unexpected result")
    print("HTTP wait run passed.", file=sys.stderr)
    state = _expect(
        *_request(base, f"/threads/{thread_id}/state", first),
        200, "Read checkpoint state",
    )
    if state["values"]["messages"][-1]["content"] != "http-copy-ok":
        raise RuntimeError("HTTP state did not retain the run result")
    streamed = _expect(
        *_request(base, "/threads", second, {}), 200, "Create stream thread"
    )["thread_id"]
    stream_body = dict(body, stream_mode=["values"])
    status, stream = _request(
        base, f"/threads/{streamed}/runs/stream", second, stream_body
    )
    if status != 200 or "http-copy-ok" not in stream or "event: error" in stream:
        raise RuntimeError("Stream run did not complete successfully")
    cancel_thread = _expect(
        *_request(base, "/threads", first, {}), 200, "Create cancel thread"
    )["thread_id"]
    cancel_body = {
        "assistant_id": "agent",
        "input": {"messages": [{"role": "user", "content": "wait-for-cancel"}]},
    }
    run = _expect(
        *_request(base, f"/threads/{cancel_thread}/runs", first, cancel_body),
        200, "Create blocking run",
    )
    run_path = f"/threads/{cancel_thread}/runs/{run['run_id']}"
    deadline = time.monotonic() + 10
    while True:
        stats = _expect(*_request(base, "/__verification"), 200, "Observe leases")
        if stats["acquired"] == 3:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Blocking run did not acquire its lease")
        time.sleep(0.02)
    status, _ = _request(
        base, run_path + "/cancel?wait=1&action=interrupt", first, method="POST"
    )
    if status not in (200, 202, 204):
        raise RuntimeError(f"Cancellation returned HTTP {status}")
    deadline = time.monotonic() + 10
    while True:
        stats = _expect(*_request(base, "/__verification"), 200, "Observe release")
        if stats["acquired"] == stats["released"] == 3:
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("Cancellation did not release the lease")
        time.sleep(0.02)
    if stats["subjects"] != ["17", "18"]:
        raise RuntimeError("HTTP run accepted a forged or cross-owner identity")
    if stats["outbound_attempts"]:
        raise RuntimeError("Verification attempted an external connection")
    if not stats["copies"] or not all(
        item["manager_preserved"] for item in stats["copies"]
    ) or not any(
        item["checkpoint_injected"] and item["store_injected"]
        for item in stats["copies"]
    ):
        raise RuntimeError("API graph copies lost a server-owned dependency")
    return {
        "status": "passed",
        "transport": "TCP HTTP",
        "api": "installed LangGraph API",
        "checks": [
            "anonymous rejected", "cross-owner/admin rejected", "wait run",
            "stream run", "checkpoint state", "authenticated identity",
            "reserved identity rejected", "cross-owner run rejected",
            "API copy dependencies", "cancel and single lease release",
        ],
        "leases": {"acquired": 3, "released": 3},
        "outbound_attempts": stats["outbound_attempts"],
        "scope": "synthetic model/lease, SQLite identity, isolated inmem runtime",
        "source_sha256": hashlib.sha256(
            (ROOT / "data_agent/services/agent_service.py").read_bytes()
        ).hexdigest(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.server:
        _server()
        return 0
    with tempfile.TemporaryDirectory(prefix="dda-graph-http-") as scratch:
        diagnostic_file = tempfile.TemporaryFile(mode="w+b")
        process = subprocess.Popen(
            [sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--server"],
            cwd=scratch,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=diagnostic_file,
            text=True,
            encoding="utf-8",
            env={
                key: value for key, value in os.environ.items()
                if key.upper() in {
                    "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP",
                    "APPDATA", "LOCALAPPDATA", "COMSPEC",
                }
            },
        )
        failed = False
        try:
            readiness = queue.Queue()
            threading.Thread(
                target=lambda: readiness.put(process.stdout.readline()),
                daemon=True,
            ).start()
            ready = readiness.get(timeout=TIMEOUT)
            if not ready:
                raise RuntimeError("HTTP verification child failed to start")
            connection = json.loads(ready)
            result = _verify(
                f"http://127.0.0.1:{connection['port']}", connection["tokens"]
            )
        except BaseException:
            failed = True
            raise
        finally:
            if process.poll() is None:
                try:
                    process.stdin.write("stop\n")
                    process.stdin.flush()
                except OSError:
                    pass
            try:
                process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            diagnostic_file.seek(0)
            diagnostic = diagnostic_file.read().decode("utf-8", errors="replace")
            diagnostic_file.close()
            if failed or process.returncode:
                print("HTTP child failed; bounded diagnostics:", file=sys.stderr)
                for line in diagnostic.splitlines()[-40:]:
                    redacted = re.sub(
                        r"\beyJ[\w-]*\.[\w-]+\.[\w-]+",
                        "<REDACTED>", line,
                    )
                    print(redacted[:300], file=sys.stderr)
        if process.returncode:
            raise RuntimeError("HTTP verification child did not shut down successfully")
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
