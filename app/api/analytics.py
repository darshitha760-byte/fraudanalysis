"""
Analytics API endpoints for fraud detection metrics and analytics.
Provides comprehensive analytics for transaction, alert, and risk data.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Optional, List
from pydantic import BaseModel

from app.db.database import get_db
from app.services.analytics_service import AnalyticsService
from app.core.security import get_current_user, require_role
from app.core.permissions import UserRole
from app.models import User
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# Pydantic models for responses
class TransactionStatsResponse(BaseModel):
    total_transactions: int
    total_volume: float
    average_amount: float
    high_risk_transactions: int
    medium_risk_transactions: int
    low_risk_transactions: int
    min_amount: float
    max_amount: float
    days: int


class RiskDistributionResponse(BaseModel):
    LOW: int
    MEDIUM: int
    HIGH: int
    total: int


class AlertStatsResponse(BaseModel):
    total_alerts: int
    pending_alerts: int
    under_review_alerts: int
    resolved_alerts: int
    dismissed_alerts: int
    approved_alerts: int
    rejected_alerts: int
    approval_rate: float
    rejection_rate: float
    average_review_time_hours: float
    days: int


class CustomerRiskProfileResponse(BaseModel):
    customer_id: str
    total_transactions: int
    high_risk_count: int
    fraud_rate: float
    average_transaction_amount: float
    suspicious_patterns: List[str]
    risk_profile: str


class HighRiskCustomerResponse(BaseModel):
    customer_id: str
    total_transactions: int
    high_risk_count: int
    fraud_rate: float
    average_transaction_amount: float
    suspicious_patterns: List[str]
    risk_profile: str


class AnomalyResponse(BaseModel):
    type: str
    severity: str
    description: str


class DailyTrendResponse(BaseModel):
    date: str
    transaction_count: int
    total_volume: float
    average_amount: float


class AnalyticsOverviewResponse(BaseModel):
    total_transactions: int
    total_alerts: int
    fraud_confirmation_rate: float
    false_positive_rate: float
    approval_rate: float
    rejection_rate: float
    average_review_time_hours: float
    high_risk_customers_count: int
    critical_anomalies: int
    pending_alerts: int
    under_review_alerts: int
    risk_distribution: dict


class FraudMetricsResponse(BaseModel):
    fraud_confirmation_rate: float
    false_positive_rate: float
    overall_fraud_rate: float


class MerchantCategoryResponse(BaseModel):
    category: str
    transaction_count: int
    total_volume: float
    average_risk_score: float


class TransactionTypeResponse(BaseModel):
    transaction_type: str
    count: int
    volume: float
    high_risk_count: int
    average_risk_score: float


class PaymentMethodResponse(BaseModel):
    payment_method: str
    count: int
    volume: float
    high_risk_count: int
    fraud_rate: float


class GeographicDataResponse(BaseModel):
    country: str
    city: Optional[str]
    transaction_count: int
    total_volume: float
    high_risk_count: int
    average_risk_score: float


class ChannelAnalysisResponse(BaseModel):
    channel: str
    count: int
    volume: float
    high_risk_count: int
    fraud_rate: float


class RiskScoreDistributionResponse(BaseModel):
    risk_score_bucket: str
    count: int
    percentage: float


@router.get("/health", status_code=200)
async def analytics_health():
    """Health check for analytics service."""
    return {"status": "healthy", "service": "analytics"}


@router.get("/dashboard", response_model=AnalyticsOverviewResponse)
def get_dashboard_overview(
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get comprehensive dashboard overview metrics.
    
    Includes:
    - Total transactions and alerts
    - Fraud rates and approval rates
    - High-risk customer count
    - Anomaly detection results
    """
    try:
        overview = AnalyticsService.get_dashboard_overview(db)
        return AnalyticsOverviewResponse(**overview)
    except Exception as e:
        logger.error(f"Error getting dashboard overview: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving dashboard data"
        )


