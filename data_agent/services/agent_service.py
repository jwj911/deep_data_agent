import hashlib
from threading import Lock
from uuid import uuid4

from deepagents import create_deep_agent
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from data_agent.config.config import ConfigurationError, config
from data_agent.config.logger import agent_logger
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
        agent_logger.info("Processing agent query request_id=%s", request_id)

        cache_key = _generate_cache_key(query)
        cached_result = global_cache_service.get(cache_key)
        if cached_result:
            agent_logger.info(
                "Using cached agent response request_id=%s", request_id
            )
            return cached_result

        try:
            result = self._get_agent().invoke(
                {"messages": [HumanMessage(content=query)]}
            )
            response = result["messages"][-1].content
            global_cache_service.set(cache_key, response, expire=86400)
            agent_logger.info(
                "Agent query completed request_id=%s", request_id
            )
            return response
        except ConfigurationError:
            agent_logger.warning(
                "Agent configuration error request_id=%s", request_id
            )
            raise
        except Exception as exc:
            agent_logger.exception(
                "Agent invocation failed request_id=%s", request_id
            )
            raise AgentInvocationError(
                "Agent upstream request failed"
            ) from exc


global_agent_service = AgentService()
