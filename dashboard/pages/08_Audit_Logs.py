"""Search recorded audit events and summarize activity."""

import json
from datetime import datetime, timedelta

import streamlit as st

from components import AuthHandler, create_audit_table, create_export_button
from utils import show_error_message


def main():
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return
    if not AuthHandler.has_permission("view_audit_logs"):
        st.error("You don't have permission to view audit logs")
        return
    client = AuthHandler.get_api_client()
    st.markdown("## 📋 Audit Logs")
    st.caption("Recorded events only. Date filters include the full end date and use UTC.")
    trail, report_tab = st.tabs(["Audit Trail", "Compliance Report"])
    with trail:
        with st.form("audit_search"):
            left, middle, right = st.columns(3)
            actor = left.text_input("Actor (Email)")
            action = middle.selectbox(
                "Action Type", ["All", "login", "logout", "create", "update", "delete", "review"]
            )
            entity = right.selectbox(
                "Target Entity",
                ["All", "user", "fraud_rule", "fraud_alert", "transaction", "model", "ml_model"],
            )
            left, right = st.columns(2)
            start = left.date_input("Start Date", datetime.now().date() - timedelta(days=30))
            end = right.date_input("End Date", datetime.now().date())
            search = st.form_submit_button("🔍 Search Logs", use_container_width=True)
        if search:
            st.session_state.pop("audit_search_result", None)
            if start > end:
                st.error("Start date must not be after end date")
            else:
                response = client.get_audit_logs(
                    actor=actor.strip() or None,
                    action=None if action == "All" else action,
                    target_entity=None if entity == "All" else entity,
                    start_date=start.isoformat(), end_date=end.isoformat(), limit=1000,
                )
                if "error" in response:
                    show_error_message("Unable to load audit logs", response["error"])
                else:
                    st.session_state.audit_search_result = response
        response = st.session_state.get("audit_search_result")
        if response is not None:
            logs = response["items"]
            st.caption(f"Showing {len(logs)} of {response['total']} matching events.")
            if response["total"] > len(logs):
                st.warning("Results are limited to the latest 1,000 events. Narrow the filters.")
            if not logs:
                st.info("No audit events found for these filters.")
            else:
                create_export_button(logs, "audit_logs")
                st.dataframe(create_audit_table(logs), use_container_width=True, hide_index=True)
                selected = st.selectbox(
                    "Select event", range(len(logs)),
                    format_func=lambda index: (
                        f"{logs[index]['timestamp']} | {logs[index]['actor']} | {logs[index]['action']}"
                    ),
                )
                st.json(logs[selected])
    with report_tab:
        st.caption("Activity summary from recorded events, not a compliance certification.")
        with st.form("audit_report"):
            report_type = st.selectbox("Report Type", [
                "User Access", "Data Changes", "Alerts Review",
                "Rule Modifications", "Model Updates", "Security Events",
            ])
            left, right = st.columns(2)
            start = left.date_input(
                "Report Start Date", datetime.now().date() - timedelta(days=30)
            )
            end = right.date_input("Report End Date", datetime.now().date())
            generate = st.form_submit_button("📄 Generate Report")
        if generate:
            st.session_state.pop("audit_report_result", None)
            if start > end:
                st.error("Start date must not be after end date")
            else:
                response = client.get_compliance_report(
                    report_type=report_type.lower().replace(" ", "_"),
                    start_date=start.isoformat(), end_date=end.isoformat(),
                )
                if "error" in response:
                    show_error_message("Unable to generate report", response["error"])
                else:
                    st.session_state.audit_report_result = {
                        **response, "report_type": report_type,
                        "start_date": start.isoformat(), "end_date": end.isoformat(),
                    }
        report = st.session_state.get("audit_report_result")
        if report:
            st.markdown(f"### {report['report_type']}")
            st.caption(f"{report['start_date']} to {report['end_date']} (UTC)")
            for column, (key, value) in zip(st.columns(4), report["summary"].items()):
                column.metric(key.replace("_", " ").title(), value)
            create_export_button(
                [{"Metric": key, "Value": value} for key, value in report["summary"].items()],
                "audit_activity_summary",
            )
            st.download_button(
                "Download report JSON", json.dumps(report, indent=2),
                "audit_activity_summary.json", "application/json",
            )


if __name__ == "__main__":
    main()
