import hashlib
import logging
from threading import Lock
from time import perf_counter
from uuid import uuid4

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import agent_logger
from data_agent.observability.context import bind_request_id
from data_agent.observability.events import emit_event
from data_agent.services.cache_service import global_cache_service
from data_agent.tools.tool_manager import global_tool_manager

_BASE_RESEARCH_INSTRUCTIONS = """You are an expert researcher. Your job is to conduct thorough research and then write a polished report.

You have access to the following tools:

## `internet_search`
Use this to run an internet search for a given query. You can specify the max number of results to return, the topic, and whether raw content should be included.

## `analyze_document`
Use this to analyze a document and return its content and metadata. Provide the file path as input.

Finally, translate the answer to Chinese.
"""


class AgentInvocationError(RuntimeError):
    """Raised when an upstream agent invocation fails."""


def _generate_cache_key(query: str) -> str:
    """Generate cache key for agent query"""
    key = f"agent:{query}"
    return hashlib.md5(key.encode()).hexdigest()


def _build_system_prompt() -> str:
    if "execute_python_code" not in global_tool_manager.get_tool_names():
        return _BASE_RESEARCH_INSTRUCTIONS
    return (
        _BASE_RESEARCH_INSTRUCTIONS
        + """

## `execute_python_code`
Use this to execute Python code and return the output. Provide the code as input.
"""
    )


def create_agent_graph():
    """Build the LangGraph-compatible agent without importing FastAPI or DB code."""
    agent_logger.info("Creating agent graph")
    tools = global_tool_manager.get_all_tools()
    agent_logger.info(
        "Registered agent tools: %s", global_tool_manager.get_tool_names()
    )

    graph = create_deep_agent(
        tools=tools,
        system_prompt=_build_system_prompt(),
        model=ChatOpenAI(
            model=config.MODEL_NAME,
            api_key=config.require_model_api_key(),
            base_url=config.MODEL_BASE_URL,
            temperature=config.MODEL_TEMPERATURE,
        ),
    )
    agent_logger.info("Agent graph created")
    return graph


class AgentService:
    """Service for managing AI agents"""

    def __init__(self, agent=None) -> None:
        self._agent = agent
        self._agent_lock = Lock()

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        with self._agent_lock:
            if self._agent is None:
                self._agent = create_agent_graph()
        return self._agent

    def invoke(self, query: str, request_id: str | None = None) -> str:
        """Invoke the agent and propagate stable exceptions to the API layer."""
        request_id = request_id or uuid4().hex
        with bind_request_id(request_id) as bound_request_id:
            started_at = perf_counter()
            emit_event(
                agent_logger,
                "agent.request.started",
                operation="invoke",
                outcome="started",
            )
            cache_key = _generate_cache_key(query)
            cached_result = global_cache_service.get(cache_key)
            if cached_result:
                emit_event(
                    agent_logger,
                    "agent.request.completed",
                    operation="invoke",
                    outcome="success",
                    cache_status="hit",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return cached_result

            try:
                result = self._get_agent().invoke(
                    {"messages": [HumanMessage(content=query)]},
                    config={
                        "configurable": {
                            "request_id": bound_request_id,
                        },
                        "metadata": {
                            "request_id": bound_request_id,
                        },
                    },
                )
                response = result["messages"][-1].content
                global_cache_service.set(
                    cache_key,
                    response,
                    expire=86400,
                )
                emit_event(
                    agent_logger,
                    "agent.request.completed",
                    operation="invoke",
                    outcome="success",
                    cache_status="miss",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return response
            except ConfigurationError:
                emit_event(
                    agent_logger,
                    "agent.request.rejected",
                    level=logging.WARNING,
                    operation="invoke",
                    outcome="rejected",
                    error_code="agent_not_configured",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                raise
            except Exception as exc:
                emit_event(
                    agent_logger,
                    "model.failure",
                    level=logging.ERROR,
                    operation="invoke",
                    outcome="error",
                    error_code="agent_upstream_error",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                agent_logger.exception(
                    "Agent invocation failed",
                    extra={
                        "event_name": "agent.request.failed",
                        "event_fields": {
                            "operation": "invoke",
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
