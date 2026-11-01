"""
Transaction Explorer Page
"""
import streamlit as st
from datetime import datetime, time, timedelta
from components import (
    AuthHandler,
    create_transaction_table,
    display_transaction_detail,
    create_export_button,
    display_empty_state,
)
from utils import show_error_message, truncate_text


def main():
    """Main transaction explorer."""

    # Check authentication
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return

    if not AuthHandler.has_permission("view_transactions"):
        st.error("You don't have permission to view this page")
        return

    client = AuthHandler.get_api_client()

    st.markdown("## 💳 Transaction Explorer")

    # Filters
    st.markdown("### Filters")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        customer_id = st.text_input(
            "Customer database ID",
            placeholder="Enter a numeric ID",
            key="txn_customer"
        )

    with col2:
        transaction_id = st.text_input(
            "Transaction ID",
            placeholder="Search by transaction...",
            key="txn_id"
        )

    with col3:
        min_amount, max_amount = st.slider(
            "Amount Range",
            min_value=0.0,
            max_value=100000.0,
            value=(0.0, 100000.0),
            step=100.0,
            key="txn_amount"
        )

    with col4:
        risk_level = st.selectbox(
            "Risk Level",
            ["All", "Low", "Medium", "High", "Critical"],
            index=0,
            key="txn_risk"
        )

    col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "Start Date",
            datetime.now() - timedelta(days=30),
            key="txn_start_date"
        )

    with col2:
        end_date = st.date_input(
            "End Date",
            datetime.now(),
            key="txn_end_date"
        )

    # Convert dates to ISO format
    start_date_str = start_date.isoformat()
    end_date_str = datetime.combine(end_date, time.max).isoformat()

    # Search button
    if st.button("🔍 Search Transactions", use_container_width=True):
        with st.spinner("Searching transactions..."):
            filters = {
                "customer_id": customer_id if customer_id else None,
                "transaction_id": transaction_id if transaction_id else None,
                "start_date": start_date_str,
                "end_date": end_date_str,
                "min_amount": min_amount,
                "max_amount": max_amount,
                "risk_level": None if risk_level == "All" else risk_level.lower(),
            }

            response = client.get_transactions(**filters)

            if "error" in response:
                show_error_message("Error", response.get("error"))
            else:
                transactions = response.get("data", [])

                if not transactions:
                    total_transactions = response.get("pagination", {}).get("total", 0)
                    if total_transactions == 0:
                        st.info(
                            "No transaction records are in the database yet. "
                            "Load clearly labeled synthetic demo records with "
                            "`docker compose exec api python scripts/generate_synthetic_data.py "
                            "--n-transactions 500`."
                        )
                    else:
                        display_empty_state(
                            "No transactions found matching your criteria"
                        )
                else:
                    total_transactions = response.get("pagination", {}).get(
                        "total",
                        len(transactions),
                    )
                    st.markdown(
                        f"### Showing {len(transactions)} of "
                        f"{total_transactions:,} transaction(s)"
                    )

                    # Create export button
                    st.markdown("**Export:**")
                    create_export_button(transactions, "transactions")

                    # Create transaction table
                    txn_table = create_transaction_table(transactions)
                    st.dataframe(txn_table, use_container_width=True, hide_index=True)

                    st.divider()

                    # Transaction details
                    st.markdown("### Transaction Details")

                    selected_txn_id = st.selectbox(
                        "Select transaction to view details",
                        [t.get("id") for t in transactions],
                        format_func=lambda x: truncate_text(x, 20),
                        key="selected_txn"
                    )

                    if selected_txn_id:
                        with st.spinner("Loading transaction details..."):
                            txn_detail = client.get_transaction(selected_txn_id)

                            if "error" not in txn_detail:
                                display_transaction_detail(txn_detail)
                            else:
                                show_error_message("Error", txn_detail.get("error"))


if __name__ == "__main__":
    main()
