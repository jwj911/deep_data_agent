import logging
import os
import subprocess
import sys
import tempfile
from time import perf_counter

from data_agent.config.logger import tool_logger
from data_agent.observability.context import bind_runnable_request_id
from data_agent.observability.events import emit_event


def execute_python_code(code: str) -> dict:
    """Execute Python code and return the output"""
    with bind_runnable_request_id():
        started_at = perf_counter()
        emit_event(
            tool_logger,
            "tool.started",
            level=logging.WARNING,
            operation="execute",
            tool_name="execute_python_code",
            outcome="started",
        )
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".py",
                delete=False,
            ) as file:
                file.write(code)
                temp_file_path = file.name

            result = subprocess.run(
                [sys.executable, temp_file_path],
                capture_output=True,
                text=True,
                timeout=30,
            )

            os.unlink(temp_file_path)
            emit_event(
                tool_logger,
                (
                    "tool.completed"
                    if result.returncode == 0
                    else "tool.failed"
                ),
                level=(
                    logging.INFO
                    if result.returncode == 0
                    else logging.WARNING
                ),
                operation="execute",
                tool_name="execute_python_code",
                outcome=(
                    "success" if result.returncode == 0 else "error"
                ),
                error_code=(
                    "nonzero_exit" if result.returncode != 0 else ""
                ),
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            if "temp_file_path" in locals() and os.path.exists(
                temp_file_path
            ):
                os.unlink(temp_file_path)
            emit_event(
                tool_logger,
                "tool.failed",
                level=logging.WARNING,
                operation="execute",
                tool_name="execute_python_code",
                outcome="error",
                error_code="timeout",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return {"error": "Execution timed out after 30 seconds"}
        except Exception as exc:
            if "temp_file_path" in locals() and os.path.exists(
                temp_file_path
            ):
                os.unlink(temp_file_path)
            tool_logger.exception(
                "Code execution failed",
                extra={
                    "event_name": "tool.failed",
                    "event_fields": {
                        "operation": "execute",
                        "tool_name": "execute_python_code",
                        "outcome": "error",
                        "error_code": "execution_error",
                        "duration_ms": (
                            perf_counter() - started_at
                        )
                        * 1000,
                    },
                },
            )
            return {"error": str(exc)}
