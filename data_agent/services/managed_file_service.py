import csv
import hashlib
import io
import json
import os
import stat
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path, PurePosixPath
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from data_agent.config.config import config
from data_agent.config.logger import file_logger
from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import User, utc_now
from data_agent.observability.events import emit_event
from data_agent.services.authorization_service import (
    AuthorizationDeniedError, Permission, ensure_permission)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_READ_CHUNK_BYTES = 64 * 1024
_FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class FileTypeSpec:
    media_type: str
    declared_types: frozenset[str]


FILE_TYPES: dict[str, FileTypeSpec] = {
    ".txt": FileTypeSpec(
        "text/plain",
        frozenset({"text/plain"}),
    ),
    ".md": FileTypeSpec(
        "text/markdown",
        frozenset({"text/markdown", "text/plain"}),
    ),
    ".csv": FileTypeSpec(
        "text/csv",
        frozenset({"text/csv", "application/vnd.ms-excel"}),
    ),
    ".json": FileTypeSpec(
        "application/json",
        frozenset({"application/json", "text/json", "text/plain"}),
    ),
}
_UNSPECIFIED_MEDIA_TYPES = frozenset({"", "application/octet-stream"})


class ManagedFileError(RuntimeError):
    """Stable file error that is safe to translate at API boundaries."""

    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class PreparedFile:
    original_name: str
    suffix: str
    media_type: str
    content: bytes
    sha256: str


@dataclass(frozen=True)
class StoredFileRef:
    file_id: str
    user_id: int
    original_name: str
    storage_key: str


def normalize_file_id(value: str) -> str:
    """Require the canonical string representation of one UUID."""
    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ManagedFileError("invalid_file_id", 422) from exc
    normalized = str(parsed)
    if value != normalized:
        raise ManagedFileError("invalid_file_id", 422)
    return normalized


def _normalize_filename(value: str | None) -> tuple[str, str, FileTypeSpec]:
    if not isinstance(value, str):
        raise ManagedFileError("invalid_filename", 400)
    normalized = unicodedata.normalize("NFC", value).strip()
    if (
        not normalized
        or len(normalized) > 255
        or "/" in normalized
        or "\\" in normalized
        or any(ord(char) < 32 or ord(char) == 127 for char in normalized)
    ):
        raise ManagedFileError("invalid_filename", 400)
    suffix = Path(normalized).suffix.lower()
    stem = normalized[: -len(suffix)] if suffix else normalized
    if not suffix or "." in stem:
        raise ManagedFileError("unsupported_file_type", 400)
    spec = FILE_TYPES.get(suffix)
    if spec is None:
        raise ManagedFileError("unsupported_file_type", 400)
    return normalized, suffix, spec


def _validate_declared_type(
    content_type: str | None,
    spec: FileTypeSpec,
) -> None:
    declared = (content_type or "").partition(";")[0].strip().lower()
    if (
        declared not in _UNSPECIFIED_MEDIA_TYPES
        and declared not in spec.declared_types
    ):
        raise ManagedFileError("unsupported_file_type", 400)


def _decode_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ManagedFileError("invalid_file_content", 400) from exc
    if "\x00" in text:
        raise ManagedFileError("invalid_file_content", 400)
    return text


def _validate_structured_content(
    suffix: str,
    text: str,
) -> None:
    if suffix == ".json":
        try:
            json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ManagedFileError("invalid_file_content", 400) from exc
    elif suffix == ".csv":
        try:
            rows = csv.reader(io.StringIO(text, newline=""))
            for row in rows:
                if any(
                    cell.lstrip().startswith(_FORMULA_PREFIXES)
                    for cell in row
                ):
                    raise ManagedFileError("unsafe_csv_formula", 400)
        except csv.Error as exc:
            raise ManagedFileError("invalid_file_content", 400) from exc


async def _prepare_upload(upload: UploadFile) -> PreparedFile:
    name, suffix, spec = _normalize_filename(upload.filename)
    _validate_declared_type(upload.content_type, spec)
    content = bytearray()
    try:
        while chunk := await upload.read(_READ_CHUNK_BYTES):
            content.extend(chunk)
            if len(content) > config.FILE_UPLOAD_MAX_BYTES:
                raise ManagedFileError("file_too_large", 413)
    finally:
        await upload.close()
    if not content:
        raise ManagedFileError("invalid_file_content", 400)
    immutable_content = bytes(content)
    text = _decode_text(immutable_content)
    _validate_structured_content(suffix, text)
    return PreparedFile(
        original_name=name,
        suffix=suffix,
        media_type=spec.media_type,
        content=immutable_content,
        sha256=hashlib.sha256(immutable_content).hexdigest(),
    )


