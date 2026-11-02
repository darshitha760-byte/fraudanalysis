from datetime import datetime, timezone
from decimal import Decimal

import pytest
from bson.decimal128 import Decimal128
from pymongo.errors import DuplicateKeyError

from app.db.database import from_bson, initialize_database, next_id, to_bson


def test_decimal128_conversion_is_exact():
    amount = Decimal("123456789012345.6789")

    encoded = to_bson({"amount": amount})
    decoded = from_bson(encoded)

    assert decoded["amount"] == amount


def test_integer_id_sequence_continues_after_imported_ids(test_session):
    test_session["transactions"].insert_one({
        "id": 147,
        "transaction_id": "imported",
        "customer_id": 41,
        "transaction_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "amount": Decimal128(Decimal("1.00")),
    })

    assert next_id(test_session, "transactions") == 148


def test_initialize_database_creates_unique_integer_identity_indexes(test_session):
    initialize_database(test_session)
    test_session["customers"].insert_one(
        {"id": 1, "customer_id": "C-1", "name": "sample"}
    )

    with pytest.raises(DuplicateKeyError):
        test_session["customers"].insert_one(
            {"id": 1, "customer_id": "C-2", "name": "sample"}
        )


def test_datetime_conversion_normalizes_to_utc():
    from datetime import datetime, timedelta, timezone

    instant = datetime(2026, 1, 1, 12, tzinfo=timezone(timedelta(hours=2)))

    converted = to_bson({"timestamp": instant})["timestamp"]

    assert converted.utcoffset() == timedelta(0)
    assert converted.hour == 10


def test_real_mongodb_decimal128_range_and_aggregation(mongo_server_only):
    """Run Decimal128 query and aggregation semantics only against a real server."""
    from app.db.database import insert_document
    from bson.decimal128 import Decimal128

    db = mongo_server_only
    base = {
        "customer_id": 41,
        "transaction_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "transaction_type": "purchase",
        "currency": "USD",
        "status": "completed",
    }
    insert_document(db, "transactions", {
        **base, "transaction_id": "MONGO_DECIMAL_100", "amount": Decimal("100.01")
    })
    insert_document(db, "transactions", {
        **base, "transaction_id": "MONGO_DECIMAL_025", "amount": Decimal("0.25")
    })

    matches = list(db["transactions"].find(
        {"amount": {"$gte": Decimal128(Decimal("100.00"))}},
        {"transaction_id": 1, "amount": 1},
    ))
    assert [document["transaction_id"] for document in matches] == ["MONGO_DECIMAL_100"]
    assert matches[0]["amount"].to_decimal() == Decimal("100.01")

    total = next(db["transactions"].aggregate([
        {"$group": {"_id": None, "sum": {"$sum": "$amount"}}}
    ]))["sum"]
    assert total.to_decimal() == Decimal("100.26")


def test_real_mongodb_enforces_integer_and_business_id_uniqueness(mongo_server_only):
    db = mongo_server_only
    customer = {"id": 123, "customer_id": "UNIQUE-CUSTOMER", "name": "Unique"}
    db["customers"].insert_one(customer)
    with pytest.raises(DuplicateKeyError):
        db["customers"].insert_one(
            {"id": 123, "customer_id": "ANOTHER-CUSTOMER", "name": "Duplicate ID"}
        )
    with pytest.raises(DuplicateKeyError):
        db["customers"].insert_one(
            {"id": 125, "customer_id": "UNIQUE-CUSTOMER", "name": "Duplicate business key"}
        )


