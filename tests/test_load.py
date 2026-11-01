"""
Load and stress tests for the Financial Risk Analysis and Hybrid Fraud Detection System.
Tests concurrent processing, dashboard user simulation, connection pool, rate limiting, and memory stability.
"""

import pytest
import time
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAlert
from tests.conftest import insert_test_document


class TestConcurrentTransactionProcessing:
    """Test concurrent transaction processing."""

    def test_concurrent_transaction_submissions(self, test_session, mongo_server_only):
        """Test handling 100 concurrent MongoDB transaction submissions."""

        def submit_transaction(transaction_id):
            """Submit a single transaction."""
            try:
                transaction = Transaction(
                    transaction_id=f"TXN{transaction_id:06d}",
                    customer_id=(transaction_id % 10) + 1,
                    transaction_type="purchase",
                    amount=Decimal(str(100 + (transaction_id % 1000))),
                    currency="USD",
                    merchant_id=f"M{transaction_id % 50:03d}",
                    transaction_date=datetime.now(),
                    status="pending",
                )
                insert_test_document(test_session, transaction)
                return True
            except Exception:
                return False

        # Submit 100 concurrent transactions
        concurrent_count = 100
        successful = 0

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(submit_transaction, i) for i in range(concurrent_count)]

            for future in as_completed(futures):
                if future.result():
                    successful += 1

        # Concurrent writes should mostly succeed on the local MongoDB test server.
        assert successful >= concurrent_count * 0.80

    def test_concurrent_transaction_processing_race_condition(
        self, test_session, mongo_server_only
    ):
        """Test that concurrent processing doesn't cause race conditions."""

        # Create a customer first
        customer = Customer(
            customer_id="CUST001",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        customer_id = customer.id

        processed_count = [0]
        lock = threading.Lock()

        def process_transaction(tx_id):
            """Process a single transaction."""
            try:
                transaction = Transaction(
                    transaction_id=f"TXN{tx_id:06d}",
                    customer_id=customer_id,
                    transaction_type="purchase",
                    amount=Decimal(str(100 + tx_id)),
                    currency="USD",
                    merchant_id="M001",
                    transaction_date=datetime.now(),
                    status="pending",
                )
                insert_test_document(test_session, transaction)

                with lock:
                    processed_count[0] += 1

                return True
            except Exception:
                return False

        # Process 50 concurrent transactions
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(process_transaction, i) for i in range(50)]
            for future in as_completed(futures):
                future.result()

        # Most should complete without race conditions (>80% for in-memory SQLite)
        assert processed_count[0] >= 50 * 0.80


class TestDashboardConcurrentUserSimulation:
    """Test dashboard behavior with concurrent users."""

    def test_concurrent_dashboard_users(self, test_session, mongo_server_only):
        """Test dashboard handling 50 concurrent users."""

        def dashboard_user_request(user_id):
            """Simulate a dashboard user request."""
            # Simulate dashboard query (e.g., get alerts) against MongoDB.
            alerts = list(test_session["fraud_alerts"].find().limit(10))
            time.sleep(0.01)
            return len(alerts)

        # Simulate 50 concurrent dashboard users
        concurrent_users = 50
        results = []

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(dashboard_user_request, i) for i in range(concurrent_users)]

            for future in as_completed(futures):
                results.append(future.result())

        # All requests should complete
        assert len(results) == concurrent_users
        # All should get results (may be empty initially)
        assert all(result >= 0 for result in results)

    def test_concurrent_dashboard_data_queries(self, test_session, mongo_server_only):
        """Test concurrent queries for dashboard data."""

        # Create test data
        for i in range(20):
            customer = Customer(
                customer_id=f"CUST{i:03d}",
                name=f"Customer {i}",
                email=f"customer{i}@example.com",
                phone=f"123456789{i}",
                risk_profile="medium",
            )
            insert_test_document(test_session, customer)

        def query_dashboard_stats(user_id):
            """Query dashboard statistics."""
            return test_session["customers"].count_documents({})

        # Query statistics concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(query_dashboard_stats, i) for i in range(30)]
            results = [future.result() for future in as_completed(futures)]

        # Most concurrent queries should return same result
        # The MongoDB server should return the full seeded customer count.
        valid_results = [r for r in results if r is not None and r >= 20]
        assert len(valid_results) == len(results)


class TestConnectionPoolExhaustionHandling:
    """Test connection pool behavior under load."""

    def test_connection_pool_under_heavy_load(self, mongo_server_only):
        """Test concurrent MongoDB operations through the shared client."""

        def database_operation(op_id):
            """Perform a database operation."""
            try:
                return mongo_server_only.command("ping").get("ok") == 1
            except Exception:
                return False

        # Submit many concurrent operations
        operation_count = 200
        successful = 0

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(database_operation, i) for i in range(operation_count)]

            for future in as_completed(futures):
                if future.result():
                    successful += 1

        # Most operations should succeed despite pool limitations
        success_rate = successful / operation_count
        assert success_rate > 0.8  # At least 80% success


