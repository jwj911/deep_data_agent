import subprocess
from pathlib import Path

import pytest

from scripts import check_release_contracts as contracts

NEXT_CONFIG_PATH = "agent_chatui/next.config.mjs"
ENV_EXAMPLE_PATH = ".env.example"
COMPOSE_PATH = "docker-config/docker-compose.yml"
DOCKERIGNORE_PATH = ".dockerignore"
DOCKERFILE_PATH = "data_agent/Dockerfile"
MIGRATIONS_VERSIONS_PATH = "migrations/versions"
USER_MODEL_PATH = "data_agent/models/user.py"
AUDIT_MODULE_PATH = "data_agent/observability/audit.py"
EVENTS_MODULE_PATH = "data_agent/observability/events.py"
LANGGRAPH_CONFIG_PATH = "langgraph.json"
LANGGRAPH_AUTH_MODULE_PATH = "data_agent/security/langgraph_auth.py"
FRONTEND_API_KEY_PATH = "agent_chatui/src/lib/api-key.ts"
MANAGED_FILE_MODEL_PATH = "data_agent/models/managed_file.py"
MANAGED_FILE_ROUTE_PATH = "data_agent/routes/managed_file.py"
MANAGED_FILE_SERVICE_PATH = "data_agent/services/managed_file_service.py"
DOCUMENT_TOOL_PATH = "data_agent/tools/document_analysis.py"
AGENT_CONFIG_PATH = "data_agent/config/config.py"
AGENT_SERVICE_PATH = "data_agent/services/agent_service.py"
SEARCH_TOOL_PATH = "data_agent/tools/search.py"
TOOL_MANAGER_PATH = "data_agent/tools/tool_manager.py"
AGENT_SERVER_PATH = "data_agent/agent_server.py"
READINESS_PATH = "data_agent/readiness.py"
CODE_EXECUTION_TOOL_PATH = "data_agent/tools/code_execution.py"
RELEASE_WORKFLOW_PATH = ".github/workflows/release-readiness.yml"
CONTAINER_SMOKE_PATH = "scripts/verify_container_smoke.py"
FRONTEND_FILE_CLIENT_PATH = "agent_chatui/src/lib/managed-file-client.ts"
FRONTEND_FILE_HOOK_PATH = "agent_chatui/src/hooks/use-file-upload.tsx"
REQUIRED_SCAN_FILES = {
    NEXT_CONFIG_PATH,
    ENV_EXAMPLE_PATH,
    COMPOSE_PATH,
    DOCKERIGNORE_PATH,
    DOCKERFILE_PATH,
    USER_MODEL_PATH,
    AUDIT_MODULE_PATH,
    EVENTS_MODULE_PATH,
    LANGGRAPH_CONFIG_PATH,
    LANGGRAPH_AUTH_MODULE_PATH,
    FRONTEND_API_KEY_PATH,
    MANAGED_FILE_MODEL_PATH,
    MANAGED_FILE_ROUTE_PATH,
    MANAGED_FILE_SERVICE_PATH,
    DOCUMENT_TOOL_PATH,
    AGENT_CONFIG_PATH,
    AGENT_SERVICE_PATH,
    SEARCH_TOOL_PATH,
    TOOL_MANAGER_PATH,
    AGENT_SERVER_PATH,
    READINESS_PATH,
    RELEASE_WORKFLOW_PATH,
    CONTAINER_SMOKE_PATH,
    FRONTEND_FILE_CLIENT_PATH,
    FRONTEND_FILE_HOOK_PATH,
}


def _migration_source(revision: str, down_revision: str | None) -> str:
    parent = "None" if down_revision is None else f'"{down_revision}"'
    return (
        f'revision = "{revision}"\n'
        f"down_revision = {parent}\n"
        "\n"
        "def upgrade() -> None:\n"
        "    pass\n"
        "\n"
        "def downgrade() -> None:\n"
        "    pass\n"
    )


