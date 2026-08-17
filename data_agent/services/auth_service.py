from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from data_agent.config.config import ConfigurationError, config
from data_agent.config.database import get_db
from data_agent.models.user import User


class UserAlreadyExistsError(Exception):
    """Raised when a user with the same username or email already exists."""


class InvalidCredentialsError(ValueError):
    """Raised when first-party credentials cannot identify an active user."""


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/auth/login",
    auto_error=False,
)


def _auth_error(
    status_code: int,
    code: str,
    message: str,
) -> HTTPException:
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def require_auth_configured() -> str:
    """Require valid JWT configuration without affecting health checks."""
    try:
        return config.require_jwt_secret_key()
    except ConfigurationError as exc:
        raise _auth_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "auth_not_configured",
            "Authentication is not configured",
        ) from exc

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Get password hash"""
    return pwd_context.hash(password)


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed access token for an immutable user ID."""
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    secret_key = require_auth_configured()
    lifetime = expires_delta or timedelta(
        minutes=config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + lifetime
    return jwt.encode(
        {"sub": str(user_id), "exp": expire},
        secret_key,
        algorithm=ALGORITHM,
    )


def decode_access_token_subject(token: str) -> int:
    """Validate an access token and return its positive user ID."""
    secret_key = config.require_jwt_secret_key()
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=[ALGORITHM],
            options={"verify_exp": True, "require_exp": True},
        )
        subject = payload.get("sub")
        if (
            not isinstance(subject, str)
            or not subject.isdigit()
            or int(subject) <= 0
            or str(int(subject)) != subject
        ):
            raise JWTError("invalid subject")
        return int(subject)
    except JWTError as exc:
        raise InvalidCredentialsError("invalid credentials") from exc


def bearer_token_from_header(authorization: str | None) -> str:
    """Extract one non-empty Bearer token without accepting other schemes."""
    if not isinstance(authorization, str):
        raise InvalidCredentialsError("invalid credentials")
    scheme, separator, token = authorization.strip().partition(" ")
    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
        or " " in token.strip()
    ):
        raise InvalidCredentialsError("invalid credentials")
    return token.strip()


def get_user_for_access_token(db: Session, token: str) -> User:
    """Resolve a valid token to a current database user."""
    user_id = decode_access_token_subject(token)
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise InvalidCredentialsError("invalid credentials")
    return user


def get_user_for_authorization_header(
    db: Session,
    authorization: str | None,
) -> User:
    """Resolve a standard Authorization header to a current user."""
    return get_user_for_access_token(
        db,
        bearer_token_from_header(authorization),
    )


def decode_access_token(token: str) -> int:
    """FastAPI-compatible access-token decoder."""
    require_auth_configured()
    try:
        return decode_access_token_subject(token)
    except InvalidCredentialsError as exc:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Could not validate credentials",
        ) from exc


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Load the authenticated user without exposing token failure details."""
    require_auth_configured()
    if not token:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Could not validate credentials",
        )
    try:
        return get_user_for_access_token(db, token)
    except InvalidCredentialsError as exc:
        raise _auth_error(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_credentials",
            "Could not validate credentials",
        ) from exc

def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Get user by username"""
    return db.query(User).filter(User.username == username).first()

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Get user by email"""
    return db.query(User).filter(User.email == email).first()

def create_user(db: Session, username: str, email: str, password: str) -> User:
    """Create new user"""
    hashed_password = get_password_hash(password)
    db_user = User(
        username=username,
        email=email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise UserAlreadyExistsError("user already exists") from exc
    db.refresh(db_user)
    return db_user
