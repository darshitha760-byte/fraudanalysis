"""
Alert Management API - Handles analyst workflow for fraud alert review and decisions.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status, status as http_status
from pydantic import BaseModel, Field

from app.db.database import from_bson, get_db
from app.models.user import User
from app.services.alert_service import AlertService
from app.services.case_service import CaseService
from app.services.audit_service import AuditService
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ===== REQUEST/RESPONSE SCHEMAS =====

class AlertDetailResponse(BaseModel):
    """Response for alert detail endpoint."""
    alert_id: int
    transaction_id: int
    customer_id: int
    risk_score: float
    risk_level: str
    alert_status: str
    alert_severity: str
    triggered_rules: List[str]
    ml_score: Optional[float] = None
    created_at: datetime
    analyst_notes: Optional[str] = None
    review_decision: Optional[str] = None
    reviewed_by: Optional[int] = None
    review_timestamp: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AlertListItem(BaseModel):
    """Item in alert list response."""
    alert_id: int
    transaction_id: int
    risk_score: float
    risk_level: str
    alert_status: str
    alert_severity: str
    created_at: datetime
    reviewed_by: Optional[int] = None
    
    class Config:
        from_attributes = True


class AlertDecisionRequest(BaseModel):
    """Request body for analyst decision on alert."""
    decision: str = Field(
        ..., 
        description="APPROVED (fraud confirmed), REJECTED (not fraud), or NEEDS_REVIEW"
    )
    justification: str = Field(
        ..., 
        min_length=10,
        description="Reasoning for the decision"
    )


class ReviewStatusRequest(BaseModel):
    """Request to mark alert for review."""
    analyst_notes: Optional[str] = Field(None, description="Initial analyst notes")


class AlertSearchRequest(BaseModel):
    """Request for alert search."""
    query: Optional[str] = Field(None, description="Search query")
    status: Optional[str] = Field(None, description="Filter by status")
    severity: Optional[str] = Field(None, description="Filter by severity")
    priority: Optional[str] = Field(None, description="Filter by priority")
    min_risk_score: Optional[float] = Field(None, description="Minimum risk score")
    max_risk_score: Optional[float] = Field(None, description="Maximum risk score")
    limit: int = Field(50, ge=1, le=500)
    offset: int = Field(0, ge=0)


class PaginatedAlertResponse(BaseModel):
    """Paginated response for alerts."""
    alerts: List[AlertListItem]
    total: int
    limit: int
    offset: int


class AlertStatsResponse(BaseModel):
    """Response for alert statistics."""
    total_alerts: int
    pending_alerts: int
    under_review_alerts: int
    resolved_alerts: int
    high_severity_count: int
    medium_severity_count: int
    low_severity_count: int
    average_risk_score: float
    approval_rate: float
    rejection_rate: float


# ===== ENDPOINTS =====

@router.get("/pending", response_model=PaginatedAlertResponse)
async def get_pending_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get alerts awaiting review.
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view pending alerts"
        )
    
    try:
        alerts, total = AlertService.get_pending_alerts_paginated(
            db, 
            limit=limit, 
            offset=offset
        )
        
        return PaginatedAlertResponse(
            alerts=alerts,
            total=total,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"Error fetching pending alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching pending alerts"
        )


@router.get("/my-alerts", response_model=PaginatedAlertResponse)
async def get_my_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get current analyst's assigned alerts.
    
    Accessible by: analyst (returns their own alerts only)
    """
    if current_user.role != "analyst":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only analysts can view their own alerts"
        )
    
    try:
        alerts, total = AlertService.get_analyst_alerts_paginated(
            db, 
            analyst_id=current_user.id,
            limit=limit,
            offset=offset
        )
        
        return PaginatedAlertResponse(
            alerts=alerts,
            total=total,
            limit=limit,
            offset=offset
        )
    except Exception as e:
        logger.error(f"Error fetching analyst alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching analyst alerts"
        )


