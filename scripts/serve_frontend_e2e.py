"""Start an isolated browser-test API against an explicitly local MongoDB URI.

The harness uses a fresh database name and never drops existing collections.
"""

import os
from pathlib import Path
import random
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    mongo_uri = os.environ.get("MONGODB_E2E_URI", "")
    parsed_uri = urlparse(mongo_uri)
    if parsed_uri.scheme not in {"mongodb", "mongodb+srv"}:
        raise RuntimeError("Set MONGODB_E2E_URI to an already-running local MongoDB instance.")
    if parsed_uri.scheme == "mongodb+srv" or parsed_uri.hostname not in {
        "localhost", "127.0.0.1", "::1",
    }:
        raise RuntimeError("Browser E2E is restricted to local MongoDB; remote connections are refused.")

    database_name = f"fraud_detection_e2e_{uuid4().hex}"
    os.environ["MONGODB_URI"] = mongo_uri
    os.environ["MONGODB_DATABASE"] = database_name
    os.environ["SECRET_KEY"] = uuid4().hex + uuid4().hex
    os.environ["ENVIRONMENT"] = "development"
    os.environ["DEBUG"] = "false"

    import numpy as np
    import uvicorn
    from app.main import app
    from app.api import models
    from app.core.permissions import UserRole
    from app.core.security import hash_password
    from app.db.database import get_database, initialize_database, insert_document
    from app.ml.train import ModelTrainer
    from app.ml.predict import ModelPredictor
    from app.models import Customer, FraudAssessment, FraudAlert, FraudRule, Transaction, User
    from scripts.generate_synthetic_data import SyntheticDataGenerator
    from decimal import Decimal

    database = get_database()
    initialize_database(database)
    random.seed(42)
    np.random.seed(42)
    for role in (UserRole.ADMIN, UserRole.ANALYST, UserRole.VIEWER):
        insert_document(
            database,
            "users",
            User(
                # The Playwright journeys use stable role-based login names.
                # Each run still gets a private database so these are isolated.
                email=f"{role.value}@example.com",
                full_name=f"Test {role.value.title()}",
                password_hash=hash_password("Browser-Test-Only-2026"),
                role=role,
                is_active=True,
            ).model_dump(exclude={"id", "created_at", "updated_at"}),
        )

    customer_ids = []
    for customer_id in range(1, 31):
        customer = insert_document(
            database,
            "customers",
            Customer(
                customer_id=f"E2E-{customer_id}",
                name=f"Test customer {customer_id}",
            ).model_dump(exclude={"id", "created_at", "updated_at"}),
        )
        customer_ids.append(int(customer["id"]))
    insert_document(
        database,
        "fraud_rules",
        FraudRule(
            rule_id="E2E-HIGH-VALUE",
            name="High value payment",
            description="Review large payments",
            rule_type="high_value",
            severity="high",
            risk_weight=Decimal("30"),
            threshold_value=Decimal("1000"),
        ).model_dump(exclude={"id", "created_at", "updated_at"}),
    )

    data = SyntheticDataGenerator.generate_synthetic_transactions(
        n_transactions=1000, n_customers=30, fraud_rate=0.15,
    )
    for index, row in data.iterrows():
        transaction = Transaction(
            transaction_id=f"E2E-{index + 1:05d}",
            customer_id=customer_ids[int(row["customer_id"]) - 1],
            transaction_date=row["transaction_date"],
            amount=Decimal(str(row["amount"])),
            merchant_name=row["merchant_name"],
            merchant_category=row["merchant_category"],
            payment_method=row["payment_method"],
            transaction_type="purchase",
            channel=row["channel"],
            device_id=row["device_id"],
            location_country=row["location_country"],
            location_city=row["location_city"],
            fraud_label=bool(row["fraud_label"]),
            is_synthetic=True,
        )
        stored_transaction = insert_document(
            database,
            "transactions",
            transaction.model_dump(exclude={"id", "created_at", "updated_at"}),
        )
        if index < 60:
            assessment = insert_document(
                database,
                "fraud_assessments",
                FraudAssessment(
                    transaction_id=int(stored_transaction["id"]),
                    risk_score=Decimal("80" if index < 3 else "20"),
                    risk_category="high" if index < 3 else "low",
                    rules_triggered_count=1 if index < 3 else 0,
                ).model_dump(exclude={"id", "created_at", "updated_at"}),
            )
            if index < 3:
                insert_document(
                    database,
                    "fraud_alerts",
                    FraudAlert(
                        transaction_id=int(stored_transaction["id"]),
                        customer_id=int(stored_transaction["customer_id"]),
                        assessment_id=int(assessment["id"]),
                        alert_severity="high",
                        alert_status="PENDING",
                        alert_reason="Browser test review queue",
                        triggered_rules_summary="High value payment",
                        risk_score=Decimal("80"),
                        risk_level="HIGH",
                    ).model_dump(exclude={"id", "created_at", "updated_at"}),
                )

    with TemporaryDirectory(prefix="foresight-e2e-") as directory:
        models.MODELS_DIR = ModelTrainer.MODELS_DIR = ModelPredictor.MODELS_DIR = Path(directory)
        uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")


if __name__ == "__main__":
    main()
