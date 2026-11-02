#!/usr/bin/env python3
"""Idempotently seed non-sensitive sample documents into configured MongoDB."""

import logging
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db.database import close_db, get_database, initialize_database, insert_document
from app.models.customer import Customer
from app.models.transaction import Transaction

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(message)s")
logger = logging.getLogger(__name__)


def seed_database() -> dict[str, int]:
    db = get_database()
    initialize_database(db)
    customers = [
        ("DEMO-CUST-001", "Sample Customer One"),
        ("DEMO-CUST-002", "Sample Customer Two"),
        ("DEMO-CUST-003", "Sample Customer Three"),
    ]
    customer_ids = {}
    created_customers = 0
    for customer_id, name in customers:
        existing = db["customers"].find_one({"customer_id": customer_id})
        if existing:
            customer_ids[customer_id] = int(existing["id"])
            continue
        document = insert_document(
            db,
            "customers",
            Customer(customer_id=customer_id, name=name).model_dump(
                exclude={"id", "created_at", "updated_at"}
            ),
        )
        customer_ids[customer_id] = int(document["id"])
        created_customers += 1

    created_transactions = 0
    now = datetime.now(timezone.utc)
    samples = (
        ("DEMO-TXN-001", "DEMO-CUST-001", Decimal("75.50"), "grocery"),
        ("DEMO-TXN-002", "DEMO-CUST-002", Decimal("850.00"), "travel"),
        ("DEMO-TXN-003", "DEMO-CUST-003", Decimal("6200.00"), "electronics"),
    )
    for external_id, customer_key, amount, category in samples:
        if db["transactions"].find_one({"transaction_id": external_id}):
            continue
        transaction = Transaction(
            transaction_id=external_id,
            customer_id=customer_ids[customer_key],
            transaction_date=now - timedelta(minutes=created_transactions),
            amount=amount,
            merchant_name="Sample Merchant",
            merchant_id=f"DEMO-{category.upper()}",
            merchant_category=category,
            is_synthetic=True,
        )
        insert_document(
            db,
            "transactions",
            transaction.model_dump(exclude={"id", "created_at", "updated_at"}),
        )
        created_transactions += 1
    return {
        "customers_created": created_customers,
        "transactions_created": created_transactions,
    }


def main() -> int:
    try:
        result = seed_database()
        logger.info("Sample seed completed: %s", result)
        return 0
    except Exception:
        logger.error("Sample seed failed; no database connection details were logged.")
        return 1
    finally:
        close_db()


if __name__ == "__main__":
    raise SystemExit(main())
