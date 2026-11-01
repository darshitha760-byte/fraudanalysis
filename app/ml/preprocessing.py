"""
Data preprocessing and feature engineering for fraud detection.
Handles data loading, feature engineering, and train/test splitting.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Tuple, Dict, Optional, List
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from pymongo.database import Database
from app.db.database import from_bson
import logging

logger = logging.getLogger(__name__)


class DataPreprocessor:
    """Handles data loading, feature engineering, and preprocessing for ML models."""

    # Merchant categories for one-hot encoding
    MERCHANT_CATEGORIES = [
        'grocery', 'restaurant', 'gas_station', 'online_retail', 'entertainment',
        'travel', 'utilities', 'healthcare', 'insurance', 'other'
    ]

    # Geographic coordinates (latitude, longitude) for distance calculation
    CUSTOMER_HOME_LOCATIONS = {
        'US': (39.8283, -98.5795),
        'CA': (56.1304, -106.3468),
        'UK': (55.3781, -3.4360),
        'DE': (51.1657, 10.4515),
        'FR': (46.2276, 2.2137),
    }

    @staticmethod
    def load_data(
        session: Database, fraud_label_only: bool = True, limit: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Load transaction data from database.

        Args:
            session: MongoDB database handle
            fraud_label_only: If True, only load transactions with known fraud labels

        Returns:
            DataFrame with transaction data
        """
        query = {"fraud_label": {"$ne": None}} if fraud_label_only else {}
        cursor = session["transactions"].find(query).sort(
            [("transaction_date", -1), ("id", -1)]
        )
        if limit is not None:
            cursor = cursor.limit(limit)
        transactions = [from_bson(document) for document in cursor]

        if not transactions:
            logger.warning("No transactions found in database")
            return pd.DataFrame()

        data = []
        for t in transactions:
            data.append({
                'transaction_id': t.get('transaction_id'),
                'customer_id': t.get('customer_id'),
                'transaction_date': t.get('transaction_date'),
                'amount': float(t.get('amount', 0)),
                'merchant_category': t.get('merchant_category') or 'other',
                'transaction_type': t.get('transaction_type'),
                'payment_method': t.get('payment_method'),
                'location_country': t.get('location_country') or 'US',
                'location_city': t.get('location_city') or 'Unknown',
                'device_id': t.get('device_id'),
                'channel': t.get('channel') or 'online',
                'fraud_label': int(t['fraud_label']) if t.get('fraud_label') is not None else None,
            })

        df = pd.DataFrame(data)
        logger.info(f"Loaded {len(df)} transactions from database")

        return df

    @staticmethod
    def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer features from raw transaction data.

        Args:
            df: Raw transaction DataFrame

        Returns:
            DataFrame with engineered features
        """
        df = df.copy()
        df['transaction_date'] = pd.to_datetime(df['transaction_date'])

        # Sort by customer and date for time-based features
        df = df.sort_values(['customer_id', 'transaction_date']).reset_index(drop=True)

        # 1. Transaction amount features (normalized, log-scaled)
        amount_std = df['amount'].std()
        df['amount_normalized'] = (
            (df['amount'] - df['amount'].mean()) / amount_std if amount_std > 0 else 0.0
        )
        df['amount_log'] = np.log1p(df['amount'])
        df['amount_squared'] = df['amount'] ** 2

        # 2. Customer-level features
        customer_stats = df.groupby('customer_id').agg({
            'amount': ['mean', 'std', 'min', 'max'],
            'transaction_id': 'count'
        }).reset_index()
        customer_stats.columns = ['customer_id', 'customer_avg_amount', 'customer_std_amount',
                                  'customer_min_amount', 'customer_max_amount', 'customer_total_transactions']

        df = df.merge(customer_stats, on='customer_id', how='left')
        df['customer_std_amount'] = df['customer_std_amount'].fillna(0)
        df['amount_deviation'] = df['amount'] - df['customer_avg_amount']
        df['amount_deviation_normalized'] = df['amount_deviation'] / (df['customer_std_amount'] + 1)

        # 3. Transaction frequency features
        df['customer_transactions_per_day'] = (
            df.groupby(['customer_id', df['transaction_date'].dt.date])['transaction_id'].transform('count')
        )

        # Weekly frequency
        df['week'] = df['transaction_date'].dt.isocalendar().week
        df['customer_transactions_per_week'] = (
            df.groupby(['customer_id', 'week'])['transaction_id'].transform('count')
        )

        # 4. Time since last transaction
        df['time_since_last_transaction'] = df.groupby('customer_id')['transaction_date'].diff().dt.total_seconds() / 3600
        df['time_since_last_transaction'] = df['time_since_last_transaction'].fillna(0)

        # 5. Transaction count in time windows
        df['transactions_1h'] = df.apply(
            lambda row: len(df[
                (df['customer_id'] == row['customer_id']) &
                (df['transaction_date'] >= row['transaction_date'] - timedelta(hours=1)) &
                (df['transaction_date'] <= row['transaction_date'])
            ]), axis=1
        )

        df['transactions_6h'] = df.apply(
            lambda row: len(df[
                (df['customer_id'] == row['customer_id']) &
                (df['transaction_date'] >= row['transaction_date'] - timedelta(hours=6)) &
                (df['transaction_date'] <= row['transaction_date'])
            ]), axis=1
        )

        df['transactions_24h'] = df.apply(
            lambda row: len(df[
                (df['customer_id'] == row['customer_id']) &
                (df['transaction_date'] >= row['transaction_date'] - timedelta(hours=24)) &
                (df['transaction_date'] <= row['transaction_date'])
            ]), axis=1
        )

        # 6. Temporal features (cyclical encoding)
        df['hour_of_day'] = df['transaction_date'].dt.hour
        df['hour_sin'] = np.sin(2 * np.pi * df['hour_of_day'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour_of_day'] / 24)

        df['day_of_week'] = df['transaction_date'].dt.dayofweek
        df['day_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)

        df['month'] = df['transaction_date'].dt.month

        # 7. Merchant category (one-hot encoding)
        for category in DataPreprocessor.MERCHANT_CATEGORIES:
            df[f'merchant_category_{category}'] = (df['merchant_category'] == category).astype(int)

        # 8. Transaction type encoding
        payment_methods = df['payment_method'].unique()
        for method in payment_methods:
            df[f'payment_method_{method}'] = (df['payment_method'] == method).astype(int)

        # 9. Device features
        df['is_new_device'] = ~df.groupby('customer_id')['device_id'].transform(
            lambda x: x.isin(x.iloc[:-1])
        ).astype(int)
        df['is_new_device'] = df['is_new_device'].fillna(0).astype(int)

        # 10. Geographic features
        df['location_encoded'] = pd.factorize(df['location_country'])[0]

        # 11. Channel encoding
        channels = df['channel'].unique()
        for channel in channels:
            df[f'channel_{channel}'] = (df['channel'] == channel).astype(int)

        logger.info(f"Engineered features, resulting shape: {df.shape}")

        return df

    @staticmethod
    def preprocess_for_training(
        df: pd.DataFrame,
        test_size: float = 0.2,
        validation_size: float = 0.1
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, List[str], StandardScaler]:
        """
        Preprocess data for model training with proper train/val/test split.
        Ensures no temporal leakage.

        Args:
            df: Preprocessed DataFrame with features and fraud_label
            test_size: Proportion of test set (0.2 = 20%)
            validation_size: Proportion of validation set (0.1 = 10%)

        Returns:
            Tuple of (X_train, X_val, X_test, y_train, y_val, y_test, feature_names, scaler)
        """
        # Sort by date to avoid temporal leakage
        df = df.sort_values('transaction_date').reset_index(drop=True)

        # Select feature columns (exclude non-features)
        exclude_cols = {
            'transaction_id', 'customer_id', 'transaction_date', 'fraud_label',
            'merchant_category', 'transaction_type', 'payment_method',
            'location_country', 'location_city', 'device_id', 'channel', 'week'
        }
        feature_cols = [
            col for col in df.select_dtypes(include='number').columns
            if col not in exclude_cols
        ]

        # Separate features and target
        X = df[feature_cols].values
        y = df['fraud_label'].values

        # Calculate split indices
        n_samples = len(X)
        train_size_pct = 1.0 - test_size - validation_size

        train_end_idx = int(n_samples * train_size_pct)
        val_end_idx = train_end_idx + int(n_samples * validation_size)

        # Split data
        X_train = X[:train_end_idx]
        y_train = y[:train_end_idx]

        X_val = X[train_end_idx:val_end_idx]
        y_val = y[train_end_idx:val_end_idx]

        X_test = X[val_end_idx:]
        y_test = y[val_end_idx:]

        for name, labels in (("training", y_train), ("validation", y_val), ("test", y_test)):
            if set(labels) != {0, 1}:
                raise ValueError(
                    f"The chronological {name} split must contain both fraud and legitimate labels. "
                    "Add labeled data across the date range or increase the sample limit."
                )
        if min(np.bincount(y_train.astype(int))) < 5:
            raise ValueError("The training split needs at least 5 samples of each class for cross-validation.")
        if not np.isfinite(X.astype(float)).all():
            raise ValueError("Training features contain missing or non-finite numeric values.")

        # Scale features
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train)
        X_val = scaler.transform(X_val)
        X_test = scaler.transform(X_test)

        logger.info(f"Data split: Train {X_train.shape}, Val {X_val.shape}, Test {X_test.shape}")
        logger.info(f"Target distribution - Train: {np.mean(y_train):.3f}, Val: {np.mean(y_val):.3f}, Test: {np.mean(y_test):.3f}")

        return X_train, X_val, X_test, y_train, y_val, y_test, feature_cols, scaler

    @staticmethod
    def preprocess_for_prediction(
        transaction_data: Dict,
        feature_cols: List[str],
        scaler: StandardScaler
    ) -> np.ndarray:
        """
        Preprocess a single transaction for prediction.

        Args:
            transaction_data: Dictionary with transaction features
            feature_cols: List of feature column names (from training)
            scaler: Fitted StandardScaler from training

        Returns:
            Scaled feature array
        """
        # Create feature vector matching training features
        features = np.zeros(len(feature_cols))

        for i, col in enumerate(feature_cols):
            if col in transaction_data:
                features[i] = float(transaction_data[col])

        # Scale using training scaler
        features = scaler.transform(features.reshape(1, -1))

        return features[0]
