"""Chat adapter for the canonical managed-file statistics service."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from threading import BoundedSemaphore

from langchain_core.tools import StructuredTool, ToolException
from pydantic import BaseModel, ConfigDict, Field

from data_agent.config.database import get_session_factory
from data_agent.models.user import User
from data_agent.services.agent_lease import get_active_agent_subject
from data_agent.services.authorization_service import AuthorizationDeniedError
from data_agent.services.managed_file_service import (
    ManagedFileError, global_managed_file_service)

_WORKERS = 4
_executor = ThreadPoolExecutor(
    max_workers=_WORKERS, thread_name_prefix="file-statistics",
)
_slots = BoundedSemaphore(_WORKERS)
_ERROR_MESSAGES = {
    "managed_file_auth_required": "Authentication is required",
    "managed_file_not_found": "Managed file is not available",
    "analysis_invalid_arguments": "Provide only a canonical file UUID and column",
    "analysis_busy": "File statistics capacity is busy; retry later",
    "analysis_error": "File statistics could not be completed",
    "invalid_file_id": "Invalid file reference",
    "analysis_unsupported_type": "Only CSV and JSON tables support statistics",
    "analysis_invalid_table": "The file is not a supported table",
    "analysis_invalid_columns": "The table has invalid columns",
    "analysis_duplicate_key": "The table contains duplicate keys",
    "analysis_non_finite": "The table contains a non-finite number",
    "analysis_invalid_column": "Invalid column name",
    "analysis_column_not_found": "Selected column was not found",
    "analysis_non_numeric": "Selected column contains a non-numeric value",
    "analysis_numeric_range": "A number exceeds the supported precision",
    "analysis_no_numeric_values": "Selected column has no numeric values",
    "analysis_table_limit": "The table exceeds statistics limits",
    "analysis_timeout": "File statistics exceeded the calculation deadline",
    "unsafe_csv_formula": "The CSV contains an unsupported formula prefix",
    "file_storage_invalid": "The file source could not be verified",
    "file_storage_unavailable": "The file source is unavailable",
    "file_database_error": "The file source is unavailable",
}


class FileStatisticsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: str = Field(
        strict=True, min_length=36, max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="Canonical UUID from the selected managed-file reference",
    )
    column: str = Field(
        strict=True, min_length=1, max_length=128,
        description="Exact column name explicitly selected by the user",
    )


def _failure(code: str) -> ToolException:
    if code not in _ERROR_MESSAGES:
        code = "analysis_error"
    return ToolException(json.dumps({
        "type": "managed_file_statistics",
        "version": 1,
        "status": "error",
        "error": {"code": code, "message": _ERROR_MESSAGES[code]},
    }))


def _calculate(file_id: str, column: str) -> dict[str, object]:
    subject = get_active_agent_subject()
    if (
        not isinstance(subject, str)
        or not subject.isascii()
        or not subject.isdigit()
        or len(subject) > 20
        or int(subject) <= 0
        or str(int(subject)) != subject
    ):
        raise _failure("managed_file_auth_required")
    try:
        with get_session_factory()() as db:
            actor = db.get(User, int(subject))
            if actor is None:
                raise _failure("managed_file_not_found")
            payload = global_managed_file_service.file_statistics(
                db, actor, file_id, column,
            )
    except ToolException:
        raise
    except AuthorizationDeniedError:
        raise _failure("managed_file_not_found") from None
    except ManagedFileError as exc:
        raise _failure(exc.code) from None
    except Exception:
        raise _failure("analysis_error") from None
    if payload is None:
        raise _failure("managed_file_not_found")
    return {
        "type": "managed_file_statistics",
        "version": 1,
        "status": "success",
        "data": payload,
    }


def _submit(file_id: str, column: str):
    # Reserve before submit: even abandoned running work occupies a slot until
    # its real completion. No unbounded executor queue or loop-bound semaphore.
    if not _slots.acquire(blocking=False):
        raise _failure("analysis_busy")
    try:
        future = _executor.submit(copy_context().run, _calculate, file_id, column)
    except Exception:
        _slots.release()
        raise _failure("analysis_error") from None
    except BaseException:
        _slots.release()
        raise
    future.add_done_callback(lambda _future: _slots.release())
    return future


def _invoke(file_id: str, column: str) -> dict[str, object]:
    return _submit(file_id, column).result()


async def _ainvoke(file_id: str, column: str) -> dict[str, object]:
    # Cancellation stops delivery, not an already running synchronous parser.
    return await asyncio.wrap_future(_submit(file_id, column))


class _StatisticsTool(StructuredTool):
    @property
    def tool_call_schema(self) -> dict:
        # LangChain's injected-argument subset drops extra="forbid". There
        # are no injected fields here; export the same schema we validate.
        return {
            **FileStatisticsInput.model_json_schema(),
            "description": self.description,
        }


analyze_file_statistics = _StatisticsTool.from_function(
    func=_invoke,
    coroutine=_ainvoke,
    name="analyze_file_statistics",
    description=(
        "Compute the exact sum of one explicitly selected column over the "
        "complete current managed CSV/JSON file. Ask for clarification if the "
        "file or column is unclear; never choose the first file or column. "
        "For text previews use analyze_document."
    ),
    args_schema=FileStatisticsInput,
    handle_tool_error=True,
    handle_validation_error=lambda _error: str(
        _failure("analysis_invalid_arguments"),
    ),
)
