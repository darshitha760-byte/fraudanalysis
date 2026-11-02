"""
Transaction tests: CRUD operations, import, duplicate detection, error handling.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta
from io import StringIO
import json

from fastapi.testclient import TestClient

from app.main import app
from conftest import insert_test_document
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.fraud_alert import FraudAssessment
from app.models.fraud_rule import FraudRule
from app.schemas import TransactionCreate, TransactionResponse
from app.services.transaction_service import TransactionService
from app.services.fraud_engine import FraudEngine
from app.core.security import hash_password


def _save(database, document):
    return insert_test_document(database, document)


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
    """Create test customer."""
    customer = Customer(
        customer_id="CUST001",
        name="John Doe",
        email="john@example.com",
        phone="+1234567890",
        country="US",
        city="New York",
        customer_type="individual",
        risk_profile="low"
    )
    return insert_test_document(db, customer)


@pytest.fixture
def test_merchant(db):
    """Create test merchant data (merchant_id is just a string in transaction model)."""
    # Merchants are referenced by merchant_id string in transactions
    # No separate merchant model table exists
    return {"merchant_id": "M001", "merchant_name": "Walmart"}


def make_transaction_create(**kwargs):
    """Helper to create TransactionCreate objects with defaults."""
    defaults = {
        "transaction_id": "TXN" + str(abs(hash(datetime.utcnow())) % 10000),
        "customer_id": kwargs.get("customer_id", 1),
        "amount": kwargs.get("amount", Decimal("100.00")),
        "currency": kwargs.get("currency", "USD"),
        "transaction_date": kwargs.get("transaction_date", datetime.utcnow()),
        "merchant_id": kwargs.get("merchant_id", "M001"),
        "merchant_name": kwargs.get("merchant_name", "Walmart"),
    }
    defaults.update(kwargs)
    return TransactionCreate(**defaults)


@pytest.fixture
def test_admin_user(db):
    """Create test admin user."""
    from app.models.user import User
    from app.core.permissions import UserRole
    
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
    from app.services.fraud_engine import FraudEngine
    
    for rule_id, rule_data in FraudEngine.DEFAULT_RULES.items():
        rule = FraudRule(
            rule_id=rule_id,
            name=rule_data["name"],
            description=rule_data["description"],
            rule_type=rule_data["rule_type"],
            threshold_value=Decimal(str(rule_data.get("threshold", 0))),
            severity=rule_data.get("severity", "medium"),
            risk_weight=Decimal(str(rule_data["risk_weight"])),
            is_enabled=True
        )
        insert_test_document(db, rule)


# Transaction Service Tests


class TestTransactionService:
    """Test TransactionService class."""
    
    def test_create_transaction(self, db, test_customer, test_merchant, test_rules):
        """Test creating a transaction."""
        transaction_data = make_transaction_create(
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            merchant_name=test_merchant["merchant_name"],
            amount=Decimal("99.99")
        )
        
        transaction = TransactionService.create_transaction(db, transaction_data)
        
        assert transaction.customer_id == test_customer.id
        assert transaction.merchant_id == test_merchant["merchant_id"]
        assert transaction.amount == Decimal("99.99")
        assert transaction.status == "completed"
    
    def test_create_transaction_customer_not_found(self, db, test_merchant):
        """Test creating transaction with non-existent customer."""
        transaction_data = make_transaction_create(
            customer_id=9999,
            merchant_id=test_merchant["merchant_id"]
        )
        
        with pytest.raises(ValueError, match="Customer with ID"):
            TransactionService.create_transaction(db, transaction_data)
    
    def test_detect_duplicate(self, db, test_customer, test_merchant):
        """Test duplicate detection."""
        now = datetime.utcnow()
        
        # Create first transaction
        txn1 = Transaction(
            transaction_id="TXN_DUP1",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=now,
            currency="USD",
            status="completed"
        )
        txn1 = _save(db, txn1)
        
        # Detect duplicate within time window
        duplicate = TransactionService.detect_duplicate(
            db, test_customer.id, Decimal("100.00"), test_merchant["merchant_id"]
        )
        assert duplicate is not None
        assert duplicate.id == txn1.id
    
    def test_detect_duplicate_outside_time_window(self, db, test_customer, test_merchant):
        """Test duplicate detection outside time window."""
        old_time = datetime.utcnow() - timedelta(minutes=6)
        
        txn1 = Transaction(
            transaction_id="TXN_OLD1",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=old_time,
            currency="USD",
            status="completed"
        )
        _save(db, txn1)
        
        # Should not detect as duplicate (outside 5 min window)
        duplicate = TransactionService.detect_duplicate(
            db, test_customer.id, Decimal("100.00"), test_merchant["merchant_id"]
        )
        assert duplicate is None
    
    def test_bulk_import_success(self, db, test_customer, test_merchant, test_rules):
        """Test successful CSV import."""
        csv_content = """transaction_id,customer_id,merchant_id,amount,transaction_date,merchant_name
