"""Pytest fixtures for isolated MongoDB document persistence."""

from datetime import datetime
from decimal import Decimal
import os
from uuid import uuid4
from pymongo.uri_parser import parse_uri

import mongomock
import pytest
from pymongo import MongoClient
from fastapi.testclient import TestClient

from app.db.database import get_db, initialize_database, to_bson, next_id


_COLLECTIONS = {
    "User": "users",
    "Customer": "customers",
    "Transaction": "transactions",
    "FraudRule": "fraud_rules",
    "FraudAssessment": "fraud_assessments",
    "TriggeredRule": "triggered_rules",
    "FraudAlert": "fraud_alerts",
    "AuditLog": "audit_logs",
    "InvestigationCase": "investigation_cases",
    "CaseNote": "case_notes",
}


def insert_test_document(database, document):
    """Persist a Pydantic document in its MongoDB test collection."""
    collection_name = _COLLECTIONS[type(document).__name__]
    if document.id is None:
        document.id = next_id(database, collection_name)
    values = document.model_dump(mode="python")
    database[collection_name].insert_one(to_bson(values))
    return document


def replace_test_document(database, document):
    """Persist explicit changes to an already inserted MongoDB test document."""
    collection_name = _COLLECTIONS[type(document).__name__]
    values = to_bson(document.model_dump(mode="python"))
    database[collection_name].replace_one({"id": document.id}, values, upsert=True)
    return document


@pytest.fixture
def test_session():
    """Provide an isolated test database; use a real server only by explicit opt-in."""
    uri = os.environ.get("MONGODB_TEST_URI")
    if uri:
        nodes = parse_uri(uri).get("nodelist") or []
        if not nodes or any(host not in {"localhost", "127.0.0.1", "::1"} for host, _ in nodes):
            pytest.skip("MONGODB_TEST_URI must target loopback only; remote databases are never used by tests")
    client = MongoClient(uri, tz_aware=True) if uri else mongomock.MongoClient()
    database_name = f"fraud_test_{uuid4().hex}"
    database = client[database_name]
    initialize_database(database)
    yield database
    client.drop_database(database_name)
    client.close()


@pytest.fixture(autouse=True)
def isolated_test_signing_key(monkeypatch):
    """Keep test JWTs deterministic without depending on an optional local .env file."""
    from app.core.config import get_settings

    monkeypatch.setattr(
        get_settings(), "secret_key",
        "unit-test-only-signing-key-not-for-deployment-32",
    )


@pytest.fixture
def mongo_server_only(test_session):
    """Require an explicitly configured real MongoDB server for server-specific semantics."""
    if isinstance(test_session.client, mongomock.MongoClient):
        pytest.skip("requires real MongoDB; set MONGODB_TEST_URI to an isolated local test server")
    test_session.client.admin.command("ping")
    return test_session


@pytest.fixture
def mongo_replica_set(mongo_server_only):
    """Require replica-set support for multi-document transaction integration tests."""
    hello = mongo_server_only.client.admin.command("hello")
    if not hello.get("setName"):
        pytest.skip("multi-document transaction test requires a MongoDB replica set")
    return mongo_server_only


@pytest.fixture
def test_client(test_session):
    """Create a FastAPI client backed only by the isolated mongomock database."""
    import app.db.database as db_module
    from app.main import app

    db_module.set_database(test_session)

    def override_get_db():
        yield test_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    db_module.set_database(None)


@pytest.fixture
def auth_headers(test_session, test_client):
    """Create authentication headers for an isolated admin account."""
    from jose import jwt
    from datetime import timedelta, timezone
    from app.core.config import get_settings
    from app.core.permissions import UserRole
    from app.core.security import hash_password
    from app.models.user import User

    settings = get_settings()
    user = insert_test_document(test_session, User(
        email="test_admin@example.com",
        password_hash=hash_password("test123"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
    ))
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}


def create_test_transaction(
    database,
    customer_id: int,
    amount: float = 1000.0,
    transaction_date: datetime = None,
    transaction_type: str = "purchase",
    status: str = "completed",
    merchant_name: str = "Test Merchant",
    merchant_id: str = "M001",
    currency: str = "USD",
):
    """Insert a test transaction document."""
    from app.models.transaction import Transaction

    transaction = Transaction(
        transaction_id=f"TXN_{customer_id}_{int(datetime.utcnow().timestamp() * 1000)}",
        customer_id=customer_id,
        amount=Decimal(str(amount)),
        transaction_date=transaction_date or datetime.utcnow(),
        transaction_type=transaction_type,
        status=status,
        merchant_name=merchant_name,
        merchant_id=merchant_id,
        currency=currency,
    )
    return insert_test_document(database, transaction)


def create_test_fraud_assessment_and_alert(
    database,
    transaction_id: int,
    customer_id: int,
    risk_score: float = 50.0,
    risk_category: str = "medium",
    alert_severity: str = "medium",
    alert_status: str = "pending",
    alert_reason: str = "Fraud assessment alert",
):
    """Insert assessment and associated alert documents."""
    from app.models.fraud_alert import FraudAssessment, FraudAlert

    assessment = insert_test_document(database, FraudAssessment(
        transaction_id=transaction_id,
        risk_score=Decimal(str(risk_score)),
        risk_category=risk_category,
        rules_triggered_count=0,
        engine_version="1.0",
    ))
    alert = insert_test_document(database, FraudAlert(
        transaction_id=transaction_id,
        customer_id=customer_id,
        assessment_id=assessment.id,
        alert_severity=alert_severity,
        alert_status=alert_status,
        alert_reason=alert_reason,
    ))
    return assessment, alert
