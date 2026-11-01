from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.models.fraud_rule import FraudRule
from app.services.fraud_engine import FraudEngine
from scripts.populate_demo_data import (
    DEMO_PREFIX,
    _customer,
    _default_rule,
    _transaction,
)


def test_default_rules_preserve_model_field_types_and_values():
    rule = _default_rule("R01", FraudEngine.DEFAULT_RULES["R01"])

    assert isinstance(rule, FraudRule)
    assert rule.threshold_value == Decimal("5000.00")
    assert rule.risk_weight == Decimal("25")
    assert rule.required_fields == "[]"
    assert rule.applicable_transaction_types == '["all"]'


def test_synthetic_customer_ids_and_dates_are_deterministic():
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)

    first = _customer(1, now)
    again = _customer(1, now)

    assert first.customer_id == f"{DEMO_PREFIX}-CUST-000001"
    assert first.name == again.name
    assert first.created_at == now - timedelta(days=60)


def test_synthetic_transactions_have_stable_labels_and_safe_dates():
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    ordinary = _transaction(1, 21, now)
    flagged = _transaction(50, 25, now)

    assert ordinary.transaction_id == f"{DEMO_PREFIX}-TXN-00000001"
    assert ordinary.customer_id == 21
    assert ordinary.is_synthetic is True
    assert ordinary.fraud_label is None
    assert now - ordinary.transaction_date < timedelta(days=30)
    assert flagged.transaction_id == f"{DEMO_PREFIX}-TXN-00000050"
    assert flagged.amount == Decimal("6500.00")
    assert flagged.location_country == "CA"
    assert flagged.merchant_category == "cryptocurrency"
    assert flagged.transaction_date.hour == 3
