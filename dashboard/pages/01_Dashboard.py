"""
Dashboard Overview Page
"""
import streamlit as st
from components import (
    AuthHandler,
    create_line_chart,
    display_chart_with_error_handling,
    display_empty_state,
)
from utils import format_currency, format_large_number, show_error_message


def main():
    """Main dashboard overview."""

    # Check authentication
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return

    # Check permission
    if not AuthHandler.has_permission("view_dashboard"):
        st.error("You don't have permission to view this page")
        return

    # Get API client
    client = AuthHandler.get_api_client()

    # Page title
    st.markdown("## Executive overview")
    st.caption("A current snapshot of transaction activity and risk signals.")

    # KPI Cards
    st.markdown("### Key Performance Indicators")

    # Fetch stats
    with st.spinner("Loading dashboard data..."):
        stats = client.get_transaction_stats()
        alert_stats = client.get_alert_stats()
        trends = client.get_transaction_trends()

    errors = [
        result["error"]
        for result in (stats, alert_stats, trends)
        if "error" in result
    ]
    if errors:
        show_error_message(
            "Error Loading Data",
            "; ".join(errors)
        )
        return

    # Display KPIs
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_txns = stats.get("total_transactions", 0)
        st.metric(
            "📊 Total Transactions",
            format_large_number(total_txns),
            "Last 30 days"
        )

    with col2:
        high_risk_count = stats.get("high_risk_transactions", 0)
        st.metric(
            "⚠️ High-Risk Transactions",
            f"{high_risk_count:,}",
            "Last 30 days"
        )

    with col3:
        pending_alerts = alert_stats.get("pending_alerts", 0)
        st.metric(
            "🚨 Pending Alerts",
            pending_alerts,
            "Awaiting review"
        )

    with col4:
        average_amount = stats.get("average_amount", 0)
        st.metric(
            "💳 Average Transaction",
            format_currency(average_amount),
            "Last 30 days"
        )

    st.divider()

    # Fraud Trends
    st.markdown("### Fraud Trends (Last 30 Days)")

    col1, col2 = st.columns(2)

    with col1:
        transaction_trend = [
            {"date": item["date"], "count": item["transaction_count"]}
            for item in trends
        ]
        if transaction_trend:
            display_chart_with_error_handling(
                create_line_chart,
                transaction_trend,
                "Transactions Over Time",
                "date",
                "count",
                "Date",
                "Transactions"
            )
        else:
            display_empty_state("No transaction trend data available")

    with col2:
        # Transaction volume trend
        amount_trend = [
            {"date": item["date"], "amount": item["total_volume"]}
            for item in trends
        ]
        if amount_trend:
            display_chart_with_error_handling(
                create_line_chart,
                amount_trend,
                "Transaction Amount Trend",
                "date",
                "amount",
                "Date",
                "Amount"
            )
        else:
            display_empty_state("No transaction amount trend data available")

    st.divider()

    # Risk Distribution
    st.markdown("### Risk Level Distribution")

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        risk_dist = {
            "low": stats.get("low_risk_transactions", 0),
            "medium": stats.get("medium_risk_transactions", 0),
            "high": stats.get("high_risk_transactions", 0),
            "critical": 0,
        }
        assessed_transactions = sum(risk_dist.values())
        if not assessed_transactions:
            st.info(
                "Transactions are available, but no fraud assessments have been "
                "recorded for this period yet."
            )
        if risk_dist:
            low = risk_dist.get("low", 0)
            low_percentage = low / assessed_transactions * 100 if assessed_transactions else 0
            st.metric(
                "Low risk",
                f"{low:,}" if assessed_transactions else "—",
                f"{low_percentage:.1f}% of assessed" if assessed_transactions else "No assessments",
            )

        st.metric(
            "Medium risk",
            f"{risk_dist.get('medium', 0):,}" if assessed_transactions else "—",
        )

    with col2:
        st.metric(
            "High risk",
            f"{risk_dist.get('high', 0):,}" if assessed_transactions else "—",
        )
        st.metric(
            "Critical",
            f"{risk_dist.get('critical', 0):,}" if assessed_transactions else "—",
        )

    with col3:
        if assessed_transactions:
            try:
                from components import create_pie_chart
                risk_data = [
                    {"name": "Low", "count": risk_dist.get("low", 0)},
                    {"name": "Medium", "count": risk_dist.get("medium", 0)},
                    {"name": "High", "count": risk_dist.get("high", 0)},
                    {"name": "Critical", "count": risk_dist.get("critical", 0)},
                ]
                display_chart_with_error_handling(
                    create_pie_chart,
                    risk_data,
                    "Risk Distribution"
                )
            except Exception as e:
                st.error(f"Error creating chart: {str(e)}")
        else:
            display_empty_state("Risk distribution will appear after assessments are recorded")

    st.divider()

    # Transaction value overview
    st.markdown("### Transaction value overview")
    value_col1, value_col2, value_col3 = st.columns(3)
    with value_col1:
        st.metric("Total volume", format_currency(stats.get("total_volume", 0)))
    with value_col2:
        st.metric("Lowest transaction", format_currency(stats.get("min_amount", 0)))
    with value_col3:
        st.metric("Highest transaction", format_currency(stats.get("max_amount", 0)))

    st.divider()

    # Alert Queue Summary
    st.markdown("### Alert Queue Summary")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "⏳ Pending",
            alert_stats.get("pending_alerts", 0)
        )

    with col2:
        st.metric(
            "👁️ Under Review",
            alert_stats.get("under_review_alerts", 0)
        )

    with col3:
        st.metric(
            "✅ Approved",
            alert_stats.get("approved_alerts", 0)
        )

    with col4:
        st.metric(
            "❌ Rejected",
            alert_stats.get("rejected_alerts", 0)
        )

    st.divider()

    st.caption(
        "Metrics reflect the most recent 30 days. Risk counts are based on "
        "stored fraud assessments, not the synthetic ground-truth labels."
    )


if __name__ == "__main__":
    main()
