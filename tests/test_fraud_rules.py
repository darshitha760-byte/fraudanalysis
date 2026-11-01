"""
Fraud Rules tests: Rule evaluation, edge cases, mock data scenarios.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.db.database import from_bson, get_db
from conftest import insert_test_document
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.fraud_rule import FraudRule
from app.services.fraud_engine import FraudEngine
from app.core.security import hash_password


# Use conftest fixtures: test_session, test_client
# They provide isolated Mongo-compatible databases for testing.

@pytest.fixture
def db(test_session):
    """Alias test_session as db for compatibility."""
    yield test_session


@pytest.fixture
def client(test_client):
    """Alias test_client for compatibility."""
    return test_client


@pytest.fixture
def test_customer(db):
    """Create test customer (old, established customer > 30 days)."""
    from datetime import datetime, timedelta
    # Create customer with past created_at to ensure it's not "new"
    customer = Customer(
        customer_id="CUST001",
        name="Jane Doe",
        email="jane@example.com",
        phone="+1234567890",
        country="US",
        city="New York",
        risk_profile="low",
        is_active=True,
        created_at=datetime.utcnow() - timedelta(days=30)
    )
    return insert_test_document(db, customer)


@pytest.fixture
def test_new_customer(db):
    """Create a new customer (< 7 days)."""
    customer = Customer(
        customer_id="CUST_NEW",
        name="New Customer",
        email="new@example.com",
        phone="+1234567890",
        country="US",
        city="New York",
        risk_profile="low",
        is_active=True
    )
    return insert_test_document(db, customer)


@pytest.fixture
def test_merchant(db):
    """Create test merchant data (merchant_id is just a string in transaction model)."""
    # Merchants are referenced by merchant_id string in transactions
    # No separate merchant model table exists
    return {"merchant_id": "M001", "merchant_name": "Walmart"}


@pytest.fixture
def test_blocked_merchant(db):
    """Create blocked merchant data."""
    # Blocked merchants are referenced by merchant_id string
    return {"merchant_id": "M_BLOCKED", "merchant_name": "Suspicious Shop"}


@pytest.fixture
def test_admin_user(db):
    """Create test admin user."""
    from app.models.user import User
    from app.core.permissions import UserRole
    from app.core.security import hash_password

    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        full_name="Admin User",
        role=UserRole.ADMIN,
        is_active=True
    )
    return insert_test_document(db, user)


@pytest.fixture
def test_rules(db):
    """Create default fraud rules."""
    for rule_id, rule_data in FraudEngine.DEFAULT_RULES.items():
        rule = FraudRule(
            rule_id=rule_id,
            name=rule_data["name"],
            description=rule_data["description"],
            rule_type=rule_data["rule_type"],
            threshold_value=Decimal(str(rule_data.get("threshold_value", 0) or 0)),
            threshold_unit=rule_data.get("threshold_unit"),
            threshold_config=rule_data.get("threshold_config"),
            severity=rule_data.get("severity", "medium"),
            risk_weight=Decimal(str(rule_data["risk_weight"])),
            is_enabled=True
        )
        insert_test_document(db, rule)


@pytest.fixture
def auth_headers(client, test_admin_user):
    """Get authentication headers."""
    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": "admin123"}
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# Fraud Engine Rule Tests

@pytest.mark.usefixtures("mongo_server_only")
class TestR01HighValueTransaction:
    """Test R01: High-value transaction (> $5000)."""

    def test_high_value_triggers_rule(self, db, test_customer, test_merchant, test_rules):
        """Test that high-value transaction triggers R01."""
        txn = Transaction(
            transaction_id="txn_1",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("6000.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert any(r.rule_id == "R01" for r in result[2])
        assert result[0] >= 20

    def test_threshold_boundary_5000(self, db, test_customer, test_merchant, test_rules):
        """Test exactly $5000 (boundary case)."""
        txn = Transaction(
            transaction_id="txn_2",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("5000.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        # At boundary, should not trigger (> 5000, not >= 5000)
        assert not any(r.rule_id == "R01" for r in result[2])

    def test_just_above_threshold(self, db, test_customer, test_merchant, test_rules):
        """Test $5000.01 (just above threshold)."""
        txn = Transaction(
            transaction_id="txn_3",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("5000.01"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert any(r.rule_id == "R01" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR02RapidTransactions:
    """Test R02: Rapid transactions (>3 within 10 mins)."""

    def test_rapid_transactions_trigger_rule(self, db, test_customer, test_merchant, test_rules):
        """Test that 4 transactions in 10 mins triggers R02."""
        now = datetime.utcnow()

        for i in range(4):
            txn = Transaction(
                transaction_id=f"txn_4_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{100 + i}.00"),
                transaction_date=now - timedelta(minutes=i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        # Evaluate the latest transaction
        latest_doc = db["transactions"].find_one(sort=[("transaction_date", -1)])
        latest = Transaction.model_validate(from_bson(latest_doc))
        result = FraudEngine.evaluate_transaction(db, latest)

        assert any(r.rule_id == "R02" for r in result[2])

    def test_three_transactions_no_trigger(self, db, test_customer, test_merchant, test_rules):
        """Test that exactly 3 transactions does not trigger."""
        now = datetime.utcnow()

        for i in range(3):
            txn = Transaction(
                transaction_id=f"txn_5_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{100 + i}.00"),
                transaction_date=now - timedelta(minutes=i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        latest_doc = db["transactions"].find_one(sort=[("transaction_date", -1)])
        latest = Transaction.model_validate(from_bson(latest_doc))
        result = FraudEngine.evaluate_transaction(db, latest)

        assert not any(r.rule_id == "R02" for r in result[2])

    def test_transactions_outside_time_window(self, db, test_customer, test_merchant, test_rules):
        """Test that transactions outside 10-min window don't trigger."""
        now = datetime.utcnow()

        # Add transactions outside window (15 mins apart)
        for i in range(4):
            txn = Transaction(
                transaction_id=f"txn_6_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{100 + i}.00"),
                transaction_date=now - timedelta(minutes=i*15),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        latest_doc = db["transactions"].find_one(sort=[("transaction_date", -1)])
        latest = Transaction.model_validate(from_bson(latest_doc))
        result = FraudEngine.evaluate_transaction(db, latest)

        assert not any(r.rule_id == "R02" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR03GeographicAnomaly:
    """Test R03: Geographic anomaly."""

    def test_new_country_triggers_rule(self, db, test_customer, test_merchant, test_rules):
        """Test that transaction from new country triggers R03."""
        # Customer's home country is US
        db["customers"].update_one(
            {"id": test_customer.id}, {"$set": {"country": "US"}}
        )

        # Transaction from different country (GB)
        txn = Transaction(
            transaction_id="txn_7",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            merchant_name=test_merchant["merchant_name"],
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed",
            location_country="GB",
            location_city="London"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        # R03 should trigger for new country
        assert any(r.rule_id == "R03" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR04DuplicateTransaction:
    """Test R04: Duplicate transaction."""

    def test_duplicate_within_window_triggers_rule(self, db, test_customer, test_merchant, test_rules):
        """Test duplicate detection within 5-min window."""
        now = datetime.utcnow()

        txn1 = Transaction(
            transaction_id="txn_8",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=now,
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn1)

        # Create duplicate within 5 mins
        txn2 = Transaction(
            transaction_id="txn_9",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=now + timedelta(minutes=3),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn2)

        result = FraudEngine.evaluate_transaction(db, txn2)

        assert any(r.rule_id == "R04" for r in result[2])

    def test_different_amount_no_trigger(self, db, test_customer, test_merchant, test_rules):
        """Test that different amount doesn't trigger duplicate rule."""
        now = datetime.utcnow()

        txn1 = Transaction(
            transaction_id="txn_10",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=now,
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn1)

        txn2 = Transaction(
            transaction_id="txn_11",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.01"),  # Different amount
            transaction_date=now + timedelta(minutes=2),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn2)

        result = FraudEngine.evaluate_transaction(db, txn2)

        assert not any(r.rule_id == "R04" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR05LateNightTransaction:
    """Test R05: Late-night transaction (2-5 AM)."""

    def test_late_night_triggers_rule(self, db, test_customer, test_merchant, test_rules):
        """Test transaction between 2-5 AM triggers R05."""
        late_night = datetime.utcnow().replace(hour=3, minute=30, second=0)

        txn = Transaction(
            transaction_id="txn_12",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=late_night,
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert any(r.rule_id == "R05" for r in result[2])

    def test_daytime_no_trigger(self, db, test_customer, test_merchant, test_rules):
        """Test daytime transaction doesn't trigger R05."""
        daytime = datetime.utcnow().replace(hour=14, minute=0, second=0)

        txn = Transaction(
            transaction_id="txn_13",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=daytime,
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert not any(r.rule_id == "R05" for r in result[2])

    def test_boundary_2am(self, db, test_customer, test_merchant, test_rules):
        """Test 2:00 AM boundary."""
        boundary_time = datetime.utcnow().replace(hour=2, minute=0, second=0)

        txn = Transaction(
            transaction_id="txn_14",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=boundary_time,
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        # At boundary (2:00 AM should trigger, rule is 2-5 AM)
        assert any(r.rule_id == "R05" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR08AmountDeviation:
    """Test R08: Amount deviation from customer average (>3x)."""

    def test_amount_deviation_triggers_rule(self, db, test_customer, test_merchant, test_rules):
        """Test amount 3x above average triggers R08."""
        # Create transactions with average of $100
        for i in range(5):
            txn = Transaction(
                transaction_id=f"txn_15_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow() - timedelta(days=i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        # Create transaction 3x average
        high_txn = Transaction(
            transaction_id=f"txn_16_{i}",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("301.00"),  # > 3x average
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, high_txn)

        result = FraudEngine.evaluate_transaction(db, high_txn)

        assert any(r.rule_id == "R08" for r in result[2])

    def test_amount_within_deviation_no_trigger(self, db, test_customer, test_merchant, test_rules):
        """Test amount within 3x average doesn't trigger."""
        # Create transactions with average of $100
        for i in range(5):
            txn = Transaction(
                transaction_id=f"txn_17_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow() - timedelta(days=i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        # Create transaction within 3x average
        normal_txn = Transaction(
            transaction_id=f"txn_18_{i}",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("299.00"),  # < 3x average
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, normal_txn)

        result = FraudEngine.evaluate_transaction(db, normal_txn)

        assert not any(r.rule_id == "R08" for r in result[2])


@pytest.mark.usefixtures("mongo_server_only")
class TestR10NewCustomerHighValue:
    """Test R10: New customer high-value transaction."""

    def test_new_customer_high_value_triggers(self, db, test_new_customer, test_merchant, test_rules):
        """Test new customer high-value transaction triggers R10."""
        txn = Transaction(
            transaction_id="txn_19",
            customer_id=test_new_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("2500.00"),  # > $2000
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert any(r.rule_id == "R10" for r in result[2])

    def test_old_customer_no_trigger(self, db, test_customer, test_merchant, test_rules):
        """Test old customer doesn't trigger R10."""
        txn = Transaction(
            transaction_id="txn_20",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("5000.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert not any(r.rule_id == "R10" for r in result[2])

    def test_new_customer_low_value_no_trigger(self, db, test_new_customer, test_merchant, test_rules):
        """Test new customer with low value doesn't trigger."""
        txn = Transaction(
            transaction_id="txn_21",
            customer_id=test_new_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("1000.00"),  # < $2000
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert not any(r.rule_id == "R10" for r in result[2])


# Risk Score & Level Tests

@pytest.mark.usefixtures("mongo_server_only")
class TestRiskScoring:
    """Test risk score calculation and risk level determination."""

    def test_risk_level_low(self, db, test_customer, test_merchant, test_rules):
        """Test normal transaction gets low risk."""
        txn = Transaction(
            transaction_id="txn_22",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("50.00"),
            transaction_date=datetime.utcnow().replace(hour=10),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert result[1] == "low"
        assert result[0] < 40

    def test_risk_level_medium(self, db, test_customer, test_merchant, test_rules):
        """Test medium risk transaction."""
        now = datetime.utcnow()

        # Create multiple rapid transactions to trigger R02 (velocity check: > 3 in 10 mins)
        # Then create a high-value transaction to trigger R01
        for i in range(4):
            txn = Transaction(
                transaction_id=f"txn_23_rapid_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal("100.00"),
                transaction_date=now - timedelta(minutes=5 - i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        # High-value late-night transaction (triggers R01: 25, R05: 8, R02: 20 = 53 total)
        txn = Transaction(
            transaction_id="txn_23_high",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("6000.00"),  # High value (triggers R01: 25 points)
            transaction_date=now.replace(hour=3),  # Late-night (triggers R05: 8 points)
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        assert result[1] in ["medium", "high"]
        assert 40 <= result[0] <= 100

    def test_risk_score_capped_at_100(self, db, test_customer, test_merchant, test_rules):
        """Test risk score is capped at 100."""
        now = datetime.utcnow()

        # Create many transactions to trigger multiple rules
        for i in range(5):
            txn = Transaction(
                transaction_id=f"txn_24_{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{100 + i}.00"),
                transaction_date=now - timedelta(minutes=i),
                currency="USD",
                status="completed"
            )
            insert_test_document(db, txn)

        latest_doc = db["transactions"].find_one(sort=[("transaction_date", -1)])
        latest = Transaction.model_validate(from_bson(latest_doc))
        result = FraudEngine.evaluate_transaction(db, latest)

        assert result[0] <= 100


# Fraud Rules API Tests

class TestFraudRulesAPI:
    """Test Fraud Rules API endpoints."""

    def test_list_rules_requires_auth(self, client):
        """Test list endpoint requires authentication."""
        response = client.get("/fraud/rules")
        assert response.status_code == 401

    def test_list_rules(self, client, auth_headers, test_rules):
        """Test listing fraud rules."""
        response = client.get("/fraud/rules", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) > 0
        assert "pagination" in data

    def test_get_rule(self, client, auth_headers, test_rules):
        """Test getting specific rule."""
        response = client.get("/fraud/rules/R01", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["rule_id"] == "R01"

    def test_get_nonexistent_rule(self, client, auth_headers):
        """Test getting non-existent rule."""
        response = client.get("/fraud/rules/INVALID", headers=auth_headers)

        assert response.status_code == 404

    def test_create_rule_admin_only(self, client, auth_headers, test_rules):
        """Test creating rule requires admin role."""
        # This should pass with admin auth_headers
        response = client.post(
            "/fraud/rules",
            json={
                "rule_id": "R99",
                "name": "Test Rule",
                "description": "Test custom rule",
                "rule_type": "amount_based",
                "threshold_value": "1000",
                "severity": "high",
                "risk_weight": "15"
            },
            headers=auth_headers
        )

        # Admin should be able to create
        assert response.status_code in [201, 200]

    def test_update_rule(self, client, auth_headers, test_rules):
        """Test updating fraud rule."""
        response = client.patch(
            "/fraud/rules/R01",
            json={"is_enabled": False},
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] == False

    def test_disable_rule(self, client, auth_headers, test_rules):
        """Test soft delete (disable) rule."""
        response = client.delete("/fraud/rules/R01", headers=auth_headers)

        assert response.status_code == 204

        # Verify it's disabled
        response = client.get("/fraud/rules/R01", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["is_enabled"] == False

    def test_enable_rule(self, client, auth_headers, test_rules):
        """Test enabling disabled rule."""
        # Disable first
        client.delete("/fraud/rules/R01", headers=auth_headers)

        # Then enable
        response = client.post(
            "/fraud/rules/R01/enable",
            headers=auth_headers
        )

        assert response.status_code == 200
        assert response.json()["is_enabled"] == True


# Edge Cases & Error Scenarios

@pytest.mark.usefixtures("mongo_server_only")
class TestFraudRuleEdgeCases:
    """Test edge cases in fraud rule evaluation."""

    def test_graceful_missing_customer_data(self, db, test_merchant, test_rules):
        """Test rules handle missing customer gracefully."""
        # Create transaction with non-existent customer
        txn = Transaction(
            transaction_id="txn_25",
            customer_id=9999,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        # Should not raise error, just skip applicable rules
        result = FraudEngine.evaluate_transaction(db, txn)

        # Result is tuple: (risk_score, risk_level, triggered_rules)
        assert isinstance(result, tuple)
        assert len(result) == 3
        assert result[0] >= 0  # risk_score

    def test_empty_transaction_history(self, db, test_customer, test_merchant, test_rules):
        """Test rules work with no historical data."""
        txn = Transaction(
            transaction_id="txn_26",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        result = FraudEngine.evaluate_transaction(db, txn)

        # Should succeed without error
        assert result[0] >= 0

    def test_null_amount_handling(self, db, test_customer, test_merchant, test_rules):
        """Test handling of zero/edge case amounts."""
        txn = Transaction(
            transaction_id="txn_27",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("0.01"),  # Minimum valid amount
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        insert_test_document(db, txn)

        # Should handle gracefully - minimal amount rules should not trigger
        result = FraudEngine.evaluate_transaction(db, txn)
        # R01 (high-value) should not trigger with minimal amount
        triggered_rule_ids = [r.rule_id for r in result[2]]
        assert "R01" not in triggered_rule_ids
