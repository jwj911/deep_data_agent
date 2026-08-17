"""Validate repository contracts required for a release build."""

from __future__ import annotations

import json
import posixpath
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urlsplit

NEXT_CONFIG_PATH = "agent_chatui/next.config.mjs"
ENV_EXAMPLE_PATH = ".env.example"
COMPOSE_PATH = "docker-config/docker-compose.yml"
LANGGRAPH_CONFIG_PATH = "langgraph.json"
LANGGRAPH_AUTH_PATH = "./data_agent/security/langgraph_auth.py:auth"
LANGGRAPH_AUTH_MODULE_PATH = "data_agent/security/langgraph_auth.py"
FRONTEND_API_KEY_PATH = "agent_chatui/src/lib/api-key.ts"
DOCKERIGNORE_PATH = ".dockerignore"
DOCKERFILE_PATH = "data_agent/Dockerfile"
MIGRATIONS_VERSIONS_PATH = "migrations/versions"
USER_MODEL_PATH = "data_agent/models/user.py"
AUDIT_MODULE_PATH = "data_agent/observability/audit.py"
EVENTS_MODULE_PATH = "data_agent/observability/events.py"
MANAGED_FILE_MODEL_PATH = "data_agent/models/managed_file.py"
MANAGED_FILE_ROUTE_PATH = "data_agent/routes/managed_file.py"
MANAGED_FILE_SERVICE_PATH = "data_agent/services/managed_file_service.py"
DOCUMENT_TOOL_PATH = "data_agent/tools/document_analysis.py"
FRONTEND_FILE_CLIENT_PATH = (
    "agent_chatui/src/lib/managed-file-client.ts"
)
FRONTEND_FILE_HOOK_PATH = "agent_chatui/src/hooks/use-file-upload.tsx"

REQUIRED_STRUCTURE_FILES = {
    NEXT_CONFIG_PATH,
    ENV_EXAMPLE_PATH,
    COMPOSE_PATH,
    LANGGRAPH_CONFIG_PATH,
    LANGGRAPH_AUTH_MODULE_PATH,
    FRONTEND_API_KEY_PATH,
    DOCKERIGNORE_PATH,
    DOCKERFILE_PATH,
    USER_MODEL_PATH,
    AUDIT_MODULE_PATH,
    EVENTS_MODULE_PATH,
    MANAGED_FILE_MODEL_PATH,
    MANAGED_FILE_ROUTE_PATH,
    MANAGED_FILE_SERVICE_PATH,
    DOCUMENT_TOOL_PATH,
    FRONTEND_FILE_CLIENT_PATH,
    FRONTEND_FILE_HOOK_PATH,
}
DOCKERIGNORE_REQUIRED_ALLOWS = (
    "requirements.txt",
    "data_agent",
    "data_agent/**",
    "langgraph.json",
    "alembic.ini",
    "migrations",
    "migrations/**",
)
DOCKERIGNORE_REQUIRED_EXCLUDES = (
    "**/__pycache__",
    "**/*.py[cod]",
    "**/.pytest_cache",
    "**/.mypy_cache",
    "**/.ruff_cache",
    "**/*.log",
)
DOCKERIGNORE_PARENT_ALLOWS = (
    ("data_agent", "data_agent/**"),
    ("migrations", "migrations/**"),
)
DOCKERFILE_COPY_REQUIREMENTS = (
    (
        "DOCKERFILE_ALEMBIC_INI_COPY",
        ("alembic.ini",),
    ),
    (
        "DOCKERFILE_MIGRATIONS_COPY",
        ("migrations/env.py", "migrations/script.py.mako"),
    ),
    (
        "DOCKERFILE_MIGRATION_VERSIONS_COPY",
        ("migrations/versions",),
    ),
)
PLACEHOLDERS = {
    "MOONSHOT_API_KEY": "your_moonshot_api_key_here",
    "TAVILY_API_KEY": "your_tavily_api_key_here",
    "JWT_SECRET_KEY": "your_jwt_secret_key_here",
}
OBSERVABILITY_DEFAULTS = {
    "SERVICE_NAME": "deep-data-agent",
    "LOG_FILE_PATH": "deep_data_agent.log",
    "LOG_MAX_BYTES": "10485760",
    "LOG_BACKUP_COUNT": "3",
    "DOCKER_LOG_MAX_SIZE": "10m",
    "DOCKER_LOG_MAX_FILES": "3",
}
RATE_LIMIT_DEFAULTS = {
    "RATE_LIMIT_ENABLED": "true",
    "TRUSTED_PROXY_COUNT": "0",
    "RATE_LIMIT_AUTH_MAX_REQUESTS": "10",
    "RATE_LIMIT_AUTH_WINDOW_SECONDS": "60",
    "RATE_LIMIT_QUERY_MAX_REQUESTS": "20",
    "RATE_LIMIT_QUERY_WINDOW_SECONDS": "60",
    "RATE_LIMIT_SESSION_MAX_REQUESTS": "60",
    "RATE_LIMIT_SESSION_WINDOW_SECONDS": "60",
    "RATE_LIMIT_DEFAULT_MAX_REQUESTS": "120",
    "RATE_LIMIT_DEFAULT_WINDOW_SECONDS": "60",
}
FILE_INGESTION_DEFAULTS = {
    "FILE_STORAGE_ROOT": "var/managed_files",
    "FILE_UPLOAD_MAX_BYTES": "5242880",
    "FILE_UPLOAD_BATCH_MAX_BYTES": "10485760",
    "FILE_UPLOAD_REQUEST_MAX_BYTES": "11534336",
    "FILE_UPLOAD_BATCH_MAX_COUNT": "5",
    "FILE_USER_QUOTA_BYTES": "104857600",
    "FILE_USER_MAX_COUNT": "100",
    "FILE_RETENTION_HOURS": "168",
    "FILE_ANALYSIS_MAX_CHARS": "20000",
    "COMPOSE_FILE_STORAGE_ROOT": "/data/managed-files",
}

