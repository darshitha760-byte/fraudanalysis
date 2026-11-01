"""
Model evaluation for fraud detection.
Calculates metrics, generates reports, and creates visualizations.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple
from sklearn.metrics import (
    precision_score, recall_score, f1_score, roc_auc_score, auc,
    roc_curve, precision_recall_curve, confusion_matrix, classification_report
)
import matplotlib.pyplot as plt
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ModelEvaluator:
    """Evaluates model performance and generates metrics."""

    REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"

    def __init__(self):
        """Initialize evaluator and create reports directory."""
        self.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def evaluate(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_pred_proba: Optional[np.ndarray] = None,
        set_name: str = "test"
    ) -> Dict[str, Any]:
        """
        Evaluate model predictions comprehensively.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_pred_proba: Predicted probabilities (optional, for probabilistic metrics)
            set_name: Name of the dataset (train/val/test)

        Returns:
            Dictionary with comprehensive metrics
        """
        # Basic metrics
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)

        # Confusion matrix
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()

        # Rates
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
        tpr = tp / (tp + fn) if (tp + fn) > 0 else 0
        tnr = tn / (tn + fp) if (tn + fp) > 0 else 0

        # Probabilistic metrics
        roc_auc = None
        pr_auc = None

        if y_pred_proba is not None:
            try:
                roc_auc = roc_auc_score(y_true, y_pred_proba)
                precision_curve, recall_curve, _ = precision_recall_curve(y_true, y_pred_proba)
                pr_auc = auc(recall_curve, precision_curve)
            except Exception as e:
                logger.warning(f"Could not calculate probabilistic metrics: {e}")

        # Class distribution
        n_fraud = np.sum(y_true)
        n_total = len(y_true)
        fraud_ratio = n_fraud / n_total

        metrics = {
            'accuracy': float(np.mean(y_true == y_pred)),
            'set_name': set_name,
            'total_samples': int(n_total),
            'fraud_count': int(n_fraud),
            'legitimate_count': int(n_total - n_fraud),
            'fraud_ratio': float(fraud_ratio),
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1),
            'roc_auc': float(roc_auc) if roc_auc is not None else None,
            'pr_auc': float(pr_auc) if pr_auc is not None else None,
            'confusion_matrix': {
                'true_negatives': int(tn),
                'false_positives': int(fp),
                'false_negatives': int(fn),
                'true_positives': int(tp),
            },
            'rates': {
                'true_positive_rate': float(tpr),
                'true_negative_rate': float(tnr),
                'false_positive_rate': float(fpr),
                'false_negative_rate': float(fnr),
            }
        }

        logger.info(f"{set_name.upper()} Metrics - Precision: {precision:.4f}, Recall: {recall:.4f}, F1: {f1:.4f}")

        return metrics

    @staticmethod
    def print_report(metrics: Dict[str, Any]) -> str:
        """
        Format metrics as readable report string.

        Args:
            metrics: Metrics dictionary from evaluate()

        Returns:
            Formatted report string
        """
        # Handle None values for optional metrics
        roc_auc_str = f"{metrics['roc_auc']:.4f}" if metrics['roc_auc'] is not None else 'N/A'
        pr_auc_str = f"{metrics['pr_auc']:.4f}" if metrics['pr_auc'] is not None else 'N/A'
        tpr_str = f"{metrics['rates']['true_positive_rate']:.4f}" if metrics['rates']['true_positive_rate'] is not None else 'N/A'
        tnr_str = f"{metrics['rates']['true_negative_rate']:.4f}" if metrics['rates']['true_negative_rate'] is not None else 'N/A'
        fpr_str = f"{metrics['rates']['false_positive_rate']:.4f}" if metrics['rates']['false_positive_rate'] is not None else 'N/A'
        fnr_str = f"{metrics['rates']['false_negative_rate']:.4f}" if metrics['rates']['false_negative_rate'] is not None else 'N/A'

        report = f"""
=== Model Evaluation Report ===
Dataset: {metrics['set_name']}
Total Samples: {metrics['total_samples']}
Fraud Cases: {metrics['fraud_count']} ({metrics['fraud_ratio']:.2%})
Legitimate Cases: {metrics['legitimate_count']}

=== Classification Metrics ===
Precision: {metrics['precision']:.4f}
Recall: {metrics['recall']:.4f}
F1-Score: {metrics['f1_score']:.4f}
ROC-AUC: {roc_auc_str}
PR-AUC: {pr_auc_str}

=== Rates ===
True Positive Rate: {tpr_str}
True Negative Rate: {tnr_str}
False Positive Rate: {fpr_str}
False Negative Rate: {fnr_str}

