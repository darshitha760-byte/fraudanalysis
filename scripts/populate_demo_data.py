"""Idempotently populate a bounded, labelled synthetic demo dataset in Atlas."""

import argparse
import json
import logging
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

from bson.decimal128 import Decimal128

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings
from app.db.database import (
    close_db,
    from_bson,
    get_client,
    get_database,
    insert_document,
)
from app.models.customer import Customer
from app.models.fraud_rule import FraudRule
from app.models.transaction import Transaction
from app.services.alert_service import AlertService
from app.services.fraud_engine import FraudEngine
from app.services.risk_engine import RiskEngine

logger = logging.getLogger(__name__)

DEMO_PREFIX = "DEMO-20261102"
CUSTOMER_LIMIT = 100
TRANSACTION_LIMIT = 1000
MAX_WORKERS = 4
ALLOWED_COLLECTIONS = {
    "customers",
    "transactions",
    "fraud_rules",
    "fraud_assessments",
    "triggered_rules",
    "fraud_alerts",
    "_id_sequences",
}
CAPACITY_GUARD_BYTES = 480 * 1024 * 1024
GROWTH_RESERVE_BYTES = 10 * 1024 * 1024


def _namespace_query(collection: str) -> dict:
    field = "customer_id" if collection == "customers" else "transaction_id"
    suffix = "CUST" if collection == "customers" else "TXN"
    return {field: {"$regex": f"^{re.escape(DEMO_PREFIX)}-{suffix}-"}}


def _transaction_ids(db) -> list[int]:
    return [
        int(document["id"])
        for document in db["transactions"].find(
            _namespace_query("transactions"), {"id": 1}
        )
    ]


def namespace_counts(db) -> dict[str, int]:
    transaction_ids = _transaction_ids(db)
    return {
        "customers": db["customers"].count_documents(_namespace_query("customers")),
        "transactions": len(transaction_ids),
        "assessments": db["fraud_assessments"].count_documents(
            {"transaction_id": {"$in": transaction_ids}}
        ),
        "triggered_rules": db["triggered_rules"].count_documents(
            {"transaction_id": {"$in": transaction_ids}}
        ),
        "alerts": db["fraud_alerts"].count_documents(
            {"transaction_id": {"$in": transaction_ids}}
        ),
    }


def collection_counts(db) -> dict[str, int]:
    return {
        name: db[name].count_documents({})
        for name in sorted(db.list_collection_names())
    }


def _check_capacity(db) -> dict[str, int]:
    stats = db.command("dbStats")
    storage_bytes = int(stats.get("storageSize", 0))
    index_bytes = int(stats.get("indexSize", 0))
    used_bytes = storage_bytes + index_bytes
    if used_bytes + GROWTH_RESERVE_BYTES > CAPACITY_GUARD_BYTES:
        raise RuntimeError("Atlas storage capacity guard exceeded")
    return {
        "storage_bytes": storage_bytes,
        "index_bytes": index_bytes,
        "capacity_guard_bytes": CAPACITY_GUARD_BYTES,
    }


