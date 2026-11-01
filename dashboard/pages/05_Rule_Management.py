"""
Rule Management Page (Admin Only)
"""
import streamlit as st
from components import (
    AuthHandler,
    create_rule_table,
    display_rule_detail,
    display_empty_state,
)
from utils import show_error_message, show_success_message, format_percentage


def main():
    """Main rule management page."""

    # Check authentication
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return

    # Check admin role
    if not AuthHandler.has_permission("manage_rules"):
        st.error("You don't have permission to manage rules")
        return

    client = AuthHandler.get_api_client()

    st.markdown("## 📋 Fraud Rules Management")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["Rules List", "Create Rule", "View Details"])

    with tab1:
        st.markdown("### Fraud Rules")

        # Load rules button
        if st.button("🔄 Refresh Rules", use_container_width=True):
            with st.spinner("Loading rules..."):
                response = client.get_fraud_rules()

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    st.session_state.rules = response.get("items", [])

        if "rules" in st.session_state:
            rules = st.session_state.rules

            if not rules:
                display_empty_state("No rules found")
            else:
                st.markdown(f"### {len(rules)} Rule(s)")

                # Create rules table
                rule_table = create_rule_table(rules)
                st.dataframe(rule_table, use_container_width=True, hide_index=True)

                # Quick actions
                st.markdown("### Actions")

                col1, col2 = st.columns(2)

                with col1:
                    selected_rule_id = st.selectbox(
                        "Select rule to edit",
                        [r.get("id", "") for r in rules],
                        key="edit_rule"
                    )

                with col2:
                    action = st.selectbox(
                        "Action",
                        ["View", "Edit", "Disable", "Delete"],
                        key="rule_action"
                    )

                if st.button("Execute Action", use_container_width=True):
                    if action == "View":
                        st.session_state.selected_rule_id = selected_rule_id

                    elif action == "Edit":
                        st.session_state.edit_rule_id = selected_rule_id
                        st.session_state.active_tab = "edit"

                    elif action == "Disable":
                        with st.spinner("Disabling rule..."):
                            result = client.update_fraud_rule(
                                selected_rule_id,
                                {"enabled": False}
                            )
                            if "error" not in result:
                                show_success_message("Success", "Rule disabled")
                                st.rerun()
                            else:
                                show_error_message("Error", result.get("error"))

                    elif action == "Delete":
                        with st.spinner("Deleting rule..."):
                            result = client.delete_fraud_rule(selected_rule_id)
                            if "error" not in result:
                                show_success_message("Success", "Rule deleted")
                                st.rerun()
                            else:
                                show_error_message("Error", result.get("error"))

    with tab2:
        st.markdown("### Create New Rule")

        col1, col2 = st.columns(2)

        with col1:
            rule_code = st.text_input(
                "Rule Code",
                placeholder="e.g., R11",
                key="new_rule_code"
            )
            rule_name = st.text_input(
                "Rule Name",
                placeholder="e.g., Large Transaction Detection",
                key="new_rule_name"
            )

        with col2:
            severity = st.selectbox(
                "Severity Level",
                ["Low", "Medium", "High", "Critical"],
                key="new_severity"
            )
            risk_weight = st.slider(
                "Risk Weight",
                0.0, 1.0, 0.5,
                key="new_weight"
            )

        threshold = st.number_input(
            "Threshold Value",
            min_value=0.0,
            value=10000.0,
            key="new_threshold"
        )

        description = st.text_area(
            "Description",
            placeholder="Describe what this rule detects...",
            key="new_description"
        )

        enabled = st.checkbox("Enable Rule", value=True, key="new_enabled")

        if st.button("✅ Create Rule", use_container_width=True):
            if not rule_code or not rule_name:
                st.error("Rule code and name are required")
            else:
                with st.spinner("Creating rule..."):
                    result = client.create_fraud_rule({
                        "code": rule_code,
                        "name": rule_name,
                        "severity": severity.lower(),
                        "threshold": threshold,
                        "risk_weight": risk_weight,
                        "description": description,
                        "enabled": enabled
                    })

                    if "error" not in result:
                        show_success_message("Success", f"Rule {rule_code} created")
                        st.session_state.rules = None
                    else:
                        show_error_message("Error", result.get("error"))

    with tab3:
        st.markdown("### Rule Details & Performance")

        if "selected_rule_id" in st.session_state:
            rule_id = st.session_state.selected_rule_id

            with st.spinner("Loading rule details..."):
                response = client.get_fraud_rule(rule_id)

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    rule = response

                    # Display rule details
                    display_rule_detail(rule)

                    st.divider()

                    # Performance metrics
                    st.markdown("### Rule Performance")

                    col1, col2, col3, col4 = st.columns(4)

                    perf = rule.get("performance", {})

                    with col1:
                        st.metric(
                            "Times Triggered",
                            perf.get("times_triggered", 0)
                        )

                    with col2:
                        st.metric(
                            "False Positives",
                            perf.get("false_positives", 0)
                        )

                    with col3:
                        st.metric(
                            "True Positives",
                            perf.get("true_positives", 0)
                        )

                    with col4:
                        precision = perf.get("precision", 0)
                        st.metric(
                            "Precision",
                            format_percentage(precision)
                        )

                    st.divider()

                    # Edit rule
                    if "edit_rule_id" in st.session_state and st.session_state.edit_rule_id == rule_id:
                        st.markdown("### Edit Rule")

                        new_name = st.text_input(
                            "Name",
                            value=rule.get("name", ""),
                            key="edit_name"
                        )

                        new_threshold = st.number_input(
                            "Threshold",
                            value=float(rule.get("threshold", 0)),
                            key="edit_threshold"
                        )

                        new_weight = st.slider(
                            "Risk Weight",
                            0.0, 1.0,
                            float(rule.get("risk_weight", 0.5)),
                            key="edit_weight"
                        )

                        new_enabled = st.checkbox(
                            "Enabled",
                            value=rule.get("enabled", True),
                            key="edit_enabled"
                        )

                        if st.button("💾 Save Changes", use_container_width=True):
                            with st.spinner("Updating rule..."):
                                result = client.update_fraud_rule(rule_id, {
                                    "name": new_name,
                                    "threshold": new_threshold,
                                    "risk_weight": new_weight,
                                    "enabled": new_enabled
                                })

                                if "error" not in result:
                                    show_success_message("Success", "Rule updated")
                                    st.session_state.rules = None
                                    st.session_state.edit_rule_id = None
                                    st.rerun()
                                else:
                                    show_error_message("Error", result.get("error"))
        else:
            st.info("Select a rule from the Rules List tab to view details")


if __name__ == "__main__":
    main()
