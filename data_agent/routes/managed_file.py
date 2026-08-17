from datetime import datetime

from fastapi import (APIRouter, Depends, File, HTTPException, Response,
                     UploadFile, status)
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from data_agent.config.database import get_db
from data_agent.models.managed_file import ManagedFile
from data_agent.models.user import User
from data_agent.services.auth_service import require_auth_configured
from data_agent.services.authorization_service import (Permission,
                                                       require_permission)
from data_agent.services.managed_file_service import (
    ManagedFileError, global_managed_file_service)

router = APIRouter(dependencies=[Depends(require_auth_configured)])


class ManagedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: str
    original_name: str
    media_type: str
    size_bytes: int
    created_at: datetime
    expires_at: datetime


class ManagedFileAnalysisResponse(ManagedFileResponse):
    content: str
    content_truncated: bool


def _file_error(exc: ManagedFileError) -> HTTPException:
    messages = {
        "invalid_file_id": "Invalid file ID",
        "invalid_filename": "Invalid filename",
        "unsupported_file_type": "Unsupported file type",
        "invalid_file_content": "Invalid file content",
        "unsafe_csv_formula": "CSV formulas are not allowed",
        "file_too_large": "File exceeds the configured limit",
        "file_batch_too_large": "File batch exceeds the configured limit",
        "file_count_exceeded": "Too many files in one upload",
        "file_quota_exceeded": "File quota exceeded",
        "duplicate_file": "File content already exists",
        "file_storage_invalid": "Managed file is unavailable",
        "file_storage_unavailable": "Managed file storage is unavailable",
        "file_database_error": "Managed file metadata is unavailable",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": messages.get(exc.code, "File operation failed"),
        },
    )


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "code": "file_not_found",
            "message": "File not found",
        },
    )


def _response(record: ManagedFile) -> ManagedFileResponse:
    return ManagedFileResponse.model_validate(record)


@router.post(
    "",
    response_model=list[ManagedFileResponse],
    status_code=status.HTTP_201_CREATED,
)
async def upload_files(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.FILE_WRITE_OWN)
    ),
):
    """Upload one owner-scoped batch into managed storage."""
    try:
        records = await global_managed_file_service.upload_files(
            db,
            current_user,
            files,
        )
    except ManagedFileError as exc:
        raise _file_error(exc) from exc
    return [_response(record) for record in records]


@router.get("", response_model=list[ManagedFileResponse])
async def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.FILE_READ_OWN)
    ),
):
    """List active files owned by the current user."""
    try:
        records = global_managed_file_service.list_files(db, current_user)
    except ManagedFileError as exc:
        raise _file_error(exc) from exc
    return [_response(record) for record in records]


@router.get(
    "/{file_id}/analysis",
    response_model=ManagedFileAnalysisResponse,
)
async def analyze_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.FILE_READ_OWN)
    ),
):
    """Return one bounded text analysis for an owned file."""
    try:
        result = global_managed_file_service.analyze_file(
            db,
            current_user,
            file_id,
        )
    except ManagedFileError as exc:
        raise _file_error(exc) from exc
    if result is None:
        raise _not_found()
    return ManagedFileAnalysisResponse(
        file_id=str(result["file_id"]),
        original_name=str(result["filename"]),
        media_type=str(result["media_type"]),
        size_bytes=int(result["size_bytes"]),
        created_at=result["created_at"],
        expires_at=result["expires_at"],
        content=str(result["content"]),
        content_truncated=bool(result["content_truncated"]),
    )


@router.get("/{file_id}", response_model=ManagedFileResponse)
async def get_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.FILE_READ_OWN)
    ),
):
    """Return safe metadata for one owned file."""
    try:
        record = global_managed_file_service.get_file(
            db,
            current_user,
            file_id,
        )
    except ManagedFileError as exc:
        raise _file_error(exc) from exc
    if record is None:
        raise _not_found()
    return _response(record)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_permission(Permission.FILE_DELETE_OWN)
    ),
):
    """Delete owned metadata and managed bytes."""
    try:
        deleted = global_managed_file_service.delete_file(
            db,
            current_user,
            file_id,
        )
    except ManagedFileError as exc:
        raise _file_error(exc) from exc
    if not deleted:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
