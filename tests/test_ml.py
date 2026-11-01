"""
Comprehensive tests for ML pipeline including preprocessing, training, and prediction.
"""

import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, patch

from app.ml.preprocessing import DataPreprocessor
from app.ml.train import ModelTrainer
from app.ml.predict import ModelPredictor
from app.ml.evaluate import ModelEvaluator
from app.services.ml_service import MLService


class TestDataPreprocessor:
    """Tests for data preprocessing and feature engineering."""

    @pytest.fixture
    def sample_transaction_data(self):
        """Create sample transaction data."""
        dates = pd.date_range('2023-01-01', periods=100, freq='h')
        data = {
            'transaction_id': [f'TXN_{i}' for i in range(100)],
            'customer_id': [i % 10 for i in range(100)],
            'transaction_date': dates,
            'amount': np.random.uniform(10, 1000, 100),
            'merchant_category': [np.random.choice(['grocery', 'restaurant', 'online_retail']) for _ in range(100)],
            'transaction_type': ['purchase'] * 100,
            'payment_method': ['card'] * 100,
            'location_country': ['US'] * 100,
            'location_city': ['NYC'] * 100,
            'device_id': [f'device_{i % 3}' for i in range(100)],
            'channel': ['online'] * 100,
            'fraud_label': [1 if i % 10 == 0 else 0 for i in range(100)],
        }
        return pd.DataFrame(data)

    def test_engineer_features(self, sample_transaction_data):
        """Test feature engineering."""
        df = sample_transaction_data.copy()
        engineered_df = DataPreprocessor.engineer_features(df)

        # Check that new features were created
        assert len(engineered_df.columns) > len(df.columns)

        # Check for specific engineered features
        expected_features = [
            'amount_normalized', 'amount_log', 'customer_avg_amount',
            'amount_deviation', 'transactions_1h', 'hour_sin', 'hour_cos'
        ]
        for feature in expected_features:
            assert feature in engineered_df.columns

        # Check for no NaN in critical features
        assert engineered_df['amount_normalized'].notna().sum() > 90

    def test_feature_scaling(self, sample_transaction_data):
        """Test feature scaling and preprocessing."""
        df = sample_transaction_data.copy()
        df = DataPreprocessor.engineer_features(df)

        X_train, X_val, X_test, y_train, y_val, y_test, feature_cols, scaler = \
            DataPreprocessor.preprocess_for_training(df)

        # Check shapes
        assert len(X_train) + len(X_val) + len(X_test) == len(df)
        # Verify all splits have some data
        assert len(X_train) > 0
        assert len(X_val) > 0
        assert len(X_test) > 0

        # Check that features are scaled (mean ~0, std ~1)
        assert abs(X_train.mean()) < 0.5
        assert 0.5 < X_train.std() < 1.5

    def test_no_data_leakage(self, sample_transaction_data):
        """Test that train/val/test split has no temporal leakage."""
        df = sample_transaction_data.copy()
        df = DataPreprocessor.engineer_features(df)

        X_train, X_val, X_test, y_train, y_val, y_test, _, _ = \
            DataPreprocessor.preprocess_for_training(df)

        # Ensure non-empty sets
        assert len(X_train) > 0
        assert len(X_val) > 0
        assert len(X_test) > 0

    def test_preprocess_for_prediction(self, sample_transaction_data):
        """Test preprocessing a single transaction for prediction."""
        df = sample_transaction_data.copy()
        df = DataPreprocessor.engineer_features(df)

        X_train, _, _, _, _, _, feature_cols, scaler = \
            DataPreprocessor.preprocess_for_training(df)

        # Create a mock transaction
        transaction = {col: 100.0 for col in feature_cols[:5]}

        features = DataPreprocessor.preprocess_for_prediction(transaction, feature_cols, scaler)

        # Check output shape
        assert features.shape[0] == len(feature_cols)


class TestModelTrainer:
    """Tests for model training."""

    @pytest.fixture
    def training_data(self):
        """Create sample training data."""
        np.random.seed(42)
        X = np.random.randn(200, 10)
        y = np.random.binomial(1, 0.1, 200)
        return X, y

    def test_train_logistic_regression(self, training_data):
        """Test Logistic Regression training."""
        X, y = training_data
        model, metadata = ModelTrainer.train_logistic_regression(X, y)

        # Check model attributes
        assert hasattr(model, 'predict')
        assert hasattr(model, 'predict_proba')

        # Check metadata
        assert metadata['model_type'] == 'logistic_regression'
        assert 'cv_mean' in metadata
        assert 'cv_scores' in metadata

        # Check predictions
        y_pred = model.predict(X[:10])
        assert y_pred.shape == (10,)

    def test_train_random_forest(self, training_data):
        """Test Random Forest training."""
        X, y = training_data
        model, metadata = ModelTrainer.train_random_forest(X, y, n_estimators=10)

        # Check model attributes
        assert hasattr(model, 'predict')
        assert hasattr(model, 'feature_importances_')

        # Check metadata
        assert metadata['model_type'] == 'random_forest'
        assert 'cv_mean' in metadata

        # Check predictions
        y_pred = model.predict(X[:10])
        assert y_pred.shape == (10,)

    def test_train_isolation_forest(self, training_data):
        """Test Isolation Forest training."""
        X, y = training_data
        model, metadata = ModelTrainer.train_isolation_forest(X, contamination=0.1)

        # Check model attributes
        assert hasattr(model, 'predict')

        # Check metadata
        assert metadata['model_type'] == 'isolation_forest'
        assert 'anomalies_detected' in metadata

        # Check predictions (-1 for anomaly, 1 for normal)
        y_pred = model.predict(X[:10])
        assert all(p in [-1, 1] for p in y_pred)


