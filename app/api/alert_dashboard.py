"""
Alert Dashboard API - Provides analytics and statistics for alert management.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.db.database import get_db
from app.models.user import User
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts/stats", tags=["alert-statistics"])


# ===== RESPONSE SCHEMAS =====

class TimelinePoint(BaseModel):
    """Point in timeline data."""
    timestamp: datetime
    alert_count: int
    high_priority: int
    medium_priority: int
    low_priority: int


class TimelineResponse(BaseModel):
    """Response for timeline statistics."""
    points: List[TimelinePoint]
    total_alerts: int
    period: str


class AnalystPerformance(BaseModel):
    """Performance metrics for an analyst."""
    analyst_id: int
    analyst_name: str
    alerts_reviewed: int
    alerts_approved: int
    alerts_rejected: int
    alerts_escalated: int
    approval_rate: float
    average_review_time_hours: float


class AnalystStatsResponse(BaseModel):
    """Response for analyst performance statistics."""
    analysts: List[AnalystPerformance]
    total_reviewed: int
    average_approval_rate: float


class PriorityDistribution(BaseModel):
    """Distribution by priority."""
    high: int
    medium: int
    low: int
    total: int


class PriorityStatsResponse(BaseModel):
    """Response for priority distribution statistics."""
    distribution: PriorityDistribution
    high_percentage: float
    medium_percentage: float
    low_percentage: float


class DecisionStats(BaseModel):
    """Decision statistics."""
    total_decisions: int
    approved: int
    rejected: int
    escalated: int
    approval_rate: float
    rejection_rate: float
    escalation_rate: float


class ApprovalRateResponse(BaseModel):
    """Response for approval rate statistics."""
    current_rate: float
    previous_period_rate: float
    trend: str
    stats: DecisionStats


# ===== ENDPOINTS =====

@router.get("/summary")
async def get_alert_summary_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get overall alert statistics summary.
    
    Includes:
    - Total alerts by status
    - Distribution by severity
    - Average risk scores
    - Approval/rejection rates
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view statistics"
        )
    
    try:
        # Count by status
        alerts = db["fraud_alerts"]
        total = alerts.count_documents({})
        pending = alerts.count_documents({"alert_status": {"$regex": "^pending$", "$options": "i"}})
        under_review = alerts.count_documents({"alert_status": {"$regex": "^under_review$", "$options": "i"}})
        resolved = alerts.count_documents({"alert_status": {"$regex": "^resolved$", "$options": "i"}})
        
        # Count by severity
        high_severity = alerts.count_documents({"alert_severity": {"$regex": "^high$", "$options": "i"}})
        medium_severity = alerts.count_documents({"alert_severity": {"$regex": "^medium$", "$options": "i"}})
        low_severity = alerts.count_documents({"alert_severity": {"$regex": "^low$", "$options": "i"}})
        
        # Average risk score
        average = list(alerts.aggregate([{"$group": {"_id": None, "value": {"$avg": "$risk_score"}}}]))
        avg_risk = average[0]["value"] if average else 0.0
        if hasattr(avg_risk, "to_decimal"):
            avg_risk = avg_risk.to_decimal()
        
        # Decision rates
        approved = alerts.count_documents({"review_decision": {"$regex": "^approved$", "$options": "i"}})
        rejected = alerts.count_documents({"review_decision": {"$regex": "^rejected$", "$options": "i"}})
        
        total_decisions = approved + rejected
        approval_rate = (approved / total_decisions * 100) if total_decisions > 0 else 0
        rejection_rate = (rejected / total_decisions * 100) if total_decisions > 0 else 0
        
        return {
            "status": "success",
            "total_alerts": total,
            "pending_alerts": pending,
            "under_review_alerts": under_review,
            "resolved_alerts": resolved,
            "high_severity_count": high_severity,
            "medium_severity_count": medium_severity,
            "low_severity_count": low_severity,
            "average_risk_score": round(float(avg_risk), 2),
            "approval_rate": round(approval_rate, 2),
            "rejection_rate": round(rejection_rate, 2),
        }
        
    except Exception as e:
        logger.error(f"Error fetching alert summary: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching alert summary"
        )


@router.get("/timeline", response_model=TimelineResponse)
async def get_alert_timeline(
    days: int = Query(7, ge=1, le=90, description="Number of days to include"),
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get alert creation timeline over specified period.
    
    Shows daily alert volumes by priority level.
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view statistics"
        )
    
    try:
        # Calculate date range
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=days)
        
        # Query alerts for each day
        timeline_points = []
        for i in range(days):
            current_date = start_date + timedelta(days=i)
            next_date = current_date + timedelta(days=1)
            
            # Count all alerts created on this day
            interval = {"created_at": {"$gte": datetime.combine(current_date, datetime.min.time(), timezone.utc),
                                       "$lt": datetime.combine(next_date, datetime.min.time(), timezone.utc)}}
            total_count = db["fraud_alerts"].count_documents(interval)
            
            # Count by severity
            high_count = db["fraud_alerts"].count_documents({**interval, "alert_severity": {"$regex": "^high$", "$options": "i"}})
            
            medium_count = db["fraud_alerts"].count_documents({**interval, "alert_severity": {"$regex": "^medium$", "$options": "i"}})
            
            low_count = db["fraud_alerts"].count_documents({**interval, "alert_severity": {"$regex": "^low$", "$options": "i"}})
            
            timeline_points.append(TimelinePoint(
                timestamp=datetime.combine(current_date, datetime.min.time(), timezone.utc),
                alert_count=total_count,
                high_priority=high_count,
                medium_priority=medium_count,
                low_priority=low_count,
            ))
        
        total_alerts = sum(p.alert_count for p in timeline_points)
        
        return TimelineResponse(
            points=timeline_points,
            total_alerts=total_alerts,
            period=f"Last {days} days"
        )
        
    except Exception as e:
        logger.error(f"Error fetching alert timeline: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching timeline"
        )


@router.get("/by-analyst", response_model=AnalystStatsResponse)
async def get_analyst_performance_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get alert review statistics by analyst.
    
    Shows:
    - Alerts reviewed per analyst
    - Approval/rejection rates
    - Average review time
    
    Accessible by: admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view analyst performance statistics"
        )
    
    try:
        # Get all analysts who have reviewed alerts
        analyst_stats = []
        
        # Query distinct analysts
        analysts = db["fraud_alerts"].distinct("reviewed_by", {"reviewed_by": {"$ne": None}})
        
        total_reviewed = 0
        
        for analyst_id in analysts:
            if not analyst_id:
                continue
            
            # Get analyst info
            analyst_user = db["users"].find_one({"id": analyst_id})
            analyst_name = analyst_user.get("full_name", analyst_user.get("email")) if analyst_user else f"User {analyst_id}"
            
            # Count alerts reviewed by this analyst
            alerts_reviewed = db["fraud_alerts"].count_documents({"reviewed_by": analyst_id})
            
            approved = db["fraud_alerts"].count_documents({"reviewed_by": analyst_id, "review_decision": {"$regex": "^approved$", "$options": "i"}})
            
            rejected = db["fraud_alerts"].count_documents({"reviewed_by": analyst_id, "review_decision": {"$regex": "^rejected$", "$options": "i"}})
            
            escalated = db["fraud_alerts"].count_documents({"reviewed_by": analyst_id, "review_decision": {"$regex": "^needs_review$", "$options": "i"}})
            
            approval_rate = (approved / alerts_reviewed * 100) if alerts_reviewed > 0 else 0
            
            # Calculate average review time (simplified)
            avg_review_time = 2.5  # Placeholder - would need review_timestamp in real system
            
            total_reviewed += alerts_reviewed
            
            analyst_stats.append(AnalystPerformance(
                analyst_id=analyst_id,
                analyst_name=analyst_name,
                alerts_reviewed=alerts_reviewed,
                alerts_approved=approved,
                alerts_rejected=rejected,
                alerts_escalated=escalated,
                approval_rate=round(approval_rate, 2),
                average_review_time_hours=avg_review_time,
            ))
        
        # Calculate average approval rate
        total_approved = sum(s.alerts_approved for s in analyst_stats)
        avg_approval_rate = (
            (total_approved / total_reviewed * 100) if total_reviewed > 0 else 0
        )
        
        return AnalystStatsResponse(
            analysts=analyst_stats,
            total_reviewed=total_reviewed,
            average_approval_rate=round(avg_approval_rate, 2),
        )
        
    except Exception as e:
        logger.error(f"Error fetching analyst stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching analyst statistics"
        )


@router.get("/by-priority", response_model=PriorityStatsResponse)
async def get_priority_distribution_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get alert distribution by priority/severity.
    
    Shows percentage breakdown of HIGH, MEDIUM, and LOW severity alerts.
    
    Accessible by: admin, analyst
    """
    if current_user.role not in ["admin", "analyst"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins and analysts can view statistics"
        )
    
    try:
        alerts = db["fraud_alerts"]
        high = alerts.count_documents({"alert_severity": {"$regex": "^high$", "$options": "i"}})
        medium = alerts.count_documents({"alert_severity": {"$regex": "^medium$", "$options": "i"}})
        low = alerts.count_documents({"alert_severity": {"$regex": "^low$", "$options": "i"}})
        
        total = high + medium + low
        
        high_pct = (high / total * 100) if total > 0 else 0
        medium_pct = (medium / total * 100) if total > 0 else 0
        low_pct = (low / total * 100) if total > 0 else 0
        
        return PriorityStatsResponse(
            distribution=PriorityDistribution(
                high=high,
                medium=medium,
                low=low,
                total=total,
            ),
            high_percentage=round(high_pct, 2),
            medium_percentage=round(medium_pct, 2),
            low_percentage=round(low_pct, 2),
        )
        
    except Exception as e:
        logger.error(f"Error fetching priority distribution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching priority statistics"
        )


