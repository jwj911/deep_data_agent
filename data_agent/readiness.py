"""Dependency readiness checks shared by FastAPI and container probes."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

import anyio
import redis
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from data_agent.config.config import ConfigurationError, config
from data_agent.config.database import _alembic_config, get_engine
from data_agent.services.managed_file_service import \
    global_managed_file_service

READY = "ready"
NOT_READY = "not_ready"
MODEL_COMPONENT = "model"
DATABASE_COMPONENT = "database"
MIGRATION_COMPONENT = "migration"
REDIS_COMPONENT = "redis"
MANAGED_FILES_COMPONENT = "managed_files"

_FAILURE_CODES = {
    MODEL_COMPONENT: "model_configuration_invalid",
    DATABASE_COMPONENT: "database_unavailable",
    MIGRATION_COMPONENT: "migration_not_ready",
    REDIS_COMPONENT: "redis_unavailable",
    MANAGED_FILES_COMPONENT: "managed_file_storage_unavailable",
}


@dataclass(frozen=True)
class ComponentReadiness:
    """One fixed, externally safe component result."""

    status: str
    code: str


@dataclass(frozen=True)
class ReadinessResult:
    """Aggregate readiness without retaining dependency details."""

    components: dict[str, ComponentReadiness]

    @property
    def ready(self) -> bool:
        return all(
            component.status == READY
            for component in self.components.values()
        )

    def response_payload(self, request_id: str) -> dict[str, object]:
        return {
            "status": READY if self.ready else NOT_READY,
            "request_id": request_id,
            "components": {
                name: {
                    "status": component.status,
                    "code": component.code,
                }
                for name, component in self.components.items()
            },
        }


def _check_model_configuration() -> None:
    config.require_model_api_key()
    parsed_url = urlsplit(config.MODEL_BASE_URL)
    if (
        parsed_url.scheme not in {"http", "https"}
        or not parsed_url.hostname
        or parsed_url.username is not None
        or parsed_url.password is not None
    ):
        raise ConfigurationError("model configuration is invalid")


def _check_database() -> None:
    with get_engine().connect() as connection:
        if connection.execute(text("SELECT 1")).scalar_one() != 1:
            raise RuntimeError("database check failed")


def _check_migration() -> None:
    heads = tuple(
        ScriptDirectory.from_config(_alembic_config()).get_heads()
    )
    if len(heads) != 1:
        raise RuntimeError("migration head is not unique")
    with get_engine().connect() as connection:
        current = tuple(
            MigrationContext.configure(connection).get_current_heads()
        )
    if current != heads:
        raise RuntimeError("database migration is not current")


def _check_redis() -> None:
    client = redis.Redis.from_url(
        config.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
        socket_timeout=config.REDIS_SOCKET_TIMEOUT_SECONDS,
    )
    try:
        if client.ping() is not True:
            raise RuntimeError("Redis check failed")
    finally:
        client.close()


def _check_managed_files() -> None:
    root = global_managed_file_service._storage_root(create=True)
    with tempfile.TemporaryFile(dir=root):
        pass


def _component_result(
    component: str,
    check: Callable[[], None],
) -> ComponentReadiness:
    try:
        check()
    except Exception:
        return ComponentReadiness(
            status="unavailable",
            code=_FAILURE_CODES[component],
        )
    return ComponentReadiness(status=READY, code=READY)


def check_readiness() -> ReadinessResult:
    """Run fresh, shallow checks without model or search calls."""
    checks = (
        (MODEL_COMPONENT, _check_model_configuration),
        (DATABASE_COMPONENT, _check_database),
        (MIGRATION_COMPONENT, _check_migration),
        (REDIS_COMPONENT, _check_redis),
        (MANAGED_FILES_COMPONENT, _check_managed_files),
    )
    return ReadinessResult(
        components={
            component: _component_result(component, check)
            for component, check in checks
        }
    )


async def check_readiness_async() -> ReadinessResult:
    """Keep blocking infrastructure probes off the application event loop."""
    return await anyio.to_thread.run_sync(check_readiness)


def main() -> int:
    """Return only a process status for local container healthchecks."""
    return 0 if check_readiness().ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
