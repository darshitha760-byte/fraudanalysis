"""
Request and response schemas using Pydantic for validation and documentation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal
from app.core.permissions import UserRole
import re


# ============= User Schemas =============

class UserCreate(BaseModel):
    """Schema for creating a new user."""
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., min_length=1, max_length=255, description="User's full name")
    password: str = Field(..., min_length=8, description="User password (minimum 8 characters)")
    role: UserRole = Field(default=UserRole.ANALYST, description="User role")

    @field_validator('email', mode='before')
    @classmethod
    def validate_email_field(cls, v):
        """Validate email format, supporting .local domains."""
        if not isinstance(v, str):
            raise ValueError('Email must be a string')
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    full_name: Optional[str] = Field(None, max_length=255)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserResponse(BaseModel):
    """Schema for user responses."""
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ============= Authentication Schemas =============

class LoginRequest(BaseModel):
    """Schema for login request."""
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")

    @field_validator('email', mode='before')
    @classmethod
    def validate_email_field(cls, v):
        """Validate email format, supporting .local domains."""
        if not isinstance(v, str):
            raise ValueError('Email must be a string')
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()


class UserRegistrationRequest(BaseModel):
    """Public registration schema; callers cannot assign their own role."""
    email: str
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator('email', mode='before')
    @classmethod
    def validate_email_field(cls, v):
        """Validate email format, supporting .local domains."""
        if not isinstance(v, str):
            raise ValueError('Email must be a string')
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z0-9.-]+$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v.lower()

    model_config = {"extra": "forbid"}


class TokenResponse(BaseModel):
    """Schema for token response."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class MeResponse(BaseModel):
    """Schema for current user info."""
    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


# ============= Customer Schemas =============

class CustomerCreate(BaseModel):
    """Schema for creating a customer."""
    customer_id: str = Field(..., max_length=100, description="External customer ID")
    name: str = Field(..., max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    customer_type: str = Field(default="individual", max_length=50)
    country: Optional[str] = Field(None, max_length=100)
    city: Optional[str] = Field(None, max_length=100)
    risk_profile: str = Field(default="low", description="low, medium, or high")


class CustomerUpdate(BaseModel):
    """Schema for updating a customer."""
    name: Optional[str] = None
    email: Optional[str] = None
    risk_profile: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerResponse(BaseModel):
    """Schema for customer response."""
    id: int
    customer_id: str
    name: str
    email: Optional[str]
    risk_profile: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= Transaction Schemas =============

class TransactionCreate(BaseModel):
    """Schema for creating a transaction."""
    transaction_id: str = Field(..., max_length=100, description="External transaction ID")
    customer_id: int = Field(..., description="Customer ID")
    transaction_date: datetime
    amount: Decimal = Field(..., decimal_places=2)
    currency: str = Field(default="USD", max_length=3)
    merchant_name: Optional[str] = None
    merchant_id: Optional[str] = None
    transaction_type: str = Field(default="purchase")
    status: str = Field(default="completed")
    payment_method: str = Field(default="card")
    location_country: Optional[str] = None
    location_city: Optional[str] = None
    device_id: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    is_synthetic: bool = Field(default=False)
    fraud_label: Optional[bool] = None


class TransactionImportRow(BaseModel):
    """Schema for CSV import row."""
    transaction_id: str
    customer_id: str  # Can be string from CSV
    transaction_date: str  # ISO format string
    amount: str  # String to handle various formats
    currency: Optional[str] = "USD"
    merchant_name: Optional[str] = None
    transaction_type: Optional[str] = "purchase"
    payment_method: Optional[str] = "card"
    location_country: Optional[str] = None


class TransactionResponse(BaseModel):
    """Schema for transaction response."""
    id: int
    transaction_id: str
    customer_id: int
    transaction_date: datetime
    amount: Decimal
    currency: str
    merchant_name: Optional[str]
    transaction_type: str
    status: str
    payment_method: str
    is_synthetic: bool
    fraud_label: Optional[bool]
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= Fraud Rule Schemas =============

class FraudRuleCreate(BaseModel):
    """Schema for creating a fraud rule."""
    rule_id: str = Field(..., max_length=50, description="Unique rule identifier")
    name: str = Field(..., max_length=255)
    description: str
    rule_type: str = Field(..., description="high_value, velocity, geographic, etc.")
    threshold_value: Optional[Decimal] = None
    threshold_unit: Optional[str] = None
    threshold_config: Optional[Dict[str, Any]] = None
    severity: str = Field(default="medium", description="low, medium, high, critical")
    risk_weight: Decimal = Field(default=10, le=100)
    required_fields: Optional[str] = None
    applicable_transaction_types: Optional[str] = None


class FraudRuleUpdate(BaseModel):
    """Schema for updating a fraud rule."""
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    threshold_value: Optional[Decimal] = None
    threshold_config: Optional[Dict[str, Any]] = None
    severity: Optional[str] = None
    risk_weight: Optional[Decimal] = None


class FraudRuleResponse(BaseModel):
    """Schema for fraud rule response."""
    id: int
    rule_id: str
    name: str
    description: str
    rule_type: str
    is_enabled: bool
    threshold_value: Optional[Decimal]
    severity: str
    risk_weight: Decimal
    version: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ============= Fraud Assessment Schemas =============

class TriggeredRuleDetail(BaseModel):
    """Schema for triggered rule detail."""
    rule_id: str
    rule_name: str
    explanation: str
    severity: str
    risk_weight: Decimal


class FraudAssessmentResponse(BaseModel):
    """Schema for fraud assessment response."""
    id: int
    transaction_id: int
    risk_score: Decimal
    risk_category: str
    rules_triggered_count: int
    ml_score: Optional[Decimal]
    ml_model_version: Optional[str]
    explanation: Optional[str]
    assessment_timestamp: datetime
    triggered_rules: List[TriggeredRuleDetail] = []

    model_config = {"from_attributes": True}


# ============= Fraud Alert Schemas =============

class AlertReview(BaseModel):
    """Schema for reviewing a fraud alert."""
    review_decision: str = Field(..., description="approved, rejected, escalated, etc.")
    review_notes: Optional[str] = None


class FraudAlertResponse(BaseModel):
    """Schema for fraud alert response."""
    id: int
    transaction_id: int
    customer_id: int
    alert_severity: str
    alert_status: str
    alert_reason: str
    triggered_rules_summary: Optional[str]
    review_decision: Optional[str]
    review_notes: Optional[str]
    alert_created_at: datetime
    review_timestamp: Optional[datetime]

    model_config = {"from_attributes": True}


# ============= Analytics Schemas =============

class AnalyticsOverview(BaseModel):
    """Schema for analytics overview."""
    total_transactions: int
    flagged_transactions: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    confirmed_fraud_count: int
    total_transaction_value: Decimal
    flagged_transaction_exposure: Decimal


class AuditLogResponse(BaseModel):
    """Schema for audit log response."""
    id: int
    actor_id: Optional[int]
    action: str
    action_category: str
    target_type: str
    target_id: Optional[str]
    action_status: str
    http_method: Optional[str]
    http_path: Optional[str]
    action_timestamp: datetime

    model_config = {"from_attributes": True}


# ============= Error Schemas =============

class ErrorResponse(BaseModel):
    """Schema for error responses."""
    detail: str = Field(..., description="Error message")
    status_code: int = Field(..., description="HTTP status code")
    error_code: Optional[str] = Field(None, description="Application error code")
