"""
Tests for transaction analytics functionality.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.analytics_service import AnalyticsService
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAlert, FraudAssessment
from tests.conftest import create_test_fraud_assessment_and_alert
from tests.conftest import insert_test_document


def test_statistics_batches_assessments_instead_of_querying_per_transaction(
    db, sample_customer, monkeypatch, mongo_server_only
):
    transactions = [
        Transaction(
            customer_id=sample_customer.id, transaction_id=f"QUERY_BOUND_{index}",
            amount=100, transaction_date=datetime.now(),
        )
        for index in range(100)
    ]
    for transaction in transactions:
        insert_test_document(db, transaction)
    for transaction in transactions[:50]:
        insert_test_document(db, FraudAssessment(
            transaction_id=transaction.id, risk_score=80, risk_category="high"
        ))
    collection_type = type(db["transactions"])
    aggregate = collection_type.aggregate
    pipelines = []

    def observe_aggregate(collection, pipeline, *args, **kwargs):
        if collection.name == "transactions":
            pipelines.append(pipeline)
        return aggregate(collection, pipeline, *args, **kwargs)

    # PyMongo creates a fresh Collection wrapper for each db["transactions"]
    # access, so patch the class method rather than one transient instance.
    monkeypatch.setattr(collection_type, "aggregate", observe_aggregate)
    result = AnalyticsService.get_transaction_statistics(db)
    assert result["total_transactions"] == 100
    assert result["high_risk_transactions"] == 50
    assert len(pipelines) == 1
    assert any("$lookup" in stage for stage in pipelines[0])


@pytest.fixture
def db(test_session):
    """Alias test_session as db for compatibility."""
    yield test_session


@pytest.fixture
def sample_customer(db):
    """Create sample customer for tests."""
    customer = Customer(
        customer_id="CUST_TXN_001",
        name="Test Customer",
        email="txn_test@example.com",
        phone="+1234567890",
        customer_type="individual",
        country="US",
        city="New York",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


class TestTransactionAnalytics:
    """Test suite for transaction-level analytics."""

    def test_get_transaction_statistics_basic(self, db, sample_customer: Customer, mongo_server_only):
        """Test basic transaction statistics retrieval."""
        # Create sample transactions
        for i in range(5):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_STAT_{i}",
                amount=Decimal(str(100.0 + i * 10)),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test Merchant",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Get statistics
        stats = AnalyticsService.get_transaction_statistics(db, days=30)

        assert stats["total_transactions"] == 5
        assert stats["total_volume"] > 500  # 100 + 110 + 120 + 130 + 140
        assert stats["average_amount"] > 0
        assert "high_risk_transactions" in stats
        assert "medium_risk_transactions" in stats
        assert "low_risk_transactions" in stats

    def test_get_transaction_statistics_with_customer_filter(
        self, db, sample_customer: Customer, mongo_server_only
    ):
        """Test transaction statistics with customer filter."""
        # Create transactions for sample customer
        for i in range(3):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_FILT_{i}",
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Get statistics for specific customer
        stats = AnalyticsService.get_transaction_statistics(
            db, days=30, customer_id=sample_customer.id
        )

        assert stats["total_transactions"] == 3

    def test_get_transaction_statistics_counts_lowercase_assessment_categories(
        self,
        db,
        sample_customer: Customer,
        mongo_server_only,
    ):
        for index, category in enumerate(("low", "medium", "high")):
            transaction = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_CATEGORY_{index}",
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="purchase",
                currency="USD",
                status="completed",
            )
            insert_test_document(db, transaction)
            insert_test_document(
                db,
                FraudAssessment(
                    transaction_id=transaction.id,
                    risk_score=Decimal("20"),
                    risk_category=category,
                    rules_triggered_count=0,
                )
            )

        stats = AnalyticsService.get_transaction_statistics(db, days=30)

        assert stats["low_risk_transactions"] == 1
        assert stats["medium_risk_transactions"] == 1
        assert stats["high_risk_transactions"] == 1

    def test_get_transaction_trends(self, db, sample_customer: Customer, mongo_server_only):
        """Test daily transaction trends."""
        # Create transactions across multiple days
        base_date = datetime.utcnow() - timedelta(days=10)
        for day in range(5):
            for i in range(2):
                txn = Transaction(
                    customer_id=sample_customer.id,
                    transaction_id=f"TXN_TREND_{day}_{i}",
                    amount=Decimal(str(100.0 + i * 10)),
                    transaction_date=base_date + timedelta(days=day),
                    transaction_type="credit_transfer",
                    currency="USD",
                    merchant_name="Test",
                    merchant_id="M001"
                )
                insert_test_document(db, txn)

        # Get trends
        trends = AnalyticsService.get_transaction_trends(db, days=30)

        assert len(trends) > 0
        assert all("date" in t and "transaction_count" in t for t in trends)
        assert all(t["transaction_count"] >= 0 for t in trends)

    def test_get_risk_distribution(self, db, sample_customer: Customer, mongo_server_only):
        """Test risk score distribution."""
        # Create transactions and their fraud assessments/alerts to assign risk scores
        # Low risk transactions (0-30)
        for i in range(3):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_LOW_RISK_{i}",
                amount=Decimal("100.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)
            # Add assessment and alert with low risk score
            create_test_fraud_assessment_and_alert(
                db, txn.id, sample_customer.id,
                risk_score=20, risk_category="low"
            )

        # Medium risk transactions (31-70)
        for i in range(2):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_MED_RISK_{i}",
                amount=Decimal("500.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)
            create_test_fraud_assessment_and_alert(
                db, txn.id, sample_customer.id,
                risk_score=50, risk_category="medium"
            )

        # High risk transactions (71-100)
        for i in range(1):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_HIGH_RISK_{i}",
                amount=Decimal("5000.00"),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)
            create_test_fraud_assessment_and_alert(
                db, txn.id, sample_customer.id,
                risk_score=80, risk_category="high"
            )


        # Get distribution
        distribution = AnalyticsService.get_risk_distribution(db, days=30)

        assert distribution["LOW"] >= 3
        assert distribution["MEDIUM"] >= 2
        assert distribution["HIGH"] >= 1
        assert distribution["total"] == 6

    def test_transaction_statistics_empty(self, db):
        """Test statistics with no transactions."""
        stats = AnalyticsService.get_transaction_statistics(db, days=30)

        assert stats["total_transactions"] == 0
        assert stats["total_volume"] == 0
        assert stats["average_amount"] == 0

    def test_transaction_statistics_time_filtering(
        self, db, sample_customer: Customer
    ):
        """Test that statistics respects time window."""
        # Create old transaction
        old_txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_OLD",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow() - timedelta(days=40),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, old_txn)

        # Create recent transaction
        recent_txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_RECENT",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, recent_txn)

        # Get 30-day statistics (should exclude old transaction)
        stats = AnalyticsService.get_transaction_statistics(db, days=30)

        assert stats["total_transactions"] == 1
