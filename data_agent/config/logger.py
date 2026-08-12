import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler

from data_agent.config.config import config
from data_agent.observability.context import (get_request_id,
                                              normalize_request_id)
from data_agent.observability.events import (normalize_event_name,
                                             safe_event_fields)
from data_agent.observability.redaction import redact_sensitive_data


class RedactingFormatter(logging.Formatter):
    """Format bounded JSON events and redact messages and exceptions."""

    def format(self, record: logging.LogRecord) -> str:
        event_fields = safe_event_fields(
            getattr(record, "event_fields", {})
            if isinstance(getattr(record, "event_fields", {}), dict)
            else {}
        )
        payload: dict[str, object] = {
            "schema_version": "1.0",
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "service": redact_sensitive_data(config.SERVICE_NAME),
            "logger": record.name,
            "event": normalize_event_name(
                getattr(record, "event_name", "log.message")
            ),
            "message": redact_sensitive_data(record.getMessage()),
        }
        request_id = normalize_request_id(
            getattr(record, "request_id", None)
        ) or get_request_id()
        if request_id:
            payload["request_id"] = request_id
        payload.update(
            {
                key: (
                    redact_sensitive_data(value)
                    if isinstance(value, str)
                    else value
                )
                for key, value in event_fields.items()
            }
        )
        if record.exc_info:
            exception_type = record.exc_info[0]
            payload["exception"] = redact_sensitive_data(
                f"{exception_type.__module__}.{exception_type.__name__}"
            )
        return json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
        )


_log_level = getattr(logging, config.LOG_LEVEL, None)
if not isinstance(_log_level, int):
    _log_level = logging.INFO

_formatter = RedactingFormatter()
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_formatter)

_handlers: list[logging.Handler] = [_stream_handler]
if config.LOG_FILE_PATH:
    _file_handler = RotatingFileHandler(
        config.LOG_FILE_PATH,
        maxBytes=config.LOG_MAX_BYTES,
        backupCount=config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    _file_handler.setFormatter(_formatter)
    _handlers.append(_file_handler)

logger = logging.getLogger("deep_data_agent")
logger.setLevel(_log_level)
logger.handlers.clear()
for handler in _handlers:
    logger.addHandler(handler)
logger.propagate = False

auth_logger = logging.getLogger("deep_data_agent.auth")
session_logger = logging.getLogger("deep_data_agent.session")
agent_logger = logging.getLogger("deep_data_agent.agent")
tool_logger = logging.getLogger("deep_data_agent.tool")
cache_logger = logging.getLogger("deep_data_agent.cache")
rate_limit_logger = logging.getLogger("deep_data_agent.rate_limit")
audit_logger = logging.getLogger("deep_data_agent.audit")
