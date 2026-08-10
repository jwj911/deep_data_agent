import uuid

from sqlalchemy.orm import Session

from data_agent.models.session import Message
from data_agent.models.session import Session as ChatSession
from data_agent.models.user import utc_now


class SessionService:
    """Service for managing chat sessions"""
    
    def create_session(
        self,
        db: Session,
        user_id: int,
        title: str,
    ) -> ChatSession:
        """Create a new chat session"""
        session_id = str(uuid.uuid4())
        db_session = ChatSession(
            user_id=user_id,
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
        user_id: int,
    ) -> list[ChatSession]:
        """Get all sessions for a user"""
        return (
            db.query(ChatSession)
            .filter(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .all()
        )
    
    def get_session(
        self,
        db: Session,
        session_id: str,
        user_id: int,
    ) -> ChatSession | None:
        """Get a session owned by a user."""
        return (
            db.query(ChatSession)
            .filter(
                ChatSession.session_id == session_id,
                ChatSession.user_id == user_id,
            )
            .first()
        )
    
    def add_message(
        self,
        db: Session,
        session_id: str,
        user_id: int,
        role: str,
        content: str,
    ) -> Message:
        """Add a message to a session"""
        session = self.get_session(db, session_id, user_id)
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
        user_id: int,
    ) -> list[Message]:
        """Get all messages for a session"""
        session = self.get_session(db, session_id, user_id)
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
        user_id: int,
    ) -> bool:
        """Delete a session"""
        session = self.get_session(db, session_id, user_id)
        if not session:
            return False
        
        db.query(Message).filter(Message.session_id == session.id).delete()
        
        db.delete(session)
        db.commit()
        return True

# Create a global session service instance
global_session_service = SessionService()
