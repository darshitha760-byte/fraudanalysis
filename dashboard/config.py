"""
Dashboard Configuration
"""
import os
from enum import Enum

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
API_TIMEOUT = 30

# Session Configuration
SESSION_TIMEOUT_MINUTES = 15
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15

# Dashboard Configuration
DASHBOARD_TITLE = "Financial Fraud Detection System"
DASHBOARD_DESCRIPTION = "Real-time fraud detection and risk analysis platform"
THEME = "light"  # light or dark

# Pagination
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100

# Charts
CHART_HEIGHT = 400
CHART_COLOR_SCHEME = {
    "primary": "#0066CC",
    "success": "#22C55E",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "info": "#3B82F6",
    "risk_high": "#DC2626",
    "risk_medium": "#F97316",
    "risk_low": "#22C55E",
}

# Risk Levels
class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

RISK_THRESHOLDS = {
    RiskLevel.LOW: (0, 25),
    RiskLevel.MEDIUM: (25, 50),
    RiskLevel.HIGH: (50, 75),
    RiskLevel.CRITICAL: (75, 100),
}

# User Roles
class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"

ROLE_PERMISSIONS = {
    UserRole.ADMIN: [
        "view_analytics",
        "train_models",
        "view_dashboard",
        "view_transactions",
        "view_alerts",
        "manage_rules",
        "manage_users",
        "view_logs",
        "view_audit_logs",
        "view_models",
        "edit_rules",
        "review_alerts",
    ],
    UserRole.ANALYST: [
        "view_analytics",
        "train_models",
        "view_dashboard",
        "view_transactions",
        "view_alerts",
        "review_alerts",
        "view_models",
        "view_logs",
    ],
    UserRole.VIEWER: [
        "view_dashboard",
        "view_transactions",
        "view_models",
        "view_analytics",
    ],
}

# Page Configuration
PAGES = {
    "Login": {"file": "00_Login.py", "icon": "🔐", "show_in_nav": False},
    "Dashboard": {"file": "01_Dashboard.py", "icon": "📊", "roles": ["admin", "analyst", "viewer"]},
    "Transactions": {"file": "02_Transaction_Explorer.py", "icon": "💳", "roles": ["admin", "analyst", "viewer"]},
    "Fraud Alerts": {"file": "03_Fraud_Alerts.py", "icon": "🚨", "roles": ["admin", "analyst"]},
    "Risk Analytics": {"file": "04_Financial_Risk_Analytics.py", "icon": "📈", "roles": ["admin", "analyst", "viewer"]},
    "Rule Management": {"file": "05_Rule_Management.py", "icon": "⚙️", "roles": ["admin"]},
    "Model Performance": {"file": "06_Model_Performance.py", "icon": "🤖", "roles": ["admin", "analyst"]},
    "User Management": {"file": "07_User_Management.py", "icon": "👥", "roles": ["admin"]},
    "Audit Logs": {"file": "08_Audit_Logs.py", "icon": "📋", "roles": ["admin"]},
}

# Alert Status
ALERT_STATUS = ["pending", "under_review", "approved", "rejected", "escalated"]

# Chart Configuration
CHART_CONFIG = {
    "responsive": True,
    "displayModeBar": True,
    "displaylogo": False,
    "toImageButtonOptions": {
        "format": "png",
        "filename": "fraud_detection_chart",
        "height": 600,
        "width": 1000,
        "scale": 1,
    },
}

# Date Format
DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT = "%H:%M:%S"

# Currency
CURRENCY_SYMBOL = "$"
CURRENCY_FORMAT = f"{CURRENCY_SYMBOL}{{:,.2f}}"