=== Confusion Matrix ===
TP: {metrics['confusion_matrix']['true_positives']}
TN: {metrics['confusion_matrix']['true_negatives']}
FP: {metrics['confusion_matrix']['false_positives']}
FN: {metrics['confusion_matrix']['false_negatives']}
"""
        return report

    @staticmethod
    def plot_roc_curve(
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        title: str = "ROC Curve"
    ) -> str:
        """
        Plot ROC curve and save to file.

        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            title: Plot title

        Returns:
            Path to saved plot
        """
        try:
            fpr, tpr, _ = roc_curve(y_true, y_pred_proba)
            roc_auc = auc(fpr, tpr)

            plt.figure(figsize=(8, 6))
            plt.plot(fpr, tpr, color='darkorange', lw=2, label=f'ROC curve (AUC = {roc_auc:.3f})')
            plt.plot([0, 1], [0, 1], color='navy', lw=2, linestyle='--', label='Random Classifier')
            plt.xlim([0.0, 1.0])
            plt.ylim([0.0, 1.05])
            plt.xlabel('False Positive Rate')
            plt.ylabel('True Positive Rate')
            plt.title(title)
            plt.legend(loc="lower right")
            plt.grid(alpha=0.3)

            plot_path = ModelEvaluator.REPORTS_DIR / f"roc_curve_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(plot_path, dpi=100, bbox_inches='tight')
            plt.close()

            logger.info(f"ROC curve saved to {plot_path}")
            return str(plot_path)

        except Exception as e:
            logger.error(f"Failed to plot ROC curve: {e}")
            return ""

    @staticmethod
    def plot_precision_recall_curve(
        y_true: np.ndarray,
        y_pred_proba: np.ndarray,
        title: str = "Precision-Recall Curve"
    ) -> str:
        """
        Plot Precision-Recall curve and save to file.

        Args:
            y_true: True labels
            y_pred_proba: Predicted probabilities
            title: Plot title

        Returns:
            Path to saved plot
        """
        try:
            precision, recall, _ = precision_recall_curve(y_true, y_pred_proba)
            pr_auc = auc(recall, precision)

            plt.figure(figsize=(8, 6))
            plt.plot(recall, precision, color='blue', lw=2, label=f'PR curve (AUC = {pr_auc:.3f})')
            plt.axhline(y=np.sum(y_true) / len(y_true), color='red', linestyle='--', lw=2, label='Random Classifier')
            plt.xlim([0.0, 1.0])
            plt.ylim([0.0, 1.05])
            plt.xlabel('Recall')
            plt.ylabel('Precision')
            plt.title(title)
            plt.legend(loc="best")
            plt.grid(alpha=0.3)

            plot_path = ModelEvaluator.REPORTS_DIR / f"pr_curve_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(plot_path, dpi=100, bbox_inches='tight')
            plt.close()

            logger.info(f"PR curve saved to {plot_path}")
            return str(plot_path)

        except Exception as e:
            logger.error(f"Failed to plot PR curve: {e}")
            return ""

    @staticmethod
    def plot_confusion_matrix(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        title: str = "Confusion Matrix"
    ) -> str:
        """
        Plot confusion matrix and save to file.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            title: Plot title

        Returns:
            Path to saved plot
        """
        try:
            cm = confusion_matrix(y_true, y_pred)

            plt.figure(figsize=(8, 6))
            plt.imshow(cm, interpolation='nearest', cmap=plt.cm.Blues)
            plt.title(title)
            plt.colorbar()

            tick_marks = np.arange(2)
            plt.xticks(tick_marks, ['Legitimate', 'Fraud'])
            plt.yticks(tick_marks, ['Legitimate', 'Fraud'])

            # Add text annotations
            thresh = cm.max() / 2.
            for i, j in np.ndindex(cm.shape):
                plt.text(j, i, f'{cm[i, j]}',
                        horizontalalignment="center",
                        color="white" if cm[i, j] > thresh else "black",
                        fontsize=14)

            plt.ylabel('True Label')
            plt.xlabel('Predicted Label')
            plt.grid(False)

            plot_path = ModelEvaluator.REPORTS_DIR / f"confusion_matrix_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(plot_path, dpi=100, bbox_inches='tight')
            plt.close()

            logger.info(f"Confusion matrix saved to {plot_path}")
            return str(plot_path)

        except Exception as e:
            logger.error(f"Failed to plot confusion matrix: {e}")
            return ""

    @staticmethod
    def plot_feature_importance(
        feature_importances: np.ndarray,
        feature_names: list,
        top_n: int = 20,
        title: str = "Feature Importance"
    ) -> str:
        """
        Plot feature importance and save to file.

        Args:
            feature_importances: Feature importance scores
            feature_names: Names of features
            top_n: Number of top features to display
            title: Plot title

        Returns:
            Path to saved plot
        """
        try:
            # Sort by importance
            indices = np.argsort(feature_importances)[::-1][:top_n]

            plt.figure(figsize=(10, 6))
            plt.barh(range(len(indices)), feature_importances[indices])
            plt.yticks(range(len(indices)), [feature_names[i] for i in indices])
            plt.xlabel('Importance')
            plt.title(title)
            plt.gca().invert_yaxis()
            plt.grid(alpha=0.3, axis='x')

            plot_path = ModelEvaluator.REPORTS_DIR / f"feature_importance_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(plot_path, dpi=100, bbox_inches='tight')
            plt.close()

            logger.info(f"Feature importance plot saved to {plot_path}")
            return str(plot_path)

        except Exception as e:
            logger.error(f"Failed to plot feature importance: {e}")
            return ""
