from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, EmailStr, field_validator
from sqlalchemy.orm import Session

from data_agent.config.config import config
from data_agent.config.database import get_db
from data_agent.models.user import User, UserRole
from data_agent.services.auth_service import (UserAlreadyExistsError,
                                              create_access_token, create_user,
                                              get_current_user,
                                              get_user_by_email,
                                              get_user_by_username,
                                              require_auth_configured,
                                              verify_password)

router = APIRouter(dependencies=[Depends(require_auth_configured)])

# Request models
class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    email: EmailStr
    password: str

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        normalized = value.strip()
        if not 3 <= len(normalized) <= 50:
            raise ValueError(
                "username must be between 3 and 50 characters"
            )
        return normalized

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("password must be at least 8 characters")
        return value

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role: UserRole

class Token(BaseModel):
    access_token: str
    token_type: str
    expires_in: int

@router.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """Register new user"""
    # Reject known conflicts before attempting to persist the user.
    if get_user_by_username(db, user.username) or get_user_by_email(
        db, user.email
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "registration_conflict",
                "message": "Username or email is already registered",
            },
        )
    # Create new user, translating race conditions into a stable conflict.
    try:
        db_user = create_user(
            db, user.username, str(user.email), user.password
        )
    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "registration_conflict",
                "message": "Username or email is already registered",
            },
        )
    return db_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """Login user"""
    username = form_data.username.strip()
    user = get_user_by_username(db, username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_credentials",
                "message": "Incorrect username or password",
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Create access token
    expires_delta = timedelta(
        minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    access_token = create_access_token(
        user_id=user.id, expires_delta=expires_delta
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Return public fields for the authenticated user."""
    return current_user