BUILD_BYPASS_PATTERN = re.compile(
    r"\b(?:ignoreBuildErrors|ignoreDuringBuilds)\b"
)
VARIABLE_AGENT_QUERY_PATTERN = re.compile(
    r"""useQueryState\s*\(\s*["'](?:apiUrl|assistantId)["']"""
)
LEGACY_AGENT_KEY_PATTERN = re.compile(
    r"\b(?:getApiKey|setApiKey|buildRequestHeaders)\b|X-Api-Key"
)
LEGACY_AGENT_KEY_READ_PATTERN = re.compile(
    r"(?:localStorage\.)?(?:getItem|setItem)\s*\([^)]*"
    r"(?:lg:chat:apiKey|LEGACY_API_KEY_STORAGE_KEY)"
)
LEGACY_FILE_UPLOAD_PATTERN = re.compile(
    r"\b(?:fileToBase64|fileToContentBlock)\b|"
    r"\breadAsDataURL\s*\("
)
REMOTE_BUILD_FONT_PATTERN = re.compile(
    r"""from\s+["']next/font/google["']"""
)
ARBITRARY_FILE_PATH_PATTERN = re.compile(
    r"\bfile_path\b|os\.path\.(?:exists|getsize)\s*\(|"
    r"(?<!os\.)\bopen\s*\("
)
COPY_INSTRUCTION_PATTERN = re.compile(r"^\s*COPY\s+(.+)$", re.IGNORECASE)
FROM_INSTRUCTION_PATTERN = re.compile(r"^\s*FROM(?:\s|$)", re.IGNORECASE)
WORKDIR_INSTRUCTION_PATTERN = re.compile(
    r"^\s*WORKDIR\s+(.+)$",
    re.IGNORECASE,
)
LEGACY_LOGIN_VARIABLE = "NEXT_PUBLIC_LOGIN_API_URL"
CREDENTIAL_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?<![A-Za-z0-9_-])tvly-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\."
        r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
    ),
    re.compile(
        r"(?i)\bBearer[ \t]+[A-Za-z0-9._~+/=-]{24,}"
        r"(?![A-Za-z0-9._~+/=-])"
    ),
)
ENV_ASSIGNMENT_PATTERN = re.compile(
    r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$"
)
COMPOSE_URL_PATTERN = re.compile(
    r"^\s*(DATABASE_URL|REDIS_URL)\s*:\s*(.*?)\s*$"
)
COMPOSE_DEFAULT_PATTERN = re.compile(
    r"^\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}$"
)
REVISION_PATTERN = re.compile(
    r"""^revision\s*(?::[^=]+)?=\s*["']([^"']+)["']""",
    re.MULTILINE,
)
DOWN_REVISION_PATTERN = re.compile(
    r"""^down_revision\s*(?::[^=]+)?=\s*(None|["']([^"']+)["'])""",
    re.MULTILINE,
)
ROLE_DEFAULT_PATTERN = re.compile(
    r"server_default\s*=\s*UserRole\.USER\.value"
)
ROLE_CONSTRAINT_PATTERN = re.compile(
    r"""role\s+IN\s+\(["']user["'],\s*["']admin["']\)"""
)
AUTO_ADMIN_PATTERN = re.compile(
    r"(?:os\.environ(?:\.get)?|os\.getenv|_optional_env)"
    r"\s*\([^\n)]*ADMIN",
    re.IGNORECASE,
)
SENSITIVE_AUDIT_FIELD_PATTERN = re.compile(
    r"""["'](?:user_id|username|email|password|token|client_ip)["']\s*,"""
)