TXN_IMP1,{},M001,50.00,2026-10-20T10:00:00,Walmart
TXN_IMP2,{},M001,75.50,2026-10-20T10:05:00,Walmart
""".format(test_customer.id, test_customer.id)
        
        result = TransactionService.bulk_import(db, csv_content, "test-key-1")
        
        assert result["successful"] == 2
        assert result["failed"] == 0
        assert result["duplicates_skipped"] == 0
    
    def test_bulk_import_with_errors(self, db, test_customer, test_merchant):
        """Test CSV import with invalid rows."""
        csv_content = """transaction_id,customer_id,merchant_id,amount,transaction_date,merchant_name
TXN_BAD1,{},M001,invalid_amount,2026-10-20T10:00:00,Walmart
TXN_BAD2,{},M001,100.00,2026-10-20T10:05:00,BadMerch
""".format(test_customer.id, test_customer.id)
        
        result = TransactionService.bulk_import(db, csv_content, "test-key-2")
        
        assert result["failed"] > 0
        assert len(result["failed_rows"]) > 0
    
    def test_bulk_import_duplicate_prevention(self, db, test_customer, test_merchant):
        """Test idempotency key prevents duplicate imports."""
        csv_content = """transaction_id,customer_id,merchant_id,amount,transaction_date,merchant_name
TXN_DUP,{},M001,100.00,2026-10-20T10:00:00,Walmart
""".format(test_customer.id)
        
        result1 = TransactionService.bulk_import(db, csv_content, "test-key-3")
        assert result1["successful"] == 1
        
        # Reimport same content
        result2 = TransactionService.bulk_import(db, csv_content, "test-key-3")
        assert result2["successful"] == 0
        assert result2["duplicates_skipped"] == 1
    
    def test_bulk_import_missing_headers(self, db):
        """Test CSV import with missing required headers."""
        csv_content = """customer_id,amount,merchant_name
1,100.00,Walmart
"""
        
        with pytest.raises(ValueError, match="Missing required"):
            TransactionService.bulk_import(db, csv_content, "test-key-4")
    
    def test_list_transactions_with_filters(self, db, test_customer, test_merchant):
        """Test listing transactions with filters."""
        # Create transactions
        for i in range(5):
            txn = Transaction(
                transaction_id=f"TXN_LIST{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{50 + i * 10}.00"),
                transaction_date=datetime.utcnow() - timedelta(days=i),
                currency="USD",
                status="completed"
            )
            _save(db, txn)
        
        # Test pagination
        result = TransactionService.list_transactions(
            db,
            page=1,
            limit=3,
            customer_id=test_customer.id
        )
        assert len(result[0]) == 3
        assert result[1] == 5
    
    def test_list_transactions_amount_range(self, db, test_customer, test_merchant):
        """Verify amount bounds are sent to Mongo as exact Decimal128 operands."""
        from bson.decimal128 import Decimal128

        query = TransactionService.build_query(
            min_amount=Decimal("100"),
            max_amount=Decimal("150")
        )
        assert query["amount"] == {
            "$gte": Decimal128("100"),
            "$lte": Decimal128("150"),
        }

    def test_list_transactions_by_risk_level_and_transaction_id(
        self,
        db,
        test_customer,
        test_merchant,
    ):
        transaction = Transaction(
            transaction_id="TXN_RISK_FILTER",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("125.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed",
        )
        transaction = _save(db, transaction)
        _save(
            db,
            FraudAssessment(
                transaction_id=transaction.id,
                risk_score=Decimal("80"),
                risk_category="high",
                rules_triggered_count=1,
            )
        )
        result, total = TransactionService.list_transactions(
            db,
            risk_level="HIGH",
            transaction_id="RISK_FILTER",
        )

        assert total == 1
        assert [item.transaction_id for item in result] == ["TXN_RISK_FILTER"]


# Transaction API Tests

class TestTransactionAPI:
    """Test Transaction API endpoints."""
    
    def test_list_transactions_unauthorized(self, client):
        """Test list endpoint requires authentication."""
        response = client.get("/transactions")
        assert response.status_code == 401
    
    def test_create_transaction_success(self, client, auth_headers, test_customer, test_merchant, test_rules):
        """Test creating transaction via API."""
        response = client.post(
            "/transactions",
            json={
                "transaction_id": "TXN_API1",
                "customer_id": test_customer.id,
                "merchant_id": test_merchant["merchant_id"],
                "amount": "99.99",
                "transaction_date": datetime.utcnow().isoformat(),
                "currency": "USD",
                "merchant_name": "Test Merchant"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["customer_id"] == test_customer.id
        assert data["amount"] == 99.99
        assert "assessment" in data
    
    def test_get_transaction(self, client, auth_headers, db, test_customer, test_merchant):
        """Test retrieving transaction."""
        txn = Transaction(
            transaction_id="TXN_GET1",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        txn = _save(db, txn)
        
        response = client.get(f"/transactions/{txn.id}", headers=auth_headers)
        
        assert response.status_code == 200
        assert response.json()["id"] == txn.id
    
    def test_bulk_import_endpoint(self, client, auth_headers, test_customer, test_merchant):
        """Test CSV import endpoint."""
        csv_content = f"""transaction_id,customer_id,merchant_id,amount,transaction_date,merchant_name
