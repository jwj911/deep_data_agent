from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class UserRole(StrEnum):
    """Fixed application roles."""

    USER = "user"
    ADMIN = "admin"


def utc_now() -> datetime:
    """Return naive UTC for the existing timezone-less DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


class User(Base):
    """User model"""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'admin')",
            name="ck_users_role",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(
        String(20),
        nullable=False,
        default=UserRole.USER.value,
        server_default=UserRole.USER.value,
    )
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
