"""Create review-queue alerts for scored transactions that do not have one yet."""

import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.database import close_db, from_bson, get_database, insert_document
from app.models import FraudAlert, FraudAssessment, Transaction

logger = logging.getLogger(__name__)


def severity_for(score: float) -> str:
    if score >= 71:
        return "high"
    if score >= 31:
        return "medium"
    return "low"


def backfill(batch_size: int = 500) -> int:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    session = get_database()
    created = 0
    try:
        cursor = session["fraud_assessments"].find(
            {"risk_category": {"$in": ["medium", "high"]}}
        ).batch_size(batch_size)
        for raw_assessment in cursor:
            assessment = FraudAssessment.model_validate(from_bson(raw_assessment))
            transaction_doc = session["transactions"].find_one(
                {"id": assessment.transaction_id}
            )
            if transaction_doc is None:
                logger.warning("Skipped assessment with no matching transaction id=%s", assessment.id)
                continue
            transaction = Transaction.model_validate(from_bson(transaction_doc))
            if session["fraud_alerts"].find_one({"transaction_id": transaction.id}):
                continue
            score = float(assessment.risk_score)
            insert_document(
                session,
                "fraud_alerts",
                FraudAlert(
                    transaction_id=transaction.id,
                    customer_id=transaction.customer_id,
                    assessment_id=assessment.id,
                    alert_severity=severity_for(score),
                    alert_status="pending",
                    alert_reason=(
                        f"Risk score {score:.1f} ({assessment.risk_category}) for "
                        f"{transaction.amount} {transaction.currency} at "
                        f"{transaction.merchant_name or 'unknown merchant'}"
                    ),
                    triggered_rules_summary=(
                        f"{assessment.rules_triggered_count} detection rule(s) triggered"
                    ),
                    alert_created_at=transaction.transaction_date or datetime.utcnow(),
                ).model_dump(exclude={"id", "created_at", "updated_at"}),
            )
            created += 1
        logger.info("Created %s alerts", created)
        return created
    finally:
        close_db()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill()
