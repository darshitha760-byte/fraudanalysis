"""
Role-based access control and permission management.
"""

from enum import Enum
from fastapi import HTTPException, status


class UserRole(str, Enum):
    """User roles in the system."""
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Permissions in the system."""
    # User management
    CREATE_USER = "create_user"
    READ_USER = "read_user"
    UPDATE_USER = "update_user"
    DELETE_USER = "delete_user"

    # Transaction management
    CREATE_TRANSACTION = "create_transaction"
    READ_TRANSACTION = "read_transaction"
    IMPORT_TRANSACTION = "import_transaction"
    EXPORT_TRANSACTION = "export_transaction"

    # Fraud detection
    VIEW_ALERTS = "view_alerts"
    REVIEW_ALERT = "review_alert"

    # Rule management
    CREATE_RULE = "create_rule"
    UPDATE_RULE = "update_rule"
    DELETE_RULE = "delete_rule"

    # Analytics
    VIEW_ANALYTICS = "view_analytics"

    # Audit logs
    VIEW_AUDIT_LOGS = "view_audit_logs"

    # Model management
    TRAIN_MODEL = "train_model"
    VIEW_MODEL_PERFORMANCE = "view_model_performance"


# Define role-based permissions
ROLE_PERMISSIONS = {
    UserRole.ADMIN: {
        Permission.CREATE_USER,
        Permission.READ_USER,
        Permission.UPDATE_USER,
        Permission.DELETE_USER,
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.IMPORT_TRANSACTION,
        Permission.EXPORT_TRANSACTION,
        Permission.VIEW_ALERTS,
        Permission.REVIEW_ALERT,
        Permission.CREATE_RULE,
        Permission.UPDATE_RULE,
        Permission.DELETE_RULE,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.TRAIN_MODEL,
        Permission.VIEW_MODEL_PERFORMANCE,
    },
    UserRole.ANALYST: {
        Permission.READ_USER,
        Permission.CREATE_TRANSACTION,
        Permission.READ_TRANSACTION,
        Permission.IMPORT_TRANSACTION,
        Permission.EXPORT_TRANSACTION,
        Permission.VIEW_ALERTS,
        Permission.REVIEW_ALERT,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_AUDIT_LOGS,
        Permission.VIEW_MODEL_PERFORMANCE,
    },
    UserRole.VIEWER: {
        Permission.READ_TRANSACTION,
        Permission.VIEW_ALERTS,
        Permission.VIEW_ANALYTICS,
        Permission.VIEW_MODEL_PERFORMANCE,
    },
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """
    Check if a role has a specific permission.

    Args:
        role: The user's role
        permission: The permission to check

    Returns:
        True if the role has the permission, False otherwise
    """
    if role not in ROLE_PERMISSIONS:
        return False
    return permission in ROLE_PERMISSIONS[role]


def require_permission(role: UserRole, permission: Permission) -> None:
    """
    Raise an exception if the role doesn't have the required permission.

    Args:
        role: The user's role
        permission: The permission to check

    Raises:
        HTTPException: If permission is denied
    """
    if not has_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {permission.value} is not allowed for {role.value} role"
        )


def require_admin_role(role: UserRole) -> None:
    """
    Require admin role, raise exception if not admin.

    Args:
        role: The user's role

    Raises:
        HTTPException: If user is not an admin
    """
    if role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this operation"
        )
