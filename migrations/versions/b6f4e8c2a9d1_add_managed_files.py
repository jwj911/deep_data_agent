"""add managed files

Revision ID: b6f4e8c2a9d1
Revises: 8f3c1b7a2d4e
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b6f4e8c2a9d1"
down_revision: Union[str, None] = "8f3c1b7a2d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "managed_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "size_bytes > 0",
            name="ck_managed_files_size_positive",
        ),
        sa.CheckConstraint(
            "media_type IN "
            "('text/plain', 'text/markdown', 'text/csv', "
            "'application/json')",
            name="ck_managed_files_media_type",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "sha256",
            name="uq_managed_files_user_sha256",
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(
        op.f("ix_managed_files_file_id"),
        "managed_files",
        ["file_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_managed_files_id"),
        "managed_files",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_managed_files_user_id"),
        "managed_files",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_managed_files_user_id"),
        table_name="managed_files",
    )
    op.drop_index(
        op.f("ix_managed_files_id"),
        table_name="managed_files",
    )
    op.drop_index(
        op.f("ix_managed_files_file_id"),
        table_name="managed_files",
    )
    op.drop_table("managed_files")
