"""
Financial Risk Analytics Page
"""
import streamlit as st
from datetime import datetime, timedelta
from components import (
    AuthHandler,
    create_bar_chart,
    create_histogram,
    create_heatmap,
    display_chart_with_error_handling,
    display_empty_state,
)
from utils import format_currency, show_error_message


def main():
    """Main financial risk analytics page."""

    # Check authentication
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return

    if not AuthHandler.has_permission("view_analytics"):
        st.error("You don't have permission to view this page")
        return

    client = AuthHandler.get_api_client()

    st.markdown("## 📈 Financial Risk Analytics")

    # Tab selection
    tab1, tab2, tab3 = st.tabs([
        "Customer Risk Profiles",
        "Transaction Patterns",
        "Risk Indicators"
    ])

    with tab1:
        st.markdown("### Customer Risk Profiles")

        # Filter options
        col1, col2 = st.columns(2)

        with col1:
            min_risk = st.slider(
                "Minimum Risk Score",
                0.0, 100.0, 0.0,
                key="customer_min_risk"
            )

        with col2:
            limit = st.number_input(
                "Number of Customers",
                min_value=5,
                max_value=100,
                value=20,
                key="customer_limit"
            )

        if st.button("🔍 Load Customer Profiles", use_container_width=True):
            with st.spinner("Loading customer profiles..."):
                response = client.get_customer_risk_profiles(
                    min_risk=min_risk,
                    limit=limit
                )

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    profiles = response.get("items", [])

                    if not profiles:
                        display_empty_state("No customer profiles found")
                    else:
                        st.session_state.customer_profiles = profiles

        if "customer_profiles" in st.session_state:
            profiles = st.session_state.customer_profiles

            st.markdown(f"### {len(profiles)} Profiles Loaded")

            # Display as table
            profile_data = []
            for p in profiles:
                profile_data.append({
                    "Customer ID": p.get("customer_id", "-"),
                    "Avg Amount": format_currency(p.get("avg_amount", 0)),
                    "Frequency": p.get("frequency", 0),
                    "Risk Score": f"{p.get('risk_score', 0):.1f}%",
                    "Geographic": p.get("geographic_pattern", "-"),
                })

            import pandas as pd
            df = pd.DataFrame(profile_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()

            # Chart: Risk score distribution by frequency
            st.markdown("### Risk vs Transaction Frequency")

            chart_data = [
                {
                    "frequency": p.get("frequency", 0),
                    "risk_score": p.get("risk_score", 0),
                    "customer": p.get("customer_id", "-")
                }
                for p in profiles
            ]

            display_chart_with_error_handling(
                create_histogram,
                chart_data,
                "Risk Score Distribution",
                "risk_score",
                bins=10
            )

    with tab2:
        st.markdown("### Transaction Patterns")

        col1, col2 = st.columns(2)

        with col1:
            days = st.number_input(
                "Period (Days)",
                min_value=1,
                max_value=365,
                value=30,
                key="pattern_days"
            )

        with col2:
            top_n = st.number_input(
                "Top N Categories",
                min_value=5,
                max_value=20,
                value=10,
                key="pattern_top_n"
            )

        if st.button("🔍 Analyze Patterns", use_container_width=True):
            with st.spinner("Analyzing transaction patterns..."):
                response = client.get_transaction_patterns(
                    days=days,
                    top_n=top_n
                )

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    st.session_state.patterns = response

        if "patterns" in st.session_state:
            patterns = st.session_state.patterns

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Amount Distribution")

                amount_dist = patterns.get("amount_distribution", [])
                if amount_dist:
                    display_chart_with_error_handling(
                        create_histogram,
                        amount_dist,
                        "Transaction Amount Distribution",
                        "amount",
                        bins=15
                    )
                else:
                    display_empty_state("No amount distribution data")

            with col2:
                st.markdown("#### Time-of-Day Analysis")

                time_patterns = patterns.get("time_patterns", [])
                if time_patterns:
                    time_data = [
                        {"hour": p.get("hour", 0), "count": p.get("count", 0)}
                        for p in time_patterns
                    ]
                    display_chart_with_error_handling(
                        create_bar_chart,
                        time_data,
                        "Transactions by Hour",
                        "hour",
                        "count",
                        "Hour",
                        "Transaction Count"
                    )
                else:
                    display_empty_state("No time pattern data")

            st.divider()

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### Merchant Category Analysis")

                merchant_cats = patterns.get("merchant_categories", [])
                if merchant_cats:
                    cat_data = [
                        {
                            "category": p.get("category", "-"),
                            "count": p.get("count", 0),
                            "avg_fraud_rate": p.get("avg_fraud_rate", 0)
                        }
                        for p in merchant_cats
                    ]
                    display_chart_with_error_handling(
                        create_bar_chart,
                        cat_data,
                        "Transactions by Category",
                        "category",
                        "count",
                        "Category",
                        "Transaction Count",
                        horizontal=True
                    )
                else:
                    display_empty_state("No merchant category data")

            with col2:
                st.markdown("#### Geographic Patterns")

                geo_data = patterns.get("geographic_patterns", [])
                if geo_data:
                    display_chart_with_error_handling(
                        create_heatmap,
                        geo_data,
                        "Geographic Heatmap",
                        "longitude",
                        "latitude",
                        "transaction_count"
                    )
                else:
                    display_empty_state("No geographic data")

    with tab3:
        st.markdown("### Risk Indicators by Segment")

        segment_type = st.selectbox(
            "Segment By",
            ["Geographic", "Merchant Category", "Customer Tenure"],
            key="segment_type"
        )

        if st.button("🔍 Load Segments", use_container_width=True):
            with st.spinner("Loading risk indicators..."):
                response = client.get_risk_indicators(segment=segment_type.lower())

                if "error" in response:
                    show_error_message("Error", response.get("error"))
                else:
                    st.session_state.risk_indicators = response

        if "risk_indicators" in st.session_state:
            indicators = st.session_state.risk_indicators

            st.markdown(f"### Risk by {segment_type}")

            seg_data = indicators.get("segments", [])
            if seg_data:
                # Display metrics
                cols = st.columns(len(seg_data[:5]))
                for i, segment in enumerate(seg_data[:5]):
                    with cols[i]:
                        st.metric(
                            segment.get("name", "-"),
                            f"{segment.get('risk_score', 0):.1f}%",
                            f"{segment.get('count', 0)} txns"
                        )

                st.divider()

                # Chart
                chart_data = [
                    {
                        "segment": s.get("name", "-"),
                        "risk_score": s.get("risk_score", 0),
                        "count": s.get("count", 0)
                    }
                    for s in seg_data
                ]

                display_chart_with_error_handling(
                    create_bar_chart,
                    chart_data,
                    f"Risk Score by {segment_type}",
                    "segment",
                    "risk_score",
                    segment_type,
                    "Average Risk Score",
                    horizontal=True
                )
            else:
                display_empty_state("No risk indicator data available")


if __name__ == "__main__":
    main()
