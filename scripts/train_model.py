"""
Training script for fraud detection models.
Loads data, preprocesses, trains, evaluates, and saves models.
"""

import logging
import sys
import argparse
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.database import close_db, get_database
from app.services.ml_service import MLService
from scripts.generate_synthetic_data import SyntheticDataGenerator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main training pipeline."""
    parser = argparse.ArgumentParser(description='Train fraud detection models')
    parser.add_argument('--generate-data', action='store_true', help='Generate synthetic data first')
    parser.add_argument('--n-transactions', type=int, default=50000, help='Number of synthetic transactions')
    parser.add_argument('--train-lr', action='store_true', help='Train Logistic Regression')
    parser.add_argument('--train-rf', action='store_true', default=True, help='Train Random Forest')
    parser.add_argument('--train-iso', action='store_true', help='Train Isolation Forest')
    parser.add_argument('--save-report', action='store_true', default=True, help='Save evaluation report')
    
    args = parser.parse_args()
    
    database = get_database()
    
    try:
        # Generate synthetic data if requested
        if args.generate_data:
            logger.info("Generating synthetic transaction data...")
            df = SyntheticDataGenerator.generate_synthetic_transactions(
                n_transactions=args.n_transactions,
                fraud_rate=0.07
            )
            SyntheticDataGenerator.insert_into_database(df, database)
        
        # Train models
        logger.info("Starting model training...")
        ml_service = MLService()
        
        results = ml_service.train_models(
            database,
            train_logistic_regression=args.train_lr,
            train_random_forest=args.train_rf,
            train_isolation_forest=args.train_iso
        )
        
        # Print results
        logger.info("\n" + "="*80)
        logger.info("TRAINING COMPLETED")
        logger.info("="*80)
        
        if results.get('status') == 'success':
            logger.info(f"Total samples: {results['total_samples']}")
            logger.info(f"Data split - Train: {results['data_split']['train']}, "
                       f"Val: {results['data_split']['val']}, Test: {results['data_split']['test']}")
            
            for model_name, model_info in results.get('models', {}).items():
                logger.info(f"\n{model_name.upper()}:")
                metrics = model_info.get('validation_metrics', {})
                logger.info(f"  Precision: {metrics.get('precision', 'N/A'):.4f}")
                logger.info(f"  Recall: {metrics.get('recall', 'N/A'):.4f}")
                logger.info(f"  F1-Score: {metrics.get('f1_score', 'N/A'):.4f}")
                logger.info(f"  ROC-AUC: {metrics.get('roc_auc', 'N/A')}")
            
            if 'test_metrics' in results:
                logger.info(f"\nTEST SET METRICS:")
                test_metrics = results['test_metrics']
                logger.info(f"  Precision: {test_metrics.get('precision', 'N/A'):.4f}")
                logger.info(f"  Recall: {test_metrics.get('recall', 'N/A'):.4f}")
                logger.info(f"  F1-Score: {test_metrics.get('f1_score', 'N/A'):.4f}")
                logger.info(f"  ROC-AUC: {test_metrics.get('roc_auc', 'N/A')}")
            
            # Save report
            if args.save_report:
                report_path = ml_service.save_training_report(results)
                logger.info(f"\nTraining report saved to: {report_path}")
        
        else:
            logger.error(f"Training failed: {results.get('message', 'Unknown error')}")
        
        logger.info("="*80)
    
    except Exception as e:
        logger.error(f"Error in training pipeline: {e}", exc_info=True)
    
    finally:
        close_db()


if __name__ == '__main__':
    main()
