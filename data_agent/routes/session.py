from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from data_agent.config.database import get_db
from data_agent.models.user import User
from data_agent.services.auth_service import (get_current_user,
                                              require_auth_configured)
from data_agent.services.session_service import global_session_service

router = APIRouter(dependencies=[Depends(require_auth_configured)])

# Request models
class SessionCreate(BaseModel):
    title: str

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 255:
            raise ValueError("title must be between 1 and 255 characters")
        return normalized

class MessageCreate(BaseModel):
    role: str
    content: str

    @field_validator("role")
    @classmethod
    def _validate_role(cls, value: str) -> str:
        if value not in {"user", "assistant"}:
            raise ValueError("role must be 'user' or 'assistant'")
        return value

    @field_validator("content")
    @classmethod
    def _validate_content(cls, value: str) -> str:
        normalized = value.strip()
        if not 1 <= len(normalized) <= 20000:
            raise ValueError(
                "content must be between 1 and 20000 characters"
            )
        return normalized

# Response models
class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime

class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    title: str
    created_at: datetime
    updated_at: datetime

class SessionWithMessagesResponse(SessionResponse):
    messages: List[MessageResponse]

@router.post("/", response_model=SessionResponse)
async def create_session(
    session: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new chat session for the authenticated user."""
    return global_session_service.create_session(
        db, current_user.id, session.title
    )

@router.get("/", response_model=List[SessionResponse])
async def get_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all sessions owned by the authenticated user."""
    return global_session_service.get_sessions(db, current_user.id)

@router.get("/{session_id}", response_model=SessionWithMessagesResponse)
async def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a session with its messages, scoped to the current user."""
    session = global_session_service.get_session(
        db, session_id, current_user.id
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    messages = global_session_service.get_messages(
        db, session_id, current_user.id
    )
    return SessionWithMessagesResponse(
        id=session.id,
        session_id=session.session_id,
        title=session.title,
        created_at=session.created_at,
        updated_at=session.updated_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )

@router.post("/{session_id}/messages", response_model=MessageResponse)
async def add_message(
    session_id: str,
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a message to a session owned by the current user."""
    try:
        return global_session_service.add_message(
            db,
            session_id,
            current_user.id,
            message.role,
            message.content,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a session owned by the current user."""
    success = global_session_service.delete_session(
        db, session_id, current_user.id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    return {"message": "Session deleted successfully"}
