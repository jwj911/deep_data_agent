import logging
import re
import sys

from data_agent.config.config import config

_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(r"(?i)(://[^:/\s]+:)[^@\s]+(@)"),
    re.compile(r"\b(?:sk|tvly)-[A-Za-z0-9_-]{8,}\b"),
)


def redact_sensitive_data(value: object) -> str:
    """Return a log-safe representation without credentials or tokens."""
    redacted = str(value)

    for sensitive_value in config.sensitive_values:
        redacted = redacted.replace(sensitive_value, "[REDACTED]")

    redacted = _REDACTION_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = _REDACTION_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = _REDACTION_PATTERNS[2].sub(r"\1[REDACTED]\2", redacted)
    redacted = _REDACTION_PATTERNS[3].sub("[REDACTED]", redacted)
    return redacted


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts both messages and formatted exceptions."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_data(super().format(record))


_log_level = getattr(logging, config.LOG_LEVEL, None)
if not isinstance(_log_level, int):
    _log_level = logging.INFO

_formatter = RedactingFormatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_formatter)
_file_handler = logging.FileHandler("deep_data_agent.log")
_file_handler.setFormatter(_formatter)

logging.basicConfig(
    level=_log_level,
    handlers=[_stream_handler, _file_handler],
)

logger = logging.getLogger("deep_data_agent")
auth_logger = logging.getLogger("deep_data_agent.auth")
session_logger = logging.getLogger("deep_data_agent.session")
agent_logger = logging.getLogger("deep_data_agent.agent")
tool_logger = logging.getLogger("deep_data_agent.tool")
cache_logger = logging.getLogger("deep_data_agent.cache")
