"""MongoDB transaction operations with stable integer IDs and Decimal128 amounts."""

import csv
import logging
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any, Dict, List, Optional

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db.database import from_bson, insert_document, to_bson
from app.models.customer import Customer
from app.models.fraud_alert import FraudAssessment
from app.models.transaction import Transaction
from app.schemas import TransactionCreate
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


def _transaction(document) -> Transaction:
    return Transaction.model_validate(from_bson(document))


class TransactionService:
    """Direct document operations; no SQL expression or ORM compatibility layer."""

    @staticmethod
    def build_query(
        customer_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        merchant_id: Optional[str] = None,
        status: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a Mongo filter while keeping financial bounds as BSON Decimal128."""
        query: dict[str, Any] = {}
        if customer_id is not None:
            query["customer_id"] = customer_id
        if start_date is not None or end_date is not None:
            query["transaction_date"] = {}
            if start_date is not None:
                query["transaction_date"]["$gte"] = start_date
            if end_date is not None:
                query["transaction_date"]["$lte"] = end_date
        if min_amount is not None or max_amount is not None:
            query["amount"] = {}
            if min_amount is not None:
                query["amount"]["$gte"] = to_bson(min_amount)
            if max_amount is not None:
                query["amount"]["$lte"] = to_bson(max_amount)
        if merchant_id:
            query["merchant_id"] = merchant_id
        if status:
            query["status"] = status
        if transaction_id:
            # Treat user search text literally; do not allow arbitrary regex operators.
            query["transaction_id"] = {
                "$regex": re.escape(transaction_id), "$options": "i"
            }
        return query

    @staticmethod
    def create_transaction(db: Database, transaction_create: TransactionCreate,
                           audit_user_id: Optional[int] = None) -> Transaction:
        customer_id = transaction_create.customer_id
        if not db["customers"].find_one({"id": customer_id}):
            raise ValueError(f"Customer with ID {customer_id} not found")
        transaction = Transaction.model_validate(transaction_create.model_dump())
        try:
            doc = insert_document(
                db, "transactions",
                transaction.model_dump(exclude={"id", "created_at", "updated_at"}),
            )
        except DuplicateKeyError as exc:
            raise ValueError(
                f"Transaction with ID {transaction_create.transaction_id} already exists"
            ) from exc
        transaction = _transaction(doc)
        AuditService.log_transaction_creation(
            db, audit_user_id, transaction.transaction_id, transaction.customer_id,
            transaction.amount,
        )
        logger.info("Transaction created: %s", transaction.transaction_id)
        return transaction

    @staticmethod
    def get_transaction(db: Database, transaction_id: int) -> Optional[Transaction]:
        doc = db["transactions"].find_one({"id": transaction_id})
        return _transaction(doc) if doc else None

    @staticmethod
    def list_transactions(
        db: Database,
        page: int = 1,
        limit: int = 50,
        customer_id: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        merchant_id: Optional[str] = None,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> tuple[List[Transaction], int]:
        query = TransactionService.build_query(
            customer_id=customer_id,
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount,
            max_amount=max_amount,
            merchant_id=merchant_id,
            status=status,
            transaction_id=transaction_id,
        )

        collection = db["transactions"]
        if not risk_level:
            total = collection.count_documents(query)
            docs = collection.find(query).sort("transaction_date", -1).skip(
                (page - 1) * limit
            ).limit(limit)
            return [_transaction(doc) for doc in docs], total

        pipeline = [
            {"$match": to_bson(query)},
            {"$lookup": {
                "from": "fraud_assessments",
                "localField": "id",
                "foreignField": "transaction_id",
                "as": "_assessment",
            }},
            {"$unwind": "$_assessment"},
            {"$match": {"_assessment.risk_category": {"$regex": f"^{risk_level}$", "$options": "i"}}},
        ]
        total_result = list(collection.aggregate(pipeline + [{"$count": "total"}]))
        total = total_result[0]["total"] if total_result else 0
        docs = collection.aggregate(pipeline + [
            {"$sort": {"transaction_date": -1}},
            {"$skip": (page - 1) * limit},
            {"$limit": limit},
            {"$project": {"_assessment": 0}},
        ])
        return [_transaction(doc) for doc in docs], total

    @staticmethod
    def detect_duplicate(db: Database, customer_id: int, amount: Decimal,
                         merchant_id: Optional[str], time_window_minutes: int = 5):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=time_window_minutes)
        doc = db["transactions"].find_one(
            {"customer_id": customer_id, "amount": to_bson(amount),
             "merchant_id": merchant_id, "transaction_date": {"$gte": cutoff},
             "status": "completed"},
            sort=[("transaction_date", -1)],
        )
        return _transaction(doc) if doc else None

    @staticmethod
    def bulk_import(db: Database, file_content: str, idempotency_key: str,
                    audit_user_id: Optional[int] = None, max_rows: int = 100000) -> Dict[str, Any]:
        result = {
            "idempotency_key": idempotency_key, "total_rows": 0, "successful": 0,
            "failed": 0, "duplicates_skipped": 0, "errors": [], "failed_rows": [],
        }
        try:
            reader = csv.DictReader(StringIO(file_content))
            if not reader.fieldnames:
                raise ValueError("CSV file is empty")
            required = {"transaction_id", "customer_id", "transaction_date", "amount", "merchant_id"}
            if not required.issubset(set(reader.fieldnames)):
                raise ValueError(f"Missing required CSV headers: {required - set(reader.fieldnames)}")
            for row_num, row in enumerate(reader, start=2):
                if result["total_rows"] >= max_rows:
                    result["errors"].append(f"Import limited to {max_rows} rows")
                    break
                result["total_rows"] += 1
                try:
                    txid = row.get("transaction_id", "").strip()
                    if not txid:
                        raise ValueError("transaction_id is required")
                    if db["transactions"].find_one({"transaction_id": txid}):
                        result["duplicates_skipped"] += 1
                        continue
                    customer_id = int(row.get("customer_id", "").strip())
                    if not db["customers"].find_one({"id": customer_id}):
                        raise ValueError(f"Customer with ID {customer_id} not found")
                    amount = Decimal(row.get("amount", "").strip())
                    if not amount.is_finite() or amount.as_tuple().exponent < -2:
                        raise ValueError("amount must be finite and have at most 2 decimal places")
                    transaction_date = datetime.fromisoformat(
                        row.get("transaction_date", "").strip().replace("Z", "+00:00")
                    )
                    if transaction_date.tzinfo is None:
                        transaction_date = transaction_date.replace(tzinfo=timezone.utc)
                    values = {
                        "transaction_id": txid, "customer_id": customer_id,
                        "transaction_date": transaction_date, "amount": amount,
                        "merchant_id": row.get("merchant_id", "").strip() or None,
                        "merchant_name": row.get("merchant_name", "").strip() or None,
                        "transaction_type": row.get("transaction_type", "purchase").strip() or "purchase",
                        "payment_method": row.get("payment_method", "card").strip() or "card",
                        "location_country": row.get("location_country", "").strip() or None,
                        "location_city": row.get("location_city", "").strip() or None,
                        "status": "completed", "is_synthetic": False,
                    }
                    try:
                        insert_document(db, "transactions", values)
                    except DuplicateKeyError:
                        result["duplicates_skipped"] += 1
                        continue
                    result["successful"] += 1
                except (ValueError, KeyError, InvalidOperation) as exc:
                    result["failed"] += 1
                    result["failed_rows"].append({
                        "row_number": row_num,
                        "transaction_id": row.get("transaction_id", ""),
                        "error": str(exc),
                    })
            if result["successful"]:
                AuditService.log_batch_import(
                    db, audit_user_id, result["successful"], idempotency_key
                )
        except Exception as exc:
            result["errors"].append(str(exc))
            raise ValueError(f"CSV import failed: {exc}") from exc
        return result
