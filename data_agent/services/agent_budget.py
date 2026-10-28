"""One server-owned ledger shared by every execution branch of an Agent run."""

from contextlib import contextmanager
from contextvars import ContextVar
from threading import Lock
from typing import Iterator

import httpx
from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest

from data_agent.config.logger import agent_logger
from data_agent.observability.events import emit_event

AGENT_MODEL_BUDGET_EXCEEDED = "agent_model_budget_exceeded"
AGENT_TOOL_BUDGET_EXCEEDED = "agent_tool_budget_exceeded"


class AgentModelBudgetExceededError(RuntimeError):
    """The run's actual model-request budget is exhausted."""

    def __init__(self) -> None:
        super().__init__(AGENT_MODEL_BUDGET_EXCEEDED)


class AgentToolBudgetExceededError(RuntimeError):
    """The run's aggregate tool-execution budget is exhausted."""

    def __init__(self) -> None:
        super().__init__(AGENT_TOOL_BUDGET_EXCEEDED)


class RunBudget:
    """Atomically reserve work before its side effect, including failed work."""

    def __init__(self, model_limit: int, tool_limit: int) -> None:
        self.model_limit = model_limit
        self.tool_limit = tool_limit
        self.model_requests = 0
        self.tool_calls = 0
        self._failure: str | None = None
        self._lock = Lock()

    def _check_locked(self) -> None:
        # Fresh exceptions avoid sharing/retaining tracebacks across branches.
        if self._failure == "model":
            raise AgentModelBudgetExceededError()
        if self._failure == "tool":
            raise AgentToolBudgetExceededError()

    def check(self) -> None:
        with self._lock:
            self._check_locked()

    def reserve(self, kind: str) -> None:
        with self._lock:
            self._check_locked()
            if kind == "model":
                if self.model_requests >= self.model_limit:
                    self._failure = "model"
                else:
                    self.model_requests += 1
            elif kind == "tool":
                if self.tool_calls >= self.tool_limit:
                    self._failure = "tool"
                else:
                    self.tool_calls += 1
            else:
                raise ValueError("unknown agent budget kind")
            self._check_locked()


_active_budget: ContextVar[RunBudget | None] = ContextVar(
    "agent_run_budget", default=None
)


def active_run_budget() -> RunBudget:
    budget = _active_budget.get()
    if budget is None:
        # A graph/model invoked outside the server-owned execution boundary
        # must never silently run without accounting.
        raise RuntimeError("agent_budget_context_missing")
    return budget


@contextmanager
def hold_run_budget(model_limit: int, tool_limit: int) -> Iterator[RunBudget]:
    budget = RunBudget(model_limit, tool_limit)
    token = _active_budget.set(budget)
    outcome = "error"
    try:
        try:
            yield budget
        except Exception:
            # SDK connection-error wrapping or a middleware fallback must not
            # turn a hard refusal into an upstream error or successful result.
            budget.check()
            raise
        budget.check()
        outcome = "success"
    finally:
        _active_budget.reset(token)
        emit_event(
            agent_logger,
            "agent.budget.completed",
            outcome=outcome,
            model_requests=budget.model_requests,
            tool_calls=budget.tool_calls,
            model_limit=budget.model_limit,
            tool_limit=budget.tool_limit,
        )


def reserve_model_request(_request: httpx.Request) -> None:
    """HTTPX runs this before each SDK attempt, including retries and streams."""
    active_run_budget().reserve("model")


async def areserve_model_request(request: httpx.Request) -> None:
    reserve_model_request(request)


def budget_http_clients(
    transport: httpx.BaseTransport | httpx.AsyncBaseTransport | None = None,
) -> tuple[httpx.Client, httpx.AsyncClient]:
    """Build process-lived model clients with no transport-level retries."""
    return (
        httpx.Client(
            transport=transport,
            event_hooks={"request": [reserve_model_request]},
            follow_redirects=False,
        ),
        httpx.AsyncClient(
            transport=transport,
            event_hooks={"request": [areserve_model_request]},
            follow_redirects=False,
        ),
    )


class AggregateToolBudgetMiddleware(AgentMiddleware):
    """Count every tool, including injected built-ins and the parent task."""

    def wrap_tool_call(self, request: ToolCallRequest, handler):
        active_run_budget().reserve("tool")
        return handler(request)

    async def awrap_tool_call(self, request: ToolCallRequest, handler):
        active_run_budget().reserve("tool")
        return await handler(request)
