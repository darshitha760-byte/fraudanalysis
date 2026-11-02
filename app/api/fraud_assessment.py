"""
Fraud Assessment API endpoints for risk assessment and alert management.
Provides REST API for transaction risk assessment and fraud analysis.
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from datetime import datetime

from app.db.database import get_db
from app.services.risk_engine import RiskEngine
from app.services.alert_service import AlertService
from app.models.fraud_alert import FraudAssessment
from app.core.security import get_current_user
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fraud-assessment", tags=["fraud-assessment"])

# Pydantic schemas for request/response

class FraudAssessmentRequest(BaseModel):
    """Request schema for fraud assessment."""
    transaction_id: int = Field(..., description="Transaction ID (database primary key)")
    customer_id: Optional[int] = Field(None, description="Customer ID (optional, looked up if not provided)")


class TriggeredRuleDetail(BaseModel):
    """Details of a triggered fraud rule."""
    rule_id: int
    rule_name: str
    severity: str
    explanation: str
    triggered_values: dict = Field(default_factory=dict)


class FraudAssessmentResponse(BaseModel):
    """Response schema for fraud assessment."""
    assessment_id: int = Field(..., description="Unique assessment ID")
    transaction_id: int = Field(..., description="Associated transaction ID")
    customer_id: int = Field(..., description="Customer ID")
    risk_score: float = Field(..., ge=0, le=100, description="Final risk score (0-100)")
    risk_level: str = Field(..., description="Risk level (LOW/MEDIUM/HIGH)")
    rule_score: float = Field(..., ge=0, le=100, description="Rule-based score")
    ml_score: float = Field(..., ge=0, le=100, description="ML-based score")
    triggered_rules: List[TriggeredRuleDetail] = Field(default_factory=list)
    alert_required: bool = Field(..., description="Whether alert should be created")
    created_at: datetime = Field(...)
    
    model_config = {"from_attributes": True}


class AssessmentDetailsResponse(BaseModel):
    """Detailed assessment response."""
    assessment_id: int
    transaction_id: int
    risk_score: float
    risk_category: str
    rules_triggered_count: int
    ml_score: Optional[float]
    ml_model_version: Optional[str]
    engine_version: str
    assessment_timestamp: datetime
    explanation: str
    assessment_metadata: dict = Field(default_factory=dict)
    triggered_rules: List[dict] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}


class AlertStatusUpdateRequest(BaseModel):
    """Request schema for updating alert status."""
    status: str = Field(..., description="New status (under_review, resolved, dismissed)")
    review_decision: Optional[str] = Field(None, description="Review decision (approved, rejected, escalated)")
    review_notes: Optional[str] = Field(None, description="Additional review notes")


class FraudAlertResponse(BaseModel):
    """Response schema for fraud alert."""
    alert_id: int
    transaction_id: int
    customer_id: int
    assessment_id: int
    alert_severity: str
    alert_status: str
    alert_reason: str
    triggered_rules_summary: Optional[str]
    reviewed_by: Optional[int]
    review_timestamp: Optional[datetime]
    review_decision: Optional[str]
    review_notes: Optional[str]
    alert_created_at: datetime
    alert_resolved_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """Response schema for alert list."""
    alerts: List[FraudAlertResponse]
    total_count: int
    limit: int
    offset: int


class AlertStatisticsResponse(BaseModel):
    """Response schema for alert statistics."""
    total_alerts: int
    status_counts: dict
    severity_counts: dict


# API Endpoints

@router.post("/assess", response_model=FraudAssessmentResponse, status_code=status.HTTP_201_CREATED)
async def assess_transaction_risk(
    request: FraudAssessmentRequest,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Assess fraud risk for a transaction.
    
    Combines fraud rule detection and ML model predictions to produce a comprehensive
    risk assessment with risk score (0-100) and risk level (LOW/MEDIUM/HIGH).
    
    Returns:
    - assessment_id: Unique assessment identifier
    - risk_score: Combined risk score (0-100)
    - risk_level: Risk category (LOW/MEDIUM/HIGH)
    - triggered_rules: List of fraud rules that were triggered
    - alert_required: Whether an alert should be created
    """
    try:
        logger.info(f"Assessing fraud risk for transaction {request.transaction_id}")
        
        risk_engine = RiskEngine()
        assessment = risk_engine.assess_fraud_risk(
            session=db,
            transaction_id=request.transaction_id,
            customer_id=request.customer_id
        )
        
        logger.info(f"Assessment complete: {assessment['assessment_id']}")
        
        # Create alert if needed
        if assessment["alert_required"]:
            try:
                alert = AlertService.create_fraud_alert(
                    session=db,
                    transaction_id=request.transaction_id,
                    customer_id=assessment["customer_id"],
                    assessment_id=assessment["assessment_id"],
                    risk_score=assessment["risk_score"],
                    risk_level=assessment["risk_level"],
                    alert_reason=f"Automatic alert created for {assessment['risk_level']} risk transaction",
                    triggered_rules_summary=", ".join(
                        [f"{r['rule_name']} ({r['severity']})" for r in assessment["triggered_rules"]]
                    ) if assessment["triggered_rules"] else None
                )
                logger.info(f"Alert created: {alert['alert_id']}")
            except Exception as e:
                logger.error(f"Failed to create alert: {e}")
                # Don't fail the assessment if alert creation fails
        
        return FraudAssessmentResponse(**assessment)
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error assessing fraud risk: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assess fraud risk"
        )


