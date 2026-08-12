import hmac
import logging
from hashlib import sha256

from data_agent.config.config import config
from data_agent.config.logger import audit_logger
from data_agent.observability.events import emit_event


def audit_identity_ref(user_id: int) -> str:
    """Return a stable, non-reversible reference for an internal user ID."""
    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        raise ValueError("user_id must be a positive integer")
    secret = config.require_jwt_secret_key().encode("utf-8")
    return hmac.new(
        secret,
        f"user:{user_id}".encode("utf-8"),
        sha256,
    ).hexdigest()


def emit_audit_event(
    event_name: str,
    *,
    operation: str,
    outcome: str,
    actor_kind: str,
    actor_user_id: int | None = None,
    target_user_id: int | None = None,
    permission: str | None = None,
    decision: str | None = None,
    previous_role: str | None = None,
    role: str | None = None,
    event_count: int | None = None,
    tool_name: str | None = None,
    level: int = logging.INFO,
) -> None:
    """Emit a bounded audit event without accepting arbitrary payloads."""
    fields: dict[str, object] = {
        "operation": operation,
        "outcome": outcome,
        "actor_kind": actor_kind,
    }
    if actor_user_id is not None:
        fields["actor_ref"] = audit_identity_ref(actor_user_id)
    if target_user_id is not None:
        fields["target_ref"] = audit_identity_ref(target_user_id)
    if permission is not None:
        fields["permission"] = permission
    if decision is not None:
        fields["decision"] = decision
    if previous_role is not None:
        fields["previous_role"] = previous_role
    if role is not None:
        fields["role"] = role
    if event_count is not None:
        fields["event_count"] = event_count
    if tool_name is not None:
        fields["tool_name"] = tool_name

    emit_event(
        audit_logger,
        event_name,
        level=level,
        **fields,
    )
