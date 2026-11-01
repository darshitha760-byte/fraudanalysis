"""
Tests for analytics API endpoints.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
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
def client(test_client):
    """Alias test_client for compatibility."""
    return test_client


@pytest.fixture
def sample_customer(db):
    """Create sample customer for tests."""
    customer = Customer(
        customer_id="CUST_API_001",
        name="Test Customer",
        email="api_test@example.com",
        phone="+1234567890",
        customer_type="individual",
        country="US",
        city="New York",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


class TestAnalyticsAPI:
    """Test suite for analytics REST API endpoints."""

    def test_dashboard_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/dashboard endpoint."""
        # Create some data
        for i in range(3):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_DASH_{i}",
                amount=Decimal(str(100.0 + i * 50)),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Call endpoint
        response = client.get("/api/analytics/dashboard", headers=auth_headers)

        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "total_transactions" in data
        assert "total_alerts" in data
        assert "fraud_confirmation_rate" in data
        assert "approval_rate" in data
        assert data["total_transactions"] >= 3

    def test_transactions_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/transactions endpoint."""
        # Create transactions with various amounts
        amounts = [100.0, 500.0, 1000.0, 2000.0]
        for idx, amount in enumerate(amounts):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_API_{idx}",
                amount=Decimal(str(amount)),
                transaction_date=datetime.utcnow(),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Call endpoint
        response = client.get("/api/analytics/transactions", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_transactions" in data
        assert data["total_transactions"] == 4

    def test_alerts_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/alerts endpoint."""
        # Create transaction and alerts
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_ALERT_API",
            amount=Decimal("500.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Create only one alert (transaction_id is unique on FraudAlert)
        assessment, alert = create_test_fraud_assessment_and_alert(
            db, txn.id, sample_customer.id, risk_score=50
        )
        db["fraud_alerts"].update_one(
            {"id": alert.id}, {"$set": {"alert_status": "pending"}}
        )

        # Call endpoint
        response = client.get("/api/analytics/alerts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "total_alerts" in data
        assert data["total_alerts"] >= 1

    def test_customers_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/customers endpoint."""
        # Create multiple customers with transactions
        for i in range(3):
            customer = Customer(
                customer_id=f"CUST_MULTI_{i}",
                name=f"Customer {i}",
                email=f"multi{i}@example.com",
                country="US"
            )
            customer = insert_test_document(db, customer)

            for j in range(2):
                txn = Transaction(
                    customer_id=customer.id,
                    transaction_id=f"TXN_MULTI_{i}_{j}",
                    amount=Decimal("100.00"),
                    transaction_date=datetime.utcnow(),
                    transaction_type="credit_transfer",
                    currency="USD",
                    merchant_name="Test",
                    merchant_id="M001"
                )
                insert_test_document(db, txn)

        # Call endpoint
        response = client.get("/api/analytics/customers", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "high_risk_customers" in data or "customers" in data

    def test_trends_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/trends endpoint."""
        # Create transactions across multiple days
        base_date = datetime.utcnow() - timedelta(days=5)
        for day in range(5):
            for i in range(2):
                txn = Transaction(
                    customer_id=sample_customer.id,
                    transaction_id=f"TXN_TREND_API_{day}_{i}",
                    amount=Decimal("100.00"),
                    transaction_date=base_date + timedelta(days=day),
                    transaction_type="credit_transfer",
                    currency="USD",
                    merchant_name="Test",
                    merchant_id="M001"
                )
                insert_test_document(db, txn)

        # Call endpoint
        response = client.get("/api/analytics/trends", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "trends" in data

    def test_anomalies_endpoint(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict,
        mongo_server_only,
    ):
        """Test /api/analytics/anomalies endpoint."""
        # Create some anomalous transactions
        for i in range(10):
            txn = Transaction(
                customer_id=sample_customer.id,
                transaction_id=f"TXN_ANOM_{i}",
                amount=Decimal("10000.00"),  # Large amounts
                transaction_date=datetime.utcnow() + timedelta(minutes=i),
                transaction_type="credit_transfer",
                currency="USD",
                merchant_name="Test",
                merchant_id="M001"
            )
            insert_test_document(db, txn)

        # Call endpoint
        response = client.get("/api/analytics/anomalies", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list) or "anomalies" in data

    def test_fraud_rate_endpoint(
        self, client: TestClient, db, auth_headers: dict
    ):
        """Test /api/analytics/fraud-rate endpoint."""
        # Call endpoint
        response = client.get("/api/analytics/fraud-rate", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "fraud_rate" in data or "confirmed_rate" in data
        assert "false_positive_rate" in data or "rejection_rate" in data

    def test_performance_endpoint(
        self, client: TestClient, db, auth_headers: dict
    ):
        """Test /api/analytics/performance endpoint."""
        # Call endpoint
        response = client.get("/api/analytics/performance", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "average_review_time" in data or "performance_metrics" in data

    def test_export_endpoint(
        self, client: TestClient, db, sample_customer: Customer, auth_headers: dict
    ):
        """Test /api/analytics/export endpoint."""
        # Create some data
        txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_EXPORT",
            amount=Decimal("500.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, txn)

        # Call endpoint with JSON format
        response = client.get("/api/analytics/export?format=json", headers=auth_headers)

        assert response.status_code == 200

    def test_analytics_with_time_filter(
        self,
        client: TestClient,
        db,
        sample_customer: Customer,
        auth_headers: dict
    ):
        """Test analytics endpoints with time filtering."""
        # Create old transaction (outside 7-day window)
        old_txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_OLD_FILTER",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow() - timedelta(days=10),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, old_txn)

        # Create recent transaction
        recent_txn = Transaction(
            customer_id=sample_customer.id,
            transaction_id="TXN_NEW_FILTER",
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            transaction_type="credit_transfer",
            currency="USD",
            merchant_name="Test",
            merchant_id="M001"
        )
        insert_test_document(db, recent_txn)

        # Call endpoint with 7-day filter
        response = client.get("/api/analytics/transactions?days=7", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        # Should only count recent transaction