@router.get("/approval-rate", response_model=ApprovalRateResponse)
async def get_approval_rate_stats(
    current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """
    Get decision statistics and approval/rejection rates.
    
    Accessible by: admin
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view approval rate statistics"
        )
    
    try:
        # Current period (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        alert_collection = db["fraud_alerts"]

        def decision_count(decision, since, until=None):
            query = {
                "review_decision": {"$regex": f"^{decision}$", "$options": "i"},
                "review_timestamp": {"$gte": since},
            }
            if until is not None:
                query["review_timestamp"]["$lt"] = until
            return alert_collection.count_documents(query)

        current_approved = decision_count("APPROVED", thirty_days_ago)
        current_rejected = decision_count("REJECTED", thirty_days_ago)
        current_escalated = decision_count("NEEDS_REVIEW", thirty_days_ago)
        
        current_total = current_approved + current_rejected + current_escalated
        current_approval_rate = (
            current_approved / current_total * 100 if current_total > 0 else 0
        )
        
        # Previous period (30-60 days ago)
        sixty_days_ago = datetime.now(timezone.utc) - timedelta(days=60)
        prev_approved = decision_count("APPROVED", sixty_days_ago, thirty_days_ago)
        prev_rejected = decision_count("REJECTED", sixty_days_ago, thirty_days_ago)
        prev_escalated = decision_count("NEEDS_REVIEW", sixty_days_ago, thirty_days_ago)
        
        prev_total = prev_approved + prev_rejected + prev_escalated
        prev_approval_rate = (
            prev_approved / prev_total * 100 if prev_total > 0 else 0
        )
        
        # Determine trend
        trend = "up" if current_approval_rate > prev_approval_rate else "down"
        if abs(current_approval_rate - prev_approval_rate) < 1:
            trend = "stable"
        
        return ApprovalRateResponse(
            current_rate=round(current_approval_rate, 2),
            previous_period_rate=round(prev_approval_rate, 2),
            trend=trend,
            stats=DecisionStats(
                total_decisions=current_total,
                approved=current_approved,
                rejected=current_rejected,
                escalated=current_escalated,
                approval_rate=round(current_approval_rate, 2),
                rejection_rate=round(100 - current_approval_rate - 
                    (current_escalated / current_total * 100 if current_total > 0 else 0), 2),
                escalation_rate=round(current_escalated / current_total * 100 if current_total > 0 else 0, 2),
            ),
        )
        
    except Exception as e:
        logger.error(f"Error fetching approval rate stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching approval rate statistics"
        )
