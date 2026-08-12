import uuid

from sqlalchemy.orm import Session

from data_agent.models.session import Message
from data_agent.models.session import Session as ChatSession
from data_agent.models.user import User, utc_now
from data_agent.services.authorization_service import (Permission,
                                                       ensure_permission)


class SessionService:
    """Service for managing chat sessions"""
    
    def create_session(
        self,
        db: Session,
        actor: User,
        title: str,
    ) -> ChatSession:
        """Create a new chat session"""
        ensure_permission(actor, Permission.SESSION_WRITE_OWN)
        session_id = str(uuid.uuid4())
        db_session = ChatSession(
            user_id=actor.id,
            session_id=session_id,
            title=title
        )
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
        return db_session
    
    def get_sessions(
        self,
        db: Session,
        actor: User,
    ) -> list[ChatSession]:
        """Get all sessions for a user"""
        ensure_permission(actor, Permission.SESSION_READ_OWN)
        return (
            db.query(ChatSession)
            .filter(ChatSession.user_id == actor.id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )
    
    def get_session(
        self,
        db: Session,
        session_id: str,
        actor: User,
    ) -> ChatSession | None:
        """Get a session owned by a user."""
        ensure_permission(actor, Permission.SESSION_READ_OWN)
        return (
            db.query(ChatSession)
            .filter(
                ChatSession.session_id == session_id,
                ChatSession.user_id == actor.id,
            )
            .first()
        )
    
    def add_message(
        self,
        db: Session,
        session_id: str,
        actor: User,
        role: str,
        content: str,
    ) -> Message:
        """Add a message to a session"""
        ensure_permission(actor, Permission.SESSION_WRITE_OWN)
        session = self.get_session(db, session_id, actor)
        if not session:
            raise ValueError("Session not found")
        
        message = Message(
            session_id=session.id,
            role=role,
            content=content,
        )
        db.add(message)
        
        # Keep session ordering current when a message is added.
        session.updated_at = utc_now()
        
        db.commit()
        db.refresh(message)
        return message
    
    def get_messages(
        self,
        db: Session,
        session_id: str,
        actor: User,
    ) -> list[Message]:
        """Get all messages for a session"""
        ensure_permission(actor, Permission.SESSION_READ_OWN)
        session = self.get_session(db, session_id, actor)
        if not session:
            raise ValueError("Session not found")
        
        return (
            db.query(Message)
            .filter(Message.session_id == session.id)
            .order_by(Message.created_at)
            .all()
        )
    
    def delete_session(
        self,
        db: Session,
        session_id: str,
        actor: User,
    ) -> bool:
        """Delete a session"""
        ensure_permission(actor, Permission.SESSION_DELETE_OWN)
        session = self.get_session(db, session_id, actor)
        if not session:
            return False
        
        db.query(Message).filter(Message.session_id == session.id).delete()
        
        db.delete(session)
        db.commit()
        return True

# Create a global session service instance
global_session_service = SessionService()
