"""Investigation-case and case-note document models."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.db.base import BaseModel
from pydantic import Field


class InvestigationCase(BaseModel):
    alert_id: int
    transaction_id: int
    customer_id: int
    case_type: str
    case_status: str = "open"
    assigned_to: int
    summary: Optional[str] = None
    findings: Optional[Dict[str, Any]] = None
    case_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    case_closed_at: Optional[datetime] = None
    case_notes: Optional[str] = None
    escalated: bool = False
    escalation_reason: Optional[str] = None
    escalated_to: Optional[int] = None


class CaseNote(BaseModel):
    case_id: int
    analyst_id: int
    note_text: str
    note_type: str = "general"