TXN_EP1,{test_customer.id},M001,50.00,2026-10-20T10:00:00,Walmart
"""
        
        response = client.post(
            "/transactions/import?idempotency_key=test-import-1",
            files={"file": ("transactions.csv", csv_content)},
            headers=auth_headers
        )
        
        if response.status_code != 202:
            print(f"Response status: {response.status_code}")
            print(f"Response body: {response.json()}")
        
        assert response.status_code == 202
        data = response.json()
        assert "successful" in data
    
    def test_list_transactions_with_pagination(self, client, auth_headers, db, test_customer, test_merchant):
        """Test paginated listing."""
        for i in range(25):
            txn = Transaction(
                transaction_id=f"TXN_PAGING{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(f"{50 + i}.00"),
                transaction_date=datetime.utcnow(),
                currency="USD",
                status="completed"
            )
            _save(db, txn)
        
        response = client.get(
            "/transactions?page=1&limit=10",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 10
        assert data["pagination"]["total"] == 25
    
    def test_list_transactions_with_filters(self, client, auth_headers, db, test_customer, test_merchant):
        """Test filtering by amount range."""
        for i, amount in enumerate([50, 100, 150]):
            txn = Transaction(
                transaction_id=f"TXN_FILTER{i}",
                customer_id=test_customer.id,
                merchant_id=test_merchant["merchant_id"],
                amount=Decimal(str(amount)),
                transaction_date=datetime.utcnow(),
                currency="USD",
                status="completed"
            )
            _save(db, txn)
        
        response = client.get(
            f"/transactions?customer_id={test_customer.id}&status=completed",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert all(t["customer_id"] == test_customer.id for t in data["data"])
        assert all(t["status"] == "completed" for t in data["data"])


# Edge case tests

class TestEdgeCases:
    """Test edge cases and error scenarios."""
    
    def test_duplicate_transaction_id(self, db, test_customer, test_merchant):
        """Test duplicate transaction_id rejection."""
        txn1 = Transaction(
            transaction_id="TXN_DUP_TEST",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("100.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        txn1 = _save(db, txn1)
        
        # Try to create with same ID (should fail or be prevented)
        txn2 = Transaction(
            transaction_id="TXN_DUP_TEST",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("200.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        
        from pymongo.errors import DuplicateKeyError
        with pytest.raises(DuplicateKeyError):
            _save(db, txn2)
    
    def test_zero_amount_transaction(self, db, test_customer, test_merchant):
        """Test transaction with zero amount."""
        txn = Transaction(
            transaction_id="TXN_ZERO",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=Decimal("0.00"),
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        _save(db, txn)
        
        assert txn.amount == Decimal("0.00")
    
    def test_large_amount_transaction(self, db, test_customer, test_merchant):
        """Test transaction with very large amount."""
        large_amount = Decimal("999999999.99")
        txn = Transaction(
            transaction_id="TXN_LARGE",
            customer_id=test_customer.id,
            merchant_id=test_merchant["merchant_id"],
            amount=large_amount,
            transaction_date=datetime.utcnow(),
            currency="USD",
            status="completed"
        )
        _save(db, txn)
        
        assert txn.amount == large_amount
    
    def test_invalid_currency_code(self, client, auth_headers, test_customer, test_merchant):
        """Test transaction with invalid currency."""
        response = client.post(
            "/transactions",
            json={
                "transaction_id": "TXN_BAD_CURR",
                "customer_id": test_customer.id,
                "merchant_id": test_merchant["merchant_id"],
                "amount": "100.00",
                "transaction_date": datetime.utcnow().isoformat(),
                "currency": "INVALID"
            },
            headers=auth_headers
        )
        
        assert response.status_code in [400, 422]  # Bad request
