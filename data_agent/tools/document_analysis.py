import logging
from time import perf_counter

from langchain_core.runnables import RunnableConfig

from data_agent.config.database import get_session_factory
from data_agent.config.logger import tool_logger
from data_agent.models.user import User
from data_agent.observability.context import bind_runnable_request_id
from data_agent.observability.events import emit_event
from data_agent.services.authorization_service import AuthorizationDeniedError
from data_agent.services.managed_file_service import (
    ManagedFileError, global_managed_file_service)


def _actor_id_from_config(config: RunnableConfig) -> int | None:
    configurable = config.get("configurable", {})
    value = configurable.get("langgraph_auth_user_id")
    if (
        not isinstance(value, str)
        or not value.isdigit()
        or int(value) <= 0
        or str(int(value)) != value
    ):
        return None
    return int(value)


def analyze_document(
    file_id: str,
    config: RunnableConfig,
) -> dict[str, object]:
    """Analyze one managed text file owned by the authenticated user."""
    with bind_runnable_request_id():
        started_at = perf_counter()
        emit_event(
            tool_logger,
            "tool.started",
            operation="analyze",
            tool_name="analyze_document",
            outcome="started",
        )
        actor_id = _actor_id_from_config(config)
        if actor_id is None:
            emit_event(
                tool_logger,
                "tool.failed",
                level=logging.WARNING,
                operation="analyze",
                tool_name="analyze_document",
                outcome="rejected",
                error_code="managed_file_auth_required",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {"error": "managed_file_auth_required"}
        try:
            with get_session_factory()() as db:
                actor = db.get(User, actor_id)
                if actor is None:
                    return {"error": "managed_file_not_found"}
                result = global_managed_file_service.analyze_file(
                    db,
                    actor,
                    file_id,
                )
            if result is None:
                return {"error": "managed_file_not_found"}
            emit_event(
                tool_logger,
                "tool.completed",
                operation="analyze",
                tool_name="analyze_document",
                outcome="success",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return result
        except (ManagedFileError, AuthorizationDeniedError) as exc:
            error_code = (
                exc.code
                if isinstance(exc, ManagedFileError)
                else "managed_file_not_found"
            )
            emit_event(
                tool_logger,
                "tool.failed",
                level=logging.WARNING,
                operation="analyze",
                tool_name="analyze_document",
                outcome="rejected",
                error_code=error_code,
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {"error": error_code}
        except Exception:
            tool_logger.exception(
                "Document analysis failed",
                extra={
                    "event_name": "tool.failed",
                    "event_fields": {
                        "operation": "analyze",
                        "tool_name": "analyze_document",
                        "outcome": "error",
                        "error_code": "document_error",
                        "duration_ms": (
                            perf_counter() - started_at
                        )
                        * 1000,
                    },
                },
            )
            return {"error": "document_error"}
