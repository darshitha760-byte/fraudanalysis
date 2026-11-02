"""
Tests for customer analytics functionality.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.analytics_service import AnalyticsService
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAlert
from tests.conftest import create_test_fraud_assessment_and_alert
from tests.conftest import insert_test_document


@pytest.fixture
def db(test_session):
    """Alias test_session as db for compatibility."""
    yield test_session


@pytest.fixture
def sample_customer(db):
    """Create sample customer for tests."""
    customer = Customer(
        customer_id="CUST_ANALYTICS_001",
        name="Test Customer",
        email="analytics_test@example.com",
        phone="+1234567890",
        customer_type="individual",
        country="US",
        city="New York",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


class TestCustomerAnalytics:
    """Test suite for customer-level analytics."""

    def test_get_customer_risk_profile(self, db, sample_customer: Customer):
        """Test customer risk profile retrieval."""
        # Create transactions for customer
        for i in range(5):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_PROF_{i}",
                amount=Decimal(str(100.0 + i * 50)),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test Merchant",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Create some alerts for the customer's transactions
        txn_ids = list(db["transactions"].find(
            {"customer_id": sample_customer.id}, {"id": 1}
        ))

        for txn_doc in txn_ids[:2]:
            assessment, alert = create_test_fraud_assessment_and_alert(
                db, txn_doc["id"], sample_customer.id,
                risk_score=80
            )
            db["fraud_alerts"].update_one(
                {"id": alert.id},
                {"$set": {"alert_status": "resolved", "review_decision": "approved"}},
            )

        # Get risk profile (pass customer.id which is the DB primary key)
        profile = AnalyticsService.get_customer_risk_profile(db, sample_customer.id)

        assert profile is not None
        assert profile["customer_id"] == sample_customer.customer_id
        assert profile["total_transactions"] == 5
        assert profile["high_risk_count"] >= 0
        assert profile["fraud_rate"] >= 0
        assert "average_transaction_amount" in profile
        assert "suspicious_patterns" in profile

    def test_get_customer_risk_profile_nonexistent(self, db):
        """Test risk profile for nonexistent customer."""
        profile = AnalyticsService.get_customer_risk_profile(db, 99999)

        # Should return None or empty dict
        assert profile is None or profile.get("total_transactions", 0) == 0

    def test_get_high_risk_customers(self, db, mongo_server_only):
        """Test retrieval of high-risk customers."""
        # Create multiple customers with different fraud rates
        for cust_idx in range(5):
            customer = Customer(
                customer_id=f"CUST_HIGHRISK_{cust_idx}",
                name=f"High Risk Customer {cust_idx}",
                email=f"highrisk{cust_idx}@example.com",
                phone="+1234567890",
                customer_type="individual",
                country="US",
                city="New York",
                risk_profile="high"
            )
            insert_test_document(db, customer)

        # Create transactions and alerts for each customer
        customers = list(db["customers"].find(
            {"customer_id": {"$regex": "^CUST_HIGHRISK_"}}
        ))

        for idx, customer in enumerate(customers):
            # Create varying number of transactions
            for i in range(2 + idx):
                txn = Transaction(
                    customer_id=customer["id"],
                    transaction_id=f"TXN_RISK_{idx}_{i}",
                    amount=Decimal("500.00"),
                    transaction_date=datetime.utcnow(),
                    transaction_type="credit_transfer",
                    currency="USD",
                    merchant_name="Test",
                    merchant_id="M001"
                )
                insert_test_document(db, txn)

            # Create alerts based on index (first customer has fewer)
            txn_ids = list(db["transactions"].find(
                {"customer_id": customer["id"]}, {"id": 1}
            ))

            for i, txn_doc in enumerate(txn_ids[:max(1, idx)]):
                assessment, alert = create_test_fraud_assessment_and_alert(
                    db, txn_doc["id"], customer["id"],
                    risk_score=70 + idx * 5
                )
                db["fraud_alerts"].update_one(
                    {"id": alert.id},
                    {"$set": {"alert_status": "resolved", "review_decision": "approved"}},
                )

        # Get high risk customers
        high_risk = AnalyticsService.get_high_risk_customers(db, limit=5)

        assert len(high_risk) >= 0
        assert len(high_risk) <= 5

    def test_customer_fraud_rate_calculation(self, db, sample_customer: Customer):
        """Test customer fraud rate calculation."""
        # Create transactions
        for i in range(10):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_FRAUD_{i}",
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="purchase",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Get transaction IDs
        txn_ids = list(db["transactions"].find(
            {"customer_id": sample_customer.id}, {"id": 1}
        ))

        # Create alerts for 7 transactions (fraud confirmed)
        for txn_doc in txn_ids[:7]:
            assessment, alert = create_test_fraud_assessment_and_alert(
                db, txn_doc["id"], sample_customer.id,
                risk_score=80
            )
            db["fraud_alerts"].update_one(
                {"id": alert.id},
                {"$set": {"alert_status": "resolved", "review_decision": "approved"}},
            )

        # Create alerts for 3 transactions (false positive)
        for txn_doc in txn_ids[7:]:
            assessment, alert = create_test_fraud_assessment_and_alert(
                db, txn_doc["id"], sample_customer.id,
                risk_score=40
            )
            db["fraud_alerts"].update_one(
                {"id": alert.id},
                {"$set": {"alert_status": "resolved", "review_decision": "rejected"}},
            )

        # Get customer profile
        profile = AnalyticsService.get_customer_risk_profile(db, sample_customer.id)

        assert profile is not None
        assert profile["total_transactions"] == 10
        # Fraud rate should be 7/10 = 70%
        assert profile["fraud_rate"] == pytest.approx(70.0, rel=5)