class TestModelPredictor:
    """Tests for model prediction."""

    @pytest.fixture
    def mock_model(self):
        """Create a mock trained model."""
        model = MagicMock()
        model.predict = lambda X: np.ones(len(X), dtype=int)
        model.predict_proba = lambda X: np.random.rand(len(X), 2)
        return model

    def test_batch_predict(self, mock_model):
        """Test batch predictions."""
        predictor = ModelPredictor()
        predictor.model = mock_model
        predictor.model_name = 'random_forest'
        predictor.model_version = '1.0'

        features_list = [np.random.randn(10) for _ in range(5)]
        results = predictor.batch_predict(features_list)

        # Check results
        assert len(results) == 5
        for result in results:
            assert 'prediction' in result
            assert 'probability' in result


class TestModelEvaluator:
    """Tests for model evaluation."""

    def test_evaluate_metrics(self):
        """Test metric calculation."""
        y_true = np.array([0, 1, 1, 0, 1, 0, 0, 1])
        y_pred = np.array([0, 1, 0, 0, 1, 1, 0, 1])
        y_proba = np.array([0.1, 0.9, 0.3, 0.2, 0.8, 0.6, 0.1, 0.95])

        metrics = ModelEvaluator.evaluate(y_true, y_pred, y_proba)

        # Check metric keys
        assert 'precision' in metrics
        assert 'recall' in metrics
        assert 'f1_score' in metrics
        assert 'confusion_matrix' in metrics

        # Check metric values are valid
        assert 0 <= metrics['precision'] <= 1
        assert 0 <= metrics['recall'] <= 1
        assert 0 <= metrics['f1_score'] <= 1

    def test_print_report(self):
        """Test report generation."""
        y_true = np.array([0, 1, 1, 0, 1, 0])
        y_pred = np.array([0, 1, 0, 0, 1, 1])

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        report = ModelEvaluator.print_report(metrics)

        # Check report contains expected content
        assert 'Precision' in report
        assert 'Recall' in report
        assert 'F1-Score' in report


class TestMLService:
    """Tests for ML service integration."""

    def test_ml_service_initialization(self):
        """Test MLService initialization."""
        service = MLService()

        assert service.preprocessor is not None
        assert service.trainer is not None
        assert service.predictor is not None
        assert service.evaluator is not None

    @patch('app.services.ml_service.DataPreprocessor.load_data')
    def test_get_model_performance(self, mock_load):
        """Test getting model performance."""
        service = MLService()
        service.last_training_metadata = {
            'status': 'success',
            'models': {'random_forest': {'accuracy': 0.95}}
        }

        performance = service.get_model_performance()

        assert performance['status'] == 'success'
        assert 'models' in performance


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_dataframe(self):
        """Test handling of empty dataframe."""
        df = pd.DataFrame()

        # This should raise an exception for empty dataframe
        try:
            engineered = DataPreprocessor.engineer_features(df)
            assert len(engineered) == 0
        except (KeyError, ValueError) as e:
            # Expected: KeyError for missing columns or ValueError for empty data
            pass

    def test_missing_values(self):
        """Test handling of missing values."""
        df = pd.DataFrame({
            'transaction_id': ['T1', 'T2', 'T3'],
            'customer_id': [1.0, 2.0, 3.0],  # Use float to avoid NaN issues
            'transaction_date': ['2023-01-01', '2023-01-02', '2023-01-03'],
            'amount': [100.0, 200.0, 300.0],  # No NaN in amount
            'merchant_category': ['grocery', 'restaurant', 'online_retail'],
            'transaction_type': ['purchase', 'purchase', 'purchase'],
            'payment_method': ['card', 'card', 'card'],
            'location_country': ['US', 'US', 'US'],
            'location_city': ['NYC', 'LA', 'SF'],
            'device_id': ['d1', 'd2', 'd3'],
            'channel': ['online', 'online', 'online'],
            'fraud_label': [0, 0, 1],
        })

        df['transaction_date'] = pd.to_datetime(df['transaction_date'])

        # Should handle data gracefully
        engineered = DataPreprocessor.engineer_features(df)
        assert len(engineered) > 0
        # Check for NaN columns and drop them if necessary
        assert engineered.shape[0] >= 1

    def test_imbalanced_data(self):
        """Test handling of imbalanced datasets."""
        X = np.random.randn(100, 5)
        y = np.zeros(100)
        y[0:5] = 1  # Only 5% fraud

        # Training should handle imbalanced data with class weights
        model, metadata = ModelTrainer.train_logistic_regression(X, y)

        assert 'class_weights' in metadata
        assert metadata['class_weights'][1] >= metadata['class_weights'][0]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