@dataclass(frozen=True)
class Violation:
    """A redacted contract failure location."""

    rule: str
    path: str
    line: int


@dataclass(frozen=True)
class DockerignoreRule:
    """A normalized, effective Docker ignore rule."""

    pattern: str
    negated: bool
    line: int


def _normalize_path(path: str | Path) -> str:
    normalized = PurePosixPath(str(path).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("path must be relative to the repository")
    return normalized.as_posix()


def _git_files(root: Path, *options: str) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", *options],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError("unable to enumerate repository files") from exc
    if result.returncode != 0:
        raise RuntimeError("unable to enumerate repository files")
    return {
        _normalize_path(path)
        for path in result.stdout.decode("utf-8", errors="surrogateescape").split(
            "\0"
        )
        if path
    }


def _git_tracked_files(root: Path) -> set[str]:
    return _git_files(root, "--cached")


def _git_scan_files(root: Path) -> set[str]:
    return _git_files(root, "--cached", "--others", "--exclude-standard")


def _read_required_text(
    root: Path,
    path: str,
    violations: list[Violation],
) -> str | None:
    try:
        content = (root / PurePosixPath(path)).read_bytes()
        if b"\0" in content:
            raise UnicodeError
        return content.decode("utf-8")
    except (OSError, UnicodeError):
        violations.append(Violation("FILE_READ", path, 1))
        return None


def _read_scan_text(
    root: Path,
    path: str,
    violations: list[Violation],
) -> str | None:
    try:
        content = (root / PurePosixPath(path)).read_bytes()
    except OSError:
        violations.append(Violation("FILE_READ", path, 1))
        return None
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _line_matches(text: str, pattern: re.Pattern[str]) -> Iterable[int]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            yield line_number


def _dockerignore_rules(text: str) -> list[DockerignoreRule]:
    rules: list[DockerignoreRule] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        negated = candidate.startswith("!")
        if negated:
            candidate = candidate[1:].strip()
        normalized = posixpath.normpath(candidate.replace("\\", "/"))
        if normalized == ".":
            normalized = ""
        rules.append(
            DockerignoreRule(
                pattern=normalized.lstrip("/"),
                negated=negated,
                line=line_number,
            )
        )
    return rules


def _check_dockerignore(
    text: str,
    violations: list[Violation],
) -> None:
    rules = _dockerignore_rules(text)
    if (
        not rules
        or rules[0].negated
        or rules[0].pattern != "**"
    ):
        line = rules[0].line if rules else 1
        violations.append(
            Violation("DOCKERIGNORE_DEFAULT_DENY", DOCKERIGNORE_PATH, line)
        )

    required_allows = set(DOCKERIGNORE_REQUIRED_ALLOWS)
    required_excludes = set(DOCKERIGNORE_REQUIRED_EXCLUDES)
    seen: dict[tuple[bool, str], DockerignoreRule] = {}
    for rule in rules:
        key = (rule.negated, rule.pattern)
        if key in seen:
            violations.append(
                Violation(
                    "DOCKERIGNORE_DUPLICATE_RULE",
                    DOCKERIGNORE_PATH,
                    rule.line,
                )
            )
            continue
        seen[key] = rule
        if rule.negated and rule.pattern not in required_allows:
            violations.append(
                Violation(
                    "DOCKERIGNORE_NON_RUNTIME_ALLOW",
                    DOCKERIGNORE_PATH,
                    rule.line,
                )
            )
        if (
            not rule.negated
            and rule.pattern not in required_excludes | {"**"}
        ):
            violations.append(
                Violation(
                    "DOCKERIGNORE_UNEXPECTED_EXCLUDE",
                    DOCKERIGNORE_PATH,
                    rule.line,
                )
            )

    allow_rules = {
        pattern: seen.get((True, pattern))
        for pattern in required_allows
    }
    if any(rule is None for rule in allow_rules.values()):
        violations.append(
            Violation(
                "DOCKERIGNORE_REQUIRED_ALLOW",
                DOCKERIGNORE_PATH,
                1,
            )
        )
    for parent, tree in DOCKERIGNORE_PARENT_ALLOWS:
        parent_rule = allow_rules[parent]
        tree_rule = allow_rules[tree]
        if (
            parent_rule is not None
            and tree_rule is not None
            and parent_rule.line > tree_rule.line
        ):
            violations.append(
                Violation(
                    "DOCKERIGNORE_PARENT_ALLOW_ORDER",
                    DOCKERIGNORE_PATH,
                    tree_rule.line,
                )
            )

    exclude_rules = {
        pattern: seen.get((False, pattern))
        for pattern in required_excludes
    }
    if any(rule is None for rule in exclude_rules.values()):
        violations.append(
            Violation(
                "DOCKERIGNORE_REQUIRED_EXCLUDE",
                DOCKERIGNORE_PATH,
                1,
            )
        )
    present_allows = [
        rule for rule in allow_rules.values() if rule is not None
    ]
    present_cleanup_excludes = [
        rule
        for rule in exclude_rules.values()
        if rule is not None
    ]
    if present_allows and present_cleanup_excludes:
        last_allow_line = max(rule.line for rule in present_allows)
        early_cleanup = min(
            (
                rule
                for rule in present_cleanup_excludes
                if rule.line < last_allow_line
            ),
            key=lambda rule: rule.line,
            default=None,
        )
        if early_cleanup is not None:
            violations.append(
                Violation(
                    "DOCKERIGNORE_EXCLUDE_ORDER",
                    DOCKERIGNORE_PATH,
                    early_cleanup.line,
                )
            )


def _dockerfile_instructions(text: str) -> Iterable[tuple[int, str]]:
    start_line = 0
    parts: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not parts and (not stripped or stripped.startswith("#")):
            continue
        if not parts:
            start_line = line_number
        continued = line.rstrip().endswith("\\")
        part = line.rstrip()
        if continued:
            part = part[:-1]
        parts.append(part)
        if continued:
            continue
        yield start_line, " ".join(parts)
        parts = []
    if parts:
        yield start_line, " ".join(parts)


def _final_dockerfile_stage(
    text: str,
) -> list[tuple[int, str]]:
    instructions = list(_dockerfile_instructions(text))
    final_stage_start = 0
    for index, (_, instruction) in enumerate(instructions):
        if FROM_INSTRUCTION_PATTERN.match(instruction):
            final_stage_start = index
    return instructions[final_stage_start:]


def _parse_copy_arguments(
    arguments: str,
) -> tuple[list[str], str] | None:
    while arguments.startswith("--"):
        option, separator, remainder = arguments.partition(" ")
        if option == "--from" or option.startswith("--from="):
            return None
        if not separator:
            return None
        arguments = remainder.lstrip()

    if arguments.startswith("["):
        try:
            values = json.loads(arguments)
        except (json.JSONDecodeError, TypeError):
            return None
        if (
            not isinstance(values, list)
            or len(values) < 2
            or not all(isinstance(value, str) for value in values)
        ):
            return None
    else:
        try:
            values = shlex.split(arguments, posix=True)
        except ValueError:
            return None
        if len(values) < 2:
            return None
    return values[:-1], values[-1]


def _resolve_container_path(
    raw_path: str,
    workdir: PurePosixPath | None,
) -> PurePosixPath | None:
    if "$" in raw_path:
        return None
    path = PurePosixPath(raw_path.replace("\\", "/"))
    if ".." in path.parts:
        return None
    if path.is_absolute():
        return path
    if workdir is None:
        return None
    return workdir / path


def _dockerfile_copy_operations(
    text: str,
) -> list[tuple[tuple[str, ...], PurePosixPath, bool]]:
    operations: list[tuple[tuple[str, ...], PurePosixPath, bool]] = []
    workdir: PurePosixPath | None = None
    for _, instruction in _final_dockerfile_stage(text):
        workdir_match = WORKDIR_INSTRUCTION_PATTERN.match(instruction)
        if workdir_match is not None:
            try:
                values = shlex.split(workdir_match.group(1), posix=True)
            except ValueError:
                workdir = None
                continue
            workdir = (
                _resolve_container_path(values[0], workdir)
                if len(values) == 1
                else None
            )
            continue

        copy_match = COPY_INSTRUCTION_PATTERN.match(instruction)
        if copy_match is None or workdir is None:
            continue
        parsed = _parse_copy_arguments(copy_match.group(1).strip())
        if parsed is None:
            continue
        raw_sources, raw_destination = parsed
        destination = _resolve_container_path(raw_destination, workdir)
        if destination is None:
            continue

        sources: list[str] = []
        for raw_source in raw_sources:
            source = PurePosixPath(
                raw_source.replace("\\", "/")
            )
            if source.is_absolute() or ".." in source.parts:
                continue
            sources.append(source.as_posix().rstrip("/"))
        destination_is_directory = (
            len(raw_sources) > 1
            or raw_destination.replace("\\", "/").endswith("/")
            or destination == workdir
        )
        operations.append(
            (tuple(sources), destination, destination_is_directory)
        )
    return operations


def _copy_operation_covers(
    operation: tuple[tuple[str, ...], PurePosixPath, bool],
    required_path: str,
) -> bool:
    sources, destination, destination_is_directory = operation
    required = PurePosixPath(required_path)
    expected = PurePosixPath("/app") / required
    for source_text in sources:
        source = PurePosixPath(source_text)
        if source_text == ".":
            continue
        if source == required:
            if required_path == "migrations/versions":
                copied_path = destination
            elif destination_is_directory:
                copied_path = destination / source.name
            else:
                copied_path = destination
        elif required_path.startswith(f"{source_text}/"):
            copied_path = destination / required.relative_to(source)
        else:
            continue
        if copied_path == expected:
            return True
    return False


def _check_dockerfile(
    text: str,
    violations: list[Violation],
) -> None:
    operations = _dockerfile_copy_operations(text)
    for rule, required_paths in DOCKERFILE_COPY_REQUIREMENTS:
        if all(
            any(
                _copy_operation_covers(operation, required_path)
                for operation in operations
            )
            for required_path in required_paths
        ):
            continue
        violations.append(Violation(rule, DOCKERFILE_PATH, 1))


def _check_agent_tenant_contracts(
    structure_texts: dict[str, str],
    scan_texts: dict[str, str],
    violations: list[Violation],
) -> None:
    langgraph_config = structure_texts.get(LANGGRAPH_CONFIG_PATH)
    if langgraph_config is not None:
        try:
            parsed = json.loads(langgraph_config)
        except json.JSONDecodeError:
            parsed = {}
        if (
            not isinstance(parsed, dict)
            or not isinstance(parsed.get("auth"), dict)
            or parsed["auth"].get("path") != LANGGRAPH_AUTH_PATH
        ):
            violations.append(
                Violation(
                    "LANGGRAPH_FIRST_PARTY_AUTH",
                    LANGGRAPH_CONFIG_PATH,
                    1,
                )
            )

    auth_module = structure_texts.get(LANGGRAPH_AUTH_MODULE_PATH)
    required_auth_markers = (
        "@auth.authenticate",
        "@auth.on",
        "@auth.on.threads",
        "get_user_for_authorization_header",
    )
    if auth_module is not None and any(
        marker not in auth_module for marker in required_auth_markers
    ):
        violations.append(
            Violation(
                "LANGGRAPH_TENANT_AUTHORIZATION",
                LANGGRAPH_AUTH_MODULE_PATH,
                1,
            )
        )

    for path, text in scan_texts.items():
        if not path.startswith("agent_chatui/src/"):
            continue
        for line in _line_matches(text, VARIABLE_AGENT_QUERY_PATTERN):
            violations.append(
                Violation("VARIABLE_AGENT_ORIGIN", path, line)
            )
        for line in _line_matches(text, LEGACY_AGENT_KEY_PATTERN):
            violations.append(
                Violation("LEGACY_AGENT_API_KEY", path, line)
            )
        for line in _line_matches(text, LEGACY_AGENT_KEY_READ_PATTERN):
            violations.append(
                Violation("LEGACY_AGENT_API_KEY", path, line)
            )

    api_key_module = structure_texts.get(FRONTEND_API_KEY_PATH)
    if api_key_module is not None and (
        "headers.Authorization" not in api_key_module
        or "localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY)"
        not in api_key_module
    ):
        violations.append(
            Violation(
                "AGENT_BEARER_AUTH",
                FRONTEND_API_KEY_PATH,
                1,
            )
        )


def _check_file_ingestion_contracts(
    structure_texts: dict[str, str],
    scan_texts: dict[str, str],
    violations: list[Violation],
) -> None:
    required_markers = {
        MANAGED_FILE_MODEL_PATH: (
            '__tablename__ = "managed_files"',
            "user_id",
            "file_id",
            "storage_key",
            "sha256",
            "expires_at",
        ),
        MANAGED_FILE_ROUTE_PATH: (
            "Permission.FILE_READ_OWN",
            "Permission.FILE_WRITE_OWN",
            "Permission.FILE_DELETE_OWN",
            "global_managed_file_service",
        ),
        MANAGED_FILE_SERVICE_PATH: (
            "FILE_UPLOAD_MAX_BYTES",
            "FILE_UPLOAD_BATCH_MAX_BYTES",
            "FILE_USER_QUOTA_BYTES",
            "with_for_update",
            "normalize_file_id",
        ),
        DOCUMENT_TOOL_PATH: (
            "file_id",
            "RunnableConfig",
            "langgraph_auth_user_id",
            "global_managed_file_service",
        ),
        FRONTEND_FILE_CLIENT_PATH: (
            "api/files",
            "uploadManagedFiles",
            "deleteManagedFile",
            "FILE_MAX_BYTES",
            "FILE_BATCH_MAX_BYTES",
        ),
        FRONTEND_FILE_HOOK_PATH: (
            "uploadManagedFiles",
            "deleteManagedFile",
            "validateManagedFileSelection",
        ),
    }
    for path, markers in required_markers.items():
        text = structure_texts.get(path)
        if text is not None and any(marker not in text for marker in markers):
            violations.append(
                Violation("MANAGED_FILE_BOUNDARY", path, 1)
            )

    tool = structure_texts.get(DOCUMENT_TOOL_PATH)
    if tool is not None:
        for line in _line_matches(tool, ARBITRARY_FILE_PATH_PATTERN):
            violations.append(
                Violation("ARBITRARY_FILE_PATH_TOOL", DOCUMENT_TOOL_PATH, line)
            )

    for path, text in scan_texts.items():
        if not path.startswith("agent_chatui/src/"):
            continue
        for line in _line_matches(text, LEGACY_FILE_UPLOAD_PATTERN):
            violations.append(
                Violation("LEGACY_BASE64_FILE_UPLOAD", path, line)
            )
        for line in _line_matches(text, REMOTE_BUILD_FONT_PATTERN):
            violations.append(
                Violation("REMOTE_BUILD_FONT", path, line)
            )

    compose = structure_texts.get(COMPOSE_PATH)
    compose_markers = (
        "COMPOSE_FILE_STORAGE_ROOT",
        "managed_file_data:/data/managed-files",
        "managed_file_data:",
    )
    if compose is not None and any(
        marker not in compose for marker in compose_markers
    ):
        violations.append(
            Violation("MANAGED_FILE_COMPOSE_VOLUME", COMPOSE_PATH, 1)
        )


def _check_env_example(
    text: str,
    violations: list[Violation],
) -> None:
    assignments: dict[str, list[tuple[str, int]]] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = ENV_ASSIGNMENT_PATTERN.match(line)
        if not match:
            continue
        value = match.group(2)
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {'"', "'"}
        ):
            value = value[1:-1]
        assignments.setdefault(match.group(1), []).append(
            (value, line_number)
        )

    for name, expected in PLACEHOLDERS.items():
        values = assignments.get(name, [])
        if len(values) != 1 or values[0][0] != expected:
            line = values[0][1] if values else 1
            violations.append(
                Violation("ENV_EXAMPLE_PLACEHOLDER", ENV_EXAMPLE_PATH, line)
            )

    for name, expected in OBSERVABILITY_DEFAULTS.items():
        values = assignments.get(name, [])
        if len(values) != 1 or values[0][0] != expected:
            line = values[0][1] if values else 1
            violations.append(
                Violation(
                    "OBSERVABILITY_ENV_DEFAULT",
                    ENV_EXAMPLE_PATH,
                    line,
                )
            )

    for name, expected in RATE_LIMIT_DEFAULTS.items():
        values = assignments.get(name, [])
        if len(values) != 1 or values[0][0] != expected:
            line = values[0][1] if values else 1
            violations.append(
                Violation(
                    "RATE_LIMIT_ENV_DEFAULT",
                    ENV_EXAMPLE_PATH,
                    line,
                )
            )

    for name, expected in FILE_INGESTION_DEFAULTS.items():
        values = assignments.get(name, [])
        if len(values) != 1 or values[0][0] != expected:
            line = values[0][1] if values else 1
            violations.append(
                Violation(
                    "FILE_INGESTION_ENV_DEFAULT",
                    ENV_EXAMPLE_PATH,
                    line,
                )
            )


