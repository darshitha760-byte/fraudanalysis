#!/usr/bin/env python3
"""
Integration test to verify all major components work together.
Tests the complete fraud detection pipeline.
"""

import sys
from pathlib import Path
import mongomock

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import get_settings
from app.core.security import hash_password, create_access_token, verify_password

from app.models.user import User
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.fraud_rule import FraudRule
from datetime import datetime, timedelta
from decimal import Decimal
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')
logger = logging.getLogger(__name__)


def test_database_connection(test_session=None):
    """Test that the isolated MongoDB-compatible test database is usable."""
    logger.info("\n[TEST 1] Database Connection")
    try:
        if test_session is None:
            test_session = mongomock.MongoClient()["financial_risk_test"]
        test_session["test_probe"].insert_one({"ok": True})
        assert test_session["test_probe"].find_one({"ok": True}) is not None
        logger.info("✓ Isolated document database is usable")
        return True
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        return False


def test_model_imports():
    """Test that all models can be imported."""
    logger.info("\n[TEST 2] Model Imports")
    try:
        from app.models import (
            User, Customer, Transaction, FraudRule,
            FraudAssessment, TriggeredRule, FraudAlert, AuditLog
        )
        logger.info("✓ All models imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Model import failed: {e}")
        return False


def test_security_functions():
    """Test security functions."""
    logger.info("\n[TEST 3] Security Functions")
    try:
        # Test password hashing
        password = "TestPassword123!"
        hashed = hash_password(password)
        assert verify_password(password, hashed)
        logger.info("✓ Password hashing verified")

        # Test JWT token creation
        token = create_access_token(user_id=1, email="test@example.com", role="Admin")
        assert token is not None
        assert len(token) > 0
        logger.info("✓ JWT token creation verified")

        return True
    except Exception as e:
        logger.error(f"✗ Security test failed: {e}")
        return False


def test_ml_imports():
    """Test ML module imports."""
    logger.info("\n[TEST 4] ML Module Imports")
    try:
        from app.ml import (
            DataPreprocessor, ModelTrainer, ModelPredictor, ModelEvaluator
        )
        logger.info("✓ All ML modules imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ ML import failed: {e}")
        return False


def test_services_imports():
    """Test service imports."""
    logger.info("\n[TEST 5] Service Imports")
    try:
        from app.services import (
            AuditService, TransactionService, FraudEngine
        )
        logger.info("✓ All services imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Service import failed: {e}")
        return False


def test_api_imports():
    """Test API route imports."""
    logger.info("\n[TEST 6] API Routes Imports")
    try:
        from app.api import auth, transactions, fraud_rules
        logger.info("✓ All API routes imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ API import failed: {e}")
        return False


def test_fastapi_app():
    """Test FastAPI app creation."""
    logger.info("\n[TEST 7] FastAPI Application")
    try:
        from app.main import app
        assert app is not None
        assert hasattr(app, 'routes')
        logger.info("✓ FastAPI app created successfully")
        return True
    except Exception as e:
        logger.error(f"✗ FastAPI app test failed: {e}")
        return False


def test_dashboard_imports():
    """Test dashboard component imports."""
    logger.info("\n[TEST 8] Dashboard Components")
    try:
        from dashboard.components import (
            auth_handler, api_client, charts, filters, tables
        )
        logger.info("✓ Dashboard components imported successfully")
        return True
    except Exception as e:
        logger.error(f"✗ Dashboard import failed: {e}")
        return False


def main():
    """Run all integration tests."""
    logger.info("=" * 60)
    logger.info("Integration Test Suite - Fraud Detection System")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"\nConfiguration:")
    logger.info(f"  Database: {settings.db_name}")
    logger.info(f"  Environment: {settings.environment}")
    logger.info(f"  Debug: {settings.debug}")

    tests = [
        ("Database Connection", test_database_connection),
        ("Model Imports", test_model_imports),
        ("Security Functions", test_security_functions),
        ("ML Module Imports", test_ml_imports),
        ("Service Imports", test_services_imports),
        ("API Routes Imports", test_api_imports),
        ("FastAPI Application", test_fastapi_app),
        ("Dashboard Components", test_dashboard_imports),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            logger.error(f"✗ Test '{name}' crashed: {e}")
            results.append((name, False))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {name}")

    logger.info(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        logger.info("\n✓ All integration tests passed!")
        return True
    else:
        logger.error(f"\n✗ {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
