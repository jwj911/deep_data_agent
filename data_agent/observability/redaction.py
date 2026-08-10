import re

from data_agent.config.config import config

_REDACTION_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|token|password|secret)\s*[:=]\s*)[^\s,;]+"
    ),
    re.compile(r"(?i)(://[^:/\s]+:)[^@\s]+(@)"),
    re.compile(r"\b(?:sk|tvly)-[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\."
        r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
)


def redact_sensitive_data(value: object) -> str:
    """Return a diagnostic-safe representation without credentials."""
    redacted = str(value)

    for sensitive_value in config.sensitive_values:
        redacted = redacted.replace(sensitive_value, "[REDACTED]")

    redacted = _REDACTION_PATTERNS[0].sub(r"\1[REDACTED]", redacted)
    redacted = _REDACTION_PATTERNS[1].sub(r"\1[REDACTED]", redacted)
    redacted = _REDACTION_PATTERNS[2].sub(r"\1[REDACTED]\2", redacted)
    redacted = _REDACTION_PATTERNS[3].sub("[REDACTED]", redacted)
    redacted = _REDACTION_PATTERNS[4].sub("[REDACTED]", redacted)
    return redacted
