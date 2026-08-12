"""add user role

Revision ID: 8f3c1b7a2d4e
Revises: 4e43e097f22b
Create Date: 2026-08-12 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f3c1b7a2d4e"
down_revision: Union[str, None] = "4e43e097f22b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_CHECK_NAME = "ck_users_role"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            server_default="user",
            nullable=True,
        ),
    )
    users = sa.table("users", sa.column("role", sa.String(length=20)))
    op.execute(users.update().where(users.c.role.is_(None)).values(role="user"))

    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "role",
            existing_type=sa.String(length=20),
            existing_server_default="user",
            nullable=False,
        )
        batch_op.create_check_constraint(
            _ROLE_CHECK_NAME,
            "role IN ('user', 'admin')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint(_ROLE_CHECK_NAME, type_="check")
        batch_op.drop_column("role")
