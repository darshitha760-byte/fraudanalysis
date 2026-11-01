"""
Security utilities for authentication, password hashing, and JWT token management.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import HTTPException, status, Depends, Header
from app.core.config import get_settings
from app.db.database import from_bson, get_db


# Initialize password hasher with Argon2
ph = PasswordHasher()
settings = get_settings()


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2.

    Args:
        password: The plain text password to hash

    Returns:
        The hashed password string
    """
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a password against its hash using Argon2.

    Args:
        password: The plain text password to verify
        password_hash: The hashed password from the database

    Returns:
        True if password matches, False otherwise
    """
    try:
        ph.verify(password_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError):
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary containing claims to encode in the token (should include 'sub' for user ID)
        expires_delta: Optional custom expiration time, defaults to JWT_EXPIRATION_HOURS from config

    Returns:
        The encoded JWT token
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            hours=settings.jwt_expiration_hours
        )

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.secret_key,
        algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT token to decode

    Returns:
        Dictionary containing the decoded token payload

    Raises:
        HTTPException: If token is invalid, expired, or signature doesn't match
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_id_from_token(token: str) -> int:
    """
    Extract user ID from a valid JWT token.

    Args:
        token: The JWT token

    Returns:
        The user ID from the 'sub' claim

    Raises:
        HTTPException: If token is invalid or doesn't contain 'sub'
    """
    payload = decode_token(token)
    user_id: int = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )
    return int(user_id)


def get_user_role_from_token(token: str) -> str:
    """
    Extract user role from a valid JWT token.

    Args:
        token: The JWT token

    Returns:
        The user role from the 'role' claim
    """
    payload = decode_token(token)
    return payload.get("role", "analyst")


async def get_current_user(
    authorization: str = Header(None),
    db = Depends(get_db)
):
    """
    Dependency function to get current authenticated user from JWT token.

    This should be used as a dependency in FastAPI endpoints to require authentication.
    Example:
        @router.get("/protected")
        async def protected_endpoint(current_user = Depends(get_current_user)):
            return {"user_id": current_user.id}

    Args:
        authorization: Authorization header with Bearer token
        db: Database session (injected by FastAPI)

    Returns:
        The authenticated User object

    Raises:
        HTTPException: If token is invalid, expired, or user not found
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = authorization.split(" ")[1]
    user_id = get_user_id_from_token(token)

    # Import here to avoid circular imports
    from app.models import User

    document = db["users"].find_one({"id": user_id})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return User.model_validate(from_bson(document))


def require_role(role: str):
    """
    Dependency factory to require a specific user role.

    Args:
        role: The required role

    Returns:
        A dependency function that validates the current user has the required role
    """
    async def role_checker(current_user = Depends(get_current_user)):
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This operation requires {role} role"
            )
        return current_user

    return role_checker
