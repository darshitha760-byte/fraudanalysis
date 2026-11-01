"""
Generate synthetic transaction data for model training.
Creates realistic fraud and legitimate transaction patterns.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pymongo.database import Database
import logging
import random
import argparse
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SyntheticDataGenerator:
    """Generates synthetic transaction data for training."""

    MERCHANT_CATEGORIES = [
        'grocery', 'restaurant', 'gas_station', 'online_retail', 'entertainment',
        'travel', 'utilities', 'healthcare', 'insurance', 'other'
    ]

    COUNTRIES = ['US', 'CA', 'UK', 'DE', 'FR']
    CHANNELS = ['online', 'atm', 'pos', 'phone']
    PAYMENT_METHODS = ['card', 'bank_transfer', 'wallet', 'cash']

    @staticmethod
    def generate_legitimate_transaction(
        customer_id: int,
        base_time: datetime,
        customer_profile: dict
    ) -> dict:
        """Generate a realistic legitimate transaction."""

        # Amount based on category
        category = random.choice(SyntheticDataGenerator.MERCHANT_CATEGORIES)
        if category == 'grocery':
            amount = np.random.normal(75, 30)
        elif category == 'restaurant':
            amount = np.random.normal(50, 25)
        elif category == 'gas_station':
            amount = np.random.normal(60, 15)
        elif category == 'online_retail':
            amount = np.random.normal(100, 60)
        elif category == 'travel':
            amount = np.random.normal(300, 200)
        else:
            amount = np.random.normal(100, 50)

        amount = max(1, amount)

        # Realistic timing
        hour = random.gauss(12, 8)  # Peak around noon
        hour = max(0, min(23, hour))

        transaction_time = base_time.replace(hour=int(hour), minute=random.randint(0, 59))

        return {
            'customer_id': customer_id,
            'transaction_date': transaction_time,
            'amount': round(amount, 2),
            'merchant_category': category,
            'transaction_type': 'purchase',
            'payment_method': random.choice(SyntheticDataGenerator.PAYMENT_METHODS),
            'location_country': customer_profile.get('home_country', 'US'),
            'location_city': customer_profile.get('home_city', 'New York'),
            'channel': random.choice(SyntheticDataGenerator.CHANNELS),
            'device_id': random.choice(customer_profile.get('known_devices', ['device_1'])),
            'fraud_label': False,
        }

    @staticmethod
    def generate_fraud_transaction(
        customer_id: int,
        base_time: datetime,
        customer_profile: dict
    ) -> dict:
        """Generate a fraudulent transaction with suspicious patterns."""

        fraud_type = random.choice(['high_amount', 'unusual_location', 'unusual_time', 'unusual_merchant'])

        if fraud_type == 'high_amount':
            # Unusually high amount
            category = random.choice(['online_retail', 'travel', 'entertainment'])
            amount = np.random.normal(5000, 1000)
        elif fraud_type == 'unusual_location':
            # Transaction from unusual location
            category = random.choice(SyntheticDataGenerator.MERCHANT_CATEGORIES)
            amount = np.random.normal(200, 100)
        elif fraud_type == 'unusual_time':
            # Transaction at unusual hour
            category = random.choice(SyntheticDataGenerator.MERCHANT_CATEGORIES)
            amount = np.random.normal(150, 80)
        else:  # unusual_merchant
            # Suspicious merchant category
            category = 'online_retail'
            amount = np.random.normal(500, 300)

        amount = max(1, amount)

        # Suspicious timing
        if fraud_type == 'unusual_time':
            hour = random.choice([2, 3, 4, 5])  # Night hours
        else:
            hour = random.randint(0, 23)

        transaction_time = base_time.replace(hour=hour, minute=random.randint(0, 59))

        # Possibly different location
        if fraud_type == 'unusual_location':
            country = random.choice([c for c in SyntheticDataGenerator.COUNTRIES
                                   if c != customer_profile.get('home_country', 'US')])
        else:
            country = customer_profile.get('home_country', 'US')

        # Possibly new device
        if random.random() < 0.3:
            device_id = f"device_fraud_{random.randint(1, 1000)}"
        else:
            device_id = random.choice(customer_profile.get('known_devices', ['device_1']))

        return {
            'customer_id': customer_id,
            'transaction_date': transaction_time,
            'amount': round(amount, 2),
            'merchant_category': category,
            'transaction_type': 'purchase',
            'payment_method': random.choice(SyntheticDataGenerator.PAYMENT_METHODS),
            'location_country': country,
            'location_city': 'Unknown City',
            'channel': random.choice(SyntheticDataGenerator.CHANNELS),
            'device_id': device_id,
            'fraud_label': True,
        }

    @staticmethod
    def generate_synthetic_transactions(
        n_transactions: int = 50000,
        fraud_rate: float = 0.07,
        n_customers: int = 1000,
        days: int = 30,
    ) -> pd.DataFrame:
        """
        Generate synthetic transaction dataset.

        Args:
            n_transactions: Total number of transactions to generate
            fraud_rate: Fraction of fraudulent transactions (0.07 = 7%)
            n_customers: Number of unique customers
            days: Date range ending today to generate transactions within

        Returns:
            DataFrame with synthetic transactions
        """
        if n_transactions < 1:
            raise ValueError("n_transactions must be at least 1")
        if not 0 <= fraud_rate <= 1:
            raise ValueError("fraud_rate must be between 0 and 1")
        if n_customers < 1:
            raise ValueError("n_customers must be at least 1")
        if days < 1:
            raise ValueError("days must be at least 1")

        logger.info(f"Generating {n_transactions} synthetic transactions ({fraud_rate*100:.1f}% fraud rate)...")

        # Generate customer profiles
        customer_profiles = {}
        for cid in range(1, n_customers + 1):
            customer_profiles[cid] = {
                'home_country': random.choice(SyntheticDataGenerator.COUNTRIES),
                'home_city': f"City_{cid % 50}",
                'known_devices': [f'device_{cid}_1', f'device_{cid}_2'],
            }

        transactions = []
        date_range_days = days - 1
        base_date = datetime.now() - timedelta(days=date_range_days)
        run_id = datetime.now().strftime("%Y%m%d%H%M%S%f")

        n_fraud = int(n_transactions * fraud_rate)
        n_legitimate = n_transactions - n_fraud

        # Generate legitimate transactions
        for i in range(n_legitimate):
            if i % 5000 == 0:
                logger.info(f"Generated {i} legitimate transactions...")

            customer_id = random.randint(1, n_customers)
            days_offset = random.randint(0, date_range_days)
            transaction_time = base_date + timedelta(days=days_offset)

            transaction = SyntheticDataGenerator.generate_legitimate_transaction(
                customer_id, transaction_time, customer_profiles[customer_id]
            )
            transaction['transaction_id'] = f"TXN_LEGIT_{run_id}_{i:08d}"
            transaction['merchant_name'] = f"Merchant_{random.randint(1, 5000)}"
            transaction['merchant_id'] = f"M{random.randint(10000, 99999)}"
            transaction['is_synthetic'] = True

            transactions.append(transaction)

        # Generate fraudulent transactions
        for i in range(n_fraud):
            if i % 1000 == 0:
                logger.info(f"Generated {i} fraudulent transactions...")

            customer_id = random.randint(1, n_customers)
            days_offset = random.randint(0, date_range_days)
            transaction_time = base_date + timedelta(days=days_offset)

            transaction = SyntheticDataGenerator.generate_fraud_transaction(
                customer_id, transaction_time, customer_profiles[customer_id]
            )
            transaction['transaction_id'] = f"TXN_FRAUD_{run_id}_{i:08d}"
            transaction['merchant_name'] = f"Suspicious_Merchant_{random.randint(1, 5000)}"
            transaction['merchant_id'] = f"M_FRAUD{random.randint(10000, 99999)}"
            transaction['is_synthetic'] = True

            transactions.append(transaction)

        df = pd.DataFrame(transactions)
        df = df.sample(frac=1).reset_index(drop=True)  # Shuffle

        logger.info(f"Generated {len(df)} synthetic transactions")
        logger.info(f"Fraud distribution: {df['fraud_label'].mean():.2%}")

        return df

    @staticmethod
    def insert_into_database(
        df: pd.DataFrame,
        session: Database,
        batch_size: int = 1000
    ) -> int:
        """
        Insert synthetic transactions into database.

        Args:
            df: DataFrame with transactions
            session: Database session
            batch_size: Number of transactions per batch insert

        Returns:
            Number of transactions inserted
        """
        from app.models import Customer, FraudAssessment, Transaction
        from app.services.fraud_engine import FraudEngine
        from app.db.database import from_bson, insert_document

        logger.info(f"Inserting {len(df)} transactions into database...")

        # Ensure generated customers exist and map generated IDs to database IDs.
        unique_customers = df['customer_id'].unique()
        customer_id_map = {}
        for cid in unique_customers:
            external_customer_id = f"SYNTH-CUST-{int(cid):06d}"
            customer_doc = session["customers"].find_one(
                {"customer_id": external_customer_id}
            )
            if not customer_doc:
                customer = Customer(
                    customer_id=external_customer_id,
                    name=f"Customer_{cid}",
                    email=f"customer_{cid}@example.com",
                    phone=f"+1-555-{random.randint(1000, 9999):04d}",
                    country="US",
                    city=f"City_{int(cid) % 50}",
                )
                customer_doc = insert_document(
                    session,
                    "customers",
                    customer.model_dump(exclude={"id", "created_at", "updated_at"}),
                )
            customer_id_map[int(cid)] = int(customer_doc["id"])

        # Insert transactions in batches
        for i in range(0, len(df), batch_size):
            batch = df.iloc[i:i+batch_size]

            for _, row in batch.iterrows():
                transaction = Transaction(
                    transaction_id=row['transaction_id'],
                    customer_id=customer_id_map[int(row['customer_id'])],
                    transaction_date=row['transaction_date'],
                    amount=row['amount'],
                    currency='USD',
                    merchant_name=row.get('merchant_name', 'Unknown'),
                    merchant_id=row.get('merchant_id'),
                    merchant_category=row['merchant_category'],
                    transaction_type=row['transaction_type'],
                    status='completed',
                    payment_method=row['payment_method'],
                    location_country=row['location_country'],
                    location_city=row['location_city'],
                    device_id=row.get('device_id'),
                    channel=row['channel'],
                    is_synthetic=row.get('is_synthetic', True),
                    fraud_label=bool(row['fraud_label']),
                )
                inserted = insert_document(
                    session,
                    "transactions",
                    transaction.model_dump(exclude={"id", "created_at", "updated_at"}),
                )
                stored_transaction = Transaction.model_validate(from_bson(inserted))
                risk_score, risk_level, triggered_rules = FraudEngine.evaluate_transaction(
                    session, stored_transaction
                )
                assessment = FraudAssessment(
                        transaction_id=stored_transaction.id,
                        risk_score=risk_score,
                        risk_category=risk_level,
                        rules_triggered_count=len(triggered_rules),
                        explanation="Scored by the configured fraud rule engine.",
                    )
                insert_document(
                    session,
                    "fraud_assessments",
                    assessment.model_dump(exclude={"id", "created_at", "updated_at"}),
                )

            logger.info(f"Inserted {min(i + batch_size, len(df))}/{len(df)} transactions")

        logger.info(f"Successfully inserted {len(df)} transactions")
        return len(df)


def main():
    """Generate and insert synthetic data."""
    parser = argparse.ArgumentParser(description="Generate synthetic transaction data")
    parser.add_argument("--n-transactions", type=int, default=500)
    parser.add_argument("--fraud-rate", type=float, default=0.07)
    parser.add_argument("--n-customers", type=int, default=100)
    parser.add_argument("--days", type=int, default=30)
    args = parser.parse_args()

    from app.db.database import close_db, get_database

    session = get_database()

    try:
        # Generate synthetic data
        df = SyntheticDataGenerator.generate_synthetic_transactions(
            n_transactions=args.n_transactions,
            fraud_rate=args.fraud_rate,
            n_customers=args.n_customers,
            days=args.days,
        )

        # Insert into database
        inserted = SyntheticDataGenerator.insert_into_database(df, session)

        logger.info(f"Synthetic data generation complete. {inserted} transactions inserted.")

    finally:
        close_db()


if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

    logging.basicConfig(level=logging.INFO)
    main()
