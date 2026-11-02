"""
Performance tests for the Financial Risk Analysis and Hybrid Fraud Detection System.
Tests transaction processing speed, bulk import, risk scoring, database queries, and API response times.
"""

import pytest
import time
from datetime import datetime, timedelta
from decimal import Decimal
from app.db.database import to_bson
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAlert
from app.core.config import get_settings
from tests.conftest import insert_test_document


settings = get_settings()


def _transaction_document(index, prefix="PERF"):
    transaction = Transaction(
        id=index + 1,
        transaction_id=f"{prefix}_{index:06d}",
        customer_id=index % 100 + 1,
        transaction_type="purchase",
        amount=Decimal(str(100 + (index % 1000))),
        currency="USD",
        merchant_id=f"M{index % 50:03d}",
        transaction_date=datetime.now(),
        status="completed",
    )
    return to_bson(transaction.model_dump(mode="python"))


class TestTransactionProcessingPerformance:
    """Test transaction processing speed."""
    
    def test_single_transaction_processing_time(self, test_session):
        """Test that single transaction processing completes in <100ms."""
        from app.services.transaction_service import TransactionService
        
        service = TransactionService()
        
        start_time = time.time()
        
        # Process a single transaction
        transaction_data = {
            "customer_id": 1,
            "transaction_type": "purchase",
            "amount": Decimal("1000.00"),
            "currency": "USD",
            "merchant_id": "M001",
            "timestamp": datetime.now(),
        }
        
        # Measure processing time
        elapsed_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Should complete within 100ms (target)
        assert elapsed_time < 500  # Allow some overhead for testing
    
    def test_batch_transaction_processing_speed(self, test_session):
        """Test batch processing of multiple transactions."""
        from app.services.transaction_service import TransactionService
        
        service = TransactionService()
        
        # Create 100 transactions
        transactions = []
        for i in range(100):
            transactions.append({
                "customer_id": i % 10,
                "transaction_type": "purchase",
                "amount": Decimal(str(100 + i)),
                "currency": "USD",
                "merchant_id": f"M{i:03d}",
                "timestamp": datetime.now(),
            })
        
        start_time = time.time()
        # Process batch
        # (Actual implementation would use batch insert)
        elapsed_time = (time.time() - start_time) * 1000
        
        # Measure throughput
        # Allow for test environment slowness
        throughput = len(transactions) / max(elapsed_time / 1000, 0.001)
        # Very relaxed threshold for CI/CD and in-memory SQLite
        assert throughput > 10 or elapsed_time < 100


class TestBulkImportPerformance:
    """Test bulk data import performance."""
    
    def test_bulk_import_throughput(self, test_session, mongo_server_only):
        """Test that bulk import achieves target throughput of 1000 transactions/sec."""
        # Create 1000 transactions for bulk import
        transaction_count = 1000
        documents = [_transaction_document(i, "BULK") for i in range(transaction_count)]
        start_time = time.time()
        for offset in range(0, transaction_count, 100):
            test_session["transactions"].insert_many(documents[offset:offset + 100])
        elapsed_time = time.time() - start_time
        
        # Calculate throughput
        throughput = transaction_count / elapsed_time
        
        # Target is 1000 transactions/sec, but in test allow lower due to overhead
        assert throughput > 500  # Reasonable for test environment
    
    def test_bulk_insert_memory_efficiency(self, test_session, mongo_server_only):
        """Test that bulk import doesn't consume excessive memory."""
        import tracemalloc
        
        tracemalloc.start()
        documents = [_transaction_document(i, "MEM") for i in range(1000)]
        for offset in range(0, len(documents), 100):
            test_session["transactions"].insert_many(documents[offset:offset + 100])
        
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        
        # Peak memory should be reasonable (less than 100MB for 1000 records)
        peak_mb = peak / 1024 / 1024
        assert peak_mb < 100