def test_real_mongodb_replica_set_transaction_rolls_back_atomically(mongo_replica_set):
    db = mongo_replica_set
    transaction = {
        "id": 7001,
        "transaction_id": "ATOMIC-ROLLBACK",
        "customer_id": 41,
        "transaction_date": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "transaction_type": "purchase",
        "currency": "USD",
        "status": "completed",
        "amount": Decimal128(Decimal("1.23")),
    }
    assessment = {
        "id": 8001,
        "transaction_id": 7001,
        "risk_score": Decimal128(Decimal("75.5")),
        "risk_category": "high",
    }

    with pytest.raises(RuntimeError, match="abort transaction"):
        with db.client.start_session() as session:
            with session.start_transaction():
                db["transactions"].insert_one(transaction, session=session)
                db["fraud_assessments"].insert_one(assessment, session=session)
                raise RuntimeError("abort transaction")

    assert db["transactions"].count_documents({"id": 7001}) == 0
    assert db["fraud_assessments"].count_documents({"id": 8001}) == 0


def test_real_mongodb_risk_assessment_and_triggered_rules_commit_atomically(
    mongo_replica_set, monkeypatch
):
    """Risk persistence preserves the former SQL commit/rollback and uniqueness contract."""
    from unittest.mock import Mock

    import app.services.risk_engine as risk_engine_module
    from app.db.database import insert_document
    from app.models.transaction import Transaction
    from app.services.risk_engine import RiskEngine

    db = mongo_replica_set
    transaction = Transaction(
        transaction_id="ATOMIC-RISK-ASSESSMENT",
        customer_id=9041,
        transaction_type="purchase",
        amount=Decimal("98.17"),
        currency="USD",
        merchant_id="M-ATOMIC",
        transaction_date=datetime.now(timezone.utc),
        status="completed",
    )
    saved_transaction = insert_document(
        db, "transactions",
        transaction.model_dump(exclude={"id", "created_at", "updated_at"}),
    )
    insert_document(db, "fraud_rules", {
        "rule_id": "ATOMIC-RULE",
        "name": "Atomic test rule",
        "description": "Integration test fixture",
        "rule_type": "threshold",
    })

    def make_engine():
        engine = RiskEngine()
        engine.fraud_engine.evaluate_transaction = Mock(return_value=(
            Decimal("25"), "medium", [{
                "rule_id": "ATOMIC-RULE",
                "rule_name": "Atomic test rule",
                "severity": "medium",
                "explanation": "Integration test trigger",
            }],
        ))
        engine._get_ml_score = lambda *_args: 0.0
        return engine

    real_insert = risk_engine_module.insert_document

    def fail_on_triggered_rule(database, collection, values, session=None):
        if collection == "triggered_rules":
            raise RuntimeError("forced triggered-rule write failure")
        return real_insert(database, collection, values, session=session)

    monkeypatch.setattr(risk_engine_module, "insert_document", fail_on_triggered_rule)
    with pytest.raises(RuntimeError, match="forced triggered-rule write failure"):
        make_engine().assess_fraud_risk(db, saved_transaction["id"])

    assert db["fraud_assessments"].count_documents(
        {"transaction_id": saved_transaction["id"]}
    ) == 0
    assert db["triggered_rules"].count_documents(
        {"transaction_id": saved_transaction["id"]}
    ) == 0

    monkeypatch.setattr(risk_engine_module, "insert_document", real_insert)
    result = make_engine().assess_fraud_risk(db, saved_transaction["id"])
    assert db["fraud_assessments"].count_documents(
        {"id": result["assessment_id"], "transaction_id": saved_transaction["id"]}
    ) == 1
    assert db["triggered_rules"].count_documents(
        {"assessment_id": result["assessment_id"], "transaction_id": saved_transaction["id"]}
    ) == 1

    with pytest.raises(DuplicateKeyError):
        make_engine().assess_fraud_risk(db, saved_transaction["id"])
    assert db["fraud_assessments"].count_documents(
        {"transaction_id": saved_transaction["id"]}
    ) == 1
    assert db["triggered_rules"].count_documents(
        {"transaction_id": saved_transaction["id"]}
    ) == 1


def test_real_mongodb_application_startup_and_readiness(test_client, mongo_server_only):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    ready = test_client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["dependencies"]["database"] == "ready"
    assert mongo_server_only.command("ping")["ok"] == 1
