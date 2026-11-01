"""Audit-log document model."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.base import BaseModel
from pydantic import Field


class AuditLog(BaseModel):
    actor_id: Optional[int] = None
    action: str
    action_category: str
    target_type: str
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    action_status: str = "success"
    status_message: Optional[str] = None
    request_id: Optional[str] = None
    http_method: Optional[str] = None
    http_path: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    action_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = None
    changes_before: Optional[Dict[str, Any]] = None
    changes_after: Optional[Dict[str, Any]] = None