def _compose_default_host(value: str) -> tuple[str | None, str | None]:
    value = value.strip()
    if (
        len(value) >= 2
        and value[0] == value[-1]
        and value[0] in {'"', "'"}
    ):
        value = value[1:-1]
    match = COMPOSE_DEFAULT_PATTERN.fullmatch(value)
    if not match:
        return None, None
    return match.group(1), urlsplit(match.group(2)).hostname


def _check_compose_urls(
    text: str,
    violations: list[Violation],
) -> None:
    expected = {
        "DATABASE_URL": ("COMPOSE_DATABASE_URL", "mysql"),
        "REDIS_URL": ("COMPOSE_REDIS_URL", "redis"),
    }
    found: set[str] = set()
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = COMPOSE_URL_PATTERN.match(line)
        if not match:
            continue
        name, value = match.groups()
        if name in found:
            violations.append(
                Violation(f"COMPOSE_{name}_DEFAULT", COMPOSE_PATH, line_number)
            )
            continue
        found.add(name)
        variable, host = _compose_default_host(value)
        expected_variable, expected_host = expected[name]
        if variable != expected_variable or host != expected_host:
            violations.append(
                Violation(f"COMPOSE_{name}_DEFAULT", COMPOSE_PATH, line_number)
            )

    for name in expected.keys() - found:
        violations.append(
            Violation(f"COMPOSE_{name}_DEFAULT", COMPOSE_PATH, 1)
        )


def _check_compose_logging(
    text: str,
    violations: list[Violation],
) -> None:
    required_lines = {
        "max-size: ${DOCKER_LOG_MAX_SIZE:-10m}",
        "max-file: ${DOCKER_LOG_MAX_FILES:-3}",
    }
    stripped_lines = {
        line.strip(): line_number
        for line_number, line in enumerate(text.splitlines(), start=1)
    }
    for required_line in required_lines:
        if required_line not in stripped_lines:
            violations.append(
                Violation("COMPOSE_LOG_RETENTION", COMPOSE_PATH, 1)
            )
    if text.count("logging: *bounded-logging") < 4:
        violations.append(
            Violation("COMPOSE_LOG_RETENTION", COMPOSE_PATH, 1)
        )


def _is_tracked_local_env(path: str) -> bool:
    name = PurePosixPath(path).name
    return name == ".env" or (
        name.startswith(".env.") and name != ".env.example"
    )


def _is_tracked_generated_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return (
        any(
            part in {"out", ".next", "node_modules"}
            for part in pure_path.parts
        )
        or pure_path.suffix.lower() == ".pyc"
        or pure_path.name.endswith(".tsbuildinfo")
    )


def _check_migration_head(
    root: Path,
    violations: list[Violation],
) -> None:
    """Ensure ``migrations/versions`` exists with exactly one revision head.

    The head is resolved purely by parsing ``revision``/``down_revision``
    assignments from the version files, so no database connection or Alembic
    runtime import is required. The head is the revision that no other file
    references through ``down_revision``. A missing directory, a directory with
    no revision files, or anything other than exactly one head is a violation.
    """

    versions_dir = root / PurePosixPath(MIGRATIONS_VERSIONS_PATH)
    if not versions_dir.is_dir():
        violations.append(
            Violation("MIGRATION_HEAD", MIGRATIONS_VERSIONS_PATH, 1)
        )
        return

    revisions: set[str] = set()
    referenced: set[str] = set()
    for candidate in sorted(versions_dir.glob("*.py")):
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            relative = candidate.relative_to(root).as_posix()
            violations.append(Violation("FILE_READ", relative, 1))
            continue
        revision_match = REVISION_PATTERN.search(text)
        if revision_match is None:
            continue
        revisions.add(revision_match.group(1))
        for down_match in DOWN_REVISION_PATTERN.finditer(text):
            parent = down_match.group(2)
            if parent is not None:
                referenced.add(parent)

    heads = revisions - referenced
    if len(revisions) < 1 or len(heads) != 1:
        violations.append(
            Violation("MIGRATION_HEAD", MIGRATIONS_VERSIONS_PATH, 1)
        )


def _check_rbac_contracts(
    structure_texts: dict[str, str],
    scan_texts: dict[str, str],
    violations: list[Violation],
) -> None:
    user_model = structure_texts.get(USER_MODEL_PATH)
    if user_model is not None:
        if (
            ROLE_DEFAULT_PATTERN.search(user_model) is None
            or "server_default=UserRole.ADMIN.value" in user_model
        ):
            violations.append(
                Violation("RBAC_DEFAULT_ROLE", USER_MODEL_PATH, 1)
            )
        if ROLE_CONSTRAINT_PATTERN.search(user_model) is None:
            violations.append(
                Violation("RBAC_ROLE_CONSTRAINT", USER_MODEL_PATH, 1)
            )

    audit_module = structure_texts.get(AUDIT_MODULE_PATH)
    events_module = structure_texts.get(EVENTS_MODULE_PATH)
    if (
        audit_module is not None
        and (
            "hmac.new" not in audit_module
            or "sha256" not in audit_module
        )
    ):
        violations.append(
            Violation("AUDIT_IDENTITY_REDACTION", AUDIT_MODULE_PATH, 1)
        )
    if events_module is not None:
        if (
            '"actor_ref"' not in events_module
            or '"target_ref"' not in events_module
            or SENSITIVE_AUDIT_FIELD_PATTERN.search(events_module)
            is not None
        ):
            violations.append(
                Violation(
                    "AUDIT_IDENTITY_REDACTION",
                    EVENTS_MODULE_PATH,
                    1,
                )
            )

    for path, text in scan_texts.items():
        if not path.startswith("data_agent/"):
            continue
        match = AUTO_ADMIN_PATTERN.search(text)
        if match is not None:
            violations.append(
                Violation(
                    "RBAC_AUTO_ADMIN",
                    path,
                    text.count("\n", 0, match.start()) + 1,
                )
            )