VALID_NEXT_CONFIG = """\
const nextConfig = {};

export default nextConfig;
"""
VALID_ENV_EXAMPLE = """\
MOONSHOT_API_KEY=your_moonshot_api_key_here
TAVILY_API_KEY=your_tavily_api_key_here
JWT_SECRET_KEY=your_jwt_secret_key_here
SERVICE_NAME=deep-data-agent
LOG_FILE_PATH=deep_data_agent.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=3
DOCKER_LOG_MAX_SIZE=10m
DOCKER_LOG_MAX_FILES=3
RATE_LIMIT_ENABLED=true
TRUSTED_PROXY_COUNT=0
RATE_LIMIT_AUTH_MAX_REQUESTS=10
RATE_LIMIT_AUTH_WINDOW_SECONDS=60
RATE_LIMIT_QUERY_MAX_REQUESTS=20
RATE_LIMIT_QUERY_WINDOW_SECONDS=60
RATE_LIMIT_SESSION_MAX_REQUESTS=60
RATE_LIMIT_SESSION_WINDOW_SECONDS=60
RATE_LIMIT_DEFAULT_MAX_REQUESTS=120
RATE_LIMIT_DEFAULT_WINDOW_SECONDS=60
FILE_STORAGE_ROOT=var/managed_files
FILE_UPLOAD_MAX_BYTES=5242880
FILE_UPLOAD_BATCH_MAX_BYTES=10485760
FILE_UPLOAD_REQUEST_MAX_BYTES=11534336
FILE_UPLOAD_BATCH_MAX_COUNT=5
FILE_USER_QUOTA_BYTES=104857600
FILE_USER_MAX_COUNT=100
FILE_RETENTION_HOURS=168
FILE_ANALYSIS_MAX_CHARS=20000
COMPOSE_FILE_STORAGE_ROOT=/data/managed-files
MODEL_REQUEST_TIMEOUT_SECONDS=45
MODEL_MAX_RETRIES=1
MODEL_MAX_OUTPUT_TOKENS=4096
AGENT_QUERY_MAX_CHARS=8000
AGENT_RESPONSE_MAX_CHARS=32000
AGENT_RUN_TIMEOUT_SECONDS=60
AGENT_RECURSION_LIMIT=25
AGENT_MODEL_CALL_LIMIT=8
AGENT_TOOL_CALL_LIMIT=12
AGENT_GLOBAL_CONCURRENCY_LIMIT=4
AGENT_USER_CONCURRENCY_LIMIT=1
AGENT_CONCURRENCY_WAIT_SECONDS=1
AGENT_CONCURRENCY_LEASE_TTL_SECONDS=75
SEARCH_QUERY_MAX_CHARS=2000
SEARCH_MAX_RESULTS=5
SEARCH_TIMEOUT_SECONDS=15
SEARCH_MAX_OUTPUT_BYTES=65536
REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS=1
REDIS_RECOVERY_MAX_BACKOFF_SECONDS=30
REDIS_RECOVERY_JITTER_RATIO=0.2
"""
VALID_COMPOSE = """\
x-bounded-logging: &bounded-logging
  driver: json-file
  options:
    max-size: ${DOCKER_LOG_MAX_SIZE:-10m}
    max-file: ${DOCKER_LOG_MAX_FILES:-3}

services:
  mysql:
    logging: *bounded-logging
  redis:
    logging: *bounded-logging
  backend:
    environment:
      DATABASE_URL: ${COMPOSE_DATABASE_URL:-mysql+pymysql://app:app@mysql:3306/app}
      REDIS_URL: ${COMPOSE_REDIS_URL:-redis://redis:6379/0}
      FILE_STORAGE_ROOT: ${COMPOSE_FILE_STORAGE_ROOT:-/data/managed-files}
      MODEL_REQUEST_TIMEOUT_SECONDS: ${MODEL_REQUEST_TIMEOUT_SECONDS:-45}
      MODEL_MAX_RETRIES: ${MODEL_MAX_RETRIES:-1}
      MODEL_MAX_OUTPUT_TOKENS: ${MODEL_MAX_OUTPUT_TOKENS:-4096}
      AGENT_QUERY_MAX_CHARS: ${AGENT_QUERY_MAX_CHARS:-8000}
      AGENT_RESPONSE_MAX_CHARS: ${AGENT_RESPONSE_MAX_CHARS:-32000}
      AGENT_RUN_TIMEOUT_SECONDS: ${AGENT_RUN_TIMEOUT_SECONDS:-60}
      AGENT_RECURSION_LIMIT: ${AGENT_RECURSION_LIMIT:-25}
      AGENT_MODEL_CALL_LIMIT: ${AGENT_MODEL_CALL_LIMIT:-8}
      AGENT_TOOL_CALL_LIMIT: ${AGENT_TOOL_CALL_LIMIT:-12}
      AGENT_GLOBAL_CONCURRENCY_LIMIT: ${AGENT_GLOBAL_CONCURRENCY_LIMIT:-4}
      AGENT_USER_CONCURRENCY_LIMIT: ${AGENT_USER_CONCURRENCY_LIMIT:-1}
      AGENT_CONCURRENCY_WAIT_SECONDS: ${AGENT_CONCURRENCY_WAIT_SECONDS:-1}
      AGENT_CONCURRENCY_LEASE_TTL_SECONDS: ${AGENT_CONCURRENCY_LEASE_TTL_SECONDS:-75}
      SEARCH_QUERY_MAX_CHARS: ${SEARCH_QUERY_MAX_CHARS:-2000}
      SEARCH_MAX_RESULTS: ${SEARCH_MAX_RESULTS:-5}
      SEARCH_TIMEOUT_SECONDS: ${SEARCH_TIMEOUT_SECONDS:-15}
      SEARCH_MAX_OUTPUT_BYTES: ${SEARCH_MAX_OUTPUT_BYTES:-65536}
      REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS: ${REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS:-1}
      REDIS_RECOVERY_MAX_BACKOFF_SECONDS: ${REDIS_RECOVERY_MAX_BACKOFF_SECONDS:-30}
      REDIS_RECOVERY_JITTER_RATIO: ${REDIS_RECOVERY_JITTER_RATIO:-0.2}
    healthcheck:
      test: http://127.0.0.1:8000/api/ready
    logging: *bounded-logging
    volumes:
      - managed_file_data:/data/managed-files
  langgraph:
    healthcheck:
      test: http://127.0.0.1:2024/info && python -m data_agent.readiness
  frontend:
    logging: *bounded-logging
volumes:
  managed_file_data:
"""
VALID_DOCKERIGNORE = """\
**
!requirements.txt
!data_agent/
!data_agent/**
!langgraph.json
!alembic.ini
!migrations/
!migrations/**

**/__pycache__
**/*.py[cod]
**/.pytest_cache
**/.mypy_cache
**/.ruff_cache
**/*.log
"""
VALID_DOCKERFILE = """\
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
COPY data_agent ./data_agent
COPY alembic.ini ./
COPY migrations ./migrations
COPY langgraph.json ./
"""
VALID_USER_MODEL = """\
class UserRole:
    USER = "user"
    ADMIN = "admin"

class User:
    role = Column(
        String(20),
        nullable=False,
        server_default=UserRole.USER.value,
    )
    constraint = "role IN ('user', 'admin')"
"""
VALID_AUDIT_MODULE = """\
from hashlib import sha256
import hmac

def reference(secret, value):
    return hmac.new(secret, value, sha256).hexdigest()
"""
VALID_EVENTS_MODULE = """\
SAFE_FIELDS = {
    "actor_ref",
    "target_ref",
}
"""
VALID_LANGGRAPH_CONFIG = """\
{
  "graphs": {"agent": "./data_agent/agent_graph.py:agent"},
  "auth": {
    "path": "./data_agent/security/langgraph_auth.py:auth"
  }
}
"""
VALID_LANGGRAPH_AUTH = """\
@auth.authenticate
def authenticate(authorization):
    return get_user_for_authorization_header(authorization)

@auth.on
async def deny(ctx, value):
    return False

@auth.on.threads
async def owner(ctx, value):
    return {"owner": ctx.user.identity}
"""
VALID_FRONTEND_API_KEY = """\
const LEGACY_API_KEY_STORAGE_KEY = "lg:chat:apiKey";
window.localStorage.removeItem(LEGACY_API_KEY_STORAGE_KEY);
headers.Authorization = `Bearer ${authToken}`;
"""
VALID_MANAGED_FILE_MODEL = """\
class ManagedFile:
    __tablename__ = "managed_files"
    user_id = file_id = storage_key = sha256 = expires_at = None
"""
VALID_MANAGED_FILE_ROUTE = """\
Permission.FILE_READ_OWN
Permission.FILE_WRITE_OWN
Permission.FILE_DELETE_OWN
global_managed_file_service
"""
VALID_MANAGED_FILE_SERVICE = """\
FILE_UPLOAD_MAX_BYTES
FILE_UPLOAD_BATCH_MAX_BYTES
FILE_USER_QUOTA_BYTES
with_for_update
normalize_file_id
"""
VALID_DOCUMENT_TOOL = """\
def analyze_document(file_id: str, config: RunnableConfig):
    user_id = config["configurable"]["langgraph_auth_user_id"]
    return global_managed_file_service.analyze_file(user_id, file_id)
"""
VALID_AGENT_CONFIG = """\
MODEL_REQUEST_TIMEOUT_SECONDS = env("MODEL_REQUEST_TIMEOUT_SECONDS", 45)
MODEL_MAX_RETRIES = env("MODEL_MAX_RETRIES", 1)
MODEL_MAX_OUTPUT_TOKENS = env("MODEL_MAX_OUTPUT_TOKENS", 4096)
AGENT_QUERY_MAX_CHARS = env("AGENT_QUERY_MAX_CHARS", 8000)
AGENT_RESPONSE_MAX_CHARS = env("AGENT_RESPONSE_MAX_CHARS", 32000)
AGENT_RUN_TIMEOUT_SECONDS = env("AGENT_RUN_TIMEOUT_SECONDS", 60)
AGENT_RECURSION_LIMIT = env("AGENT_RECURSION_LIMIT", 25)
AGENT_MODEL_CALL_LIMIT = env("AGENT_MODEL_CALL_LIMIT", 8)
AGENT_TOOL_CALL_LIMIT = env("AGENT_TOOL_CALL_LIMIT", 12)
AGENT_GLOBAL_CONCURRENCY_LIMIT = env("AGENT_GLOBAL_CONCURRENCY_LIMIT", 4)
AGENT_USER_CONCURRENCY_LIMIT = env("AGENT_USER_CONCURRENCY_LIMIT", 1)
AGENT_CONCURRENCY_WAIT_SECONDS = env("AGENT_CONCURRENCY_WAIT_SECONDS", 1)
AGENT_CONCURRENCY_LEASE_TTL_SECONDS = env("AGENT_CONCURRENCY_LEASE_TTL_SECONDS", 75)
SEARCH_QUERY_MAX_CHARS = env("SEARCH_QUERY_MAX_CHARS", 2000)
SEARCH_MAX_RESULTS = env("SEARCH_MAX_RESULTS", 5)
SEARCH_TIMEOUT_SECONDS = env("SEARCH_TIMEOUT_SECONDS", 15)
SEARCH_MAX_OUTPUT_BYTES = env("SEARCH_MAX_OUTPUT_BYTES", 65536)
REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS = env("REDIS_RECOVERY_INITIAL_BACKOFF_SECONDS", 1)
REDIS_RECOVERY_MAX_BACKOFF_SECONDS = env("REDIS_RECOVERY_MAX_BACKOFF_SECONDS", 30)
REDIS_RECOVERY_JITTER_RATIO = env("REDIS_RECOVERY_JITTER_RATIO", 0.2)
"""
VALID_AGENT_SERVICE = """\
ModelCallLimitMiddleware(
    run_limit=config.AGENT_MODEL_CALL_LIMIT,
    exit_behavior="error",
)
ToolCallLimitMiddleware(
    run_limit=config.AGENT_TOOL_CALL_LIMIT,
    exit_behavior="error",
)
bounded["recursion_limit"] = config.AGENT_RECURSION_LIMIT
ChatOpenAI(
    timeout=config.MODEL_REQUEST_TIMEOUT_SECONDS,
    max_retries=config.MODEL_MAX_RETRIES,
    max_tokens=config.MODEL_MAX_OUTPUT_TOKENS,
)
"""
VALID_SEARCH_TOOL = """\
from tavily import AsyncTavilyClient

async def internet_search(
    query: Annotated[str, Field(max_length=2000)],
    max_results: Annotated[int, Field(le=5)],
    topic: Literal["general", "news"],
):
    async with asyncio.timeout(config.SEARCH_TIMEOUT_SECONDS):
        return await client.search(
            include_raw_content=False,
            max_bytes=config.SEARCH_MAX_OUTPUT_BYTES,
        )
"""
VALID_TOOL_MANAGER = """\
self.register_tool("internet_search", internet_search)
self.register_tool("analyze_document", analyze_document)
"""
VALID_AGENT_SERVER = """\
@app.get("/api/live")
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/ready")
async def readiness_check():
    return await check_readiness_async()
"""
VALID_READINESS = """\
def check_readiness():
    config.require_model_api_key()
    connection.execute(text("SELECT 1"))
    ScriptDirectory.from_config(config).get_heads()
    MigrationContext.configure(connection).get_current_heads()
    client.ping()
    root = storage._storage_root(create=True)

async def check_readiness_async():
    return await anyio.to_thread.run_sync(check_readiness)
"""
VALID_RELEASE_WORKFLOW = """\
- name: Verify Redis stop and recovery
  run: python scripts/verify_container_smoke.py redis-canary
"""
VALID_CONTAINER_SMOKE = """\
AGENT_PROTECTION_UNAVAILABLE = "agent_protection_unavailable"

def verify_redis_recovery_canary():
    live = "/api/live"
    ready = "/api/ready"
    commands = ("stop", "start")
"""
VALID_FRONTEND_FILE_CLIENT = """\
const path = "api/files";
const FILE_MAX_BYTES = 5242880;
const FILE_BATCH_MAX_BYTES = 10485760;
export function uploadManagedFiles() {}
export function deleteManagedFile() {}
"""
VALID_FRONTEND_FILE_HOOK = """\
uploadManagedFiles
deleteManagedFile
validateManagedFileSelection
"""