@router.get("/{alert_id}", response_model=AlertDetailResponse)
async def get_alert_detail(
    alert_id: int,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get detailed alert information.
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view alerts"
        )
    
    try:
        alert = db["fraud_alerts"].find_one({"id": alert_id})
        
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found"
            )
        
        # Format alert response with all required fields
        alert_data = AlertService._format_alert_response(from_bson(alert))
        
        # Parse triggered_rules from summary string
        triggered_rules = []
        if alert_data.get("triggered_rules_summary"):
            triggered_rules = [rule.strip() for rule in alert_data["triggered_rules_summary"].split(",")]
        
        alert_data["triggered_rules"] = triggered_rules
        alert_data["alert_id"] = alert_data["alert_id"]
        alert_data["transaction_id"] = alert_data["transaction_id"]
        alert_data["customer_id"] = alert_data["customer_id"]
        alert_data["risk_score"] = alert_data.get("risk_score", 0.0)
        alert_data["risk_level"] = alert_data.get("risk_level", "low")
        alert_data["alert_status"] = alert_data["alert_status"]
        alert_data["alert_severity"] = alert_data["alert_severity"]
        alert_data["ml_score"] = alert_data.get("ml_score")
        alert_data["created_at"] = alert_data.get("created_at") or alert_data.get("alert_created_at")
        alert_data["analyst_notes"] = alert_data.get("review_notes")
        alert_data["review_decision"] = alert_data.get("review_decision")
        alert_data["reviewed_by"] = alert_data.get("reviewed_by")
        alert_data["review_timestamp"] = alert_data.get("review_timestamp")
        
        return AlertDetailResponse.model_validate(alert_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching alert"
        )


@router.put("/{alert_id}/review")
async def mark_alert_for_review(
    alert_id: int,
    request: ReviewStatusRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Mark alert as UNDER_REVIEW by analyst.
    
    Accessible by: analyst, admin
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can review alerts"
        )
    
    try:
        alert = db["fraud_alerts"].find_one({"id": alert_id})
        
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found"
            )
        
        # Update alert status
        old_status = alert.get("alert_status")
        AlertService.update_alert_status(
            db,
            alert_id,
            "under_review",
            reviewed_by_user_id=current_user.id,
            review_notes=request.analyst_notes,
        )
        
        # Log the action
        AuditService.log_alert_status_change(
            db=db,
            alert_id=alert_id,
            old_status=old_status,
            new_status="UNDER_REVIEW",
            analyst_id=current_user.id
        )
        
        logger.info(f"Alert {alert_id} marked for review by analyst {current_user.id}")
        
        return {
            "status": "success",
            "alert_id": alert_id,
            "new_status": "UNDER_REVIEW",
            "message": "Alert marked for review"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking alert {alert_id} for review: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating alert"
        )


@router.put("/{alert_id}/decide")
async def record_analyst_decision(
    alert_id: int,
    request: AlertDecisionRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Record analyst's decision on an alert.
    
    Decision types:
    - APPROVED: Fraud confirmed, create investigation case
    - REJECTED: Not fraud, close alert
    - NEEDS_REVIEW: Escalate for further review
    
    Accessible by: analyst, admin
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can make decisions"
        )
    
    if request.decision not in ["APPROVED", "REJECTED", "NEEDS_REVIEW"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid decision. Must be APPROVED, REJECTED, or NEEDS_REVIEW"
        )
    
    try:
        alert = db["fraud_alerts"].find_one({"id": alert_id})
        
        if not alert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Alert {alert_id} not found"
            )
        
        # Record decision
        old_status = alert.get("alert_status")
        
        # Update status based on decision
        if request.decision == "APPROVED":
            new_status = "resolved"
            case_type = "FRAUD_CONFIRMED"
        elif request.decision == "REJECTED":
            new_status = "resolved"
            case_type = "FALSE_POSITIVE"
        else:  # NEEDS_REVIEW
            new_status = "pending"
            case_type = "UNDER_INVESTIGATION"
        AlertService.update_alert_status(
            db,
            alert_id,
            new_status,
            reviewed_by_user_id=current_user.id,
            review_decision=request.decision,
            review_notes=request.justification,
        )
        
        # Create investigation case if fraud confirmed or needs review
        if request.decision in ["APPROVED", "NEEDS_REVIEW"]:
            try:
                CaseService.create_case_from_alert(
                    db,
                    alert_id=alert_id,
                    case_type=case_type,
                    assigned_to=current_user.id,
                    summary=f"Case created from analyst decision: {request.decision}"
                )
            except Exception as e:
                logger.warning(f"Could not create case for alert {alert_id}: {e}")
        
        # Log the decision
        AuditService.log_analyst_decision(
            db=db,
            alert_id=alert_id,
            decision=request.decision,
            justification=request.justification,
            analyst_id=current_user.id
        )
        
        logger.info(
            f"Analyst {current_user.id} recorded decision on alert {alert_id}: {request.decision}"
        )
        
        return {
            "status": "success",
            "alert_id": alert_id,
            "decision": request.decision,
            "alert_status": new_status.upper(),
            "message": f"Decision recorded: {request.decision}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error recording decision on alert {alert_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error recording decision"
        )


