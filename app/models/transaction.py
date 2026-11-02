"""Financial transaction document with exact Decimal monetary values."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from app.db.base import BaseModel


class Transaction(BaseModel):
    transaction_id: str
    customer_id: int
    transaction_date: datetime
    amount: Decimal
    currency: str = "USD"
    merchant_name: Optional[str] = None
    merchant_id: Optional[str] = None
    merchant_category: Optional[str] = None
    transaction_type: str = "purchase"
    status: str = "completed"
    payment_method: str = "card"
    location_country: Optional[str] = None
    location_city: Optional[str] = None
    device_id: Optional[str] = None
    channel: Optional[str] = None
    description: Optional[str] = None
    reference_number: Optional[str] = None
    is_synthetic: bool = False
    fraud_label: Optional[bool] = None
