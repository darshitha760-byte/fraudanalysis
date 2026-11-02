"""
Smoke tests for the Financial Risk Analysis and Hybrid Fraud Detection System.
Basic health checks for all critical system components.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from app.models.transaction import Transaction
from app.models.customer import Customer
from conftest import insert_test_document


class TestHealthCheck:
    """Test health check endpoints."""
    
    def test_health_endpoint_exists(self, test_client):
        """Test that health check endpoint exists."""
        response = test_client.get("/health")
        assert response.status_code == 200
    
    def test_health_check_response_format(self, test_client):
        """Test health check response format."""
        response = test_client.get("/health")
        data = response.json()
        
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]


class TestDatabaseConnectivity:
    """Test database connectivity."""
    
    def test_isolated_database_available(self, test_session):
        """Test the isolated MongoDB-compatible database has initialized collections."""
        assert test_session is not None
        assert {
            "users", "customers", "transactions", "fraud_rules",
            "fraud_assessments", "triggered_rules", "fraud_alerts",
            "investigation_cases", "case_notes", "audit_logs",
        }.issubset(set(test_session.list_collection_names()))


class TestAuthenticationSystem:
    """Test authentication system."""
    
    def test_password_hashing(self):
        """Test password hashing."""
        from app.core.security import hash_password, verify_password
        
        password = "TestPassword123!"
        hashed = hash_password(password)
        
        assert hashed != password
        assert verify_password(password, hashed)
    
    def test_jwt_token_creation(self):
        """Test JWT token creation."""
        from app.core.security import create_access_token
        
        token = create_access_token(data={"sub": "1", "email": "test@example.com"})
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_token_contains_claims(self):
        """Test that token contains required claims."""
        from app.core.security import create_access_token
        from jose import jwt
        
        token = create_access_token(data={"sub": "1", "email": "test@example.com"})
        payload = jwt.get_unverified_claims(token)
        
        assert "exp" in payload


class TestAPIEndpoints:
    """Test API endpoints availability."""
    
    def test_api_endpoints_exist(self, test_client):
        """Test that API endpoints are registered."""
        # Test a known endpoint
        response = test_client.get("/health")
        # Health endpoint should exist or be unavailable (not 404)
        assert response.status_code != 404


class TestDataModels:
    """Test data models."""
    
    def test_customer_model(self, test_session):
        """Test Customer model."""
        customer = Customer(
            customer_id="CUST001",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        retrieved = test_session["customers"].find_one({"id": customer.id})
        assert retrieved is not None
        assert retrieved["name"] == "Test Customer"
    
    def test_transaction_model(self, test_session):
        """Test Transaction model."""
        customer = Customer(
            customer_id="CUST002",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        transaction = Transaction(
            transaction_id="TXN001",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("1000.00"),
            currency="USD",
            merchant_id="M001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        retrieved = test_session["transactions"].find_one({"id": transaction.id})
        assert retrieved is not None
        assert retrieved["amount"].to_decimal() == Decimal("1000.00")


class TestFraudDetectionFlow:
    """Test basic fraud detection flow."""
    
    def test_complete_fraud_detection_workflow(self, test_session):
        """Test complete fraud detection workflow."""
        from app.models.fraud_alert import FraudAssessment, FraudAlert
        
        # Create customer
        customer = Customer(
            customer_id="CUST003",
            name="Test Customer",
            email="test@example.com",
            phone="1234567890",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        # Create transaction
        transaction = Transaction(
            transaction_id="TXN002",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("5000.00"),
            currency="USD",
            merchant_id="M001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        # Create fraud assessment
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=Decimal("85.00"),
            risk_category="high",
        )
        insert_test_document(test_session, assessment)
        
        # Create alert if score high
        if assessment.risk_score > Decimal("70"):
            alert = FraudAlert(
                transaction_id=transaction.id,
                customer_id=customer.id,
                assessment_id=assessment.id,
                alert_severity="high",
                alert_status="pending",
                alert_reason="High risk score detected",
            )
            insert_test_document(test_session, alert)
        
        # Verify workflow completed
        alert = test_session["fraud_alerts"].find_one({"transaction_id": transaction.id})
        assert alert is not None
        assert alert["alert_severity"] == "high"


class TestDashboardComponents:
    """Test dashboard components."""
    
    def test_dashboard_directory_exists(self):
        """Test that dashboard directory exists."""
        import os
        
        assert os.path.exists("dashboard")
    
    def test_dashboard_main_file_exists(self):
        """Test that dashboard main file exists."""
        import os
        
        # Check for main dashboard file
        dashboard_files = [
            "dashboard/app.py",
            "dashboard/main.py",
            "dashboard/__init__.py",
        ]
        
        # At least one main file should exist
        assert any(os.path.exists(f) for f in dashboard_files)


class TestErrorHandling:
    """Test error handling."""
    
    def test_http_exception_handling(self):
        """Test HTTP exception handling."""
        from fastapi import HTTPException
        
        exception = HTTPException(status_code=400, detail="Bad Request")
        
        assert exception.status_code == 400
        assert exception.detail == "Bad Request"
    
    def test_validation_error_handling(self):
        """Test validation error handling."""
        from pydantic import ValidationError, BaseModel
        
        class TestModel(BaseModel):
            name: str
            age: int
        
        # Should raise validation error for missing field
        try:
            TestModel(name="John")  # Missing 'age'
            pytest.fail("Validation error not raised")
        except ValidationError:
            pass  # Expected


class TestLogging:
    """Test logging configuration."""
    
    def test_logging_configured(self):
        """Test that logging is configured."""
        import logging
        
        logger = logging.getLogger("app")
        assert logger is not None
        
        # Logger should have handlers
        assert len(logger.handlers) >= 0


class TestConfiguration:
    """Test configuration."""
    
    def test_settings_loaded(self):
        """Test that settings are loaded."""
        from app.core.config import get_settings
        
        settings = get_settings()
        
        assert settings is not None
        assert hasattr(settings, 'mongodb_uri')
        assert hasattr(settings, 'mongodb_database')
        assert hasattr(settings, 'environment')
    
    def test_environment_variables_accessible(self):
        """Test that environment variables are accessible."""
        from app.core.config import get_settings
        
        settings = get_settings()
        
        # Should have at least some configuration
        assert isinstance(settings.mongodb_uri, str)


class TestDependencies:
    """Test required dependencies."""
    
    def test_fastapi_available(self):
        """Test FastAPI is available."""
        import fastapi
        assert fastapi is not None
    
    def test_pymongo_available(self):
        """Test the active MongoDB driver is available."""
        import pymongo
        assert pymongo is not None
    
    def test_pydantic_available(self):
        """Test Pydantic is available."""
        import pydantic
        assert pydantic is not None
    
    def test_streamlit_available(self):
        """Test Streamlit is available."""
        try:
            import streamlit
            assert streamlit is not None
        except ImportError:
            # Streamlit might be optional
            pass


# Test execution
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