def _write(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_bytes(root: Path, relative_path: str, content: bytes) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
    )


def _create_minimal_repository(root: Path) -> set[str]:
    _write(root, NEXT_CONFIG_PATH, VALID_NEXT_CONFIG)
    _write(root, ENV_EXAMPLE_PATH, VALID_ENV_EXAMPLE)
    _write(root, COMPOSE_PATH, VALID_COMPOSE)
    _write(root, DOCKERIGNORE_PATH, VALID_DOCKERIGNORE)
    _write(root, DOCKERFILE_PATH, VALID_DOCKERFILE)
    _write(root, USER_MODEL_PATH, VALID_USER_MODEL)
    _write(root, AUDIT_MODULE_PATH, VALID_AUDIT_MODULE)
    _write(root, EVENTS_MODULE_PATH, VALID_EVENTS_MODULE)
    _write(root, LANGGRAPH_CONFIG_PATH, VALID_LANGGRAPH_CONFIG)
    _write(root, LANGGRAPH_AUTH_MODULE_PATH, VALID_LANGGRAPH_AUTH)
    _write(root, FRONTEND_API_KEY_PATH, VALID_FRONTEND_API_KEY)
    _write(root, MANAGED_FILE_MODEL_PATH, VALID_MANAGED_FILE_MODEL)
    _write(root, MANAGED_FILE_ROUTE_PATH, VALID_MANAGED_FILE_ROUTE)
    _write(root, MANAGED_FILE_SERVICE_PATH, VALID_MANAGED_FILE_SERVICE)
    _write(root, DOCUMENT_TOOL_PATH, VALID_DOCUMENT_TOOL)
    _write(root, AGENT_CONFIG_PATH, VALID_AGENT_CONFIG)
    _write(root, AGENT_SERVICE_PATH, VALID_AGENT_SERVICE)
    _write(root, SEARCH_TOOL_PATH, VALID_SEARCH_TOOL)
    _write(root, TOOL_MANAGER_PATH, VALID_TOOL_MANAGER)
    _write(root, AGENT_SERVER_PATH, VALID_AGENT_SERVER)
    _write(root, READINESS_PATH, VALID_READINESS)
    _write(root, RELEASE_WORKFLOW_PATH, VALID_RELEASE_WORKFLOW)
    _write(root, CONTAINER_SMOKE_PATH, VALID_CONTAINER_SMOKE)
    _write(root, FRONTEND_FILE_CLIENT_PATH, VALID_FRONTEND_FILE_CLIENT)
    _write(root, FRONTEND_FILE_HOOK_PATH, VALID_FRONTEND_FILE_HOOK)
    _write(
        root,
        f"{MIGRATIONS_VERSIONS_PATH}/0001_initial.py",
        _migration_source("0001", None),
    )
    return set(REQUIRED_SCAN_FILES)


