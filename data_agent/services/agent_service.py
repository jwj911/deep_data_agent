import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator, Iterator, Mapping
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4

from deepagents import create_deep_agent
from langchain.agents.middleware import (ModelCallLimitMiddleware,
                                         ToolCallLimitMiddleware)
from langchain.agents.middleware.model_call_limit import \
    ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import \
    ToolCallLimitExceededError
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph.state import CompiledStateGraph

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import agent_logger
from data_agent.models.user import User
from data_agent.observability.context import bind_request_id
from data_agent.observability.events import emit_event
from data_agent.services.agent_lease import (AGENT_BUSY,
                                             AGENT_PROTECTION_UNAVAILABLE,
                                             AgentBusyError,
                                             AgentIdentityError,
                                             AgentLeaseManager,
                                             AgentProtectionUnavailableError,
                                             get_active_agent_subject,
                                             global_agent_lease_manager)
from data_agent.services.authorization_service import (
    AuthorizationDeniedError, Permission, ensure_permission)
from data_agent.services.cache_service import global_cache_service
from data_agent.tools.tool_manager import global_tool_manager

_TOOL_POLICY_VERSION = "3"
_SERVER_CONFIG = config
AGENT_CANCELLED = "agent_cancelled"
AGENT_INVALID_QUERY = "agent_invalid_query"
AGENT_MODEL_BUDGET_EXCEEDED = "agent_model_budget_exceeded"
AGENT_RESPONSE_TOO_LARGE = "agent_response_too_large"
AGENT_TIMEOUT = "agent_timeout"
AGENT_TOOL_BUDGET_EXCEEDED = "agent_tool_budget_exceeded"
_CLIENT_BUDGET_KEYS = frozenset(
    {
        "max_completion_tokens",
        "max_retries",
        "max_tokens",
        "model_call_limit",
        "request_timeout",
        "timeout",
        "tool_call_limit",
    }
)
_CLIENT_IDENTITY_KEYS = frozenset({"langgraph_auth_user_id"})

_BASE_RESEARCH_INSTRUCTIONS = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

You have access to the following tools:

## `internet_search`
Use this for bounded general or news searches. Queries may contain at most
2,000 characters and return at most 5 results. Raw page content and media
search are unavailable.

## `analyze_document`
Use this to analyze an attached managed text file. Provide only the file UUID
from a `__managed_file_v1__` reference in the user message; never provide a
server or local path.

