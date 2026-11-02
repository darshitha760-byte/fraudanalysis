"""
Model prediction for fraud detection.
Loads trained models and generates predictions for transactions.
"""

import numpy as np
from typing import Dict, Any, List, Optional
from pathlib import Path
import joblib
import json
import logging

from app.core.config import get_settings
from app.db.database import get_database

logger = logging.getLogger(__name__)


class ModelPredictor:
    """Generates predictions using trained fraud detection models."""
    
    MODELS_DIR = Path(__file__).parent.parent.parent / "models"
    
    def __init__(self, database=None):
        """Initialize predictor (lazy load models)."""
        self.model = None
        self.model_version = None
        self.model_name = None
        self.database = database
        self.metadata = {}
        self.scaler = None

    def _artifact_database(self):
        if self.database is not None:
            return self.database
        settings = get_settings()
        if settings.model_storage_backend.lower() == "atlas":
            self.database = get_database()
        return self.database
    
    @staticmethod
    def load_model(model_path: str) -> Optional[Any]:
        """
        Load a trained model from disk.
        
        Args:
            model_path: Path to the saved model file
        
        Returns:
            Loaded model object or None if failed
        """
        try:
            if not Path(model_path).exists():
                logger.error(f"Model file not found: {model_path}")
                return None
            
            model = joblib.load(model_path)
            logger.info(f"Model loaded from {model_path}")
            return model
        
        except Exception as e:
            logger.error(f"Failed to load model from {model_path}: {e}")
            return None
    
    @staticmethod
    def get_latest_model() -> Optional[tuple[str, str]]:
        """
        Get path to the latest trained model.
        
        Returns:
            Tuple of (model_path, model_name) or None if no models found
        """
        settings = get_settings()
        if settings.model_storage_backend.lower() == "atlas":
            from app.ml.artifact_store import latest_model_id

            database = get_database()
            return latest_model_id(database, settings.model_artifact_signing_key)
        models_dir = ModelPredictor.MODELS_DIR
        
        if not models_dir.exists():
            logger.warning(f"Models directory not found: {models_dir}")
            return None
        
        # Look for Random Forest first (preferred), then others
        for pattern in ["random_forest_v*.joblib", "logistic_regression_v*.joblib", "isolation_forest_v*.joblib"]:
            model_files = sorted(models_dir.glob(pattern), reverse=True)
            for path in model_files:
                metadata_path = path.with_suffix(".json")
                if metadata_path.is_file():
                    try:
                        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        logger.exception("Cannot read candidate model metadata: %s", metadata_path.name)
                        continue
                    if metadata.get("evaluation_only") or metadata.get("data_source") == "synthetic":
                        continue
                model_path = str(path)
                model_name = pattern.split('_v')[0]
                return model_path, model_name
        
        return None
    
    def load_active_model(self, model_path: Optional[str] = None) -> bool:
        """
        Load the active model for predictions.
        
        Args:
            model_path: Optional specific model path. If None, loads latest.
        
        Returns:
            True if model loaded successfully, False otherwise
        """
        if model_path is None:
            database = self._artifact_database()
            settings = get_settings()
            if database is not None and settings.model_storage_backend.lower() == "atlas":
                from app.ml.artifact_store import latest_model_id

                result = latest_model_id(database, settings.model_artifact_signing_key)
                if result is None:
                    logger.warning("No authenticated model artifacts found")
                    return False
                model_path, self.model_name = result
                try:
                    from app.ml.artifact_store import load_model_artifacts

                    loaded = load_model_artifacts(
                        database, model_path, settings.model_artifact_signing_key
                    )
                except Exception:
                    logger.exception("Unable to load authenticated model artifact.")
                    return False
                if loaded is None:
                    return False
                self.model, self.scaler, self.metadata = loaded
                self.model_version = model_path.split("_v", 1)[-1].split("_", 1)[0]
                return True
            result = self.get_latest_model()
            if result is None:
                logger.warning("No trained models found")
                return False
            model_path, self.model_name = result
        else:
            database = self._artifact_database()
            if database is not None and get_settings().model_storage_backend.lower() == "atlas":
                try:
                    from app.ml.artifact_store import load_model_artifacts

                    loaded = load_model_artifacts(
                        database, model_path, get_settings().model_artifact_signing_key
                    )
                except Exception:
                    logger.exception("Unable to load authenticated model artifact.")
                    return False
                if loaded is None:
                    return False
                self.model, self.scaler, self.metadata = loaded
                self.model_name = self.metadata.get("model_type")
                self.model_version = model_path.split("_v", 1)[-1].split("_", 1)[0]
                return True
            self.model_name = Path(model_path).stem.split('_v')[0]
        
        self.model = self.load_model(model_path)
        
        if self.model is None:
            return False

        model_file = Path(model_path)
        metadata_path = model_file.with_suffix(".json")
        try:
            if metadata_path.is_file():
                self.metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            scaler_name = self.metadata.get("scaler_artifact")
            if scaler_name:
                scaler_path = (ModelPredictor.MODELS_DIR / scaler_name).resolve()
                if scaler_path.parent != ModelPredictor.MODELS_DIR.resolve():
                    logger.error("Model metadata references an invalid scaler artifact.")
                    return False
                self.scaler = joblib.load(scaler_path)
        except Exception:
            logger.exception("Unable to load model preprocessing metadata.")
            return False

        self.model_version = model_file.stem.split('_v')[1] if '_v' in model_file.stem else 'unknown'
        logger.info(f"Active model: {self.model_name} v{self.model_version}")
        
        return True
    
    def predict(self, features: np.ndarray) -> Dict[str, Any]:
        """
        Generate prediction for a single transaction.
        
        Args:
            features: Scaled feature array (should match training shape)
        
        Returns:
            Dictionary with prediction, probability, and metadata
        """
        if self.model is None:
            if not self.load_active_model():
                return {
                    'prediction': None,
                    'probability': None,
                    'model_version': None,
                    'status': 'error',
                    'message': 'No model available'
                }
        
        try:
            # Ensure features are the right shape
            if len(features.shape) == 1:
                features = features.reshape(1, -1)
            
            # Make prediction
            prediction = int(self.model.predict(features)[0])
            
            # Get probability if available
            probability = None
            if hasattr(self.model, 'predict_proba'):
                proba = self.model.predict_proba(features)[0]
                probability = float(proba[1])  # Probability of fraud (class 1)
            elif hasattr(self.model, 'decision_function'):
                # For SVM-like models
                decision = self.model.decision_function(features)[0]
                probability = 1.0 / (1.0 + np.exp(-decision))  # Sigmoid conversion
            
            return {
                'prediction': prediction,
                'probability': probability,
                'model_version': self.model_version,
                'model_name': self.model_name,
                'status': 'success'
            }
        
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return {
                'prediction': None,
                'probability': None,
                'model_version': self.model_version,
                'status': 'error',
                'message': str(e)
            }
    
    def batch_predict(self, features_list: List[np.ndarray]) -> List[Dict[str, Any]]:
        """
        Generate predictions for multiple transactions.
        
        Args:
            features_list: List of scaled feature arrays
        
        Returns:
            List of prediction dictionaries
        """
        results = []
        
        if self.model is None:
            if not self.load_active_model():
                return [{
                    'prediction': None,
                    'probability': None,
                    'status': 'error',
                    'message': 'No model available'
                } for _ in features_list]
        
        try:
            # Stack features
            X = np.vstack(features_list)
            
            # Make predictions
            predictions = self.model.predict(X)
            
            # Get probabilities if available
            probabilities = None
            if hasattr(self.model, 'predict_proba'):
                probabilities = self.model.predict_proba(X)[:, 1]
            elif hasattr(self.model, 'decision_function'):
                decisions = self.model.decision_function(X)
                probabilities = 1.0 / (1.0 + np.exp(-decisions))
            
            # Format results
            for i, pred in enumerate(predictions):
                result = {
                    'prediction': int(pred),
                    'probability': float(probabilities[i]) if probabilities is not None else None,
                    'model_version': self.model_version,
                    'model_name': self.model_name,
                    'status': 'success'
                }
                results.append(result)
        
        except Exception as e:
            logger.error(f"Batch prediction error: {e}")
            results = [{
                'prediction': None,
                'probability': None,
                'status': 'error',
                'message': str(e)
            } for _ in features_list]
        
        return results
    
    def predict_anomaly(self, features: np.ndarray) -> Dict[str, Any]:
        """
        Generate anomaly score for a transaction (using Isolation Forest if available).
        
        Args:
            features: Scaled feature array
        
        Returns:
            Dictionary with anomaly score and status
        """
        # Try to load Isolation Forest model
        if self.model_name != 'isolation_forest':
            result = self.get_latest_model()
            if result:
                iso_model_path, iso_model_name = result
                if iso_model_name == 'isolation_forest':
                    self.load_active_model(iso_model_path)
        
        if self.model is None or self.model_name != 'isolation_forest':
            return {
                'anomaly_score': None,
                'is_anomaly': None,
                'status': 'error',
                'message': 'Isolation Forest model not available'
            }
        
        try:
            if len(features.shape) == 1:
                features = features.reshape(1, -1)
            
            # Isolation Forest returns -1 for anomalies, 1 for normal
            prediction = self.model.predict(features)[0]
            is_anomaly = prediction == -1
            
            # Get anomaly score
            score = None
            if hasattr(self.model, 'score_samples'):
                score = float(self.model.score_samples(features)[0])
            
            return {
                'anomaly_score': score,
                'is_anomaly': bool(is_anomaly),
                'model_version': self.model_version,
                'status': 'success'
            }
        
        except Exception as e:
            logger.error(f"Anomaly prediction error: {e}")
            return {
                'anomaly_score': None,
                'is_anomaly': None,
                'status': 'error',
                'message': str(e)
            }
