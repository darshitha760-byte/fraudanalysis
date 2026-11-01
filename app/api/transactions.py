"""
Transactions API routes.
Handles transaction CRUD, listing, filtering, and batch import.
"""

import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query, UploadFile, File
from app.db.database import from_bson, get_db, insert_document
from app.schemas import TransactionCreate
from app.models.fraud_alert import FraudAssessment
from app.services.transaction_service import TransactionService
from app.services.fraud_engine import FraudEngine
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("", response_model=dict)
async def list_transactions(
    db=Depends(get_db),
    _current_user = Depends(get_current_user),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    customer_id: Optional[int] = Query(None, description="Filter by customer ID"),
    start_date: Optional[str] = Query(None, description="Filter by start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="Filter by end date (ISO format)"),
    min_amount: Optional[Decimal] = Query(None, description="Minimum transaction amount"),
    max_amount: Optional[Decimal] = Query(None, description="Maximum transaction amount"),
    merchant_id: Optional[str] = Query(None, description="Filter by merchant ID"),
    status: Optional[str] = Query(None, description="Filter by transaction status"),
    risk_level: Optional[str] = Query(None, description="Filter by assessed risk level"),
    transaction_id: Optional[str] = Query(None, description="Search transaction ID")
):
    """
    List transactions with pagination and filtering.

    Query parameters:
    - page: Page number (1-indexed)
    - limit: Results per page (1-500)
    - customer_id: Filter by customer
    - start_date: ISO format datetime
    - end_date: ISO format datetime
    - min_amount: Minimum amount
    - max_amount: Maximum amount
    - merchant_id: Merchant ID filter
    - status: Transaction status filter
    - risk_level: Assessed risk category
    - transaction_id: Partial transaction ID search
    """
    try:
        # Parse dates if provided
        start_dt = None
        end_dt = None

        if start_date:
            try:
                start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )

        if end_date:
            try:
                end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(
                    status_code=http_status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS)"
                )

        transactions, total_count = TransactionService.list_transactions(
            db=db,
            page=page,
            limit=limit,
            customer_id=customer_id,
            start_date=start_dt,
            end_date=end_dt,
            min_amount=min_amount,
            max_amount=max_amount,
            merchant_id=merchant_id,
            status=status,
            risk_level=risk_level,
            transaction_id=transaction_id
        )

        assessment_by_transaction = {
            doc["transaction_id"]: doc for doc in db["fraud_assessments"].find(
                {"transaction_id": {"$in": [t.id for t in transactions]}}
            )
        }
        return {
            "data": [
                {
                    "id": t.id,
                    "transaction_id": t.transaction_id,
                    "customer_id": t.customer_id,
                    "amount": float(t.amount),
                    "merchant_name": t.merchant_name,
                    "transaction_date": t.transaction_date.isoformat(),
                    "status": t.status,
                    "currency": t.currency,
                    "risk_score": float(assessment_by_transaction[t.id]["risk_score"].to_decimal())
                    if t.id in assessment_by_transaction else None,
                    "risk_level": assessment_by_transaction[t.id]["risk_category"]
                    if t.id in assessment_by_transaction else None,
                }
                for t in transactions
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List transactions failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list transactions"
        )


@router.post("", response_model=dict, status_code=http_status.HTTP_201_CREATED)
async def create_transaction(
    transaction_create: TransactionCreate,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new transaction with validation and fraud assessment."""
    try:
        # Create transaction
        transaction = TransactionService.create_transaction(
            db=db,
            transaction_create=transaction_create,
            audit_user_id=current_user.id
        )

        # Evaluate fraud rules
        risk_score, risk_level, triggered_rules = FraudEngine.evaluate_transaction(
            db=db,
            transaction=transaction
        )

        # Create fraud assessment
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=risk_score,
            risk_category=risk_level,
            rules_triggered_count=len(triggered_rules),
            assessment_timestamp=datetime.utcnow()
        )
        assessment = FraudAssessment.model_validate(insert_document(
            db, "fraud_assessments",
            assessment.model_dump(exclude={"id", "created_at", "updated_at"}),
        ))

        # Create triggered rule records
        for rule_result in triggered_rules:
            rule_doc = db["fraud_rules"].find_one({"rule_id": rule_result.rule_id})
            triggered_values = {
                "transaction_id": transaction.id,
                "assessment_id": assessment.id,
                "rule_id": rule_doc["id"] if rule_doc else 0,
                "triggered_rule_id": rule_result.rule_id,
                "triggered_rule_name": rule_result.rule_name,
                "rule_explanation": rule_result.explanation,
                "trigger_timestamp": datetime.now(timezone.utc),
            }
            insert_document(db, "triggered_rules", triggered_values)

        return {
            "id": transaction.id,
            "transaction_id": transaction.transaction_id,
            "customer_id": transaction.customer_id,
            "amount": float(transaction.amount),
            "merchant_name": transaction.merchant_name,
            "transaction_date": transaction.transaction_date.isoformat(),
            "assessment": {
                "risk_score": float(risk_score),
                "risk_level": risk_level,
                "triggered_rules": [
                    {
                        "rule_id": r.rule_id,
                        "rule_name": r.rule_name,
                        "explanation": r.explanation
                    }
                    for r in triggered_rules
                ]
            }
        }

    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Create transaction failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create transaction"
        )


@router.get("/{transaction_id}", response_model=dict)
async def get_transaction(
    transaction_id: int,
    db=Depends(get_db),
    _current_user = Depends(get_current_user)
):
    """Get transaction details with fraud assessment."""
    try:
        transaction = TransactionService.get_transaction(db=db, transaction_id=transaction_id)

        if not transaction:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Transaction not found"
            )

        # Get assessment if exists
        assessment_doc = db["fraud_assessments"].find_one({"transaction_id": transaction.id})
        assessment = FraudAssessment.model_validate(from_bson(assessment_doc)) if assessment_doc else None

        triggered_rules = []
        if assessment:
            rules = db["triggered_rules"].find({"assessment_id": assessment.id})
            for record in rules:
                rule = db["fraud_rules"].find_one({"id": record.get("rule_id")})
                triggered_rules.append({
                    "rule_id": record.get("triggered_rule_id") or (rule or {}).get("rule_id"),
                    "rule_name": record.get("triggered_rule_name") or (rule or {}).get("name"),
                    "explanation": record.get("rule_explanation") or record.get("explanation", ""),
                })

        return {
            "id": transaction.id,
            "transaction_id": transaction.transaction_id,
            "customer_id": transaction.customer_id,
            "amount": float(transaction.amount),
            "merchant_name": transaction.merchant_name,
            "transaction_date": transaction.transaction_date.isoformat(),
            "status": transaction.status,
            "currency": transaction.currency,
            "assessment": {
                "risk_score": float(assessment.risk_score) if assessment else 0,
                "risk_level": assessment.risk_category if assessment else "low",
                "triggered_rules": triggered_rules
            } if assessment else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get transaction failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get transaction"
        )


@router.post("/import", response_model=dict, status_code=http_status.HTTP_202_ACCEPTED)
async def import_transactions(
    file: UploadFile = File(...),
    idempotency_key: str = Query(..., description="Unique key for idempotency"),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Bulk import transactions from CSV file.

    CSV must contain headers: transaction_id, customer_id, transaction_date, amount, merchant_id

    File size limit: 10MB
    Row limit: 100,000
    """
    try:
        # Validate file size (10MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        file_size = 0
        content = ""

        # Read file with size check
        chunk_size = 1024 * 1024  # 1MB chunks
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File size exceeds 10MB limit"
                )
            content += chunk.decode('utf-8')

        # Perform bulk import
        result = TransactionService.bulk_import(
            db=db,
            file_content=content,
            idempotency_key=idempotency_key,
            audit_user_id=current_user.id,
            max_rows=100000
        )

        return {
            "idempotency_key": result["idempotency_key"],
            "total_rows": result["total_rows"],
            "successful": result["successful"],
            "failed": result["failed"],
            "duplicates_skipped": result["duplicates_skipped"],
            "errors": result["errors"],
            "failed_rows": result["failed_rows"][:100]  # Return first 100 failures
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Import transactions failed: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import transactions"
        )
