"""User document model for authentication and authorization."""

from app.core.permissions import UserRole
from app.db.base import BaseModel


class User(BaseModel):
    email: str
    full_name: str
    password_hash: str
    role: UserRole = UserRole.ANALYST
    is_active: bool = True
