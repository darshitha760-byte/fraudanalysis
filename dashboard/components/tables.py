"""
Table components for the dashboard
"""
import streamlit as st
import pandas as pd
from typing import List, Dict, Any, Optional
from utils import format_currency, format_datetime, format_percentage, truncate_text


def create_transaction_table(transactions: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create formatted transaction table."""
    if not transactions:
        return pd.DataFrame()

    rows = []
    for txn in transactions:
        risk_score = txn.get("risk_score")
        rows.append({
            "ID": truncate_text(
                txn.get("transaction_id", txn.get("id", "")),
                20,
            ),
            "Customer": txn.get("customer_id", "-"),
            "Merchant": txn.get("merchant_name", txn.get("merchant_id", "-")),
            "Amount": format_currency(txn.get("amount", 0)),
            "Date": format_datetime(
                txn.get("transaction_date", txn.get("created_at", ""))
            ),
            "Risk": f"{risk_score:.1f}%" if risk_score is not None else "Not assessed",
            "Risk Level": (
                (txn.get("risk_level") or "Not assessed").replace("_", " ").title()
            ),
            "Status": txn.get("status", "-"),
        })

    return pd.DataFrame(rows)


def create_alert_table(alerts: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create formatted alert table."""
    if not alerts:
        return pd.DataFrame()

    rows = []
    for alert in alerts:
        rows.append({
            "ID": truncate_text(alert.get("id", ""), 12),
            "Transaction": truncate_text(alert.get("transaction_id", ""), 12),
            "Customer": alert.get("customer_id", "-"),
            "Risk Level": alert.get("risk_level", "-").upper(),
            "Status": alert.get("status", "-").replace("_", " ").title(),
            "Created": format_datetime(alert.get("created_at", "")),
            "Rules Triggered": str(len(alert.get("triggered_rules", []))),
        })

    return pd.DataFrame(rows)


def create_rule_table(rules: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create formatted rule table."""
    if not rules:
        return pd.DataFrame()

    rows = []
    for rule in rules:
        rows.append({
            "Code": rule.get("code", "-"),
            "Name": truncate_text(rule.get("name", ""), 30),
            "Threshold": rule.get("threshold", "-"),
            "Severity": rule.get("severity", "-").upper(),
            "Weight": format_percentage(rule.get("weight", 0)),
            "Status": "✓ Active" if rule.get("is_active", False) else "✗ Inactive",
            "Triggered": rule.get("triggered_count", 0),
        })

    return pd.DataFrame(rows)


def create_user_table(users: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create formatted user table."""
    if not users:
        return pd.DataFrame()

    rows = []
    for user in users:
        rows.append({
            "Email": user.get("email", "-"),
            "Role": user.get("role", "-").title(),
            "Status": "✓ Active" if user.get("is_active", False) else "✗ Inactive",
            "Created": format_datetime(user.get("created_at", "")),
            "Last Login": format_datetime(user.get("last_login", "-")) if user.get("last_login") else "-",
        })

    return pd.DataFrame(rows)


def create_audit_log_table(logs: List[Dict[str, Any]]) -> pd.DataFrame:
    """Create formatted audit log table."""
    if not logs:
        return pd.DataFrame()

    rows = []
    for log in logs:
        rows.append({
            "Timestamp": format_datetime(log.get("timestamp", "")),
            "Actor": log.get("actor", "-"),
            "Action": log.get("action", "-").replace("_", " ").upper(),
            "Target": f"{log.get('target_type', '-')} : {truncate_text(str(log.get('target_id') or ''), 15)}",
            "Status": "✓ Success" if log.get("success", False) else "✗ Failed",
            "Details": truncate_text(log.get("details", ""), 40),
        })

    return pd.DataFrame(rows)


def display_transaction_detail(transaction: Dict[str, Any]):
    """Display detailed transaction information."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Transaction ID", truncate_text(transaction.get("id", ""), 20))
        st.metric("Customer ID", transaction.get("customer_id", "-"))
        st.metric("Merchant ID", transaction.get("merchant_id", "-"))

    with col2:
        st.metric("Amount", format_currency(transaction.get("amount", 0)))
        st.metric("Risk Score", f"{transaction.get('risk_score', 0):.1f}%")
        st.metric("Status", transaction.get("status", "-").title())

    with col3:
        st.metric("Created", format_datetime(transaction.get("created_at", "")))
        st.metric("Updated", format_datetime(transaction.get("updated_at", "")))
        st.metric("Risk Level", transaction.get("risk_level", "-").upper())

    # Triggered Rules
    if "assessment" in transaction and "triggered_rules" in transaction["assessment"]:
        st.subheader("Triggered Rules")
        rules = transaction["assessment"]["triggered_rules"]

        if rules:
            rule_rows = []
            for rule in rules:
                rule_rows.append({
                    "Code": rule.get("code", "-"),
                    "Name": rule.get("name", "-"),
                    "Reason": truncate_text(rule.get("reason", "-"), 50),
                    "Risk Score": f"{rule.get('risk_score', 0):.1f}%",
                })

            rules_df = pd.DataFrame(rule_rows)
            st.dataframe(rules_df, use_container_width=True, hide_index=True)
        else:
            st.info("No rules triggered for this transaction")


def display_alert_detail(alert: Dict[str, Any]):
    """Display detailed alert information."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Alert ID", truncate_text(alert.get("id", ""), 20))
        st.metric("Transaction ID", alert.get("transaction_id", "-"))
        st.metric("Customer ID", alert.get("customer_id", "-"))

    with col2:
        st.metric("Risk Level", alert.get("risk_level", "-").upper())
        st.metric("Status", alert.get("status", "-").replace("_", " ").title())
        st.metric("Priority", alert.get("priority", "-"))

    with col3:
        st.metric("Created", format_datetime(alert.get("created_at", "")))
        st.metric("Updated", format_datetime(alert.get("updated_at", "")))
        if alert.get("reviewed_at"):
            st.metric("Reviewed", format_datetime(alert.get("reviewed_at", "")))

    # Triggered Rules
    if "triggered_rules" in alert:
        st.subheader("Triggered Rules")
        rules = alert["triggered_rules"]

        if rules:
            rule_rows = []
            for rule in rules:
                rule_rows.append({
                    "Code": rule.get("code", "-") if isinstance(rule, dict) else rule,
                    "Name": rule.get("name", "-") if isinstance(rule, dict) else "-",
                })

            rules_df = pd.DataFrame(rule_rows)
            st.dataframe(rules_df, use_container_width=True, hide_index=True)

    # Notes
    if alert.get("notes"):
        st.subheader("Notes")
        st.text_area("Alert Notes", value=alert.get("notes", ""), disabled=True, height=100)

    # Reviewer Info
    if alert.get("reviewed_by"):
        st.subheader("Review Information")
        col1, col2 = st.columns(2)
        with col1:
            st.text(f"Reviewed by: {alert.get('reviewed_by', '-')}")
        with col2:
            st.text(f"Decision: {alert.get('decision', '-').upper()}")


def create_paginated_table(
    data: List[Dict[str, Any]],
    columns: Optional[List[str]] = None,
    page_size: int = 20,
):
    """Display paginated table."""
    if not data:
        st.info("No data to display")
        return

    total_records = len(data)
    total_pages = (total_records + page_size - 1) // page_size

    # Pagination controls
    col1, col2, col3 = st.columns(3)
    with col1:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            key="pagination_page"
        )

    with col2:
        st.text(f"Total: {total_records} records")

    with col3:
        st.text(f"Page {page} of {total_pages}")

    # Get page data
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_records)
    page_data = data[start_idx:end_idx]

    # Display table
    if columns:
        page_data = [{k: row.get(k, "-") for k in columns} for row in page_data]

    df = pd.DataFrame(page_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def display_empty_state(message: str = "No data available", icon: str = "📭"):
    """Display empty state message."""
    st.info(f"{icon} {message}")


def display_user_detail(user: Dict[str, Any]):
    """Display detailed user information."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("User ID", str(user.get("id", "")))
        st.metric("Email", user.get("email", "-"))
        st.metric("Full Name", user.get("full_name", "-"))

    with col2:
        st.metric("Role", user.get("role", "-").title())
        st.metric("Department", user.get("department", "-"))
        st.metric("Status", "✓ Active" if user.get("is_active", False) else "✗ Inactive")

    with col3:
        st.metric("Created", format_datetime(user.get("created_at", "")))
        st.metric("Last Login", format_datetime(user.get("last_login", "-")) if user.get("last_login") else "-")
        st.metric("Last Activity", format_datetime(user.get("last_activity", "-")) if user.get("last_activity") else "-")


def display_rule_detail(rule: Dict[str, Any]):
    """Display detailed rule information."""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Rule Code", rule.get("code", "-"))
        st.metric("Rule Name", rule.get("name", "-"))
        st.metric("Severity", rule.get("severity", "-").title())

    with col2:
        st.metric("Threshold", format_currency(rule.get("threshold", 0)))
        st.metric("Risk Weight", f"{rule.get('risk_weight', 0):.2f}")
        st.metric("Status", "✓ Enabled" if rule.get("enabled", False) else "✗ Disabled")

    with col3:
        st.metric("Created", format_datetime(rule.get("created_at", "")))
        st.metric("Updated", format_datetime(rule.get("updated_at", "")))
        st.metric("Version", rule.get("version", "1"))

    if rule.get("description"):
        st.subheader("Description")
        st.write(rule.get("description", ""))


# Alias for compatibility
create_audit_table = create_audit_log_table
