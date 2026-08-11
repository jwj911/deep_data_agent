"""Validate repository contracts required for a release build."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urlsplit

NEXT_CONFIG_PATH = "agent_chatui/next.config.mjs"
ENV_EXAMPLE_PATH = ".env.example"
COMPOSE_PATH = "docker-config/docker-compose.yml"
MIGRATIONS_VERSIONS_PATH = "migrations/versions"

SCAN_EXACT_FILES = {
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "agent_chatui/.dockerignore",
    "agent_chatui/.prettierignore",
    "agent_chatui/Dockerfile",
    "agent_chatui/README.md",
    "agent_chatui/components.json",
    "agent_chatui/eslint.config.js",
    "agent_chatui/next.config.mjs",
    "agent_chatui/nginx.conf",
    "agent_chatui/package.json",
    "agent_chatui/postcss.config.mjs",
    "agent_chatui/prettier.config.js",
    "agent_chatui/start.sh",
    "agent_chatui/tailwind.config.js",
    "agent_chatui/tsconfig.json",
    "data_agent/Dockerfile",
    "docker-config/docker-compose.yml",
    "langgraph.json",
    "requirements.txt",
    "setup.py",
    "start.sh",
    "utils/README.md",
    "utils/requirements.txt",
    "utils/setup.py",
}
SCAN_PREFIXES = ("agent_chatui/src", "data_agent", "utils")
TEXT_SUFFIXES = {
    ".css",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".ts",
    ".tsx",
    ".txt",
    ".yml",
    ".yaml",
}
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

BUILD_BYPASS_PATTERN = re.compile(
    r"\b(?:ignoreBuildErrors|ignoreDuringBuilds)\b"
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


@dataclass(frozen=True)
class Violation:
    """A redacted contract failure location."""

    rule: str
    path: str
    line: int


def _normalize_path(path: str | Path) -> str:
    normalized = PurePosixPath(str(path).replace("\\", "/"))
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("path must be relative to the repository")
    return normalized.as_posix()


def _is_scanned_path(path: str) -> bool:
    if path in SCAN_EXACT_FILES:
        return True
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in SCAN_PREFIXES
    ) and (
        PurePosixPath(path).suffix.lower() in TEXT_SUFFIXES
        or PurePosixPath(path).name == "Dockerfile"
    )


def _discover_scan_files(root: Path) -> set[str]:
    files = {
        path
        for path in SCAN_EXACT_FILES
        if (root / PurePosixPath(path)).is_file()
    }
    for prefix in SCAN_PREFIXES:
        directory = root / PurePosixPath(prefix)
        if not directory.is_dir():
            continue
        for candidate in directory.rglob("*"):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root).as_posix()
            if _is_scanned_path(relative):
                files.add(relative)
    return files


def _git_tracked_files(root: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError("unable to enumerate tracked files") from exc
    if result.returncode != 0:
        raise RuntimeError("unable to enumerate tracked files")
    return {
        _normalize_path(path)
        for path in result.stdout.decode("utf-8", errors="surrogateescape").split(
            "\0"
        )
        if path
    }


def _read_text(
    root: Path,
    path: str,
    violations: list[Violation],
) -> str | None:
    try:
        return (root / PurePosixPath(path)).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        violations.append(Violation("FILE_READ", path, 1))
        return None


def _line_matches(text: str, pattern: re.Pattern[str]) -> Iterable[int]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if pattern.search(line):
            yield line_number


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
        scanned = _discover_scan_files(repository_root)
    else:
        scanned = {
            normalized
            for path in scan_files
            if _is_scanned_path(normalized := _normalize_path(path))
        }

    required_files = {
        NEXT_CONFIG_PATH,
        ENV_EXAMPLE_PATH,
        COMPOSE_PATH,
    }
    texts: dict[str, str] = {}
    for path in sorted(scanned | required_files):
        if not (repository_root / PurePosixPath(path)).is_file():
            if path in required_files:
                violations.append(Violation("REQUIRED_FILE", path, 1))
            continue
        text = _read_text(repository_root, path, violations)
        if text is not None:
            texts[path] = text

    next_config = texts.get(NEXT_CONFIG_PATH)
    if next_config is not None:
        for line in _line_matches(next_config, BUILD_BYPASS_PATTERN):
            violations.append(
                Violation("NEXT_BUILD_BYPASS", NEXT_CONFIG_PATH, line)
            )

    env_example = texts.get(ENV_EXAMPLE_PATH)
    if env_example is not None:
        _check_env_example(env_example, violations)

    compose = texts.get(COMPOSE_PATH)
    if compose is not None:
        _check_compose_urls(compose, violations)
        _check_compose_logging(compose, violations)

    legacy_pattern = re.compile(re.escape(LEGACY_LOGIN_VARIABLE))
    for path, text in texts.items():
        for line in _line_matches(text, legacy_pattern):
            violations.append(
                Violation("LEGACY_LOGIN_VARIABLE", path, line)
            )
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in CREDENTIAL_PATTERNS):
                violations.append(
                    Violation("CREDENTIAL_PATTERN", path, line_number)
                )

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
