"""
Utility functions for the dashboard
"""
from datetime import datetime
from typing import Any, Dict
import streamlit as st
from config import CURRENCY_SYMBOL, DATE_FORMAT, DATETIME_FORMAT, RISK_THRESHOLDS, RiskLevel


def format_currency(value: float) -> str:
    """Format value as currency."""
    if value is None:
        return f"{CURRENCY_SYMBOL}0.00"
    return f"{CURRENCY_SYMBOL}{value:,.2f}"


def format_date(date_obj: Any) -> str:
    """Format date object to string."""
    if isinstance(date_obj, str):
        return date_obj
    if isinstance(date_obj, datetime):
        return date_obj.strftime(DATE_FORMAT)
    return str(date_obj)


def format_datetime(dt_obj: Any) -> str:
    """Format datetime object to string."""
    if isinstance(dt_obj, str):
        return dt_obj
    if isinstance(dt_obj, datetime):
        return dt_obj.strftime(DATETIME_FORMAT)
    return str(dt_obj)


def format_percentage(value: float, decimal_places: int = 2) -> str:
    """Format value as percentage."""
    if value is None:
        return "0.00%"
    return f"{value:.{decimal_places}f}%"


def get_risk_color(risk_score: float) -> str:
    """Get color based on risk score."""
    if risk_score >= 75:
        return "#DC2626"  # Red - Critical
    elif risk_score >= 50:
        return "#F97316"  # Orange - High
    elif risk_score >= 25:
        return "#FBBF24"  # Yellow - Medium
    else:
        return "#22C55E"  # Green - Low


def get_risk_level(risk_score: float) -> str:
    """Get risk level based on score."""
    if risk_score >= 75:
        return "CRITICAL"
    elif risk_score >= 50:
        return "HIGH"
    elif risk_score >= 25:
        return "MEDIUM"
    else:
        return "LOW"


def format_risk_score(score: float) -> str:
    """Format risk score with color indicator."""
    return f"{score:.1f}%"


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def format_large_number(value: float) -> str:
    """Format large numbers with K, M, B suffixes."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K"
    else:
        return f"{value:.0f}"


def show_error_message(title: str, message: str):
    """Display error message using Streamlit."""
    st.error(f"**{title}**\n{message}")


def show_success_message(title: str, message: str):
    """Display success message using Streamlit."""
    st.success(f"**{title}**\n{message}")


def show_warning_message(title: str, message: str):
    """Display warning message using Streamlit."""
    st.warning(f"**{title}**\n{message}")


def show_info_message(title: str, message: str):
    """Display info message using Streamlit."""
    st.info(f"**{title}**\n{message}")


def get_badge_color_by_status(status: str) -> str:
    """Get color for status badge."""
    status_lower = status.lower()
    if status_lower in ["approved", "resolved", "active", "enabled"]:
        return "green"
    elif status_lower in ["pending", "under_review", "under review"]:
        return "blue"
    elif status_lower in ["rejected", "failed", "disabled"]:
        return "red"
    elif status_lower in ["escalated"]:
        return "orange"
    else:
        return "gray"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers."""
    if denominator == 0 or denominator is None:
        return default
    return numerator / denominator


def parse_iso_datetime(dt_string: str) -> datetime:
    """Parse ISO format datetime string."""
    if isinstance(dt_string, datetime):
        return dt_string
    try:
        return datetime.fromisoformat(dt_string.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now()


def calculate_percentage_change(new_value: float, old_value: float) -> float:
    """Calculate percentage change between two values."""
    if old_value == 0:
        return 0.0 if new_value == 0 else 100.0
    return ((new_value - old_value) / abs(old_value)) * 100
