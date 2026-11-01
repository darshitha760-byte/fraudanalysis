"""
ML Service for fraud detection.
Integrates preprocessing, training, prediction, and evaluation.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd
import logging
from datetime import datetime
from pathlib import Path
from pymongo.database import Database

from app.ml.preprocessing import DataPreprocessor
from app.ml.train import ModelTrainer
from app.ml.predict import ModelPredictor
from app.ml.evaluate import ModelEvaluator

logger = logging.getLogger(__name__)


class MLService:
    """Orchestrates ML pipeline for fraud detection."""

    def __init__(self):
        """Initialize ML service components."""
        self.preprocessor = DataPreprocessor()
        self.trainer = ModelTrainer()
        self.predictor = ModelPredictor()
        self.evaluator = ModelEvaluator()
        self.last_training_metadata = None
        self.feature_cols = None
        self.scaler = None

    def train_models(
        self,
        session: Database,
        use_fraud_labeled_only: bool = True,
        train_logistic_regression: bool = True,
        train_random_forest: bool = True,
        train_isolation_forest: bool = False,
        training_data: Optional[pd.DataFrame] = None,
        data_source: str = "database",
        evaluation_only: bool = False,
        generate_plots: bool = True,
        artifact_database=None,
        artifact_signing_key: str = "",
    ) -> Dict[str, Any]:
        """
        Train one or more ML models.

        Args:
            session: Database session
            use_fraud_labeled_only: Only use transactions with known fraud labels
            train_logistic_regression: Train baseline model
            train_random_forest: Train main model
            train_isolation_forest: Train anomaly detection model

        Returns:
            Dictionary with training results and metrics
        """
        logger.info("Starting ML model training pipeline...")

        try:
            # Load data
            logger.info("Loading data from database...")
            if not any((train_logistic_regression, train_random_forest, train_isolation_forest)):
                raise ValueError("Select at least one model to train.")
            df = (
                training_data.copy() if training_data is not None else
                DataPreprocessor.load_data(session, fraud_label_only=use_fraud_labeled_only)
            )

            if len(df) < 100:
                logger.error("Insufficient data for training (< 100 samples)")
                return {
                    'status': 'error',
                    'message': 'At least 100 labeled transactions are required for training.',
                    'error_type': 'invalid_data',
                    'samples': len(df)
                }

            # Feature engineering
            logger.info("Engineering features...")
            df = DataPreprocessor.engineer_features(df)

            # Preprocessing and splitting
            logger.info("Preprocessing and splitting data...")
            X_train, X_val, X_test, y_train, y_val, y_test, feature_cols, scaler = \
                DataPreprocessor.preprocess_for_training(df)

            self.feature_cols = feature_cols
            self.scaler = scaler
            provenance = {
                'data_source': data_source,
                'evaluation_only': evaluation_only,
                'total_samples': len(df),
                'split_strategy': 'chronological_70_10_20',
            }

            results = {
                'status': 'success',
                'timestamp': datetime.utcnow().isoformat(),
                'total_samples': len(df),
                'data_split': {
                    'train': len(X_train),
                    'val': len(X_val),
                    'test': len(X_test),
                },
                'fraud_distribution': {
                    'train': float(np.mean(y_train)),
                    'val': float(np.mean(y_val)),
                    'test': float(np.mean(y_test)),
                },
                'models': {}
            }

            # Train Logistic Regression
            if train_logistic_regression:
                logger.info("Training Logistic Regression...")
                lr_model, lr_metadata = ModelTrainer.train_logistic_regression(X_train, y_train)

                # Evaluate
                y_pred_lr = lr_model.predict(X_val)
                lr_proba = lr_model.predict_proba(X_val)[:, 1] if hasattr(lr_model, 'predict_proba') else None
                lr_metrics = ModelEvaluator.evaluate(y_val, y_pred_lr, lr_proba, set_name='validation')

                # Save
                lr_metadata.update(provenance, validation_metrics=lr_metrics, feature_names=feature_cols)
                model_path = ModelTrainer.save_model(
                    lr_model, lr_metadata, 'logistic_regression', scaler=scaler,
                    artifact_database=artifact_database, signing_key=artifact_signing_key,
                )

                results['models']['logistic_regression'] = {
                    'path': model_path,
                    'training_metadata': lr_metadata,
                    'validation_metrics': lr_metrics
                }

            # Train Random Forest
            if train_random_forest:
                logger.info("Training Random Forest...")
                rf_model, rf_metadata = ModelTrainer.train_random_forest(X_train, y_train)

                # Evaluate
                y_pred_rf = rf_model.predict(X_val)
                y_pred_proba_rf = rf_model.predict_proba(X_val)[:, 1] if hasattr(rf_model, 'predict_proba') else None
                rf_metrics = ModelEvaluator.evaluate(y_val, y_pred_rf, y_pred_proba_rf, set_name='validation')

                # Save
                rf_metadata.update(provenance, validation_metrics=rf_metrics, feature_names=feature_cols)
                model_path = ModelTrainer.save_model(
                    rf_model, rf_metadata, 'random_forest', scaler=scaler,
                    artifact_database=artifact_database, signing_key=artifact_signing_key,
                )

                results['models']['random_forest'] = {
                    'path': model_path,
                    'training_metadata': rf_metadata,
                    'validation_metrics': rf_metrics
                }

                # Plot feature importance
                if generate_plots and hasattr(rf_model, 'feature_importances_'):
                    importance_plot = ModelEvaluator.plot_feature_importance(
                        rf_model.feature_importances_,
                        feature_cols,
                        top_n=20
                    )
                    results['models']['random_forest']['feature_importance_plot'] = importance_plot

            # Train Isolation Forest
            if train_isolation_forest:
                logger.info("Training Isolation Forest...")
                iso_model, iso_metadata = ModelTrainer.train_isolation_forest(X_train, contamination=np.mean(y_train))

                # Evaluate
                y_pred_iso = iso_model.predict(X_val)
                y_pred_iso = (y_pred_iso == -1).astype(int)
                iso_metrics = ModelEvaluator.evaluate(y_val, y_pred_iso, set_name='validation')

                # Save
                iso_metadata.update(provenance, validation_metrics=iso_metrics, feature_names=feature_cols)
                model_path = ModelTrainer.save_model(
                    iso_model, iso_metadata, 'isolation_forest', scaler=scaler,
                    artifact_database=artifact_database, signing_key=artifact_signing_key,
                )

                results['models']['isolation_forest'] = {
                    'path': model_path,
                    'training_metadata': iso_metadata,
                    'validation_metrics': iso_metrics
                }

            # Test set evaluation (if Random Forest available)
            if train_random_forest:
                logger.info("Evaluating on test set...")
                y_pred_test = rf_model.predict(X_test)
                y_pred_proba_test = rf_model.predict_proba(X_test)[:, 1] if hasattr(rf_model, 'predict_proba') else None
                test_metrics = ModelEvaluator.evaluate(y_test, y_pred_test, y_pred_proba_test, set_name='test')

                results['test_metrics'] = test_metrics

                # Plot curves
                if generate_plots and y_pred_proba_test is not None:
                    roc_plot = ModelEvaluator.plot_roc_curve(y_test, y_pred_proba_test)
                    pr_plot = ModelEvaluator.plot_precision_recall_curve(y_test, y_pred_proba_test)
                    cm_plot = ModelEvaluator.plot_confusion_matrix(y_test, y_pred_test)

                    results['evaluation_plots'] = {
                        'roc_curve': roc_plot,
                        'pr_curve': pr_plot,
                        'confusion_matrix': cm_plot
                    }

            self.last_training_metadata = results
            logger.info("Model training completed successfully")

            return results

        except Exception as e:
            logger.exception("Error in model training")
            return {
                'status': 'error',
                'message': str(e),
                'error_type': 'invalid_data' if isinstance(e, ValueError) else 'training_failure',
            }

    def predict_transaction(
        self, transaction_features: Dict[str, float], database=None
    ) -> Dict[str, Any]:
        """
        Predict fraud for a transaction.

        Args:
            transaction_features: Dictionary of transaction features

        Returns:
            Dictionary with prediction and metadata
        """
        try:
            if self.feature_cols is None or self.scaler is None:
                logger.warning("Model not trained yet, attempting to load the active artifact...")
                if database is not None:
                    self.predictor.database = database
                self.predictor.load_active_model()
                if self.predictor.model is None:
                    return {
                        'prediction': None,
                        'probability': None,
                        'status': 'error',
                        'message': 'No trained model available'
                    }
                self.feature_cols = self.predictor.metadata.get("feature_names")
                self.scaler = self.predictor.scaler
                if not self.feature_cols or self.scaler is None:
                    return {
                        'prediction': None,
                        'probability': None,
                        'status': 'error',
                        'message': 'The active model is missing its preprocessing artifacts'
                    }

            # Preprocess features
            features = DataPreprocessor.preprocess_for_prediction(
                transaction_features,
                self.feature_cols,
                self.scaler
            )

            # Predict
            result = self.predictor.predict(features)

            return result

        except Exception as e:
            logger.error(f"Error in transaction prediction: {e}")
            return {
                'prediction': None,
                'probability': None,
                'status': 'error',
                'message': str(e)
            }

    def batch_predict_transactions(
        self,
        transactions_list: List[Dict[str, float]]
    ) -> List[Dict[str, Any]]:
        """
        Predict fraud for multiple transactions.

        Args:
            transactions_list: List of transaction feature dictionaries

        Returns:
            List of prediction dictionaries
        """
        results = []

        for transaction in transactions_list:
            result = self.predict_transaction(transaction)
            results.append(result)

        return results

    def get_model_performance(self) -> Dict[str, Any]:
        """
        Get performance metrics of trained models.

        Returns:
            Dictionary with model performance metrics
        """
        if self.last_training_metadata is None:
            return {
                'status': 'error',
                'message': 'No training metadata available'
            }

        return self.last_training_metadata

    def get_active_model_version(self) -> Optional[str]:
        """
        Get version of active model.

        Returns:
            Model version string or None
        """
        if self.predictor.model_version:
            return self.predictor.model_version

        return None

    def save_training_report(self, report_dict: Dict[str, Any]) -> str:
        """
        Save training report to file.

        Args:
            report_dict: Report dictionary

        Returns:
            Path to saved report
        """
        import json

        reports_dir = ModelEvaluator.REPORTS_DIR
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_filename = f"training_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = reports_dir / report_filename

        with open(report_path, 'w') as f:
            json.dump(report_dict, f, indent=2, default=str)

        logger.info(f"Training report saved to {report_path}")

        return str(report_path)
