"""
Authentication API endpoints for login, logout, and token validation.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, status
from datetime import timedelta
from app.db.database import from_bson, get_db, insert_document
from app.core.security import hash_password, verify_password, create_access_token, get_user_id_from_token
from app.core.config import get_settings
from app.core.permissions import UserRole
from app.models import User
from app.services.audit_service import AuditService
from app.schemas import (
    LoginRequest,
    MeResponse,
    TokenResponse,
    UserRegistrationRequest,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])
settings = get_settings()


@router.post("/register", response_model=MeResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserRegistrationRequest,
    db = Depends(get_db),
):
    """Create a new viewer account through public self-registration."""
    normalized_email = str(request.email).lower()
    existing_user = db["users"].find_one({"email": normalized_email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=normalized_email,
        full_name=request.full_name.strip(),
        password_hash=hash_password(request.password),
        role=UserRole.VIEWER,
        is_active=True,
    )
    if not user.full_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Full name cannot be blank",
        )

    try:
        document = insert_document(
            db, "users", user.model_dump(exclude={"id", "created_at", "updated_at"})
        )
        user = User.model_validate(document)
    except Exception:
        logger.exception("Failed to register account")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create account",
        )

    logger.info("New viewer account registered: %s", user.email)
    AuditService.log_action(
        db, "create_user", "user_management", "user",
        target_id=str(user.id), actor_id=user.id,
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    db=Depends(get_db)
):
    """
    User login endpoint.
    Validates credentials and returns JWT access token.
    
    Security:
    - Does not reveal whether email exists or not (generic error message)
    - Uses Argon2 password hashing
    - Rate limiting should be applied at deployment
    """
    # Find user by email
    document = db["users"].find_one({"email": str(request.email).lower()})
    user = User.model_validate(from_bson(document)) if document else None
    
    # Verify user exists and password matches
    if not user or not verify_password(request.password, user.password_hash):
        AuditService.log_login(
            db, user.id if user else None, str(request.email).lower(), False
        )
        logger.warning(f"Failed login attempt for email: {request.email}")
        # Generic error - don't reveal if user exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive"
        )
    
    # Create JWT token
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role.value
        },
        expires_delta=access_token_expires
    )
    
    logger.info(f"Successful login for user: {user.email}")
    AuditService.log_login(db, user.id, user.email, True)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": int(access_token_expires.total_seconds())
    }


@router.get("/me", response_model=MeResponse)
async def get_current_user(
    authorization: str = Header(default=None),
    db=Depends(get_db)
):
    """
    Get current authenticated user information.
    Requires valid JWT token in Authorization header.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.split(" ")[1]
    user_id = get_user_id_from_token(token)
    
    document = db["users"].find_one({"id": user_id})
    if not document:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    
    return User.model_validate(from_bson(document))


@router.post("/logout")
async def logout():
    """
    Logout endpoint (stateless JWT).
    In stateless JWT, logout is typically handled client-side by discarding the token.
    This endpoint provides a consistent logout endpoint for clients.
    """
    return {"message": "Logged out successfully. Please discard your token."}


@router.post("/token", response_model=TokenResponse)
async def refresh_token(authorization: str = Header(default=None)):
    """
    Token refresh endpoint placeholder.
    Current implementation uses simple JWT with expiration.
    For production, implement refresh tokens separately.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Refresh token endpoint not yet implemented"
    )
