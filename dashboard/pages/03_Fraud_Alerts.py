"""
Fraud Alerts Page
"""
import streamlit as st
from datetime import datetime, timedelta
from components import (
    AuthHandler,
    create_alert_table,
    display_alert_detail,
    display_empty_state,
)
from utils import show_error_message, format_datetime, truncate_text, show_success_message


def main():
    """Main fraud alerts page."""

    # Check authentication
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return

    if not AuthHandler.has_permission("view_alerts"):
        st.error("You don't have permission to view this page")
        return

    client = AuthHandler.get_api_client()

    st.markdown("## 🚨 Fraud Alerts")

    # Tabs for different views
    tab1, tab2 = st.tabs(["Alert Queue", "Review Alert"])

    with tab1:
        st.markdown("### Alert Queue")

        # Filters
        col1, col2, col3 = st.columns(3)

        with col1:
            status_filter = st.selectbox(
                "Status",
                ["All", "Pending", "Under Review", "Approved", "Rejected"],
                index=0,
                key="alert_status"
            )

        with col2:
            risk_filter = st.selectbox(
                "Risk Level",
                ["All", "Low", "Medium", "High", "Critical"],
                index=0,
                key="alert_risk"
            )

        with col3:
            days_back = st.number_input(
                "Days Back",
                min_value=1,
                max_value=90,
                value=7,
                key="alert_days"
            )

        start_date = (datetime.now() - timedelta(days=days_back)).isoformat()
        end_date = datetime.now().isoformat()

        # Search alerts
        if st.button("🔍 Load Alerts", use_container_width=True):
            with st.spinner("Loading alerts..."):
                status_param = None if status_filter == "All" else status_filter.lower().replace(" ", "_")
                risk_param = None if risk_filter == "All" else risk_filter.lower()

                response = client.get_alerts(
                    status=status_param,
                    risk_level=risk_param,
                    start_date=start_date,
                    end_date=end_date,
                    limit=100
                )

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    alerts = response.get("items", [])

                    if not alerts:
                        display_empty_state("No alerts found")
                    else:
                        st.markdown(f"### {len(alerts)} Alert(s) Found")

                        alert_table = create_alert_table(alerts)
                        st.dataframe(alert_table, use_container_width=True, hide_index=True)

                        # Store alerts in session for detail view
                        st.session_state.alerts = alerts

    with tab2:
        st.markdown("### Review Alert")

        if "alerts" not in st.session_state or not st.session_state.alerts:
            st.info("Load alerts from the 'Alert Queue' tab first")
            return

        alerts = st.session_state.alerts

        alert_options = [
            f"{truncate_text(a.get('id', ''), 12)} - {a.get('customer_id', '-')} - {a.get('risk_level', '-').upper()}"
            for a in alerts
        ]

        selected_idx = st.selectbox(
            "Select Alert",
            range(len(alert_options)),
            format_func=lambda x: alert_options[x],
            key="selected_alert"
        )

        if selected_idx is not None:
            alert = alerts[selected_idx]

            # Display alert details
            display_alert_detail(alert)

            st.divider()

            # Review workflow
            if alert.get("status", "").lower() == "pending":
                st.markdown("### Review Decision")

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("✅ Approve", use_container_width=True, key="btn_approve"):
                        notes = st.text_area("Review Notes", key="notes_approve")
                        with st.spinner("Submitting review..."):
                            result = client.review_alert(
                                alert.get("id"),
                                "approved",
                                notes if notes else None
                            )
                            if "error" not in result:
                                show_success_message("Success", "Alert approved successfully")
                                st.rerun()
                            else:
                                show_error_message("Error", result.get("error"))

                with col2:
                    if st.button("❌ Reject", use_container_width=True, key="btn_reject"):
                        notes = st.text_area("Review Notes", key="notes_reject")
                        with st.spinner("Submitting review..."):
                            result = client.review_alert(
                                alert.get("id"),
                                "rejected",
                                notes if notes else None
                            )
                            if "error" not in result:
                                show_success_message("Success", "Alert rejected")
                                st.rerun()
                            else:
                                show_error_message("Error", result.get("error"))

                with col3:
                    if st.button("⬆️ Escalate", use_container_width=True, key="btn_escalate"):
                        notes = st.text_area("Escalation Reason", key="notes_escalate")
                        with st.spinner("Escalating..."):
                            result = client.review_alert(
                                alert.get("id"),
                                "escalated",
                                notes if notes else None
                            )
                            if "error" not in result:
                                show_success_message("Success", "Alert escalated")
                                st.rerun()
                            else:
                                show_error_message("Error", result.get("error"))
            else:
                st.info(f"This alert has already been {alert.get('status', 'processed')}")


if __name__ == "__main__":
    main()