class ManagedFileService:
    """Persist and resolve owner-scoped files without exposing paths."""

    @staticmethod
    def _actor_id(actor: User) -> int:
        actor_id = getattr(actor, "id", None)
        if (
            not isinstance(actor_id, int)
            or isinstance(actor_id, bool)
            or actor_id <= 0
        ):
            raise AuthorizationDeniedError("permission denied")
        return actor_id

    @staticmethod
    def _storage_root(*, create: bool) -> Path:
        root = Path(config.FILE_STORAGE_ROOT).expanduser()
        if not root.is_absolute():
            root = _PROJECT_ROOT / root
        if create:
            root.mkdir(parents=True, exist_ok=True)
        try:
            resolved = root.resolve(strict=True)
        except OSError as exc:
            raise ManagedFileError("file_storage_unavailable", 503) from exc
        if not resolved.is_dir():
            raise ManagedFileError("file_storage_unavailable", 503)
        return resolved

    @classmethod
    def _user_directory(cls, user_id: int) -> Path:
        root = cls._storage_root(create=True)
        directory = root / str(user_id)
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.is_symlink() or directory.resolve() != directory:
                raise ManagedFileError("file_storage_invalid", 503)
        except OSError as exc:
            raise ManagedFileError("file_storage_unavailable", 503) from exc
        return directory

    @classmethod
    def _record_path(
        cls,
        record: ManagedFile,
        *,
        require_exists: bool,
    ) -> Path:
        root = cls._storage_root(create=False)
        key = PurePosixPath(record.storage_key)
        suffix = Path(record.original_name).suffix.lower()
        expected_name = f"{record.file_id}{suffix}"
        if (
            key.is_absolute()
            or key.parts != (str(record.user_id), expected_name)
        ):
            raise ManagedFileError("file_storage_invalid", 503)
        candidate = root.joinpath(*key.parts)
        parent = candidate.parent
        try:
            if parent.is_symlink() or parent.resolve(strict=True) != parent:
                raise ManagedFileError("file_storage_invalid", 503)
            if require_exists:
                candidate.lstat()
        except FileNotFoundError as exc:
            raise ManagedFileError("file_storage_invalid", 503) from exc
        except OSError as exc:
            raise ManagedFileError("file_storage_unavailable", 503) from exc
        if candidate.is_symlink() or (
            require_exists and not candidate.is_file()
        ):
            raise ManagedFileError("file_storage_invalid", 503)
        return candidate

    @classmethod
    def _write_file(
        cls,
        user_id: int,
        file_id: str,
        suffix: str,
        content: bytes,
    ) -> tuple[str, Path]:
        directory = cls._user_directory(user_id)
        final_path = directory / f"{file_id}{suffix}"
        temporary_path = directory / f".{file_id}.upload"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor: int | None = None
        try:
            descriptor = os.open(temporary_path, flags, 0o600)
            with os.fdopen(descriptor, "wb") as file:
                descriptor = None
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, final_path)
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise ManagedFileError("file_storage_unavailable", 503) from exc
        return f"{user_id}/{final_path.name}", final_path

    @classmethod
    def _unlink_record(
        cls,
        record: ManagedFile | StoredFileRef,
    ) -> None:
        try:
            path = cls._record_path(record, require_exists=False)
            path.unlink(missing_ok=True)
        except (ManagedFileError, OSError):
            file_logger.warning(
                "file.cleanup.failed",
                extra={
                    "event_name": "file.cleanup.failed",
                    "event_fields": {
                        "operation": "cleanup",
                        "outcome": "error",
                        "error_code": "file_cleanup_failed",
                    },
                },
            )

    @staticmethod
    def _storage_ref(record: ManagedFile) -> StoredFileRef:
        return StoredFileRef(
            file_id=record.file_id,
            user_id=record.user_id,
            original_name=record.original_name,
            storage_key=record.storage_key,
        )

    def cleanup_expired(self, db: Session, actor: User) -> int:
        """Delete expired metadata first, then remove inaccessible bytes."""
        actor_id = self._actor_id(actor)
        expired = (
            db.query(ManagedFile)
            .filter(
                ManagedFile.user_id == actor_id,
                ManagedFile.expires_at <= utc_now(),
            )
            .all()
        )
        if not expired:
            return 0
        stored_refs = [self._storage_ref(record) for record in expired]
        for record in expired:
            db.delete(record)
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise ManagedFileError("file_database_error", 503) from exc
        for record in stored_refs:
            self._unlink_record(record)
        return len(expired)

    async def upload_files(
        self,
        db: Session,
        actor: User,
        uploads: list[UploadFile],
    ) -> list[ManagedFile]:
        """Validate and atomically persist one bounded file batch."""
        ensure_permission(actor, Permission.FILE_WRITE_OWN)
        actor_id = self._actor_id(actor)
        started_at = perf_counter()
        emit_event(
            file_logger,
            "file.upload.started",
            operation="upload",
            outcome="started",
        )
        if not uploads or len(uploads) > config.FILE_UPLOAD_BATCH_MAX_COUNT:
            raise ManagedFileError("file_count_exceeded", 413)

        prepared: list[PreparedFile] = []
        batch_bytes = 0
        try:
            for upload in uploads:
                item = await _prepare_upload(upload)
                batch_bytes += len(item.content)
                if batch_bytes > config.FILE_UPLOAD_BATCH_MAX_BYTES:
                    raise ManagedFileError("file_batch_too_large", 413)
                prepared.append(item)
            hashes = [item.sha256 for item in prepared]
            if len(set(hashes)) != len(hashes):
                raise ManagedFileError("duplicate_file", 409)

            self.cleanup_expired(db, actor)
            locked_user = (
                db.query(User)
                .filter(User.id == actor_id)
                .with_for_update()
                .one_or_none()
            )
            if locked_user is None:
                raise AuthorizationDeniedError("permission denied")

            count, used_bytes = (
                db.query(
                    func.count(ManagedFile.id),
                    func.coalesce(func.sum(ManagedFile.size_bytes), 0),
                )
                .filter(ManagedFile.user_id == actor_id)
                .one()
            )
            if count + len(prepared) > config.FILE_USER_MAX_COUNT:
                raise ManagedFileError("file_quota_exceeded", 413)
            if used_bytes + batch_bytes > config.FILE_USER_QUOTA_BYTES:
                raise ManagedFileError("file_quota_exceeded", 413)
            duplicate = (
                db.query(ManagedFile.id)
                .filter(
                    ManagedFile.user_id == actor_id,
                    ManagedFile.sha256.in_(hashes),
                )
                .first()
            )
            if duplicate is not None:
                raise ManagedFileError("duplicate_file", 409)

            expires_at = utc_now() + timedelta(
                hours=config.FILE_RETENTION_HOURS
            )
            records: list[ManagedFile] = []
            written_paths: list[Path] = []
            try:
                for item in prepared:
                    file_id = str(uuid4())
                    storage_key, path = self._write_file(
                        actor_id,
                        file_id,
                        item.suffix,
                        item.content,
                    )
                    written_paths.append(path)
                    records.append(
                        ManagedFile(
                            file_id=file_id,
                            user_id=actor_id,
                            original_name=item.original_name,
                            media_type=item.media_type,
                            size_bytes=len(item.content),
                            sha256=item.sha256,
                            storage_key=storage_key,
                            expires_at=expires_at,
                        )
                    )
                db.add_all(records)
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                for path in written_paths:
                    path.unlink(missing_ok=True)
                raise ManagedFileError("duplicate_file", 409) from exc
            except ManagedFileError:
                db.rollback()
                for path in written_paths:
                    path.unlink(missing_ok=True)
                raise
            except SQLAlchemyError as exc:
                db.rollback()
                for path in written_paths:
                    path.unlink(missing_ok=True)
                raise ManagedFileError("file_database_error", 503) from exc
            except OSError as exc:
                db.rollback()
                for path in written_paths:
                    path.unlink(missing_ok=True)
                raise ManagedFileError("file_storage_unavailable", 503) from exc
            for record in records:
                db.refresh(record)
            emit_event(
                file_logger,
                "file.upload.completed",
                operation="upload",
                outcome="success",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            return records
        except (ManagedFileError, AuthorizationDeniedError):
            db.rollback()
            for upload in uploads:
                await upload.close()
            emit_event(
                file_logger,
                "file.upload.rejected",
                operation="upload",
                outcome="rejected",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            raise
        except Exception as exc:
            db.rollback()
            for upload in uploads:
                await upload.close()
            emit_event(
                file_logger,
                "file.upload.failed",
                operation="upload",
                outcome="error",
                error_code="file_upload_error",
                duration_ms=(perf_counter() - started_at) * 1000,
            )
            raise ManagedFileError("file_storage_unavailable", 503) from exc

    def list_files(self, db: Session, actor: User) -> list[ManagedFile]:
        ensure_permission(actor, Permission.FILE_READ_OWN)
        actor_id = self._actor_id(actor)
        self.cleanup_expired(db, actor)
        return (
            db.query(ManagedFile)
            .filter(
                ManagedFile.user_id == actor_id,
                ManagedFile.expires_at > utc_now(),
            )
            .order_by(ManagedFile.created_at.desc(), ManagedFile.id.desc())
            .all()
        )

    def get_file(
        self,
        db: Session,
        actor: User,
        file_id: str,
    ) -> ManagedFile | None:
        ensure_permission(actor, Permission.FILE_READ_OWN)
        actor_id = self._actor_id(actor)
        normalized_id = normalize_file_id(file_id)
        return (
            db.query(ManagedFile)
            .filter(
                ManagedFile.file_id == normalized_id,
                ManagedFile.user_id == actor_id,
                ManagedFile.expires_at > utc_now(),
            )
            .first()
        )

    def delete_file(
        self,
        db: Session,
        actor: User,
        file_id: str,
    ) -> bool:
        ensure_permission(actor, Permission.FILE_DELETE_OWN)
        record = self.get_file(db, actor, file_id)
        if record is None:
            self.cleanup_expired(db, actor)
            return False
        stored_ref = self._storage_ref(record)
        db.delete(record)
        try:
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise ManagedFileError("file_database_error", 503) from exc
        self._unlink_record(stored_ref)
        emit_event(
            file_logger,
            "file.delete.completed",
            operation="delete",
            outcome="success",
        )
        return True

    def _read_bytes(self, record: ManagedFile) -> bytes:
        if (
            record.size_bytes <= 0
            or record.size_bytes > config.FILE_UPLOAD_MAX_BYTES
        ):
            raise ManagedFileError("file_storage_invalid", 503)
        path = self._record_path(record, require_exists=True)
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(path, flags)
            with os.fdopen(descriptor, "rb") as file:
                info = os.fstat(file.fileno())
                if not stat.S_ISREG(info.st_mode):
                    raise ManagedFileError("file_storage_invalid", 503)
                content = file.read(config.FILE_UPLOAD_MAX_BYTES + 1)
        except ManagedFileError:
            raise
        except OSError as exc:
            raise ManagedFileError("file_storage_unavailable", 503) from exc
        if (
            len(content) != record.size_bytes
            or len(content) > config.FILE_UPLOAD_MAX_BYTES
            or hashlib.sha256(content).hexdigest() != record.sha256
        ):
            raise ManagedFileError("file_storage_invalid", 503)
        return content

    def analyze_file(
        self,
        db: Session,
        actor: User,
        file_id: str,
    ) -> dict[str, object] | None:
        ensure_permission(actor, Permission.FILE_READ_OWN)
        started_at = perf_counter()
        record = self.get_file(db, actor, file_id)
        if record is None:
            self.cleanup_expired(db, actor)
            return None
        content = self._read_bytes(record)
        text = _decode_text(content)
        limit = config.FILE_ANALYSIS_MAX_CHARS
        emit_event(
            file_logger,
            "file.analysis.completed",
            operation="analyze",
            outcome="success",
            duration_ms=(perf_counter() - started_at) * 1000,
        )
        return {
            "file_id": record.file_id,
            "filename": record.original_name,
            "media_type": record.media_type,
            "size_bytes": record.size_bytes,
            "created_at": record.created_at,
            "content": text[:limit],
            "content_truncated": len(text) > limit,
            "expires_at": record.expires_at,
        }


global_managed_file_service = ManagedFileService()