def _validate_existing_namespace(db, now: datetime) -> None:
    customer_pattern = re.compile(
        rf"{re.escape(DEMO_PREFIX)}-CUST-([0-9]{{6}})"
    )
    for customer in db["customers"].find(
        _namespace_query("customers"),
        {"customer_id": 1, "name": 1, "notes": 1},
    ):
        match = customer_pattern.fullmatch(customer.get("customer_id", ""))
        index = int(match.group(1)) if match else 0
        if (
            not 1 <= index <= CUSTOMER_LIMIT
            or customer.get("name") != f"Synthetic Demo Customer {index:04d}"
            or customer.get("notes") != "Synthetic demo profile"
        ):
            raise RuntimeError("Demo customer namespace contains an unexpected document")

    transaction_pattern = re.compile(
        rf"{re.escape(DEMO_PREFIX)}-TXN-([0-9]{{8}})"
    )
    cutoff = now - timedelta(days=30)
    for transaction in db["transactions"].find(
        _namespace_query("transactions"),
        {
            "transaction_id": 1,
            "customer_id": 1,
            "transaction_date": 1,
            "is_synthetic": 1,
            "fraud_label": 1,
        },
    ):
        match = transaction_pattern.fullmatch(transaction.get("transaction_id", ""))
        ordinal = int(match.group(1)) if match else 0
        expected_customer_index = ((ordinal - 1) // 10) + 1 if ordinal else 0
        customer = db["customers"].find_one(
            {"customer_id": f"{DEMO_PREFIX}-CUST-{expected_customer_index:06d}"},
            {"id": 1},
        )
        transaction_date = transaction.get("transaction_date")
        if (
            not 1 <= ordinal <= TRANSACTION_LIMIT
            or transaction.get("is_synthetic") is not True
            or transaction.get("fraud_label") is not None
            or transaction.get("customer_id") != (customer or {}).get("id")
            or not isinstance(transaction_date, datetime)
            or transaction_date.replace(tzinfo=timezone.utc) < cutoff
            or transaction_date.replace(tzinfo=timezone.utc) > now
        ):
            raise RuntimeError(
                "Demo transaction namespace contains an unexpected document"
            )


def _verify_transaction_support(db) -> None:
    with db.client.start_session() as session:
        session.start_transaction()
        db["fraud_rules"].find_one({}, {"id": 1}, session=session)
        session.abort_transaction()


def _default_rule(rule_id: str, values: dict) -> FraudRule:
    return FraudRule(
        rule_id=rule_id,
        name=values["name"],
        description=values["description"],
        rule_type=values["rule_type"],
        threshold_value=(
            Decimal(str(values["threshold_value"]))
            if values.get("threshold_value") is not None
            else None
        ),
        threshold_unit=values.get("threshold_unit"),
        threshold_config=values.get("threshold_config"),
        severity=values.get("severity", "medium"),
        risk_weight=Decimal(str(values["risk_weight"])),
        required_fields=json.dumps(values.get("required_fields", [])),
        applicable_transaction_types=json.dumps(
            values.get("applicable_types", ["all"])
        ),
        is_enabled=True,
        version=1,
        notes=f"Default fraud detection rule: {values['description']}",
    )


def _seed_missing_rules(db) -> int:
    created = 0
    for rule_id, values in FraudEngine.DEFAULT_RULES.items():
        if db["fraud_rules"].find_one({"rule_id": rule_id}, {"id": 1}):
            continue
        rule = _default_rule(rule_id, values)
        insert_document(
            db,
            "fraud_rules",
            rule.model_dump(exclude={"id", "created_at", "updated_at"}),
        )
        created += 1
    return created


def _customer(customer_index: int, now: datetime) -> Customer:
    created_at = now - timedelta(days=60)
    return Customer(
        customer_id=f"{DEMO_PREFIX}-CUST-{customer_index:06d}",
        name=f"Synthetic Demo Customer {customer_index:04d}",
        country="US",
        city=f"Demo City {customer_index % 20:02d}",
        notes="Synthetic demo profile",
        created_at=created_at,
        updated_at=created_at,
    )


def _transaction(
    ordinal: int, customer_id: int, now: datetime
) -> Transaction:
    if not 1 <= ordinal <= TRANSACTION_LIMIT:
        raise ValueError("Transaction ordinal must be within the approved range")

    span_seconds = 29 * 24 * 60 * 60
    transaction_date = now - timedelta(days=29) + timedelta(
        seconds=(ordinal - 1) * span_seconds // (TRANSACTION_LIMIT - 1)
    )
    flagged_scenario = ordinal % 50 == 0
    amount = Decimal("6500.00") if flagged_scenario else Decimal(
        str(100 + (ordinal * 37) % 1700)
    )
    if flagged_scenario:
        transaction_date = transaction_date.replace(hour=3)
        if transaction_date > now:
            transaction_date -= timedelta(days=1)

    return Transaction(
        transaction_id=f"{DEMO_PREFIX}-TXN-{ordinal:08d}",
        customer_id=customer_id,
        transaction_date=transaction_date,
        amount=amount,
        merchant_name=f"Synthetic Demo Merchant {ordinal % 40:02d}",
        merchant_id=f"{DEMO_PREFIX}-MERCHANT-{ordinal % 40:02d}",
        merchant_category="cryptocurrency" if flagged_scenario else (
            "grocery", "restaurant", "travel", "utilities", "online_retail"
        )[(ordinal - 1) % 5],
        payment_method="card",
        location_country="CA" if flagged_scenario else "US",
        location_city="Synthetic Demo Location",
        channel="online",
        is_synthetic=True,
        fraud_label=None,
    )


def _seed_customers(db, now: datetime) -> tuple[dict[int, int], int]:
    existing = db["customers"].count_documents(_namespace_query("customers"))
    if existing > CUSTOMER_LIMIT:
        raise RuntimeError("Demo customer namespace exceeds its approved limit")

    created = 0
    customer_ids = {}
    for index in range(1, CUSTOMER_LIMIT + 1):
        external_id = f"{DEMO_PREFIX}-CUST-{index:06d}"
        document = db["customers"].find_one(
            {"customer_id": external_id}, {"id": 1}
        )
        if document is None:
            customer = _customer(index, now)
            document = insert_document(
                db,
                "customers",
                customer.model_dump(exclude={"id"}),
            )
            created += 1
        customer_ids[index] = int(document["id"])
    return customer_ids, created


def _ensure_assessment_and_alert(
    db, transaction: Transaction, risk_engine: RiskEngine
) -> None:
    existing = db["fraud_assessments"].find_one(
        {"transaction_id": transaction.id}
    )
    if existing is None:
        result = risk_engine.assess_fraud_risk(
            db, transaction.id, customer_id=transaction.customer_id
        )
        assessment_id = result["assessment_id"]
        risk_score = result["risk_score"]
        risk_level = result["risk_level"]
        alert_required = result["alert_required"]
        triggered = result["triggered_rules"]
    else:
        assessment_id = int(existing["id"])
        risk_score = float(existing["risk_score"].to_decimal()
                            if hasattr(existing["risk_score"], "to_decimal")
                            else existing["risk_score"])
        risk_level = str(existing["risk_category"])
        alert_required = risk_score >= RiskEngine.ALERT_THRESHOLD_MIN
        triggered = []

    if alert_required and db["fraud_alerts"].find_one(
        {"transaction_id": transaction.id}, {"id": 1}
    ) is None:
        summary = ", ".join(
            getattr(rule, "rule_id", "") for rule in triggered
        ) or "Previously computed fraud risk"
        AlertService.create_fraud_alert(
            session=db,
            transaction_id=transaction.id,
            customer_id=transaction.customer_id,
            assessment_id=assessment_id,
            risk_score=risk_score,
            risk_level=risk_level,
            alert_reason="Automated alert based on computed demo risk assessment",
            triggered_rules_summary=summary,
        )


def _populate_customer_transactions(
    db, customer_index: int, customer_id: int, now: datetime
) -> int:
    risk_engine = RiskEngine()
    # This population is rule-only; no model is trained, uploaded, or scored.
    risk_engine._get_ml_score = lambda *_args: 0.0
    created = 0
    first_ordinal = (customer_index - 1) * 10 + 1
    for ordinal in range(first_ordinal, first_ordinal + 10):
        external_id = f"{DEMO_PREFIX}-TXN-{ordinal:08d}"
        stored = db["transactions"].find_one({"transaction_id": external_id})
        if stored is None:
            transaction = _transaction(ordinal, customer_id, now)
            stored = insert_document(
                db,
                "transactions",
                transaction.model_dump(
                    exclude={"id", "created_at", "updated_at"}
                ),
            )
            created += 1

        transaction = Transaction.model_validate(from_bson(stored))
        if transaction.is_synthetic is not True or transaction.fraud_label is not None:
            raise RuntimeError("Existing demo transaction has unexpected labels")
        _ensure_assessment_and_alert(db, transaction, risk_engine)
    return created


def populate_demo_data(db, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Population time must be timezone-aware")
    now = now.astimezone(timezone.utc)

    before = collection_counts(db)
    initial = namespace_counts(db)
    if initial["customers"] > CUSTOMER_LIMIT:
        raise RuntimeError("Demo customer namespace exceeds its approved limit")
    if initial["transactions"] > TRANSACTION_LIMIT:
        raise RuntimeError("Demo transaction namespace exceeds its approved limit")
    _validate_existing_namespace(db, now)

    rules_created = _seed_missing_rules(db)
    customer_ids, customers_created = _seed_customers(db, now)
    transactions_created = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(
                _populate_customer_transactions,
                db,
                index,
                customer_ids[index],
                now,
            )
            for index in range(1, CUSTOMER_LIMIT + 1)
        ]
        for future in as_completed(futures):
            transactions_created += future.result()

    after = collection_counts(db)
    final = namespace_counts(db)
    if final["customers"] != CUSTOMER_LIMIT:
        raise RuntimeError("Demo customer count verification failed")
    if final["transactions"] != TRANSACTION_LIMIT:
        raise RuntimeError("Demo transaction count verification failed")
    if final["assessments"] != TRANSACTION_LIMIT:
        raise RuntimeError("Demo assessment count verification failed")
    if final["triggered_rules"] > TRANSACTION_LIMIT * 10:
        raise RuntimeError("Triggered-rule count verification failed")
    if final["alerts"] > TRANSACTION_LIMIT:
        raise RuntimeError("Alert count verification failed")
    if any(
        before.get(name, 0) != after.get(name, 0)
        for name in set(before) | set(after)
        if name not in ALLOWED_COLLECTIONS
    ):
        raise RuntimeError("An unrelated collection count changed")

    transaction_ids = _transaction_ids(db)
    eligible_assessments = list(db["fraud_assessments"].find(
        {
            "transaction_id": {"$in": transaction_ids},
            "risk_score": {"$gte": Decimal128(Decimal("31"))},
        },
        {"transaction_id": 1},
    ))
    eligible_ids = {int(doc["transaction_id"]) for doc in eligible_assessments}
    alerted_ids = {
        int(doc["transaction_id"])
        for doc in db["fraud_alerts"].find(
            {"transaction_id": {"$in": transaction_ids}},
            {"transaction_id": 1},
        )
    }
    if eligible_ids != alerted_ids:
        raise RuntimeError("Computed-risk alert verification failed")

    return {
        "rules_created": rules_created,
        "customers_created": customers_created,
        "transactions_created": transactions_created,
        "namespace_counts": final,
        "collection_counts_before": before,
        "collection_counts_after": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="write the approved synthetic demo dataset to configured Atlas",
    )
    args = parser.parse_args()

    settings = get_settings()
    hostname = urlparse(settings.mongodb_uri).hostname or ""
    if not hostname.endswith("mongodb.net"):
        logger.error("Population aborted: configured database is not verifiably Atlas")
        return 1

    try:
        client = get_client()
        client.admin.command("ping")
        db = get_database()
        capacity = _check_capacity(db)
        _verify_transaction_support(db)
        before = collection_counts(db)
        namespace = namespace_counts(db)
        if namespace["customers"] > CUSTOMER_LIMIT:
            raise RuntimeError("Demo customer namespace exceeds its approved limit")
        if namespace["transactions"] > TRANSACTION_LIMIT:
            raise RuntimeError("Demo transaction namespace exceeds its approved limit")
        if not args.execute:
            print(json.dumps({
                "mode": "plan",
                "namespace_counts_before": namespace,
                "collection_counts_before": before,
                "capacity": capacity,
                "would_create": {
                    "customers_max": CUSTOMER_LIMIT - namespace["customers"],
                    "transactions_max": TRANSACTION_LIMIT - namespace["transactions"],
                },
            }, sort_keys=True))
            return 0

        summary = populate_demo_data(db)
        summary["capacity"] = capacity
        print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception as exc:
        logger.error("Population aborted (%s); diagnostic details suppressed",
                     type(exc).__name__)
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(message)s")
    raise SystemExit(main())