@router.get("/status/{status}", response_model=PaginatedAlertResponse)
async def get_alerts_by_status(
    status: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Filter alerts by status.
    
    Valid statuses: PENDING, UNDER_REVIEW, RESOLVED, DISMISSED
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view alerts"
        )
    
    valid_statuses = ["PENDING", "UNDER_REVIEW", "RESOLVED", "DISMISSED"]
    if status.upper() not in valid_statuses:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        )
    
    try:
        alerts, total = AlertService.get_alerts_by_status_paginated(
            db,
            status=status.upper(),
            limit=limit,
            offset=offset
        )
        
        return PaginatedAlertResponse(
            alerts=alerts,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error fetching alerts by status: {e}", exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching alerts"
        )


@router.get("/priority/{priority}", response_model=PaginatedAlertResponse)
async def get_alerts_by_priority(
    priority: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Filter alerts by priority/severity.
    
    Valid priorities: HIGH, MEDIUM, LOW
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view alerts"
        )
    
    valid_priorities = ["HIGH", "MEDIUM", "LOW"]
    if priority.upper() not in valid_priorities:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid priority. Must be one of: {', '.join(valid_priorities)}"
        )
    
    try:
        alerts, total = AlertService.get_alerts_by_priority_paginated(
            db,
            priority=priority.upper(),
            limit=limit,
            offset=offset
        )
        
        return PaginatedAlertResponse(
            alerts=alerts,
            total=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error fetching alerts by priority: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching alerts"
        )


@router.post("/search", response_model=PaginatedAlertResponse)
async def search_alerts(
    request: AlertSearchRequest,
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Search alerts with advanced filters.
    
    Filters:
    - query: Search term (in transaction details)
    - status: Alert status
    - severity: Alert severity (HIGH, MEDIUM, LOW)
    - priority: Alert priority
    - min_risk_score: Minimum risk score (0-100)
    - max_risk_score: Maximum risk score (0-100)
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can search alerts"
        )
    
    try:
        alerts, total = AlertService.search_alerts_paginated(
            db,
            query=request.query,
            filters={
                "status": request.status,
                "severity": request.severity,
                "priority": request.priority,
                "min_risk_score": request.min_risk_score,
                "max_risk_score": request.max_risk_score,
            },
            limit=request.limit,
            offset=request.offset
        )
        
        return PaginatedAlertResponse(
            alerts=alerts,
            total=total,
            limit=request.limit,
            offset=request.offset
        )
        
    except Exception as e:
        logger.error(f"Error searching alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error searching alerts"
        )


@router.get("/stats/summary", response_model=AlertStatsResponse)
async def get_alert_stats_summary(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get alert statistics summary.
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view statistics"
        )
    
    try:
        stats = AlertService.get_alert_statistics(db)
        return AlertStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error fetching alert statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching statistics"
        )
