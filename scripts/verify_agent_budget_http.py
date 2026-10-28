"""Count actual SDK TCP requests across the production parent/child factory."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import secrets
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class ControlledProvider:
    """An OpenAI-compatible loopback server; no paid provider is contacted."""

    def __init__(self, scenario):
        self.scenario = scenario
        self.requests = 0
        self.received = set()
        self.lock = threading.Lock()

    def completion(self, payload, attempt_id):
        with self.lock:
            self.requests += 1
            self.received.add(attempt_id)
            attempt = self.requests
        if self.scenario == "retry" and attempt == 1:
            return 500, {"error": {"message": "isolated retry canary"}}
        messages = payload["messages"]
        user = next(m["content"] for m in messages if m["role"] == "user")
        results = sum(m["role"] == "tool" for m in messages)
        calls = []

        def call(name, index, args):
            return {
                "id": f"call-{name}-{index}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)},
            }

        if self.scenario in ("model", "tool", "parallel"):
            if user.startswith("parent") and not results:
                calls = [
                    call("task", i, {
                        "subagent_type": "general-purpose",
                        "description": f"child-{i}",
                    }) for i in range(2 if self.scenario == "parallel" else 1)
                ]
            elif user.startswith("child"):
                if self.scenario == "tool" and not results:
                    calls = [call("ls", i, {"path": "/"}) for i in range(19)]
                elif self.scenario != "tool" and results < 7:
                    calls = [call("ls", results, {"path": "/"})]
        message = {"role": "assistant", "content": "isolated model canary"}
        if calls:
            message.update(content="", tool_calls=calls)
        return 200, {
            "id": f"completion-{attempt}", "object": "chat.completion",
            "model": "isolated-model", "created": 1,
            "choices": [{
                "index": 0, "message": message,
                "finish_reason": "tool_calls" if calls else "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }


@contextmanager
def serve_provider(provider, *, host="127.0.0.1"):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            size = int(self.headers.get("Content-Length", "0"))
            if size > 4 * 1024 * 1024:
                self.send_error(413)
                return
            payload = json.loads(self.rfile.read(size))
            status, body = provider.completion(payload, self.headers.get("X-Gate-Attempt"))
            if status == 200 and payload.get("stream"):
                message = body["choices"][0]["message"]
                delta = dict(message)
                if "tool_calls" in delta:
                    delta["tool_calls"] = [
                        {"index": i, **call} for i, call in enumerate(delta["tool_calls"])
                    ]
                body["object"] = "chat.completion.chunk"
                body["choices"] = [{"index": 0, "delta": delta, "finish_reason": None}]
                content = f"data: {json.dumps(body)}\n\ndata: [DONE]\n\n".encode()
                content_type = "text/event-stream"
            else:
                content = json.dumps(body).encode()
                content_type = "application/json"
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            if status == 500:
                self.send_header("retry-after-ms", "1")
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                # A sibling's hard refusal can cancel an already sent request.
                pass

    server = ThreadingHTTPServer((host, 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1"
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


class AttemptTracker:
    """Observe real HTTP transports without replacing their TCP behavior."""

    def __init__(self, *, cancel_pending_at=None):
        self.reserved = set()
        self.cancelled = set()
        self.cancel_pending_at = cancel_pending_at
        self.lock = threading.Lock()

    def hook(self, request):
        attempt_id = uuid4().hex
        request.headers["X-Gate-Attempt"] = attempt_id
        with self.lock:
            self.reserved.add(attempt_id)

    async def ahook(self, request):
        self.hook(request)

    def clients(self, factory):
        import httpx

        sync, asynchronous = factory()
        sync.event_hooks["request"].append(self.hook)
        asynchronous.event_hooks["request"].append(self.ahook)
        tracker = self
        delegate = asynchronous._transport

        class Transport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                try:
                    if len(tracker.reserved) == tracker.cancel_pending_at:
                        # Hold one child after charging but before TCP. Its
                        # sibling's next attempt must refuse and cancel it.
                        await asyncio.Event().wait()
                    return await delegate.handle_async_request(request)
                except asyncio.CancelledError:
                    with tracker.lock:
                        tracker.cancelled.add(request.headers["X-Gate-Attempt"])
                    raise

            async def aclose(self):
                await delegate.aclose()

        asynchronous._transport = Transport()
        return sync, asynchronous


def verify(redis_url=None):
    monitor = None
    if redis_url:
        address = urlparse(redis_url)
        if (
            address.scheme != "redis" or address.hostname not in ("127.0.0.1", "::1")
            or address.username or address.password or address.path not in ("", "/", "/0")
        ):
            raise ValueError("tcp_budget_requires_private_loopback_redis")
        from redis import Redis

        monitor = Redis.from_url(redis_url, socket_timeout=2)
        if monitor.dbsize():
            raise ValueError("tcp_budget_requires_empty_redis")
    os.environ.update(
        PYTHON_DOTENV_DISABLED="1", LANGSMITH_TRACING="false",
        LANGCHAIN_TRACING_V2="false", LANGSMITH_API_KEY="",
        DATABASE_URL="sqlite://", REDIS_URL=redis_url or "redis://127.0.0.1:1/0",
        JWT_SECRET_KEY=secrets.token_hex(32),
        LOG_FILE_PATH="",
    )
    logging.disable(logging.CRITICAL)
    from langchain_core.messages import HumanMessage

    from data_agent.config.config import config
    from data_agent.services import agent_budget, agent_service
    from data_agent.services.agent_lease import AgentLease, AgentLeaseManager

    class Lease(AgentLeaseManager):
        def acquire(self, subject):
            return AgentLease(str(uuid4()), self.subject_digest(subject), 75000)

        async def acquire_async(self, subject):
            return self.acquire(subject)

        def release(self, lease):
            return True

    events = []

    class RecordingRedisLease(AgentLeaseManager):
        def acquire(self, subject):
            result = super().acquire(subject)
            events.append("acquired")
            return result

        async def acquire_async(self, subject):
            result = await super().acquire_async(subject)
            events.append("acquired")
            return result

        def release(self, lease):
            result = super().release(lease)
            if not result:
                raise RuntimeError("tcp_budget_real_lease_release_failed")
            events.append("released")
            return result

    lease = RecordingRedisLease() if redis_url else Lease()
    results = []
    completed = []
    original_emit = agent_budget.emit_event

    def record(logger, event, **fields):
        if event == "agent.budget.completed":
            completed.append(fields)
        original_emit(logger, event, **fields)

    agent_budget.emit_event = record
    original_lease = agent_service.global_agent_lease_manager
    original_clients = agent_service.budget_http_clients
    agent_service.global_agent_lease_manager = lease
    original_config = {
        name: getattr(config, name) for name in (
            "MOONSHOT_API_KEY", "MODEL_BASE_URL", "AGENT_MODEL_CALL_LIMIT",
            "AGENT_TOOL_CALL_LIMIT", "AGENT_RUN_TIMEOUT_SECONDS",
        )
    }
    try:
        config.MOONSHOT_API_KEY = "isolated-model-key"
        config.AGENT_RUN_TIMEOUT_SECONDS = 30
        for scenario in ("model", "tool", "parallel", "retry", "summary"):
            for mode in ("invoke", "stream", "ainvoke", "astream"):
                provider = ControlledProvider(scenario)
                cancellation_canary = scenario == "parallel" and mode in ("ainvoke", "astream")
                tracker = AttemptTracker(cancel_pending_at=8 if cancellation_canary else None)
                agent_service.budget_http_clients = lambda: tracker.clients(original_clients)
                with serve_provider(provider) as base:
                    config.MODEL_BASE_URL = base
                    config.AGENT_MODEL_CALL_LIMIT = 1 if scenario in ("retry", "summary") else 8
                    config.AGENT_TOOL_CALL_LIMIT = 12
                    graph = agent_service.create_agent_graph().copy().with_config({})
                    auth = {"configurable": {
                        "langgraph_auth_user": SimpleNamespace(identity="17", is_authenticated=True),
                        "langgraph_auth_permissions": ["agent.invoke_own"],
                    }}
                    value = {"messages": (
                        [HumanMessage(content=f"history-{i}: " + "x" * 100000)
                         for i in range(8)]
                        if scenario == "summary" else [HumanMessage(content="parent")]
                    )}

                    async def run():
                        if mode == "ainvoke":
                            await graph.ainvoke(value, auth)
                        else:
                            stream = graph.astream(value, auth, stream_mode="values")
                            try:
                                async for _ in stream:
                                    pass
                            finally:
                                await stream.aclose()

                    try:
                        if mode in ("ainvoke", "astream"):
                            asyncio.run(run())
                        elif mode == "invoke":
                            graph.invoke(value, auth)
                        else:
                            list(graph.stream(value, auth, stream_mode="values"))
                    except (agent_budget.AgentModelBudgetExceededError,
                            agent_budget.AgentToolBudgetExceededError) as exc:
                        error = str(exc)
                    else:
                        raise RuntimeError("tcp_budget_refusal_missing")
                # Shutdown joins request handlers before checking receipt IDs.
                count = completed[-1]
                missing = tracker.reserved - provider.received
                assert len(completed) == len(results) + 1
                assert provider.requests == len(provider.received)
                assert provider.received <= tracker.reserved, "unbudgeted_tcp_request"
                assert missing <= tracker.cancelled, "unexplained_unreceived_request"
                assert count["model_requests"] == len(tracker.reserved)
                expected = "agent_tool_budget_exceeded" if scenario == "tool" else "agent_model_budget_exceeded"
                assert error == expected
                assert count["model_requests"] == (2 if scenario == "tool" else config.AGENT_MODEL_CALL_LIMIT)
                assert provider.requests <= config.AGENT_MODEL_CALL_LIMIT
                if scenario != "parallel":
                    assert not missing
                if cancellation_canary:
                    assert len(missing) == 1
                if scenario == "tool":
                    assert count["tool_calls"] == 12
                if monitor:
                    assert monitor.dbsize() == 0, "tcp_budget_lease_keys_remain"
                    assert events == ["acquired", "released"] * (len(results) + 1)
                results.append({
                    "scenario": scenario, "surface": mode, "error": error,
                    "model_requests": count["model_requests"],
                    "received_requests": provider.requests,
                    "cancelled_before_receipt": len(missing),
                    "transport_cancellations": len(tracker.cancelled),
                    "deliberate_parallel_cancellation": cancellation_canary,
                    "tool_calls": count["tool_calls"],
                })
        return {
            "gate": "agent_budget_tcp", "passed": len(results), "cases": results,
            "lease_storage": "Redis" if monitor else "synthetic",
            "leases": {
                "acquired": events.count("acquired"),
                "released": events.count("released"),
                "remaining_keys": monitor.dbsize(),
            } if monitor else None,
        }
    finally:
        agent_budget.emit_event = original_emit
        agent_service.global_agent_lease_manager = original_lease
        agent_service.budget_http_clients = original_clients
        for name, value in original_config.items():
            setattr(config, name, value)
        if monitor:
            monitor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    storage = parser.add_mutually_exclusive_group()
    storage.add_argument("--redis-url")
    storage.add_argument("--isolated-redis", action="store_true")
    args = parser.parse_args()
    container_id = None

    def docker(*command):
        result = subprocess.run(
            ["docker", *command], capture_output=True, text=True, timeout=60,
        )
        if result.returncode:
            raise RuntimeError("tcp_budget_redis_container_command_failed")
        return result.stdout.strip()

    try:
        redis_url = args.redis_url
        if args.isolated_redis:
            container_id = docker(
                "run", "-d", "--label", "dda.gate=aggregate-budget",
                "--tmpfs", "/data:rw,size=64m", "-p", "127.0.0.1::6379",
                "redis:7-alpine",
            )
            inspection = json.loads(docker("inspect", container_id))[0]
            port = inspection["NetworkSettings"]["Ports"]["6379/tcp"][0]["HostPort"]
            redis_url = f"redis://127.0.0.1:{port}/0"
            from redis import Redis
            from redis.exceptions import \
                ConnectionError as RedisConnectionError

            with Redis.from_url(redis_url, socket_timeout=1) as monitor:
                deadline = time.monotonic() + 10
                while True:
                    try:
                        monitor.ping()
                        break
                    except (RedisConnectionError, OSError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError("tcp_budget_redis_startup_timeout") from None
                        time.sleep(0.05)
        print(json.dumps(verify(redis_url)))
    finally:
        if container_id:
            docker("rm", "-f", container_id)


if __name__ == "__main__":
    main()