def _check(
    root: Path,
    *,
    tracked_files=(),
    scan_files=None,
) -> list[contracts.Violation]:
    if scan_files is None:
        scan_files = REQUIRED_SCAN_FILES
    return contracts.check_repository(
        root,
        tracked_files=tracked_files,
        scan_files=scan_files,
    )


def test_minimal_repository_and_tracked_file_contracts(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)

    assert _check(tmp_path, scan_files=scan_files) == []

    local_env = _check(
        tmp_path,
        tracked_files={".env"},
        scan_files=scan_files,
    )
    assert [
        (item.rule, item.path, item.line) for item in local_env
    ] == [("TRACKED_LOCAL_ENV", ".env", 1)]

    generated = _check(
        tmp_path,
        tracked_files={"agent_chatui/.next/build-manifest.json"},
        scan_files=scan_files,
    )
    assert [
        (item.rule, item.path, item.line) for item in generated
    ] == [
        (
            "TRACKED_GENERATED_FILE",
            "agent_chatui/.next/build-manifest.json",
            1,
        )
    ]


def _dockerignore_violations(
    violations,
) -> list[tuple[str, str, int]]:
    return [
        (item.rule, item.path, item.line)
        for item in violations
        if item.path == DOCKERIGNORE_PATH
    ]


def test_dockerignore_runtime_allowlist_satisfies_contract(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert _dockerignore_violations(violations) == []


@pytest.mark.parametrize(
    ("required_line", "expected_rule"),
    [
        ("**\n", "DOCKERIGNORE_DEFAULT_DENY"),
        ("!requirements.txt\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!data_agent/\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!data_agent/**\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!langgraph.json\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!alembic.ini\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!migrations/\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("!migrations/**\n", "DOCKERIGNORE_REQUIRED_ALLOW"),
        ("**/__pycache__\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
        ("**/*.py[cod]\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
        ("**/.pytest_cache\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
        ("**/.mypy_cache\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
        ("**/.ruff_cache\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
        ("**/*.log\n", "DOCKERIGNORE_REQUIRED_EXCLUDE"),
    ],
    ids=[
        "default-deny",
        "requirements",
        "data-agent-parent",
        "data-agent-tree",
        "langgraph",
        "alembic",
        "migrations-parent",
        "migrations-tree",
        "pycache",
        "bytecode",
        "pytest-cache",
        "mypy-cache",
        "ruff-cache",
        "logs",
    ],
)
def test_missing_dockerignore_allowlist_rule_is_rejected(
    tmp_path,
    required_line,
    expected_rule,
):
    scan_files = _create_minimal_repository(tmp_path)
    invalid = VALID_DOCKERIGNORE.replace(required_line, "", 1)
    _write(tmp_path, DOCKERIGNORE_PATH, invalid)

    violations = _check(tmp_path, scan_files=scan_files)

    assert _dockerignore_violations(violations) == [
        (expected_rule, DOCKERIGNORE_PATH, 1)
    ]


def test_dockerignore_comment_does_not_satisfy_required_allow(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    invalid = VALID_DOCKERIGNORE.replace(
        "!requirements.txt\n",
        "# !requirements.txt\n",
    )
    _write(tmp_path, DOCKERIGNORE_PATH, invalid)

    violations = _check(tmp_path, scan_files=scan_files)

    assert _dockerignore_violations(violations) == [
        ("DOCKERIGNORE_REQUIRED_ALLOW", DOCKERIGNORE_PATH, 1)
    ]


def test_dockerignore_parser_accepts_comments_and_equivalent_paths(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    valid = (
        "# !README.md remains excluded from the runtime context.\n"
        + VALID_DOCKERIGNORE.replace(
            "!requirements.txt\n",
            "  !/requirements.txt/  \n",
        ).replace(
            "!data_agent/\n",
            "!/data_agent/\n",
        )
    )
    _write(tmp_path, DOCKERIGNORE_PATH, valid)

    violations = _check(tmp_path, scan_files=scan_files)

    assert _dockerignore_violations(violations) == []


@pytest.mark.parametrize(
    ("invalid", "expected_rule"),
    [
        (
            VALID_DOCKERIGNORE.replace(
                "!data_agent/\n!data_agent/**\n",
                "!data_agent/**\n!data_agent/\n",
            ),
            "DOCKERIGNORE_PARENT_ALLOW_ORDER",
        ),
        (
            VALID_DOCKERIGNORE.replace("**/*.log\n", "").replace(
                "**\n",
                "**\n**/*.log\n",
                1,
            ),
            "DOCKERIGNORE_EXCLUDE_ORDER",
        ),
    ],
    ids=["parent-before-tree", "cleanup-after-allows"],
)
def test_dockerignore_rule_order_is_enforced(
    tmp_path,
    invalid,
    expected_rule,
):
    scan_files = _create_minimal_repository(tmp_path)
    _write(tmp_path, DOCKERIGNORE_PATH, invalid)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        item.rule
        for item in violations
        if item.path == DOCKERIGNORE_PATH
    ] == [expected_rule]


@pytest.mark.parametrize(
    "unexpected_allow",
    [
        "README.md",
        "AGENTS.md",
        "CHANGELOG.md",
        "scripts/**",
        "utils/**",
        "tests/**",
        "agent_chatui/**",
        ".trae/**",
        ".env",
        ".git/**",
        ".venv/**",
        "data_agent/__pycache__/**",
        "data_agent/debug.log",
    ],
    ids=[
        "readme",
        "agents",
        "changelog",
        "scripts",
        "utils",
        "tests",
        "frontend",
        "trae",
        "env",
        "git",
        "venv",
        "cache",
        "log",
    ],
)
def test_dockerignore_non_runtime_allow_is_rejected(
    tmp_path,
    unexpected_allow,
):
    scan_files = _create_minimal_repository(tmp_path)
    invalid = VALID_DOCKERIGNORE + f"!{unexpected_allow}\n"
    _write(tmp_path, DOCKERIGNORE_PATH, invalid)

    violations = _check(tmp_path, scan_files=scan_files)

    assert _dockerignore_violations(violations) == [
        (
            "DOCKERIGNORE_NON_RUNTIME_ALLOW",
            DOCKERIGNORE_PATH,
            len(VALID_DOCKERIGNORE.splitlines()) + 1,
        )
    ]


def test_dockerignore_failure_output_contains_only_location(
    tmp_path,
    monkeypatch,
    capsys,
):
    scan_files = _create_minimal_repository(tmp_path)
    invalid = VALID_DOCKERIGNORE + "!README-private-details.md\n"
    _write(tmp_path, DOCKERIGNORE_PATH, invalid)
    violations = _check(tmp_path, scan_files=scan_files)
    monkeypatch.setattr(
        contracts,
        "check_repository",
        lambda root: violations,
    )

    assert contracts.main() == 1

    captured = capsys.readouterr()
    line = len(VALID_DOCKERIGNORE.splitlines()) + 1
    assert captured.out == ""
    assert captured.err == (
        f"DOCKERIGNORE_NON_RUNTIME_ALLOW {DOCKERIGNORE_PATH}:{line}\n"
    )
    assert "README-private-details.md" not in captured.err


def test_dockerfile_parent_migrations_copy_satisfies_asset_contract(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert not [
        item for item in violations if item.rule.startswith("DOCKERFILE_")
    ]


@pytest.mark.parametrize(
    ("dockerfile", "expected_rule"),
    [
        (
            VALID_DOCKERFILE.replace("COPY alembic.ini ./\n", ""),
            "DOCKERFILE_ALEMBIC_INI_COPY",
        ),
        (
            VALID_DOCKERFILE.replace(
                "COPY migrations ./migrations\n",
                "COPY migrations/versions ./migrations/versions\n",
            ),
            "DOCKERFILE_MIGRATIONS_COPY",
        ),
        (
            VALID_DOCKERFILE.replace(
                "COPY migrations ./migrations\n",
                "COPY migrations/env.py ./migrations/env.py\n"
                "COPY migrations/script.py.mako ./migrations/script.py.mako\n",
            ),
            "DOCKERFILE_MIGRATION_VERSIONS_COPY",
        ),
    ],
    ids=["alembic-ini", "migration-root-assets", "migration-versions"],
)
def test_missing_dockerfile_migration_asset_is_rejected(
    tmp_path,
    dockerfile,
    expected_rule,
):
    scan_files = _create_minimal_repository(tmp_path)
    _write(tmp_path, DOCKERFILE_PATH, dockerfile)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line)
        for item in violations
        if item.rule.startswith("DOCKERFILE_")
    ] == [(expected_rule, DOCKERFILE_PATH, 1)]


@pytest.mark.parametrize(
    "dockerfile",
    [
        VALID_DOCKERFILE.replace(
            "COPY alembic.ini ./\n",
            "COPY alembic.ini /tmp/\n",
        ).replace(
            "COPY migrations ./migrations\n",
            "COPY migrations /tmp/migrations\n",
        ),
        VALID_DOCKERFILE
        + "\nFROM python:3.12-slim\n"
        "WORKDIR /app\n"
        "COPY data_agent ./data_agent\n",
        VALID_DOCKERFILE.replace(
            "COPY alembic.ini ./\n",
            "# COPY alembic.ini ./\n"
            'RUN echo "COPY alembic.ini ./"\n'
            "COPY alembic.ini.backup ./alembic.ini\n",
        ).replace(
            "COPY migrations ./migrations\n",
            "# COPY migrations ./migrations\n"
            'RUN echo "COPY migrations ./migrations"\n'
            "COPY migrations-backup ./migrations\n",
        ),
    ],
    ids=["wrong-destination", "earlier-stage", "comments-and-similar-paths"],
)
def test_dockerfile_copy_contract_cannot_be_bypassed(
    tmp_path,
    dockerfile,
):
    scan_files = _create_minimal_repository(tmp_path)
    _write(tmp_path, DOCKERFILE_PATH, dockerfile)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        item.rule
        for item in violations
        if item.rule.startswith("DOCKERFILE_")
    ] == [
        "DOCKERFILE_ALEMBIC_INI_COPY",
        "DOCKERFILE_MIGRATIONS_COPY",
        "DOCKERFILE_MIGRATION_VERSIONS_COPY",
    ]


@pytest.mark.parametrize(
    "keyword",
    ["ignoreBuildErrors", "ignoreDuringBuilds"],
)
def test_next_build_bypass_is_rejected(tmp_path, keyword):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        NEXT_CONFIG_PATH,
        f"const nextConfig = {{ {keyword}: true }};\n",
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line) for item in violations
    ] == [("NEXT_BUILD_BYPASS", NEXT_CONFIG_PATH, 1)]


def test_required_files_are_read_outside_explicit_scan_set(tmp_path):
    _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        NEXT_CONFIG_PATH,
        "const nextConfig = { ignoreBuildErrors: true };\n",
    )

    violations = _check(tmp_path, scan_files=set())

    assert [
        (item.rule, item.path, item.line) for item in violations
    ] == [("NEXT_BUILD_BYPASS", NEXT_CONFIG_PATH, 1)]


def test_explicit_file_sets_do_not_invoke_git(
    tmp_path,
    monkeypatch,
):
    scan_files = _create_minimal_repository(tmp_path)

    def fail_if_called(root):
        raise AssertionError("explicit file sets must not invoke Git")

    monkeypatch.setattr(contracts, "_git_tracked_files", fail_if_called)
    monkeypatch.setattr(contracts, "_git_scan_files", fail_if_called)

    assert contracts.check_repository(
        tmp_path,
        tracked_files=(),
        scan_files=scan_files,
    ) == []


def test_legacy_login_variable_and_main_output_are_redacted(
    tmp_path,
    monkeypatch,
    capsys,
):
    scan_files = _create_minimal_repository(tmp_path)
    source_path = "agent_chatui/src/login.ts"
    _write(
        tmp_path,
        source_path,
        "const loginUrl = process.env.NEXT_PUBLIC_LOGIN_API_URL;\n",
    )
    scan_files.add(source_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line) for item in violations
    ] == [("LEGACY_LOGIN_VARIABLE", source_path, 1)]

    monkeypatch.setattr(
        contracts,
        "check_repository",
        lambda root: [
            contracts.Violation("CREDENTIAL_PATTERN", source_path, 7)
        ],
    )
    assert contracts.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"CREDENTIAL_PATTERN {source_path}:7\n"


def test_langgraph_first_party_auth_path_is_required(tmp_path) -> None:
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        LANGGRAPH_CONFIG_PATH,
        VALID_LANGGRAPH_CONFIG.replace(
            "./data_agent/security/langgraph_auth.py:auth",
            "./unsafe.py:auth",
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "LANGGRAPH_FIRST_PARTY_AUTH"
    ] == [("LANGGRAPH_FIRST_PARTY_AUTH", LANGGRAPH_CONFIG_PATH)]


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        (
            'const [apiUrl] = useQueryState("apiUrl");\n',
            "VARIABLE_AGENT_ORIGIN",
        ),
        (
            'const [assistant] = useQueryState("assistantId");\n',
            "VARIABLE_AGENT_ORIGIN",
        ),
        ("const key = getApiKey();\n", "LEGACY_AGENT_API_KEY"),
        ('headers["X-Api-Key"] = key;\n', "LEGACY_AGENT_API_KEY"),
        (
            "localStorage.getItem(LEGACY_API_KEY_STORAGE_KEY);\n",
            "LEGACY_AGENT_API_KEY",
        ),
    ],
)
def test_variable_agent_connection_and_legacy_key_are_rejected(
    tmp_path,
    source,
    rule,
) -> None:
    scan_files = _create_minimal_repository(tmp_path)
    source_path = "agent_chatui/src/unsafe-agent.ts"
    _write(tmp_path, source_path, source)
    scan_files.add(source_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line)
        for item in violations
        if item.rule == rule
    ] == [(rule, source_path, 1)]


