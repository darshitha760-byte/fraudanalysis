from datetime import datetime, timedelta

from scripts.generate_synthetic_data import SyntheticDataGenerator


def test_synthetic_transactions_are_recent_and_insert_with_valid_customers(test_session):
    generated = SyntheticDataGenerator.generate_synthetic_transactions(
        n_transactions=6,
        fraud_rate=0.17,
        n_customers=2,
        days=30,
    )

    assert generated["transaction_id"].is_unique
    assert generated["transaction_date"].min() >= datetime.now() - timedelta(days=31)

    inserted = SyntheticDataGenerator.insert_into_database(generated, test_session)

    assert inserted == 6
    assert test_session["transactions"].count_documents({}) == 6
    assert test_session["customers"].count_documents(
        {"customer_id": {"$regex": "^SYNTH-CUST-"}}
    ) == len(generated["customer_id"].unique())