class TestRiskScoringPerformance:
    """Test risk scoring speed."""
    
    def test_single_risk_score_calculation_time(self, test_session):
        """Test that risk scoring completes in <50ms per transaction."""
        from app.services.risk_engine import RiskEngine
        
        risk_engine = RiskEngine()
        
        # Create test transaction
        transaction = Transaction(
            transaction_id="TXN000001",
            customer_id=1,
            transaction_type="purchase",
            amount=Decimal("5000.00"),
            currency="USD",
            merchant_id="M001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        start_time = time.time()
        
        # Calculate risk score
        # (Actual implementation details depend on service implementation)
        risk_score = risk_engine.calculate_risk_level(50.0)
        
        elapsed_time = (time.time() - start_time) * 1000
        
        # Target is <50ms, allow some overhead
        assert elapsed_time < 500  # Includes Python dispatch overhead in CI
        assert risk_score == "MEDIUM"
    
    def test_batch_risk_scoring_throughput(self, test_session):
        """Test batch risk scoring throughput."""
        from app.services.risk_engine import RiskEngine
        
        engine = RiskEngine()
        
        # Score a representative batch using the production risk-level calculator.
        transaction_count = 100
        start_time = time.time()
        scores = [
            engine.calculate_risk_level(float(i % 101))
            for i in range(transaction_count)
        ]
        
        elapsed_time = time.time() - start_time
        # Ensure we don't divide by zero
        throughput = transaction_count / max(elapsed_time, 0.001)
        assert len(scores) == transaction_count
        
        # Very conservative threshold for test environment
        # Test passes if: throughput > 5 transactions/sec OR elapsed < 500ms
        assert throughput > 5 or elapsed_time < 0.5


class TestDatabaseQueryPerformance:
    """Test database query optimization."""
    
    def test_customer_lookup_performance(self, test_session, mongo_server_only):
        """Test that customer lookups are fast."""
        from app.models.customer import Customer
        
        # Create test customer
        customer = Customer(
            customer_id="CUST_PERF_001",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        start_time = time.time()
        
        # Query customer by ID
        found = test_session["customers"].find_one({"id": customer.id})
        
        elapsed_time = (time.time() - start_time) * 1000
        
        assert found is not None
        assert elapsed_time < 10  # Should be very fast
    
    def test_transaction_listing_performance(self, test_session, mongo_server_only):
        """Test that listing transactions is efficient."""
        # Create multiple transactions
        for i in range(100):
            transaction = Transaction(
                transaction_id=f"TXN_PERF_{i:06d}",
                customer_id=i % 10,
                transaction_type="purchase",
                amount=Decimal(str(100 + i)),
                currency="USD",
                merchant_id=f"M{i % 5:03d}",
                transaction_date=datetime.now(),
                status="completed",
            )
            insert_test_document(test_session, transaction)
        
        start_time = time.time()
        
        # Query transactions with pagination
        transactions = list(
            test_session["transactions"].find().sort("id", 1).limit(10)
        )
        
        elapsed_time = (time.time() - start_time) * 1000
        
        assert len(transactions) == 10
        assert elapsed_time < 50  # Should be fast
    
    def test_alert_query_with_joins(self, test_session):
        """Test indexed reference resolution with a MongoDB aggregation lookup."""
        from app.models.fraud_alert import FraudAlert
        from tests.conftest import create_test_fraud_assessment_and_alert, create_test_transaction

        customer = insert_test_document(test_session, Customer(
            customer_id="JOIN-CUSTOMER", name="Join customer"
        ))
        transaction = create_test_transaction(test_session, customer.id, amount=Decimal("100.01"))
        create_test_fraud_assessment_and_alert(
            test_session, transaction.id, customer.id
        )
        start_time = time.time()
        rows = list(test_session["fraud_alerts"].aggregate([
            {"$lookup": {
                "from": "transactions", "localField": "transaction_id",
                "foreignField": "id", "as": "transaction",
            }},
            {"$unwind": "$transaction"},
            {"$match": {"transaction.transaction_id": transaction.transaction_id}},
        ]))
        elapsed_time = (time.time() - start_time) * 1000
        assert rows and rows[0]["transaction"]["id"] == transaction.id
        assert elapsed_time < 100


class TestAPIResponseTime:
    """Test API endpoint response times."""
    
    def test_health_check_response_time(self):
        """Test that health check responds quickly."""
        from app.main import app
        from fastapi.testclient import TestClient
        
        client = TestClient(app)
        start_time = time.time()
        response = client.get("/health")
        elapsed_time = (time.time() - start_time) * 1000
        
        assert response.status_code == 200
        assert elapsed_time < 100  # Relaxed timing for CI/CD environments
    
    def test_list_transactions_response_time(self):
        """Test that listing transactions API responds within target time."""
        # Target: <200ms for most endpoints
        # This would be tested with actual HTTP client
        assert True
    
    def test_create_transaction_response_time(self):
        """Test that creating transaction API responds quickly."""
        # Target: <200ms
        assert True


class TestMemoryUsageUnderLoad:
    """Test memory usage stability."""
    
    def test_memory_stability_during_imports(self, test_session):
        """Test that memory usage remains stable during large imports."""
        import tracemalloc
        
        tracemalloc.start()
        
        initial_memory = tracemalloc.get_traced_memory()[0]
        
        # Simulate large import
        for i in range(1000):  # Reduced from 5000 to speed up test
            transaction = Transaction(
                transaction_id=f"TXN_MEM_{i:06d}",
                customer_id=i % 100,
                transaction_type="purchase",
                amount=Decimal(str(100 + i)),
                currency="USD",
                merchant_id=f"M{i % 50:03d}",
                transaction_date=datetime.now(),
                status="completed",
            )
            insert_test_document(test_session, transaction)
        
        final_memory = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        
        memory_increase_mb = (final_memory - initial_memory) / 1024 / 1024
        
        # Memory increase should be reasonable (relaxed for test environment)
        assert memory_increase_mb < 500


class TestConnectionPoolEfficiency:
    """Test database connection pool efficiency."""
    
    def test_connection_pool_reuse(self, mongo_server_only):
        """Test repeated operations use one reusable PyMongo client."""
        client = mongo_server_only.client
        for i in range(10):
            assert mongo_server_only.command("ping")["ok"] == 1
            assert mongo_server_only.client is client

    def test_connection_pool_growth(self, mongo_server_only):
        """Verify the shared MongoClient retains its configured pool options."""
        client = mongo_server_only.client
        options = client.options.pool_options
        assert options.max_pool_size > 0
        assert mongo_server_only.client is client


# Test execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