Finally, translate the answer to Chinese.
"""


class AgentInvocationError(RuntimeError):
    """Raised when an upstream agent invocation fails."""


class AgentModelBudgetExceededError(RuntimeError):
    """Raised when the server-owned model-call budget is exhausted."""

    def __init__(self) -> None:
        super().__init__(AGENT_MODEL_BUDGET_EXCEEDED)


class AgentToolBudgetExceededError(RuntimeError):
    """Raised when the server-owned tool-call budget is exhausted."""

    def __init__(self) -> None:
        super().__init__(AGENT_TOOL_BUDGET_EXCEEDED)


class AgentQueryValidationError(ValueError):
    """Raised when a service caller bypasses the HTTP query schema."""

    def __init__(self) -> None:
        super().__init__(AGENT_INVALID_QUERY)


class AgentResponseTooLargeError(RuntimeError):
    """Raised when the final Agent text exceeds the response budget."""

    def __init__(self) -> None:
        super().__init__(AGENT_RESPONSE_TOO_LARGE)


class AgentTimeoutError(TimeoutError):
    """Raised when an Agent run exceeds its server-owned deadline."""

    def __init__(self) -> None:
        super().__init__(AGENT_TIMEOUT)


def _stable_budget_error(error: Exception) -> RuntimeError:
    if isinstance(
        error,
        (AgentModelBudgetExceededError, ModelCallLimitExceededError),
    ):
        return AgentModelBudgetExceededError()
    return AgentToolBudgetExceededError()


def _bounded_run_config(
    run_config: RunnableConfig | None,
) -> RunnableConfig:
    """Copy client config while enforcing server-owned resource budgets."""
    bounded = dict(run_config or {})
    for key in _CLIENT_BUDGET_KEYS | _CLIENT_IDENTITY_KEYS:
        bounded.pop(key, None)
    configurable = dict(bounded.get("configurable") or {})
    for key in (
        _CLIENT_BUDGET_KEYS
        | _CLIENT_IDENTITY_KEYS
        | {"recursion_limit"}
    ):
        configurable.pop(key, None)
    bounded["configurable"] = configurable
    if "context" in bounded:
        context = dict(bounded.get("context") or {})
        for key in (
            _CLIENT_BUDGET_KEYS
            | _CLIENT_IDENTITY_KEYS
            | {"recursion_limit"}
        ):
            context.pop(key, None)
        bounded["context"] = context
    bounded["recursion_limit"] = config.AGENT_RECURSION_LIMIT
    return bounded


def _canonical_subject(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if (
        not isinstance(value, str)
        or not value.isdigit()
        or int(value) <= 0
        or str(int(value)) != value
    ):
        raise AgentIdentityError()
    return value


def _authenticated_subject(run_config: RunnableConfig) -> str:
    active_subject = get_active_agent_subject()
    if active_subject is not None:
        return _canonical_subject(active_subject)

    configurable = run_config.get("configurable") or {}
    auth_user = configurable.get("langgraph_auth_user")
    if isinstance(auth_user, Mapping):
        is_authenticated = auth_user.get("is_authenticated")
        identity = auth_user.get("identity")
    else:
        is_authenticated = getattr(
            auth_user,
            "is_authenticated",
            False,
        )
        identity = getattr(auth_user, "identity", None)
    permissions = configurable.get("langgraph_auth_permissions")
    if (
        is_authenticated is not True
        or not isinstance(permissions, (list, tuple, set, frozenset))
        or Permission.AGENT_INVOKE_OWN.value not in permissions
    ):
        raise AgentIdentityError()
    return _canonical_subject(identity)


def _prepare_run_config(
    run_config: RunnableConfig | None,
) -> tuple[RunnableConfig, str]:
    bounded = _bounded_run_config(run_config)
    subject = _authenticated_subject(bounded)
    configurable = dict(bounded.get("configurable") or {})
    configurable["langgraph_auth_user_id"] = subject
    bounded["configurable"] = configurable
    return bounded, subject


class ResourceBoundedAgentGraph(CompiledStateGraph):
    """Compiled graph with server-owned recursion, deadline and lease bounds."""

    _agent_lease_manager: AgentLeaseManager

    def stream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Iterator[Any]:
        bounded, subject = _prepare_run_config(config)
        deadline = perf_counter() + _SERVER_CONFIG.AGENT_RUN_TIMEOUT_SECONDS
        try:
            with self._agent_lease_manager.hold(subject):
                for chunk in super().stream(input, bounded, **kwargs):
                    if perf_counter() > deadline:
                        raise AgentTimeoutError()
                    yield chunk
        except (
            ModelCallLimitExceededError,
            ToolCallLimitExceededError,
        ) as exc:
            raise _stable_budget_error(exc) from exc

    async def astream(
        self,
        input: Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        bounded, subject = _prepare_run_config(config)
        try:
            async with asyncio.timeout(
                _SERVER_CONFIG.AGENT_RUN_TIMEOUT_SECONDS
            ):
                async with self._agent_lease_manager.hold_async(subject):
                    async for chunk in super().astream(
                        input,
                        bounded,
                        **kwargs,
                    ):
                        yield chunk
        except (
            ModelCallLimitExceededError,
            ToolCallLimitExceededError,
        ) as exc:
            raise _stable_budget_error(exc) from exc
        except TimeoutError as exc:
            raise AgentTimeoutError() from exc


def _apply_graph_resource_bounds(
    graph: CompiledStateGraph,
    lease_manager: AgentLeaseManager | None = None,
) -> ResourceBoundedAgentGraph:
    attributes = {
        key: value
        for key, value in graph.__dict__.items()
        if key != "__orig_class__"
    }
    bounded = ResourceBoundedAgentGraph(**attributes)
    bounded._agent_lease_manager = (
        lease_manager or global_agent_lease_manager
    )
    return bounded


def _generate_cache_key(query: str, actor_id: int) -> str:
    """Generate a tenant- and policy-scoped cache key."""
    tool_policy = ",".join(
        sorted(global_tool_manager.get_tool_names())
    )
    material = "\n".join(
        (
            f"tenant:{actor_id}",
            f"model:{config.MODEL_NAME}",
            f"base_url:{config.MODEL_BASE_URL}",
            f"temperature:{config.MODEL_TEMPERATURE}",
            f"tool_policy:{_TOOL_POLICY_VERSION}:{tool_policy}",
            f"query:{query}",
        )
    )
    return "agent:" + hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


def create_agent_graph():
    """Build the LangGraph-compatible agent without importing FastAPI or DB code."""
    agent_logger.info("Creating agent graph")
    tools = global_tool_manager.get_all_tools()
    agent_logger.info(
        "Registered agent tools: %s", global_tool_manager.get_tool_names()
    )

    graph = create_deep_agent(
        tools=tools,
        system_prompt=_BASE_RESEARCH_INSTRUCTIONS,
        model=ChatOpenAI(
            model=config.MODEL_NAME,
            api_key=config.require_model_api_key(),
            base_url=config.MODEL_BASE_URL,
            temperature=config.MODEL_TEMPERATURE,
            timeout=config.MODEL_REQUEST_TIMEOUT_SECONDS,
            max_retries=config.MODEL_MAX_RETRIES,
            max_tokens=config.MODEL_MAX_OUTPUT_TOKENS,
        ),
        middleware=(
            ModelCallLimitMiddleware(
                run_limit=config.AGENT_MODEL_CALL_LIMIT,
                exit_behavior="error",
            ),
            ToolCallLimitMiddleware(
                run_limit=config.AGENT_TOOL_CALL_LIMIT,
                exit_behavior="error",
            ),
        ),
    )
    agent_logger.info("Agent graph created")
    return _apply_graph_resource_bounds(graph)


class AgentService:
    """Service for managing AI agents"""

    def __init__(
        self,
        agent=None,
        lease_manager: AgentLeaseManager | None = None,
    ) -> None:
        self._agent = agent
        self._agent_lock = Lock()
        self._lease_manager = lease_manager or global_agent_lease_manager

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        with self._agent_lock:
            if self._agent is None:
                self._agent = create_agent_graph()
        return self._agent

    @staticmethod
    def _validate_query(query: str) -> None:
        if (
            not isinstance(query, str)
            or not query.strip()
            or len(query) > config.AGENT_QUERY_MAX_CHARS
        ):
            raise AgentQueryValidationError()

    @staticmethod
    def _response_text(result: Any) -> str:
        try:
            response = result["messages"][-1].content
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise AgentInvocationError(
                "Agent upstream request failed"
            ) from exc
        return AgentService._validate_response_text(response)

    @staticmethod
    def _validate_response_text(response: Any) -> str:
        if not isinstance(response, str):
            raise AgentInvocationError("Agent upstream request failed")
        if len(response) > config.AGENT_RESPONSE_MAX_CHARS:
            raise AgentResponseTooLargeError()
        return response

    async def ainvoke(
        self,
        query: str,
        actor: User,
        request_id: str | None = None,
    ) -> str:
        """Invoke the graph asynchronously within the total run deadline."""
        ensure_permission(actor, Permission.AGENT_INVOKE_OWN)
        actor_id = getattr(actor, "id", None)
        if (
            not isinstance(actor_id, int)
            or isinstance(actor_id, bool)
            or actor_id <= 0
        ):
            raise AuthorizationDeniedError("permission denied")
        self._validate_query(query)

        request_id = request_id or uuid4().hex
        with bind_request_id(request_id) as bound_request_id:
            started_at = perf_counter()
            emit_event(
                agent_logger,
                "agent.request.started",
                operation="ainvoke",
                outcome="started",
            )
            cache_key = _generate_cache_key(query, actor_id)

            try:
                async with asyncio.timeout(
                    config.AGENT_RUN_TIMEOUT_SECONDS
                ):
                    async with self._lease_manager.hold_async(
                        str(actor_id)
                    ):
                        cached_result = await global_cache_service.aget(
                            cache_key
                        )
                        if cached_result is not None:
                            response = self._validate_response_text(
                                cached_result
                            )
                            cache_status = "hit"
                        else:
                            result = await self._get_agent().ainvoke(
                                {
                                    "messages": [
                                        HumanMessage(content=query)
                                    ]
                                },
                                config=_bounded_run_config(
                                    {
                                        "configurable": {
                                            "request_id": bound_request_id,
                                        },
                                        "metadata": {
                                            "request_id": bound_request_id,
                                        },
                                    },
                                ),
                            )
                            response = self._response_text(result)
                            await global_cache_service.aset(
                                cache_key,
                                response,
                                expire=86400,
                            )
                            cache_status = "miss"
                emit_event(
                    agent_logger,
                    "agent.request.completed",
                    operation="ainvoke",
                    outcome="success",
                    cache_status=cache_status,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return response
            except AgentQueryValidationError:
                raise
            except AgentBusyError as exc:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_BUSY,
                    retry_after=exc.retry_after,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except AgentProtectionUnavailableError as exc:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_PROTECTION_UNAVAILABLE,
                    retry_after=exc.retry_after,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except (
                AgentModelBudgetExceededError,
                ModelCallLimitExceededError,
            ) as exc:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_MODEL_BUDGET_EXCEEDED,
                    limit=config.AGENT_MODEL_CALL_LIMIT,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise AgentModelBudgetExceededError() from exc
            except (
                AgentToolBudgetExceededError,
                ToolCallLimitExceededError,
            ) as exc:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_TOOL_BUDGET_EXCEEDED,
                    limit=config.AGENT_TOOL_CALL_LIMIT,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise AgentToolBudgetExceededError() from exc
            except AgentResponseTooLargeError:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_RESPONSE_TOO_LARGE,
                    limit=config.AGENT_RESPONSE_MAX_CHARS,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except AgentTimeoutError:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_TIMEOUT,
                    limit=config.AGENT_RUN_TIMEOUT_SECONDS,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except TimeoutError as exc:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_TIMEOUT,
                    limit=config.AGENT_RUN_TIMEOUT_SECONDS,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise AgentTimeoutError() from exc
            except asyncio.CancelledError:
                emit_event(
                    agent_logger,
                    "agent.request.cancelled",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code=AGENT_CANCELLED,
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except ConfigurationError:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="ainvoke",
                    outcome="rejected",
                    error_code="agent_not_configured",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except AgentInvocationError:
                emit_event(
                    agent_logger,
                    "model.failure",
                    level=logging.ERROR,
                    operation="ainvoke",
                    outcome="error",
                    error_code="agent_upstream_error",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except Exception as exc:
                emit_event(
                    agent_logger,
                    "model.failure",
                    level=logging.ERROR,
                    operation="ainvoke",
                    outcome="error",
                    error_code="agent_upstream_error",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                agent_logger.exception(
                    "Agent invocation failed",
                    extra={
                        "event_name": "agent.request.failed",
                        "event_fields": {
                            "operation": "ainvoke",
                            "outcome": "error",
                            "error_code": "agent_upstream_error",
                            "duration_ms": (
                                perf_counter() - started_at
                            )
                            * 1000,
                        },
                    },
                )
                raise AgentInvocationError(
                    "Agent upstream request failed"
                ) from exc


global_agent_service = AgentService()