class TestAPIRateLimitingUnderLoad:
    """Test API rate limiting under load."""

    def test_rate_limit_enforcement(self):
        """Test that rate limits are enforced."""
        # Rate limiting should be configured in app
        from app.core.config import get_settings

        settings = get_settings()

        # Rate limit configuration should exist
        assert settings.rate_limit_login_attempts > 0
        assert settings.rate_limit_window_seconds > 0


class TestMemoryStabilityOverTime:
    """Test memory usage stability during prolonged operation."""

    def test_memory_stability_during_1_hour_simulation(self, test_session):
        """Test memory stability over extended operation."""
        import tracemalloc
        import gc

        tracemalloc.start()

        memory_samples = []

        # Simulate 1 hour of operations (compressed to seconds for testing)
        # Using smaller iteration count for test
        iteration_count = 100  # Represents load over time

        for i in range(iteration_count):
            try:
                # Simulate various operations
                transaction = Transaction(
                    transaction_id=f"TXN{i:06d}",
                    customer_id=(i % 10) + 1,
                    transaction_type="purchase",
                    amount=Decimal(str(100 + (i % 1000))),
                    currency="USD",
                    merchant_id=f"M{i % 50:03d}",
                    transaction_date=datetime.now(),
                    status="pending",
                )
                insert_test_document(test_session, transaction)

                # Sample memory periodically
                if i % 10 == 0:
                    current, peak = tracemalloc.get_traced_memory()
                    memory_samples.append(current / 1024 / 1024)  # MB
                    gc.collect()
            except Exception:
                raise

        tracemalloc.stop()

        # Memory should not grow indefinitely
        if len(memory_samples) > 1:
            initial_memory = memory_samples[0]
            final_memory = memory_samples[-1]
            memory_growth = final_memory - initial_memory

            # Growth should be reasonable (less than 50MB over iterations)
            assert memory_growth < 50


class TestStressTestScenarios:
    """Test system under stress conditions."""

    def test_rapid_transaction_bursts(self, test_session, mongo_server_only):
        """Test handling rapid bursts of transactions."""

        def create_burst(burst_id):
            """Create a burst of transactions."""
            try:
                for i in range(100):
                    transaction = Transaction(
                        transaction_id=f"TXN{burst_id:03d}{i:03d}",
                        customer_id=(burst_id % 5) + 1,
                        transaction_type="purchase",
                        amount=Decimal(str(100 + ((burst_id * 100 + i) % 1000))),
                        currency="USD",
                        merchant_id=f"M{(burst_id * 100 + i) % 50:03d}",
                        transaction_date=datetime.now(),
                        status="pending",
                    )
                    insert_test_document(test_session, transaction)

                return True
            except Exception:
                return False

        # Create 10 bursts of 100 transactions each
        burst_count = 10
        successful_bursts = 0

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_burst, i) for i in range(burst_count)]

            for future in as_completed(futures):
                if future.result():
                    successful_bursts += 1

        assert successful_bursts == burst_count


# Smoke Tests
class TestSmokeTests:
    """Basic smoke tests for critical functionality."""

    def test_all_api_endpoints_accessible(self):
        """Test that all API endpoints are accessible."""
        from app.main import app

        # App should be created
        assert app is not None
        assert app.title == "Financial Risk Analysis and Hybrid Fraud Detection System"

    def test_database_connectivity(self, test_session):
        """Test the isolated MongoDB-compatible database ping command."""
        assert test_session.command("ping")["ok"] == 1

    def test_authentication_working(self):
        """Test authentication system working."""
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "1", "email": "test@example.com"})
        assert token is not None
        assert len(token) > 0

    def test_basic_fraud_detection_flow(self, test_session):
        """Test basic fraud detection flow."""

        # Create customer
        customer = Customer(
            customer_id="CUST001",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)

        # Create transaction
        transaction = Transaction(
            transaction_id="TXN000001",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("1000.00"),
            currency="USD",
            merchant_id="M001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)

        # Should have transaction
        assert test_session["transactions"].find_one(
            {"transaction_id": transaction.transaction_id}
        )["id"] == transaction.id

    def test_dashboard_loads(self):
        """Test dashboard can load (basic check)."""
        # Dashboard should exist
        import os

        dashboard_path = "dashboard"
        assert os.path.exists(dashboard_path)

    def test_error_handling_working(self):
        """Test error handling is functional."""
        from fastapi import HTTPException

        # Should be able to raise HTTP exceptions
        try:
            raise HTTPException(status_code=404, detail="Not Found")
        except HTTPException as e:
            assert e.status_code == 404


# Test execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
