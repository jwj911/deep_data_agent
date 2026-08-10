import logging
import os
from time import perf_counter

from data_agent.config.logger import tool_logger
from data_agent.observability.context import bind_runnable_request_id
from data_agent.observability.events import emit_event


def analyze_document(file_path: str) -> dict:
    """Analyze a document and return its content and metadata"""
    with bind_runnable_request_id():
        started_at = perf_counter()
        emit_event(
            tool_logger,
            "tool.started",
            operation="analyze",
            tool_name="analyze_document",
            outcome="started",
        )
        try:
            if not os.path.exists(file_path):
                emit_event(
                    tool_logger,
                    "tool.failed",
                    level=logging.WARNING,
                    operation="analyze",
                    tool_name="analyze_document",
                    outcome="rejected",
                    error_code="file_not_found",
                    duration_ms=(perf_counter() - started_at) * 1000,
                )
                return {"error": f"File not found: {file_path}"}

            file_size = os.path.getsize(file_path)

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore",
            ) as file:
                content = file.read(10000)

            file_extension = os.path.splitext(file_path)[1]
            emit_event(
                tool_logger,
                "tool.completed",
                operation="analyze",
                tool_name="analyze_document",
                outcome="success",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {
                "file_path": file_path,
                "file_size": file_size,
                "file_extension": file_extension,
                "content": content,
                "content_truncated": len(content) >= 10000,
            }
        except Exception as exc:
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
            return {"error": str(exc)}
