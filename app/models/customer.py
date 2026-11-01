"""Customer document model."""

from typing import Optional

from app.db.base import BaseModel


class Customer(BaseModel):
    customer_id: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    customer_type: str = "individual"
    country: Optional[str] = None
    city: Optional[str] = None
    risk_profile: str = "low"
    notes: Optional[str] = None
    is_active: bool = True
