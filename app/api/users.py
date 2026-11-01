"""User management backed by MongoDB user and audit documents."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.permissions import UserRole
from app.core.security import get_current_user, hash_password, require_role
from app.db.database import from_bson, get_db, insert_document, to_bson
from app.models import User
from app.services.audit_service import AuditService
from app.schemas import UserCreate as UserCreateRequest, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/users", tags=["users"])


class UserUpdateRequest(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(None, min_length=1, max_length=255)
    is_active: bool | None = None
    role: UserRole | None = None
    model_config = {"extra": "forbid"}


class UserRoleUpdateRequest(BaseModel):
    role: UserRole


def record_user_change(db, actor: User, user: User, action: str) -> None:
    AuditService.log_action(
        db, action, "user_management", "user", target_id=str(user.id),
        actor_id=actor.id,
        changes_after={"role": user.role.value, "is_active": user.is_active}
        if action != "delete_user" else None,
    )


def find_user(db, user_id: int) -> User:
    document = db["users"].find_one({"id": user_id})
    if document is None:
        raise HTTPException(404, detail="User not found")
    return User.model_validate(from_bson(document))


@router.get("/me", response_model=UserResponse)
async def current_user_profile(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("", response_model=list[UserResponse])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db=Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    docs = db["users"].find().sort("id", 1).skip(skip).limit(limit)
    return [User.model_validate(from_bson(doc)) for doc in docs]


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    user_data: UserCreateRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    email, name = str(user_data.email).lower(), user_data.full_name.strip()
    if not name:
        raise HTTPException(422, detail="Full name cannot be blank")
    if db["users"].find_one({"email": email}):
        raise HTTPException(409, detail="Email already exists")
    user = User(email=email, full_name=name,
                password_hash=hash_password(user_data.password),
                role=user_data.role, is_active=True)
    try:
        saved = insert_document(
            db, "users", user.model_dump(exclude={"id", "created_at", "updated_at"})
        )
    except DuplicateKeyError:
        raise HTTPException(409, detail="Email already exists")
    except PyMongoError:
        logger.exception("Unable to create user")
        raise HTTPException(500, detail="Unable to create user")
    user = User.model_validate(saved)
    record_user_change(db, current_user, user, "create_user")
    return user


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(403, detail="Not authorized to view this user")
    return find_user(db, user_id)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdateRequest,
    db=Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != UserRole.ADMIN:
        raise HTTPException(403, detail="Not authorized to update this user")
    if current_user.role != UserRole.ADMIN and (
        user_data.role is not None or user_data.is_active is not None
    ):
        raise HTTPException(403, detail="Only admins can change account role or status")
    user = find_user(db, user_id)
    changes = user_data.model_dump(exclude_unset=True)
    if changes.get("email") is not None:
        email = str(changes["email"]).lower()
        if db["users"].find_one({"email": email, "id": {"$ne": user_id}}):
            raise HTTPException(409, detail="Email already exists")
        changes["email"] = email
    if changes.get("full_name") is not None:
        changes["full_name"] = changes["full_name"].strip()
        if not changes["full_name"]:
            raise HTTPException(422, detail="Full name cannot be blank")
    if changes.get("role") is not None:
        changes["role"] = changes["role"].value
    changes["updated_at"] = datetime.now(timezone.utc)
    try:
        db["users"].update_one({"id": user_id}, {"$set": to_bson(changes)})
    except DuplicateKeyError:
        raise HTTPException(409, detail="Email already exists")
    except PyMongoError:
        logger.exception("Unable to save user change")
        raise HTTPException(500, detail="Unable to save user change")
    user = find_user(db, user_id)
    record_user_change(db, current_user, user, "update_user")
    return user


@router.put("/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: int,
    role_data: UserRoleUpdateRequest,
    db=Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    return await update_user(user_id, UserUpdateRequest(role=role_data.role), db, current_user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    db=Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    if current_user.id == user_id:
        raise HTTPException(400, detail="Cannot delete your own user account")
    user = find_user(db, user_id)
    # Preserve the former FK RESTRICT behavior rather than orphaning ownership refs.
    if (db["investigation_cases"].find_one({"$or": [
        {"assigned_to": user_id}, {"escalated_to": user_id}
    ]}) or db["audit_logs"].find_one({"actor_id": user_id})):
        raise HTTPException(409, detail="Email already exists or account is still referenced")
    record_user_change(db, current_user, user, "delete_user")
    db["users"].delete_one({"id": user_id})
