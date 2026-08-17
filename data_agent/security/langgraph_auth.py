"""First-party authentication and tenant authorization for LangGraph."""

from typing import Any

from langgraph_sdk import Auth

from data_agent.config.config import ConfigurationError
from data_agent.config.database import get_session_factory
from data_agent.services.auth_service import (
    InvalidCredentialsError, get_user_for_authorization_header)
from data_agent.services.authorization_service import ROLE_PERMISSIONS

AGENT_GRAPH_ID = "agent"

auth = Auth()


def _http_error(status_code: int, detail: str) -> Exception:
    return Auth.exceptions.HTTPException(
        status_code=status_code,
        detail=detail,
    )


@auth.authenticate
def authenticate(
    authorization: str | None,
) -> Auth.types.MinimalUserDict:
    """Validate a first-party JWT and load the current database role."""
    try:
        with get_session_factory()() as db:
            user = get_user_for_authorization_header(db, authorization)
            permissions = sorted(
                permission.value
                for permission in ROLE_PERMISSIONS.get(
                    user.role,
                    frozenset(),
                )
            )
            return {
                "identity": str(user.id),
                "is_authenticated": True,
                "permissions": permissions,
            }
    except ConfigurationError as exc:
        raise _http_error(
            503,
            "Authentication is not configured",
        ) from exc
    except InvalidCredentialsError as exc:
        raise _http_error(401, "Invalid credentials") from exc


@auth.on
async def deny_unhandled(
    ctx: Auth.types.AuthContext,
    value: Any,
) -> bool:
    """Deny resources and actions that are not explicitly allowed."""
    return False


@auth.on.threads
async def authorize_thread_owner(
    ctx: Auth.types.AuthContext,
    value: dict[str, Any],
) -> dict[str, str]:
    """Force thread and run operations into the caller's owner scope."""
    owner = ctx.user.identity
    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        value["metadata"] = metadata
    metadata["owner"] = owner
    return {"owner": owner}


@auth.on.assistants.search
async def allow_agent_assistant_search(
    ctx: Auth.types.AuthContext,
    value: dict[str, Any],
) -> dict[str, str]:
    """Limit assistant discovery to the configured application graph."""
    value["graph_id"] = AGENT_GRAPH_ID
    return {"graph_id": AGENT_GRAPH_ID}


@auth.on.assistants.read
async def allow_agent_assistant_read(
    ctx: Auth.types.AuthContext,
    value: dict[str, Any],
) -> dict[str, str]:
    """Allow read-only access to the preconfigured application assistant."""
    return {"graph_id": AGENT_GRAPH_ID}
