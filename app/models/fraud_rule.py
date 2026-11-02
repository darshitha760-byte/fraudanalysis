"""Configurable fraud-rule document."""

from decimal import Decimal
from typing import Any, Dict, Optional

from app.db.base import BaseModel


class FraudRule(BaseModel):
    rule_id: str
    name: str
    description: str
    rule_type: str
    is_enabled: bool = True
    threshold_value: Optional[Decimal] = None
    threshold_unit: Optional[str] = None
    threshold_config: Optional[Dict[str, Any]] = None
    severity: str = "medium"
    risk_weight: Decimal = Decimal("10")
    required_fields: Optional[str] = None
    applicable_transaction_types: Optional[str] = None
    version: int = 1
    notes: Optional[str] = None