@router.get("/transactions", response_model=TransactionStatsResponse)
def get_transactions(
    days: int = Query(30, ge=1, le=365),
    customer_id: Optional[int] = Query(None),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get transaction statistics.
    
    Query Parameters:
    - days: Number of days to analyze (1-365, default 30)
    - customer_id: Optional customer filter
    """
    try:
        stats = AnalyticsService.get_transaction_statistics(
            db, days=days, customer_id=customer_id
        )
        return TransactionStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting transaction statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving transaction statistics"
        )


@router.get("/trends", response_model=List[DailyTrendResponse])
async def get_trends(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get daily transaction trends.
    
    Returns daily transaction counts and volumes for charting.
    
    Query Parameters:
    - days: Number of days to analyze (1-365, default 30)
    """
    try:
        trends = AnalyticsService.get_transaction_trends(db, days=days)
        return [DailyTrendResponse(**t) for t in trends]
    except Exception as e:
        logger.error(f"Error getting transaction trends: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving transaction trends"
        )


@router.get("/alerts", response_model=AlertStatsResponse)
async def get_alerts(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get alert statistics and metrics.
    
    Includes pending, under review, resolved alerts and rates.
    
    Query Parameters:
    - days: Number of days to analyze (1-365, default 30)
    """
    try:
        stats = AnalyticsService.get_alert_statistics(db, days=days)
        return AlertStatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error getting alert statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving alert statistics"
        )


@router.get("/customers")
def get_customers(
    limit: int = Query(10, ge=1, le=100),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get high-risk customers.
    
    Returns top customers by fraud rate.
    
    Query Parameters:
    - limit: Number of customers to return (1-100, default 10)
    """
    try:
        customers = AnalyticsService.get_high_risk_customers(db, limit=limit)
        return {
            "high_risk_customers": [HighRiskCustomerResponse(**c).dict() for c in customers],
            "customers": [HighRiskCustomerResponse(**c).dict() for c in customers]
        }
    except Exception as e:
        logger.error(f"Error getting high-risk customers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving high-risk customers"
        )


@router.get("/anomalies", response_model=List[AnomalyResponse])
async def get_anomalies(
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get detected transaction anomalies.
    
    Returns list of detected anomalies:
    - Large spikes in transaction volume
    - Unusual time-of-day patterns
    - Geographic anomalies
    - Velocity anomalies
    """
    try:
        anomalies = AnalyticsService.detect_transaction_anomalies(db)
        return [AnomalyResponse(**a) for a in anomalies]
    except Exception as e:
        logger.error(f"Error detecting anomalies: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error detecting anomalies"
        )


@router.get("/fraud-rate")
async def get_fraud_rate(
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get overall fraud metrics.
    
    Returns:
    - Fraud confirmation rate
    - False positive rate
    - Overall fraud rate
    """
    try:
        fraud_confirmed_rate = AnalyticsService.get_fraud_confirmed_rate(db)
        false_positive_rate = AnalyticsService.get_false_positive_rate(db)
        overall_fraud_rate = (fraud_confirmed_rate + false_positive_rate) / 2 if (fraud_confirmed_rate + false_positive_rate) > 0 else 0
        
        return {
            "fraud_rate": fraud_confirmed_rate,
            "confirmed_rate": fraud_confirmed_rate,
            "false_positive_rate": false_positive_rate,
            "rejection_rate": false_positive_rate,
            "overall_fraud_rate": overall_fraud_rate
        }
    except Exception as e:
        logger.error(f"Error getting fraud rate: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving fraud rate"
        )


@router.get("/performance")
async def get_performance(
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get system performance metrics.
    
    Returns:
    - Average processing time
    - System health status
    - API response times
    """
    try:
        stats = AnalyticsService.get_alert_statistics(db)
        return {
            "average_review_time": stats.get("average_review_time_hours", 0),
            "average_review_time_hours": stats.get("average_review_time_hours", 0),
            "performance_metrics": {
                "average_review_time": stats.get("average_review_time_hours", 0),
                "total_alerts": stats.get("total_alerts", 0),
                "pending_alerts": stats.get("pending_alerts", 0)
            },
            "total_alerts": stats.get("total_alerts", 0),
            "pending_alerts": stats.get("pending_alerts", 0),
            "system_health": "healthy"
        }
    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving performance metrics"
        )


@router.get("/export")
async def export_analytics(
    format: str = Query("json", regex="^(json|csv)$"),
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Export analytics data.
    
    Query Parameters:
    - format: Export format (json or csv, default json)
    - days: Number of days to export (1-365, default 30)
    """
    try:
        # Get all analytics data
        transactions = AnalyticsService.get_transaction_statistics(db, days=days)
        alerts = AnalyticsService.get_alert_statistics(db, days=days)
        
        if format == "json":
            return {
                "transactions": transactions,
                "alerts": alerts,
                "export_format": "json"
            }
        else:
            # CSV format (simplified)
            return {
                "message": "CSV export functionality",
                "transactions_data": transactions,
                "alerts_data": alerts,
                "export_format": "csv"
            }
    except Exception as e:
        logger.error(f"Error exporting analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error exporting analytics data"
        )


@router.get("/merchant-categories")
async def get_merchant_categories(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get transaction volume and risk by merchant category.
    
    Returns data for merchant category bar chart.
    """
    try:
        categories = AnalyticsService.get_merchant_category_analysis(db, days=days)
        return [MerchantCategoryResponse(**c).dict() for c in categories]
    except Exception as e:
        logger.error(f"Error getting merchant categories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving merchant category data"
        )


@router.get("/transaction-types")
async def get_transaction_types(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get transaction breakdown by type (purchase, withdrawal, transfer, etc).
    
    Returns data for transaction type pie/bar chart.
    """
    try:
        types = AnalyticsService.get_transaction_type_analysis(db, days=days)
        return [TransactionTypeResponse(**t).dict() for t in types]
    except Exception as e:
        logger.error(f"Error getting transaction types: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving transaction type data"
        )


@router.get("/payment-methods")
async def get_payment_methods(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get payment method distribution and fraud rates.
    
    Returns data for payment method bar/pie chart.
    """
    try:
        methods = AnalyticsService.get_payment_method_analysis(db, days=days)
        return [PaymentMethodResponse(**m).dict() for m in methods]
    except Exception as e:
        logger.error(f"Error getting payment methods: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving payment method data"
        )


@router.get("/geographic")
async def get_geographic_data(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get transaction data by geographic location (country/city).
    
    Returns data for geographic heatmap and distribution charts.
    """
    try:
        locations = AnalyticsService.get_geographic_analysis(db, days=days)
        return [GeographicDataResponse(**loc).dict() for loc in locations]
    except Exception as e:
        logger.error(f"Error getting geographic data: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving geographic data"
        )


@router.get("/channel-analysis")
async def get_channel_analysis(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get transaction volume and fraud by channel (online, atm, pos, phone, etc).
    
    Returns data for channel comparison charts.
    """
    try:
        channels = AnalyticsService.get_channel_analysis(db, days=days)
        return [ChannelAnalysisResponse(**c).dict() for c in channels]
    except Exception as e:
        logger.error(f"Error getting channel analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving channel data"
        )


@router.get("/risk-distribution")
async def get_risk_distribution(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),
    current_user = Depends(get_current_user)
):
    """
    Get risk score distribution histogram data.
    
    Returns bucketed risk scores for histogram visualization.
    """
    try:
        distribution = AnalyticsService.get_risk_score_distribution(db, days=days)
        return [RiskScoreDistributionResponse(**d).dict() for d in distribution]
    except Exception as e:
        logger.error(f"Error getting risk distribution: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving risk distribution data"
        )