def test_agent_bearer_header_and_legacy_key_cleanup_are_required(
    tmp_path,
) -> None:
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        FRONTEND_API_KEY_PATH,
        "export const headers = {};\n",
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "AGENT_BEARER_AUTH"
    ] == [("AGENT_BEARER_AUTH", FRONTEND_API_KEY_PATH)]


@pytest.mark.parametrize(
    "variable",
    ["MOONSHOT_API_KEY", "TAVILY_API_KEY", "JWT_SECRET_KEY"],
)
def test_env_example_placeholder_must_be_exact(tmp_path, variable):
    scan_files = _create_minimal_repository(tmp_path)
    expected = contracts.PLACEHOLDERS[variable]
    invalid_env = VALID_ENV_EXAMPLE.replace(
        f"{variable}={expected}",
        f"{variable}=invalid-placeholder",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    assert len(violations) == 1
    assert violations[0].rule == "ENV_EXAMPLE_PLACEHOLDER"
    assert violations[0].path == ENV_EXAMPLE_PATH


@pytest.mark.parametrize(
    "variable",
    sorted(contracts.OBSERVABILITY_DEFAULTS),
)
def test_observability_env_defaults_must_be_exact(tmp_path, variable):
    scan_files = _create_minimal_repository(tmp_path)
    expected = contracts.OBSERVABILITY_DEFAULTS[variable]
    invalid_env = VALID_ENV_EXAMPLE.replace(
        f"{variable}={expected}",
        f"{variable}=invalid-default",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    matching = [
        item
        for item in violations
        if item.rule == "OBSERVABILITY_ENV_DEFAULT"
    ]
    assert len(matching) == 1
    assert matching[0].path == ENV_EXAMPLE_PATH


@pytest.mark.parametrize(
    "variable",
    sorted(contracts.RATE_LIMIT_DEFAULTS),
)
def test_rate_limit_env_defaults_must_be_exact(tmp_path, variable):
    scan_files = _create_minimal_repository(tmp_path)

    baseline = _check(tmp_path, scan_files=scan_files)
    assert not [
        (item.rule, item.path)
        for item in baseline
        if item.rule == "RATE_LIMIT_ENV_DEFAULT"
    ]

    expected = contracts.RATE_LIMIT_DEFAULTS[variable]
    invalid_env = VALID_ENV_EXAMPLE.replace(
        f"{variable}={expected}",
        f"{variable}=999",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    matching = [
        (item.rule, item.path)
        for item in violations
        if item.rule == "RATE_LIMIT_ENV_DEFAULT"
    ]
    assert matching == [("RATE_LIMIT_ENV_DEFAULT", ENV_EXAMPLE_PATH)]


def test_rate_limit_env_default_missing_key_is_reported(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    invalid_env = VALID_ENV_EXAMPLE.replace(
        "RATE_LIMIT_AUTH_MAX_REQUESTS=10\n",
        "",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    matching = [
        (item.rule, item.path)
        for item in violations
        if item.rule == "RATE_LIMIT_ENV_DEFAULT"
    ]
    assert matching == [("RATE_LIMIT_ENV_DEFAULT", ENV_EXAMPLE_PATH)]


@pytest.mark.parametrize(
    "variable",
    sorted(contracts.FILE_INGESTION_DEFAULTS),
)
def test_file_ingestion_env_defaults_must_be_exact(tmp_path, variable):
    scan_files = _create_minimal_repository(tmp_path)
    expected = contracts.FILE_INGESTION_DEFAULTS[variable]
    invalid_env = VALID_ENV_EXAMPLE.replace(
        f"{variable}={expected}",
        f"{variable}=invalid",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "FILE_INGESTION_ENV_DEFAULT"
    ] == [("FILE_INGESTION_ENV_DEFAULT", ENV_EXAMPLE_PATH)]


@pytest.mark.parametrize(
    "variable",
    sorted(contracts.AGENT_RESOURCE_DEFAULTS),
)
def test_agent_resource_env_defaults_must_be_exact(tmp_path, variable):
    scan_files = _create_minimal_repository(tmp_path)
    expected = contracts.AGENT_RESOURCE_DEFAULTS[variable]
    invalid_env = VALID_ENV_EXAMPLE.replace(
        f"{variable}={expected}",
        f"{variable}=invalid",
    )
    _write(tmp_path, ENV_EXAMPLE_PATH, invalid_env)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "AGENT_RESOURCE_ENV_DEFAULT"
    ] == [("AGENT_RESOURCE_ENV_DEFAULT", ENV_EXAMPLE_PATH)]


@pytest.mark.parametrize(
    "variable",
    sorted(contracts.AGENT_RESOURCE_DEFAULTS),
)
def test_agent_resource_compose_defaults_must_be_exact(
    tmp_path,
    variable,
):
    scan_files = _create_minimal_repository(tmp_path)
    expected = contracts.AGENT_RESOURCE_DEFAULTS[variable]
    invalid_compose = VALID_COMPOSE.replace(
        f"{variable}: ${{{variable}:-{expected}}}",
        f"{variable}: invalid",
    )
    _write(tmp_path, COMPOSE_PATH, invalid_compose)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "AGENT_RESOURCE_COMPOSE_DEFAULT"
    ] == [("AGENT_RESOURCE_COMPOSE_DEFAULT", COMPOSE_PATH)]


@pytest.mark.parametrize(
    ("path", "source"),
    [
        (ENV_EXAMPLE_PATH, "ENABLE_CODE_EXECUTION=true\n"),
        (TOOL_MANAGER_PATH, "register(execute_python_code)\n"),
        (CODE_EXECUTION_TOOL_PATH, "def execute_python_code(): pass\n"),
    ],
)
def test_code_execution_runtime_cannot_be_restored(
    tmp_path,
    path,
    source,
):
    scan_files = _create_minimal_repository(tmp_path)
    if path == ENV_EXAMPLE_PATH:
        source = VALID_ENV_EXAMPLE + source
    elif path == TOOL_MANAGER_PATH:
        source = VALID_TOOL_MANAGER + source
    else:
        scan_files.add(path)
    _write(tmp_path, path, source)

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "CODE_EXECUTION_RUNTIME_REMOVED"
        and item.path == path
        for item in violations
    )


def test_readiness_compose_healthcheck_cannot_use_liveness(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    invalid_compose = VALID_COMPOSE.replace(
        "127.0.0.1:8000/api/ready",
        "127.0.0.1:8000/api/health",
    )
    _write(tmp_path, COMPOSE_PATH, invalid_compose)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "READINESS_COMPOSE_HEALTHCHECK"
    ] == [("READINESS_COMPOSE_HEALTHCHECK", COMPOSE_PATH)]


def test_readiness_helper_cannot_call_external_services(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        READINESS_PATH,
        VALID_READINESS + "\nclient = ChatOpenAI()\n",
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "READINESS_EXTERNAL_CALL"
    ] == [("READINESS_EXTERNAL_CALL", READINESS_PATH)]


def test_redis_recovery_canary_is_required_by_release_workflow(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(tmp_path, RELEASE_WORKFLOW_PATH, "steps: []\n")

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "READINESS_RUNTIME"
    ] == [("READINESS_RUNTIME", RELEASE_WORKFLOW_PATH)]


def test_managed_file_compose_volume_is_required(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        COMPOSE_PATH,
        VALID_COMPOSE.replace(
            "      - managed_file_data:/data/managed-files\n",
            "",
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "MANAGED_FILE_COMPOSE_VOLUME"
        for item in violations
    )


@pytest.mark.parametrize(
    "source",
    [
        "def analyze_document(file_path):\n    return open(file_path).read()\n",
        "if os.path.exists(value):\n    pass\n",
    ],
)
def test_arbitrary_path_document_tool_is_rejected(tmp_path, source):
    scan_files = _create_minimal_repository(tmp_path)
    _write(tmp_path, DOCUMENT_TOOL_PATH, source)

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "ARBITRARY_FILE_PATH_TOOL"
        for item in violations
    )


@pytest.mark.parametrize(
    "source",
    [
        "reader.readAsDataURL(file);\n",
        "const encoded = fileToBase64(file);\n",
        "const block = fileToContentBlock(file);\n",
    ],
)
def test_new_frontend_base64_upload_is_rejected(tmp_path, source):
    scan_files = _create_minimal_repository(tmp_path)
    path = "agent_chatui/src/unsafe-upload.ts"
    _write(tmp_path, path, source)
    scan_files.add(path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "LEGACY_BASE64_FILE_UPLOAD"
        and item.path == path
        for item in violations
    )


def test_remote_build_font_is_rejected(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    path = "agent_chatui/src/app/layout.tsx"
    _write(tmp_path, path, 'import { Inter } from "next/font/google";\n')
    scan_files.add(path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "REMOTE_BUILD_FONT" and item.path == path
        for item in violations
    )


def test_compose_log_retention_contract_is_required(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        COMPOSE_PATH,
        VALID_COMPOSE.replace(
            "max-size: ${DOCKER_LOG_MAX_SIZE:-10m}",
            "max-size: 100m",
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert any(
        item.rule == "COMPOSE_LOG_RETENTION" for item in violations
    )


@pytest.mark.parametrize(
    ("variable", "valid_host", "rule"),
    [
        ("DATABASE_URL", "@mysql:", "COMPOSE_DATABASE_URL_DEFAULT"),
        ("REDIS_URL", "//redis:", "COMPOSE_REDIS_URL_DEFAULT"),
    ],
)
def test_compose_default_must_use_service_host(
    tmp_path,
    variable,
    valid_host,
    rule,
):
    scan_files = _create_minimal_repository(tmp_path)
    invalid_compose = VALID_COMPOSE.replace(valid_host, valid_host[0:2] + "localhost:")
    _write(tmp_path, COMPOSE_PATH, invalid_compose)

    violations = _check(tmp_path, scan_files=scan_files)

    matching = [item for item in violations if item.rule == rule]
    assert len(matching) == 1
    assert matching[0].path == COMPOSE_PATH
    assert variable in VALID_COMPOSE.splitlines()[matching[0].line - 1]


def _credential_samples(group: str) -> list[str]:
    if group == "api-keys":
        return [
            "sk-" + "A" * 24,
            "tvly-" + "B" * 24,
        ]
    return [
        "eyJ" + "C" * 8 + "." + "D" * 8 + "." + "E" * 8,
        "Bearer " + "F" * 24,
    ]


@pytest.mark.parametrize(
    "source_path",
    [
        "scripts/canary.py",
        "migrations/canary.py",
        ".github/workflows/canary.yml",
        "tests/canary.txt",
        ".trae/specs/canary.md",
        "future-area/CREDENTIALS",
    ],
    ids=[
        "scripts",
        "migrations",
        "github",
        "tests",
        "trae",
        "new-top-level",
    ],
)
def test_explicit_scan_files_cover_repository_paths(tmp_path, source_path):
    scan_files = _create_minimal_repository(tmp_path)
    canary = "sk-" + "A" * 24
    _write(tmp_path, source_path, f'value = "{canary}"\n')
    scan_files.add(source_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line) for item in violations
    ] == [("CREDENTIAL_PATTERN", source_path, 1)]


def test_git_discovery_scans_tracked_and_nonignored_untracked_files(tmp_path):
    _create_minimal_repository(tmp_path)
    canary = "sk-" + "A" * 24
    tracked_path = "tracked/canary.txt"
    untracked_path = "pending/canary.txt"
    _write(tmp_path, ".gitignore", ".env\n")
    _write(tmp_path, tracked_path, f'tracked = "{canary}"\n')
    _write(tmp_path, ".env", f'IGNORED = "{canary}"\n')
    _git(tmp_path, "init", "--quiet")
    _git(tmp_path, "add", ".")
    _write(tmp_path, untracked_path, f'untracked = "{canary}"\n')

    violations = contracts.check_repository(tmp_path)

    assert [
        (item.rule, item.path, item.line)
        for item in violations
        if item.rule == "CREDENTIAL_PATTERN"
    ] == [
        ("CREDENTIAL_PATTERN", untracked_path, 1),
        ("CREDENTIAL_PATTERN", tracked_path, 1),
    ]
    assert not [item for item in violations if item.path == ".env"]


def test_binary_scan_candidates_are_skipped(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    canary = ("sk-" + "A" * 24).encode()
    nul_path = "assets/nul.bin"
    invalid_utf8_path = "assets/invalid-utf8.bin"
    _write_bytes(tmp_path, nul_path, canary + b"\0payload")
    _write_bytes(tmp_path, invalid_utf8_path, b"\xff" + canary)
    scan_files.update({nul_path, invalid_utf8_path})

    violations = _check(tmp_path, scan_files=scan_files)

    assert violations == []


def test_placeholders_and_split_canaries_are_allowed(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    placeholder_path = "examples/placeholders.txt"
    split_path = "examples/split_canary.py"
    _write(
        tmp_path,
        placeholder_path,
        "MOONSHOT_API_KEY=your_moonshot_api_key_here\n"
        "Authorization=Bearer <token>\n",
    )
    _write(
        tmp_path,
        split_path,
        'prefix = "sk-"\nvalue = prefix + "A" * 24\n',
    )
    scan_files.update({placeholder_path, split_path})

    violations = _check(tmp_path, scan_files=scan_files)

    assert violations == []


@pytest.mark.parametrize(
    "credential_group",
    ["api-keys", "tokens"],
    ids=["api-key-patterns", "token-patterns"],
)
def test_common_credential_patterns_are_reported_without_values(
    tmp_path,
    credential_group,
):
    scan_files = _create_minimal_repository(tmp_path)
    source_path = "data_agent/credential_fixture.py"
    source = "\n".join(
        f'VALUE_{index} = "{sample}"'
        for index, sample in enumerate(
            _credential_samples(credential_group),
            start=1,
        )
    )
    _write(tmp_path, source_path, source)
    scan_files.add(source_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path, item.line) for item in violations
    ] == [
        ("CREDENTIAL_PATTERN", source_path, 1),
        ("CREDENTIAL_PATTERN", source_path, 2),
    ]


def test_credential_failure_output_does_not_include_matched_value(
    tmp_path,
    monkeypatch,
    capsys,
):
    scan_files = _create_minimal_repository(tmp_path)
    source_path = "new-area/canary.txt"
    canary = "sk-" + "A" * 24
    _write(tmp_path, source_path, f'value = "{canary}"\n')
    scan_files.add(source_path)
    violations = _check(tmp_path, scan_files=scan_files)
    monkeypatch.setattr(
        contracts,
        "check_repository",
        lambda root: violations,
    )

    assert contracts.main() == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"CREDENTIAL_PATTERN {source_path}:1\n"
    assert canary not in captured.err


def _migration_head_rules(
    violations,
) -> list[tuple[str, str]]:
    return [
        (item.rule, item.path)
        for item in violations
        if item.rule == "MIGRATION_HEAD"
    ]


def test_single_migration_head_passes_contract(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        f"{MIGRATIONS_VERSIONS_PATH}/0002_next.py",
        _migration_source("0002", "0001"),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert _migration_head_rules(violations) == []


def test_missing_migrations_versions_reports_single_violation(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    versions_dir = tmp_path / MIGRATIONS_VERSIONS_PATH
    for candidate in versions_dir.glob("*.py"):
        candidate.unlink()

    violations = _check(tmp_path, scan_files=scan_files)

    assert _migration_head_rules(violations) == [
        ("MIGRATION_HEAD", MIGRATIONS_VERSIONS_PATH)
    ]


def test_absent_migrations_directory_reports_single_violation(tmp_path):
    _write(tmp_path, NEXT_CONFIG_PATH, VALID_NEXT_CONFIG)
    _write(tmp_path, ENV_EXAMPLE_PATH, VALID_ENV_EXAMPLE)
    _write(tmp_path, COMPOSE_PATH, VALID_COMPOSE)

    violations = _check(tmp_path, scan_files=set(REQUIRED_SCAN_FILES))

    assert _migration_head_rules(violations) == [
        ("MIGRATION_HEAD", MIGRATIONS_VERSIONS_PATH)
    ]


def test_multiple_migration_heads_report_single_violation(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        f"{MIGRATIONS_VERSIONS_PATH}/0002_fork.py",
        _migration_source("0002", None),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert _migration_head_rules(violations) == [
        ("MIGRATION_HEAD", MIGRATIONS_VERSIONS_PATH)
    ]


def test_default_admin_role_is_rejected(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        USER_MODEL_PATH,
        VALID_USER_MODEL.replace(
            "server_default=UserRole.USER.value",
            "server_default=UserRole.ADMIN.value",
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "RBAC_DEFAULT_ROLE"
    ] == [("RBAC_DEFAULT_ROLE", USER_MODEL_PATH)]


def test_unconstrained_role_is_rejected(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        USER_MODEL_PATH,
        VALID_USER_MODEL.replace(
            """    constraint = "role IN ('user', 'admin')"\n""",
            "",
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "RBAC_ROLE_CONSTRAINT"
    ] == [("RBAC_ROLE_CONSTRAINT", USER_MODEL_PATH)]


def test_environment_driven_admin_promotion_is_rejected(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    source_path = "data_agent/config/unsafe_admin.py"
    _write(
        tmp_path,
        source_path,
        'value = os.environ.get("ADMIN_EMAIL")\n',
    )
    scan_files.add(source_path)

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "RBAC_AUTO_ADMIN"
    ] == [("RBAC_AUTO_ADMIN", source_path)]


def test_raw_identity_audit_field_is_rejected(tmp_path):
    scan_files = _create_minimal_repository(tmp_path)
    _write(
        tmp_path,
        EVENTS_MODULE_PATH,
        VALID_EVENTS_MODULE.replace(
            '"target_ref",',
            '"target_ref",\n    "email",',
        ),
    )

    violations = _check(tmp_path, scan_files=scan_files)

    assert [
        (item.rule, item.path)
        for item in violations
        if item.rule == "AUDIT_IDENTITY_REDACTION"
    ] == [("AUDIT_IDENTITY_REDACTION", EVENTS_MODULE_PATH)]
