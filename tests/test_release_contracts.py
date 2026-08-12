from pathlib import Path

import pytest

from scripts import check_release_contracts as contracts

NEXT_CONFIG_PATH = "agent_chatui/next.config.mjs"
ENV_EXAMPLE_PATH = ".env.example"
COMPOSE_PATH = "docker-config/docker-compose.yml"
MIGRATIONS_VERSIONS_PATH = "migrations/versions"
USER_MODEL_PATH = "data_agent/models/user.py"
AUDIT_MODULE_PATH = "data_agent/observability/audit.py"
EVENTS_MODULE_PATH = "data_agent/observability/events.py"
REQUIRED_SCAN_FILES = {
    NEXT_CONFIG_PATH,
    ENV_EXAMPLE_PATH,
    COMPOSE_PATH,
    USER_MODEL_PATH,
    AUDIT_MODULE_PATH,
    EVENTS_MODULE_PATH,
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
    logging: *bounded-logging
  frontend:
    logging: *bounded-logging
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


def _write(root: Path, relative_path: str, text: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _create_minimal_repository(root: Path) -> set[str]:
    _write(root, NEXT_CONFIG_PATH, VALID_NEXT_CONFIG)
    _write(root, ENV_EXAMPLE_PATH, VALID_ENV_EXAMPLE)
    _write(root, COMPOSE_PATH, VALID_COMPOSE)
    _write(root, USER_MODEL_PATH, VALID_USER_MODEL)
    _write(root, AUDIT_MODULE_PATH, VALID_AUDIT_MODULE)
    _write(root, EVENTS_MODULE_PATH, VALID_EVENTS_MODULE)
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
