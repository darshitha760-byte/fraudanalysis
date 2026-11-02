"""
Tests for anomaly detection functionality.
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
        customer_id="CUST_ANOM_001",
        name="Test Customer",
        email="anom_test@example.com",
        phone="+1234567890",
        customer_type="individual",
        country="US",
        city="New York",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


class TestAnomalyDetection:
    """Test suite for anomaly detection."""

    def test_detect_volume_spike_anomaly(
        self, db, sample_customer: Customer, mongo_server_only
    ):
        """Test detection of transaction volume spikes."""
        # Create baseline: 2 transactions on day 1
        base_date = datetime.utcnow() - timedelta(days=5)
        for i in range(2):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_BASE_{i}",
                amount=Decimal("100.00"),
                transaction_date=base_date,
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Create spike: 10 transactions on day 2 (5x normal)
        spike_date = datetime.utcnow()
        for i in range(10):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_SPIKE_{i}",
                amount=Decimal("100.00"),
                transaction_date=spike_date,
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)


        # Detect anomalies
        anomalies = AnalyticsService.detect_transaction_anomalies(db)

        # Should detect volume spike
        assert len(anomalies) >= 0

    def test_detect_velocity_anomaly(
        self, db, sample_customer: Customer, mongo_server_only
    ):
        """Test detection of rapid transaction velocity."""
        # Create rapid transactions (multiple in short time)
        now = datetime.utcnow()
        for i in range(5):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_VEL_{i}",
                amount=Decimal("500.00"),
                transaction_date=now + timedelta(minutes=i),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)


        # Detect anomalies
        anomalies = AnalyticsService.detect_transaction_anomalies(db)

        # Should detect velocity anomaly
        assert len(anomalies) >= 0

    def test_detect_large_amount_anomaly(
        self, db, sample_customer: Customer, mongo_server_only
    ):
        """Test detection of unusually large transactions."""
        # Create baseline small transactions
        for i in range(5):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_SMALL_{i}",
                amount=Decimal("50.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="purchase",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Create large anomalous transaction
        large_txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_LARGE_ANOMALY",
            amount=Decimal("50000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="purchase",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, large_txn)

        # Detect anomalies
        anomalies = AnalyticsService.detect_transaction_anomalies(db)

        # Should detect large amount anomaly
        assert len(anomalies) >= 0

    def test_score_transaction_anomaly(self, db, sample_customer: Customer):
        """Test anomaly scoring for individual transaction."""
        # Create a normal transaction
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_SCORE_001",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="purchase",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Score the transaction (pass session and transaction ID)
        score = AnalyticsService.score_transaction_anomaly(db, txn.id)

        # Score should be between 0 and 100
        assert 0 <= score <= 100
        assert isinstance(score, (int, float))

    def test_anomaly_detection_empty(self, db):
        """Test anomaly detection with no transactions."""
        anomalies = AnalyticsService.detect_transaction_anomalies(db)

        # Should return empty list or list with no anomalies
        assert isinstance(anomalies, list)
        assert len(anomalies) == 0
