"""
Fraud Rules API routes.
Handles fraud rule CRUD operations and validation.
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.db.database import from_bson, get_db, insert_document, to_bson
from app.schemas import FraudRuleCreate, FraudRuleUpdate, FraudRuleResponse
from app.models.fraud_rule import FraudRule
from app.core.security import get_current_user
from app.core.permissions import UserRole

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fraud/rules", tags=["fraud-rules"])


def check_admin(current_user) -> None:
    """Check if user is admin for write operations."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for this operation"
        )


@router.get("", response_model=dict)
async def list_fraud_rules(
    db=Depends(get_db),
    current_user = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    rule_type: Optional[str] = Query(None),
    is_enabled: Optional[bool] = Query(None)
):
    """
    List fraud rules with pagination and filtering.
    
    Query parameters:
    - page: Page number (1-indexed)
    - limit: Results per page (1-500)
    - rule_type: Filter by rule type
    - is_enabled: Filter by enabled status
    """
    try:
        query = {}
        if rule_type:
            query["rule_type"] = rule_type
        if is_enabled is not None:
            query["is_enabled"] = is_enabled
        collection = db["fraud_rules"]
        total_count = collection.count_documents(query)
        rules = [FraudRule.model_validate(from_bson(doc)) for doc in
                 collection.find(query).sort("rule_id", 1).skip((page - 1) * limit).limit(limit)]
        
        return {
            "data": [
                {
                    "id": r.id,
                    "rule_id": r.rule_id,
                    "name": r.name,
                    "description": r.description,
                    "rule_type": r.rule_type,
                    "is_enabled": r.is_enabled,
                    "severity": r.severity,
                    "risk_weight": float(r.risk_weight),
                    "threshold_value": float(r.threshold_value) if r.threshold_value else None,
                    "version": r.version,
                    "created_at": r.created_at.isoformat()
                }
                for r in rules
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total_count,
                "pages": (total_count + limit - 1) // limit
            }
        }
    
    except Exception as e:
        logger.error(f"List fraud rules failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list fraud rules"
        )


@router.get("/{rule_id}", response_model=dict)
async def get_fraud_rule(
    rule_id: str,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get fraud rule details by rule ID."""
    try:
        document = db["fraud_rules"].find_one({"rule_id": rule_id})
        rule = FraudRule.model_validate(from_bson(document)) if document else None
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fraud rule {rule_id} not found"
            )
        
        return {
            "id": rule.id,
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "rule_type": rule.rule_type,
            "is_enabled": rule.is_enabled,
            "threshold_value": float(rule.threshold_value) if rule.threshold_value else None,
            "threshold_unit": rule.threshold_unit,
            "threshold_config": rule.threshold_config,
            "severity": rule.severity,
            "risk_weight": float(rule.risk_weight),
            "required_fields": rule.required_fields,
            "applicable_transaction_types": rule.applicable_transaction_types,
            "version": rule.version,
            "notes": rule.notes,
            "created_at": rule.created_at.isoformat(),
            "updated_at": rule.updated_at.isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get fraud rule failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get fraud rule"
        )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_fraud_rule(
    rule_create: FraudRuleCreate,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Create a new fraud rule (admin only)."""
    check_admin(current_user)
    
    try:
        # Check if rule_id already exists
        existing = db["fraud_rules"].find_one({"rule_id": rule_create.rule_id})
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Fraud rule {rule_create.rule_id} already exists"
            )
        
        # Validate risk_weight
        if rule_create.risk_weight < 0 or rule_create.risk_weight > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="risk_weight must be between 0 and 100"
            )
        
        # Create rule
        rule = FraudRule(
            **rule_create.model_dump()
        )
        
        rule = FraudRule.model_validate(insert_document(
            db, "fraud_rules",
            rule.model_dump(exclude={"id", "created_at", "updated_at"}),
        ))
        
        logger.info(f"Fraud rule created: {rule.rule_id}")
        
        return {
            "id": rule.id,
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "rule_type": rule.rule_type,
            "is_enabled": rule.is_enabled,
            "threshold_value": float(rule.threshold_value) if rule.threshold_value else None,
            "severity": rule.severity,
            "risk_weight": float(rule.risk_weight),
            "version": rule.version,
            "created_at": rule.created_at.isoformat()
        }
    
    except HTTPException:
        raise
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail=f"Fraud rule {rule_create.rule_id} already exists")
    except Exception as e:
        logger.error(f"Create fraud rule failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create fraud rule"
        )


@router.patch("/{rule_id}", response_model=dict)
async def update_fraud_rule(
    rule_id: str,
    rule_update: FraudRuleUpdate,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Update fraud rule (admin only)."""
    check_admin(current_user)
    
    try:
        document = db["fraud_rules"].find_one({"rule_id": rule_id})
        rule = FraudRule.model_validate(from_bson(document)) if document else None
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fraud rule {rule_id} not found"
            )
        
        # Validate risk_weight if provided
        if rule_update.risk_weight is not None:
            if rule_update.risk_weight < 0 or rule_update.risk_weight > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="risk_weight must be between 0 and 100"
                )
        
        # Update fields
        update_data = to_bson(rule_update.model_dump(exclude_unset=True))
        update_data["updated_at"] = datetime.now().astimezone()
        db["fraud_rules"].update_one(
            {"rule_id": rule_id},
            {"$set": update_data, "$inc": {"version": 1}},
        )
        rule = FraudRule.model_validate(from_bson(db["fraud_rules"].find_one({"rule_id": rule_id})))
        
        logger.info(f"Fraud rule updated: {rule.rule_id}")
        
        return {
            "id": rule.id,
            "rule_id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "rule_type": rule.rule_type,
            "is_enabled": rule.is_enabled,
            "threshold_value": float(rule.threshold_value) if rule.threshold_value else None,
            "severity": rule.severity,
            "risk_weight": float(rule.risk_weight),
            "version": rule.version,
            "updated_at": rule.updated_at.isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update fraud rule failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update fraud rule"
        )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fraud_rule(
    rule_id: str,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Disable/soft delete fraud rule (admin only)."""
    check_admin(current_user)
    
    try:
        document = db["fraud_rules"].find_one({"rule_id": rule_id})
        rule = FraudRule.model_validate(from_bson(document)) if document else None
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fraud rule {rule_id} not found"
            )
        
        # Soft delete by disabling
        db["fraud_rules"].update_one(
            {"rule_id": rule_id},
            {"$set": {"is_enabled": False, "updated_at": datetime.now().astimezone()}},
        )
        
        logger.info(f"Fraud rule disabled: {rule.rule_id}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete fraud rule failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete fraud rule"
        )


@router.post("/{rule_id}/enable", response_model=dict)
async def enable_fraud_rule(
    rule_id: str,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Enable a disabled fraud rule (admin only)."""
    check_admin(current_user)
    
    try:
        document = db["fraud_rules"].find_one({"rule_id": rule_id})
        rule = FraudRule.model_validate(from_bson(document)) if document else None
        
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fraud rule {rule_id} not found"
            )
        
        db["fraud_rules"].update_one(
            {"rule_id": rule_id},
            {"$set": {"is_enabled": True, "updated_at": datetime.now().astimezone()}},
        )
        rule = FraudRule.model_validate(from_bson(db["fraud_rules"].find_one({"rule_id": rule_id})))
        
        logger.info(f"Fraud rule enabled: {rule.rule_id}")
        
        return {
            "id": rule.id,
            "rule_id": rule.rule_id,
            "name": rule.name,
            "is_enabled": rule.is_enabled,
            "updated_at": rule.updated_at.isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Enable fraud rule failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable fraud rule"
        )