@router.get("/assessment/{assessment_id}", response_model=AssessmentDetailsResponse)
async def get_assessment(
    assessment_id: int,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Retrieve detailed fraud assessment by ID.
    
    Returns full assessment details including:
    - Risk scores and levels
    - Triggered rules with explanations
    - ML model predictions
    - Assessment metadata
    """
    try:
        risk_engine = RiskEngine()
        assessment = risk_engine.get_assessment(db, assessment_id)
        
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment {assessment_id} not found"
            )
        
        return AssessmentDetailsResponse(**assessment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving assessment: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve assessment"
        )


@router.get("/transaction/{transaction_id}", response_model=AssessmentDetailsResponse)
async def get_transaction_assessment(
    transaction_id: int,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get fraud assessment for a specific transaction.
    
    Args:
        transaction_id: Transaction database ID
    
    Returns:
        Assessment details for the transaction
    """
    try:
        risk_engine = RiskEngine()
        assessment = risk_engine.get_transaction_assessment(db, transaction_id)
        
        if not assessment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No assessment found for transaction {transaction_id}"
            )
        
        return AssessmentDetailsResponse(**assessment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transaction assessment: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve assessment"
        )


@router.get("/alerts/pending", response_model=AlertListResponse)
async def get_pending_alerts(
    db=Depends(get_db),
    current_user = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get all pending fraud alerts.
    
    Returns alerts awaiting analyst review, sorted by creation date (newest first).
    
    Query parameters:
    - limit: Number of results per page (1-500, default 100)
    - offset: Pagination offset (default 0)
    """
    try:
        alerts, total = AlertService.get_pending_alerts(
            session=db,
            limit=limit,
            offset=offset
        )
        
        return AlertListResponse(
            alerts=[FraudAlertResponse(**a) for a in alerts],
            total_count=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error retrieving pending alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve pending alerts"
        )


@router.get("/alerts", response_model=AlertListResponse)
async def get_alerts_by_status(
    db=Depends(get_db),
    current_user = Depends(get_current_user),
    status: str = Query("pending", description="Alert status filter"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get fraud alerts filtered by status.
    
    Query parameters:
    - status: Alert status (pending, under_review, resolved, dismissed)
    - limit: Number of results per page
    - offset: Pagination offset
    """
    try:
        alerts, total = AlertService.get_alerts_by_status(
            session=db,
            status=status,
            limit=limit,
            offset=offset
        )
        
        return AlertListResponse(
            alerts=[FraudAlertResponse(**a) for a in alerts],
            total_count=total,
            limit=limit,
            offset=offset
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error retrieving alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alerts"
        )


@router.get("/alerts/customer/{customer_id}", response_model=AlertListResponse)
async def get_customer_alerts(
    customer_id: int,
    db=Depends(get_db),
    current_user = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get all alerts for a specific customer.
    
    Path parameters:
    - customer_id: Customer ID
    
    Query parameters:
    - limit: Number of results per page
    - offset: Pagination offset
    """
    try:
        alerts, total = AlertService.get_alerts_by_customer(
            session=db,
            customer_id=customer_id,
            limit=limit,
            offset=offset
        )
        
        return AlertListResponse(
            alerts=[FraudAlertResponse(**a) for a in alerts],
            total_count=total,
            limit=limit,
            offset=offset
        )
        
    except Exception as e:
        logger.error(f"Error retrieving customer alerts: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customer alerts"
        )


@router.patch("/alerts/{alert_id}/status", response_model=FraudAlertResponse)
async def update_alert_status(
    alert_id: int,
    request: AlertStatusUpdateRequest,
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Update fraud alert status and review information.
    
    Allows analyst to review, approve, or dismiss alerts.
    
    Path parameters:
    - alert_id: Alert ID
    
    Request body:
    - status: New status (under_review, resolved, dismissed)
    - review_decision: Decision (approved, rejected, escalated)
    - review_notes: Additional notes
    """
    try:
        alert = AlertService.update_alert_status(
            session=db,
            alert_id=alert_id,
            new_status=request.status,
            reviewed_by_user_id=current_user.id,
            review_decision=request.review_decision,
            review_notes=request.review_notes
        )
        
        logger.info(f"Updated alert {alert_id}: status={request.status}")
        
        return FraudAlertResponse(**alert)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error updating alert status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update alert status"
        )


@router.post("/alerts/{alert_id}/dismiss", response_model=FraudAlertResponse)
async def dismiss_alert(
    alert_id: int,
    reason: str = Query(..., description="Reason for dismissal"),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Dismiss a fraud alert as false positive.
    
    Path parameters:
    - alert_id: Alert ID
    
    Query parameters:
    - reason: Reason for dismissal
    """
    try:
        alert = AlertService.dismiss_alert(
            session=db,
            alert_id=alert_id,
            reviewed_by_user_id=current_user.id,
            reason=reason
        )
        
        logger.info(f"Dismissed alert {alert_id}: {reason}")
        
        return FraudAlertResponse(**alert)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error dismissing alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dismiss alert"
        )


@router.post("/alerts/{alert_id}/approve", response_model=FraudAlertResponse)
async def approve_alert(
    alert_id: int,
    action_taken: str = Query(..., description="Action taken (blocked_card, frozen_account, etc.)"),
    notes: str = Query(None, description="Additional notes"),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Approve a fraud alert and mark as resolved.
    
    Path parameters:
    - alert_id: Alert ID
    
    Query parameters:
    - action_taken: Action taken to resolve
    - notes: Optional additional notes
    """
    try:
        alert = AlertService.approve_alert(
            session=db,
            alert_id=alert_id,
            reviewed_by_user_id=current_user.id,
            action_taken=action_taken,
            notes=notes
        )
        
        logger.info(f"Approved alert {alert_id}: action={action_taken}")
        
        return FraudAlertResponse(**alert)
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error approving alert: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve alert"
        )


@router.get("/statistics", response_model=AlertStatisticsResponse)
async def get_alert_statistics(
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get fraud alert statistics for dashboard.
    
    Returns:
    - Total alert count
    - Count by status
    - Count by severity
    """
    try:
        stats = AlertService.get_alert_statistics(db)
        return AlertStatisticsResponse(**stats)
        
    except Exception as e:
        logger.error(f"Error retrieving alert statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve alert statistics"
        )