def check_repository(
    root: str | Path,
    *,
    tracked_files: Iterable[str | Path] | None = None,
    scan_files: Iterable[str | Path] | None = None,
) -> list[Violation]:
    """Return deterministic, redacted contract violations for a repository."""

    repository_root = Path(root).resolve()
    violations: list[Violation] = []

    if tracked_files is None:
        try:
            tracked = _git_tracked_files(repository_root)
        except RuntimeError:
            tracked = set()
            violations.append(Violation("TRACKED_FILES", ".", 1))
    else:
        tracked = {_normalize_path(path) for path in tracked_files}

    if scan_files is None:
        try:
            scanned = _git_scan_files(repository_root)
        except RuntimeError:
            scanned = set()
            violations.append(Violation("SCAN_FILES", ".", 1))
    else:
        scanned = {_normalize_path(path) for path in scan_files}

    structure_texts: dict[str, str] = {}
    for path in sorted(REQUIRED_STRUCTURE_FILES):
        if not (repository_root / PurePosixPath(path)).is_file():
            violations.append(Violation("REQUIRED_FILE", path, 1))
            continue
        text = _read_required_text(repository_root, path, violations)
        if text is not None:
            structure_texts[path] = text

    scan_texts: dict[str, str] = {}
    for path in sorted(scanned):
        if not (repository_root / PurePosixPath(path)).is_file():
            continue
        text = _read_scan_text(repository_root, path, violations)
        if text is not None:
            scan_texts[path] = text

    next_config = structure_texts.get(NEXT_CONFIG_PATH)
    if next_config is not None:
        for line in _line_matches(next_config, BUILD_BYPASS_PATTERN):
            violations.append(
                Violation("NEXT_BUILD_BYPASS", NEXT_CONFIG_PATH, line)
            )

    env_example = structure_texts.get(ENV_EXAMPLE_PATH)
    if env_example is not None:
        _check_env_example(env_example, violations)

    compose = structure_texts.get(COMPOSE_PATH)
    if compose is not None:
        _check_compose_urls(compose, violations)
        _check_compose_logging(compose, violations)

    dockerignore = structure_texts.get(DOCKERIGNORE_PATH)
    if dockerignore is not None:
        _check_dockerignore(dockerignore, violations)

    dockerfile = structure_texts.get(DOCKERFILE_PATH)
    if dockerfile is not None:
        _check_dockerfile(dockerfile, violations)

    _check_agent_tenant_contracts(
        structure_texts,
        scan_texts,
        violations,
    )
    _check_file_ingestion_contracts(
        structure_texts,
        scan_texts,
        violations,
    )

    legacy_pattern = re.compile(re.escape(LEGACY_LOGIN_VARIABLE))
    for path, text in scan_texts.items():
        if path.startswith("agent_chatui/src/"):
            for line in _line_matches(text, legacy_pattern):
                violations.append(
                    Violation("LEGACY_LOGIN_VARIABLE", path, line)
                )
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in CREDENTIAL_PATTERNS):
                violations.append(
                    Violation("CREDENTIAL_PATTERN", path, line_number)
                )

    _check_rbac_contracts(structure_texts, scan_texts, violations)

    for path in tracked:
        if _is_tracked_local_env(path):
            violations.append(Violation("TRACKED_LOCAL_ENV", path, 1))
        if _is_tracked_generated_file(path):
            violations.append(
                Violation("TRACKED_GENERATED_FILE", path, 1)
            )

    _check_migration_head(repository_root, violations)

    return sorted(
        set(violations),
        key=lambda violation: (
            violation.path,
            violation.line,
            violation.rule,
        ),
    )


def main() -> int:
    repository_root = Path(__file__).resolve().parents[1]
    violations = check_repository(repository_root)
    if violations:
        for violation in violations:
            print(
                f"{violation.rule} {violation.path}:{violation.line}",
                file=sys.stderr,
            )
        return 1
    print("Release contracts passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
