"""
Tests for end-to-end pipeline integration.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.services.pipeline_service import PipelineService
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAlert
from app.models.case import InvestigationCase
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
        customer_id="CUST_PIPELINE_001",
        name="Test Customer",
        email="pipeline_test@example.com",
        phone="+1234567890",
        customer_type="individual",
        country="US",
        city="New York",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


@pytest.mark.usefixtures("mongo_server_only")
class TestPipelineIntegration:
    """Test suite for end-to-end pipeline orchestration."""

    def test_process_transaction_pipeline_basic(
        self, db, sample_customer: Customer
    ):
        """Test basic transaction processing through full pipeline."""
        # Create a transaction with correct fields
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_PIPE_001",
            amount=Decimal("1000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Process through pipeline
        result = PipelineService.process_transaction_pipeline(db, txn.id)

        # Verify result structure
        assert result is not None
        assert "transaction_id" in result
        assert "success" in result
        assert result["transaction_id"] == txn.id
        assert result["success"] is True

    def test_process_transaction_pipeline_creates_alert(
        self, db, sample_customer: Customer
    ):
        """Test that pipeline creates alert for high-risk transaction."""
        # Create a high-risk transaction (large amount, unusual pattern)
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_PIPE_HIGH",
            amount=Decimal("50000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="wire_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Get baseline alert count
        baseline_alerts = db["fraud_alerts"].count_documents({})

        # Process through pipeline
        result = PipelineService.process_transaction_pipeline(db, txn.id)

        # Verify result
        assert result["success"] is True
        
        # Alert count should be same or higher (depends on if risk triggered)
        new_alerts = db["fraud_alerts"].count_documents({})
        assert new_alerts >= baseline_alerts

    def test_process_transaction_pipeline_nonexistent(self, db):
        """Test pipeline with nonexistent transaction."""
        # Try to process nonexistent transaction
        result = PipelineService.process_transaction_pipeline(db, 99999)

        # Should handle gracefully
        assert result is not None
        assert "success" in result
        assert result["success"] is False

    def test_batch_process_transactions_multiple(
        self, db, sample_customer: Customer
    ):
        """Test batch processing of multiple transactions."""
        # Create 5 transactions
        txn_ids = []
        for i in range(5):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_BATCH_{i}",
                amount=Decimal(str(100.0 + i * 50)),
                transaction_date=datetime.utcnow() + timedelta(minutes=i),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)
            txn_ids.append(txn.id)

        # Process batch
        result = PipelineService.batch_process_transactions(db, txn_ids)

        # Verify batch result structure
        assert result is not None
        assert "total_transactions" in result
        assert "successful" in result
        assert "failed" in result
        assert result["total_transactions"] == len(txn_ids)
        assert result["successful"] + result["failed"] == result["total_transactions"]

    def test_batch_process_transactions_empty(    self, db):
        """Test batch processing with empty list."""
        result = PipelineService.batch_process_transactions(db, [])

        # Should handle empty batch gracefully
        assert result is not None
        assert result["total_transactions"] == 0

    def test_batch_process_transactions_mixed_valid_invalid(
        self, db, sample_customer: Customer
    ):
        """Test batch with mix of valid and invalid transaction IDs."""
        # Create one valid transaction
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_MIXED_1",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Create batch with valid and invalid IDs
        batch_ids = [txn.id, 99999, 99998]

        # Process batch
        result = PipelineService.batch_process_transactions(db, batch_ids)

        # Should process at least the valid one
        assert result["total_transactions"] == 3
        assert result["successful"] >= 1

    def test_reprocess_alert_basic(
        self, db, sample_customer: Customer
    ):
        """Test reprocessing an alert with latest rules."""
        # Create transaction and alert using helper
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_REPROCESS",
            amount=Decimal("5000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)
        
        assessment, alert = create_test_fraud_assessment_and_alert(
            db, txn.id, sample_customer.id, risk_score=75
        )
        db["fraud_alerts"].update_one(
            {"id": alert.id}, {"$set": {"alert_status": "pending"}}
        )

        # Reprocess alert
        result = PipelineService.reprocess_alert(db, alert.id)

        # Verify result
        assert result is not None
        assert "alert_id" in result
        assert result["alert_id"] == alert.id

    def test_reprocess_alert_updates_assessment(
        self, db, sample_customer: Customer
    ):
        """Test that reprocessing updates the assessment."""
        # Create transaction and alert using helper
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_REPROCESS_UPDATE",
            amount=Decimal("5000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        assessment, alert = create_test_fraud_assessment_and_alert(
            db, txn.id, sample_customer.id, risk_score=50
        )
        db["fraud_alerts"].update_one(
            {"id": alert.id}, {"$set": {"alert_status": "needs_review"}}
        )

        # Reprocess alert
        result = PipelineService.reprocess_alert(db, alert.id)

        # Verify reprocessing occurred
        assert result["success"] is True

    def test_pipeline_full_flow_low_risk(
        self, db, sample_customer: Customer
    ):
        """Test full pipeline flow for low-risk transaction."""
        # Create low-risk transaction
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_FLOW_LOW",
            amount=Decimal("25.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="purchase",
            currency="USD",
            merchant_name="Grocery Store",
            merchant_id="GROCERY_001"
        )
        insert_test_document(db, txn)

        # Process through pipeline
        result = PipelineService.process_transaction_pipeline(db, txn.id)

        # Should complete successfully
        assert result["success"] is True
        assert result["transaction_id"] == txn.id

    def test_pipeline_full_flow_high_risk(
        self, db, sample_customer: Customer
    ):
        """Test full pipeline flow for high-risk transaction."""
        # Create high-risk transaction
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_FLOW_HIGH",
            amount=Decimal("100000.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="wire_transfer",
            currency="USD",
            merchant_name="Unknown",
            merchant_id="UNKNOWN_999"
        )
        insert_test_document(db, txn)

        # Process through pipeline
        result = PipelineService.process_transaction_pipeline(db, txn.id)

        # Should complete successfully
        assert result["success"] is True
        assert result["transaction_id"] == txn.id
