import argparse
import sys
from collections.abc import Sequence

from data_agent.config.config import ConfigurationError, config
from data_agent.config.database import get_session_factory, init_db
from data_agent.models.user import User, UserRole
from data_agent.observability.audit import emit_audit_event


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "Invalid administrator bootstrap arguments.\n")


def _positive_user_id(value: str) -> int:
    try:
        user_id = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "user ID must be a positive integer"
        ) from exc
    if user_id <= 0:
        raise argparse.ArgumentTypeError(
            "user ID must be a positive integer"
        )
    return user_id


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(
        description="Promote one existing user to the administrator role.",
    )
    parser.add_argument(
        "--user-id",
        required=True,
        type=_positive_user_id,
        help="Positive internal ID returned by the current-user endpoint.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    db = None
    try:
        config.require_jwt_secret_key()
        init_db()
        db = get_session_factory()()
        user = db.query(User).filter(User.id == args.user_id).first()
        if user is None:
            sys.stderr.write("Unable to activate administrator role.\n")
            return 3

        previous_role = user.role
        if previous_role != UserRole.ADMIN.value:
            user.role = UserRole.ADMIN.value
            db.commit()
            db.refresh(user)

        emit_audit_event(
            "admin.role.bootstrap",
            operation="users.role_bootstrap",
            outcome="success",
            actor_kind="system",
            target_user_id=user.id,
            previous_role=previous_role,
            role=UserRole.ADMIN.value,
        )
    except ConfigurationError:
        if db is not None:
            db.rollback()
        sys.stderr.write("Administrator bootstrap is not configured.\n")
        return 2
    except Exception:
        if db is not None:
            db.rollback()
        sys.stderr.write("Unable to activate administrator role.\n")
        return 3
    finally:
        if db is not None:
            db.close()

    sys.stdout.write("Administrator role is active.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
