from sqlalchemy import (BigInteger, CheckConstraint, Column, DateTime,
                        ForeignKey, Integer, String, UniqueConstraint)
from sqlalchemy.orm import relationship

from data_agent.models.user import Base, utc_now


class ManagedFile(Base):
    """Owner-scoped metadata for a file stored under the managed root."""

    __tablename__ = "managed_files"
    __table_args__ = (
        CheckConstraint(
            "size_bytes > 0",
            name="ck_managed_files_size_positive",
        ),
        CheckConstraint(
            "media_type IN "
            "('text/plain', 'text/markdown', 'text/csv', "
            "'application/json')",
            name="ck_managed_files_media_type",
        ),
        UniqueConstraint(
            "user_id",
            "sha256",
            name="uq_managed_files_user_sha256",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(
        String(36),
        unique=True,
        index=True,
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        index=True,
        nullable=False,
    )
    original_name = Column(String(255), nullable=False)
    media_type = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    sha256 = Column(String(64), nullable=False)
    storage_key = Column(String(255), unique=True, nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", backref="managed_files")
