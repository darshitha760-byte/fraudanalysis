"""Fraud-assessment, triggered-rule, and alert document models."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

from app.db.base import BaseModel
from pydantic import Field


class FraudAssessment(BaseModel):
    transaction_id: int
    risk_score: Decimal
    risk_category: str
    rules_triggered_count: int = 0
    ml_score: Optional[Decimal] = None
    ml_model_version: Optional[str] = None
    engine_version: str = "1.0"
    assessment_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    explanation: Optional[str] = None
    assessment_metadata: Optional[Dict[str, Any]] = None
    missing_features: Optional[str] = None


class TriggeredRule(BaseModel):
    assessment_id: int
    transaction_id: int
    rule_id: int
    trigger_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rule_explanation: str = ""
    triggered_values: Optional[Dict[str, Any]] = None
    triggered_rule_id: Optional[str] = None
    triggered_rule_name: Optional[str] = None
    explanation: Optional[str] = None
    triggered_at: Optional[datetime] = None


class FraudAlert(BaseModel):
    transaction_id: int
    customer_id: int
    assessment_id: int
    alert_severity: str = "medium"
    alert_status: str = "pending"
    alert_reason: str = ""
    triggered_rules_summary: Optional[str] = None
    reviewed_by: Optional[int] = None
    review_timestamp: Optional[datetime] = None
    review_decision: Optional[str] = None
    review_notes: Optional[str] = None
    alert_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    alert_resolved_at: Optional[datetime] = None
    risk_score: Optional[Decimal] = None
    risk_level: Optional[str] = None
    analyst_notes: Optional[str] = None
    ml_score: Optional[Decimal] = None
