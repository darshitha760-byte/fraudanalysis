"""
Model training for fraud detection.
Includes Logistic Regression, Random Forest, and Isolation Forest models.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Any, Dict, Tuple, Optional
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelTrainer:
    """Trains and manages fraud detection models."""
    
    MODELS_DIR = Path(__file__).parent.parent.parent / "models"
    
    def __init__(self):
        """Initialize trainer and create models directory if needed."""
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    @staticmethod
    def train_logistic_regression(
        X_train: np.ndarray,
        y_train: np.ndarray,
        cv: int = 5
    ) -> Tuple[LogisticRegression, Dict[str, Any]]:
        """
        Train Logistic Regression baseline model.
        
        Args:
            X_train: Training features
            y_train: Training labels
            cv: Number of cross-validation folds
        
        Returns:
            Tuple of (trained model, training metadata)
        """
        logger.info("Training Logistic Regression baseline model...")
        
        # Calculate class weights to handle imbalance
        n_samples = len(y_train)
        n_fraud = np.sum(y_train)
        n_legitimate = n_samples - n_fraud
        
        class_weight = {
            0: n_fraud / n_legitimate if n_legitimate > 0 else 1.0,
            1: 1.0
        }
        
        model = LogisticRegression(
            max_iter=1000,
            class_weight=class_weight,
            random_state=42,
            solver='lbfgs'
        )
        
        # Train model
        model.fit(X_train, y_train)
        
        # Cross-validation
        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv=StratifiedKFold(n_splits=cv, shuffle=True, random_state=42),
            scoring='f1'
        )
        
        metadata = {
            'model_type': 'logistic_regression',
            'training_samples': len(X_train),
            'fraud_ratio': n_fraud / n_samples,
            'class_weights': class_weight,
            'cv_scores': cv_scores.tolist(),
            'cv_mean': float(cv_scores.mean()),
            'cv_std': float(cv_scores.std()),
            'trained_at': datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Logistic Regression trained. CV F1: {metadata['cv_mean']:.4f} (+/- {metadata['cv_std']:.4f})")
        
        return model, metadata
    
    @staticmethod
    def train_random_forest(
        X_train: np.ndarray,
        y_train: np.ndarray,
        cv: int = 5,
        n_estimators: int = 100
    ) -> Tuple[RandomForestClassifier, Dict[str, Any]]:
        """
        Train Random Forest classifier model.
        
        Args:
            X_train: Training features
            y_train: Training labels
            cv: Number of cross-validation folds
            n_estimators: Number of trees in forest
        
        Returns:
            Tuple of (trained model, training metadata)
        """
        logger.info(f"Training Random Forest model with {n_estimators} estimators...")
        
        # Calculate class weights
        n_samples = len(y_train)
        n_fraud = np.sum(y_train)
        n_legitimate = n_samples - n_fraud
        
        class_weight = {
            0: n_fraud / n_legitimate if n_legitimate > 0 else 1.0,
            1: 1.0
        }
        
        model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            class_weight=class_weight,
            random_state=42,
            n_jobs=-1,
            verbose=0
        )
        
        # Train model
        model.fit(X_train, y_train)
        
        # Cross-validation
        cv_scores = cross_val_score(
            model, X_train, y_train,
            cv=StratifiedKFold(n_splits=cv, shuffle=True, random_state=42),
            scoring='f1',
            n_jobs=-1
        )
        
        metadata = {
            'model_type': 'random_forest',
            'n_estimators': n_estimators,
            'training_samples': len(X_train),
            'fraud_ratio': n_fraud / n_samples,
            'class_weights': class_weight,
            'cv_scores': cv_scores.tolist(),
            'cv_mean': float(cv_scores.mean()),
            'cv_std': float(cv_scores.std()),
            'trained_at': datetime.utcnow().isoformat(),
            'feature_importance': model.feature_importances_.tolist() if hasattr(model, 'feature_importances_') else [],
        }
        
        logger.info(f"Random Forest trained. CV F1: {metadata['cv_mean']:.4f} (+/- {metadata['cv_std']:.4f})")
        
        return model, metadata
    
    @staticmethod
    def train_isolation_forest(
        X_train: np.ndarray,
        contamination: float = 0.05
    ) -> Tuple[IsolationForest, Dict[str, Any]]:
        """
        Train Isolation Forest for anomaly detection.
        
        Args:
            X_train: Training features
            contamination: Expected fraction of anomalies
        
        Returns:
            Tuple of (trained model, training metadata)
        """
        logger.info(f"Training Isolation Forest with contamination={contamination}...")
        
        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_jobs=-1
        )
        
        # Train model
        model.fit(X_train)
        
        # Get predictions on training set
        predictions = model.predict(X_train)
        n_anomalies = np.sum(predictions == -1)
        
        metadata = {
            'model_type': 'isolation_forest',
            'contamination': contamination,
            'training_samples': len(X_train),
            'anomalies_detected': int(n_anomalies),
            'anomaly_ratio': float(n_anomalies / len(X_train)),
            'trained_at': datetime.utcnow().isoformat(),
        }
        
        logger.info(f"Isolation Forest trained. Detected {n_anomalies} anomalies.")
        
        return model, metadata
    
    @staticmethod
    def save_model(
        model: Any,
        metadata: Dict[str, Any],
        name: str,
        version: str = "1.0.0",
        scaler: Optional[StandardScaler] = None,
        artifact_database: Any = None,
        signing_key: str = "",
    ) -> str:
        """
        Save trained model and metadata using joblib.
        
        Args:
            model: Trained model object
            metadata: Model metadata dictionary
            name: Model name (e.g., 'logistic_regression', 'random_forest')
            version: Model version string
        
        Returns:
            Path to saved model
        """
        # Create version-specific filename
        stem = f"{name}_v{version}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
        if artifact_database is not None:
            from app.ml.artifact_store import save_model_artifacts

            return save_model_artifacts(
                artifact_database, model, metadata, name, stem, signing_key, scaler=scaler
            )

        models_dir = ModelTrainer.MODELS_DIR
        models_dir.mkdir(parents=True, exist_ok=True)
        model_filename = f"{stem}.joblib"
        model_path = models_dir / model_filename
        
        # Save model
        joblib.dump(model, model_path)
        if scaler is not None:
            scaler_path = models_dir / f"{stem}.scaler"
            joblib.dump(scaler, scaler_path)
            metadata = dict(metadata, scaler_artifact=scaler_path.name)
        logger.info(f"Model saved to {model_path}")
        
        # Save metadata
        metadata_filename = f"{stem}.json"
        metadata_path = models_dir / metadata_filename
        
        import json
        temporary_metadata = metadata_path.with_suffix(".json.tmp")
        with open(temporary_metadata, 'w', encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        temporary_metadata.replace(metadata_path)
        logger.info(f"Metadata saved to {metadata_path}")
        
        return str(model_path)
    
    @staticmethod
    def load_model(model_path: str) -> Any:
        """
        Load a trained model from disk.
        
        Args:
            model_path: Path to the saved model file
        
        Returns:
            Loaded model object
        """
        if not Path(model_path).exists():
            logger.error(f"Model file not found: {model_path}")
            return None
        
        model = joblib.load(model_path)
        logger.info(f"Model loaded from {model_path}")
        
        return model
    
    @staticmethod
    def get_latest_model_path(model_name: str) -> Optional[str]:
        """
        Get path to the latest version of a model.
        
        Args:
            model_name: Name of the model (e.g., 'random_forest')
        
        Returns:
            Path to latest model or None if not found
        """
        models_dir = ModelTrainer.MODELS_DIR
        
        model_files = sorted(models_dir.glob(f"{model_name}_v*.joblib"), reverse=True)
        
        if model_files:
            return str(model_files[0])
        
        return None
