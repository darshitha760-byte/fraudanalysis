"""
Filter components for the dashboard
"""
import streamlit as st
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any


def filter_date_range() -> Tuple[datetime, datetime]:
    """Create date range filter."""
    col1, col2 = st.columns(2)

    end_date = datetime.now().date()
    start_date = (datetime.now() - timedelta(days=30)).date()

    with col1:
        start = st.date_input("Start Date", start_date, key="date_start")
    with col2:
        end = st.date_input("End Date", end_date, key="date_end")

    return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.max.time())


def filter_amount_range(min_val: float = 0, max_val: float = 1000000) -> Tuple[float, float]:
    """Create amount range filter."""
    values = st.slider(
        "Transaction Amount Range",
        min_value=min_val,
        max_value=max_val,
        value=(min_val, max_val),
        step=100.0,
        key="amount_range",
    )
    return values


def filter_risk_level() -> Optional[str]:
    """Create risk level filter."""
    options = ["All", "Low", "Medium", "High", "Critical"]
    selected = st.selectbox(
        "Risk Level",
        options,
        index=0,
        key="risk_level",
    )
    return None if selected == "All" else selected.lower()


def filter_status(statuses: list) -> Optional[str]:
    """Create status filter."""
    options = ["All"] + statuses
    selected = st.selectbox(
        "Status",
        options,
        index=0,
        key="status_filter",
    )
    return None if selected == "All" else selected.lower()


def filter_customer_id() -> Optional[str]:
    """Create customer ID filter."""
    customer_id = st.text_input(
        "Customer ID",
        placeholder="Enter customer ID...",
        key="customer_id_filter",
    )
    return customer_id if customer_id else None


def filter_merchant_id() -> Optional[str]:
    """Create merchant ID filter."""
    merchant_id = st.text_input(
        "Merchant ID",
        placeholder="Enter merchant ID...",
        key="merchant_id_filter",
    )
    return merchant_id if merchant_id else None


def filter_transaction_id() -> Optional[str]:
    """Create transaction ID filter."""
    transaction_id = st.text_input(
        "Transaction ID",
        placeholder="Enter transaction ID...",
        key="transaction_id_filter",
    )
    return transaction_id if transaction_id else None


def filter_user_email() -> Optional[str]:
    """Create user email filter."""
    email = st.text_input(
        "User Email",
        placeholder="Enter email...",
        key="user_email_filter",
    )
    return email if email else None


def filter_user_role() -> Optional[str]:
    """Create user role filter."""
    roles = ["All", "Admin", "Analyst", "Viewer"]
    selected = st.selectbox(
        "Role",
        roles,
        index=0,
        key="role_filter",
    )
    return None if selected == "All" else selected.lower()


def filter_action_type() -> Optional[str]:
    """Create action type filter."""
    actions = [
        "All",
        "Login",
        "Logout",
        "Create",
        "Update",
        "Delete",
        "Review",
        "Export",
    ]
    selected = st.selectbox(
        "Action Type",
        actions,
        index=0,
        key="action_filter",
    )
    return None if selected == "All" else selected.lower()


def create_filter_sidebar() -> Dict[str, Any]:
    """Create sidebar with common filters."""
    with st.sidebar:
        st.header("🔍 Filters")

        filters = {}

        # Date range
        if st.checkbox("Date Range", value=True, key="filter_date"):
            start_date, end_date = filter_date_range()
            filters["start_date"] = start_date.isoformat()
            filters["end_date"] = end_date.isoformat()

        # Amount range
        if st.checkbox("Amount Range", key="filter_amount"):
            min_amt, max_amt = filter_amount_range()
            filters["min_amount"] = min_amt
            filters["max_amount"] = max_amt

        # Risk level
        if st.checkbox("Risk Level", key="filter_risk"):
            risk = filter_risk_level()
            if risk:
                filters["risk_level"] = risk

        # Customer ID
        if st.checkbox("Customer", key="filter_customer"):
            customer = filter_customer_id()
            if customer:
                filters["customer_id"] = customer

        # Merchant ID
        if st.checkbox("Merchant", key="filter_merchant"):
            merchant = filter_merchant_id()
            if merchant:
                filters["merchant_id"] = merchant

        return filters


def create_quick_filters(available_filters: list) -> Dict[str, Any]:
    """Create quick inline filters."""
    col1, col2, col3, col4 = st.columns(4)
    filters = {}

    with col1:
        if "date_range" in available_filters:
            start_date, end_date = filter_date_range()
            filters["start_date"] = start_date.isoformat()
            filters["end_date"] = end_date.isoformat()

    with col2:
        if "amount_range" in available_filters:
            min_amt, max_amt = filter_amount_range()
            filters["min_amount"] = min_amt
            filters["max_amount"] = max_amt

    with col3:
        if "risk_level" in available_filters:
            risk = filter_risk_level()
            if risk:
                filters["risk_level"] = risk

    with col4:
        if "status" in available_filters:
            statuses = ["pending", "under_review", "approved", "rejected"]
            status = filter_status(statuses)
            if status:
                filters["status"] = status

    return filters


def apply_filters_to_data(data: list, filters: Dict[str, Any]) -> list:
    """Apply filters to data."""
    if not data:
        return []

    filtered = data

    # Date range filter
    if "start_date" in filters and "end_date" in filters:
        start = datetime.fromisoformat(filters["start_date"])
        end = datetime.fromisoformat(filters["end_date"])
        filtered = [
            item for item in filtered
            if start <= datetime.fromisoformat(item.get("created_at", "")) <= end
        ]

    # Amount range filter
    if "min_amount" in filters and "max_amount" in filters:
        filtered = [
            item for item in filtered
            if filters["min_amount"] <= item.get("amount", 0) <= filters["max_amount"]
        ]

    # Risk level filter
    if "risk_level" in filters:
        risk_level = filters["risk_level"]
        if isinstance(risk_level, str):
            filtered = [
                item for item in filtered
                if item.get("risk_level", "").lower() == risk_level.lower()
            ]

    # Customer ID filter
    if "customer_id" in filters:
        customer_id = filters["customer_id"]
        filtered = [
            item for item in filtered
            if customer_id.lower() in item.get("customer_id", "").lower()
        ]

    # Merchant ID filter
    if "merchant_id" in filters:
        merchant_id = filters["merchant_id"]
        filtered = [
            item for item in filtered
            if merchant_id.lower() in item.get("merchant_id", "").lower()
        ]

    # Status filter
    if "status" in filters:
        status = filters["status"]
        filtered = [
            item for item in filtered
            if item.get("status", "").lower() == status.lower()
        ]

    return filtered


def create_export_button(data: list, filename: str):
    """Create export to CSV button."""
    import csv
    import io

    if not data:
        st.warning("No data to export")
        return

    # Convert to CSV
    output = io.StringIO()
    if data:
        keys = data[0].keys()
        writer = csv.DictWriter(output, fieldnames=keys)
        writer.writeheader()
        writer.writerows(data)

    csv_content = output.getvalue()

    st.download_button(
        label="📥 Download as CSV",
        data=csv_content,
        file_name=f"{filename}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )
