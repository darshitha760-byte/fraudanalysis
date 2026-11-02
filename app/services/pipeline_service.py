"""
Pipeline Service - End-to-end transaction processing orchestration.
Orchestrates full pipeline from transaction input to alert/case creation.
"""

import logging
from typing import Dict, List, Any, Optional
from decimal import Decimal
from pymongo.database import Database

from app.db.database import from_bson
from app.models.transaction import Transaction
from app.models.fraud_alert import FraudAssessment, FraudAlert
from app.models.case import InvestigationCase
from app.models.user import User
from app.services.fraud_engine import FraudEngine
from app.services.risk_engine import RiskEngine
from app.services.alert_service import AlertService
from app.services.case_service import CaseService
from app.services.ml_service import MLService
from app.core.permissions import UserRole

logger = logging.getLogger(__name__)


class PipelineService:
    """
    Orchestrates end-to-end transaction processing pipeline.
    
    Pipeline Steps:
    1. Load and validate transaction
    2. Execute fraud rules (Phase 4)
    3. Get ML predictions (Phase 7)
    4. Calculate combined risk score (Phase 5)
    5. Create fraud alert if needed (Phase 5)
    6. Create investigation case if high-risk (Phase 6)
    7. Return full assessment
    """
    
    @staticmethod
    def process_transaction_pipeline(
        session: Database,
        transaction_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Execute full pipeline for a single transaction.
        
        Args:
            session: Database session
            transaction_id: Transaction database ID
            user_id: Optional user ID for audit trail
        
        Returns:
            Dictionary with assessment results
        """
        try:
            logger.info(f"Starting pipeline for transaction {transaction_id}")
            
            # Step 1: Load transaction
            raw_transaction = session["transactions"].find_one({"id": transaction_id})
            transaction = Transaction.model_validate(from_bson(raw_transaction)) if raw_transaction else None
            
            if not transaction:
                logger.error(f"Transaction {transaction_id} not found")
                return {
                    "success": False,
                    "transaction_id": transaction_id,
                    "error": f"Transaction {transaction_id} not found"
                }
            
            # Step 2: Execute fraud rules
            fraud_engine = FraudEngine()
            risk_score, risk_level, triggered_rules = fraud_engine.evaluate_transaction(
                db=session,
                transaction=transaction
            )
            
            rules_result = {
                "score": float(risk_score),
                "level": risk_level,
                "triggered_rules": triggered_rules,
                "summary": f"{len(triggered_rules)} rules triggered"
            }
            
            logger.info(f"Fraud rules check completed: {len(triggered_rules)} rules triggered")
            
            # Step 3: Get ML predictions - convert transaction to features dict
            ml_service = MLService()
            transaction_features = {
                "amount": float(transaction.amount),
                "transaction_type": transaction.transaction_type or "unknown",
                "merchant_id": transaction.merchant_id or "unknown",
                "customer_id": transaction.customer_id,
            }
            
            ml_result = ml_service.predict_transaction(transaction_features, database=session)
            ml_score = ml_result.get("probability", 0) if ml_result.get("probability") is not None else 0
            if isinstance(ml_score, (int, float)):
                ml_score = ml_score * 100 if ml_score <= 1 else ml_score  # Convert 0-1 to 0-100
            else:
                ml_score = 0
            
            logger.info(f"ML prediction completed: fraud score {ml_score}")
            
            # Step 4: Calculate risk score using RiskEngine.assess_fraud_risk
            risk_engine = RiskEngine()
            risk_result = risk_engine.assess_fraud_risk(
                session=session,
                transaction_id=transaction_id,
                customer_id=transaction.customer_id,
                transaction_data=None
            )
            
            logger.info(f"Risk score calculated: {risk_result.get('risk_score')} ({risk_result.get('risk_level')})")
            
            # Step 5: Create fraud alert if needed
            alert_result = None
            if risk_result.get("alert_required", False):
                try:
                    alert_result = AlertService.create_fraud_alert(
                        session=session,
                        transaction_id=transaction_id,
                        customer_id=transaction.customer_id,
                        assessment_id=risk_result.get("assessment_id"),
                        risk_score=risk_result.get("risk_score", 0),
                        risk_level=risk_result.get("risk_level", "MEDIUM"),
                        alert_reason=f"Automated alert: {len(triggered_rules)} rules triggered"
                    )
                    logger.info(f"Fraud alert created")
                except Exception as e:
                    logger.warning(f"Could not create alert: {e}")
                    alert_result = None
            
            # Step 6: Create investigation case if high-risk
            case_result = None
            if risk_result.get("risk_level") == "HIGH" and alert_result:
                try:
                    # Get or create analyst user
                    analyst_user = session["users"].find_one({"role": UserRole.ANALYST.value})
                    if analyst_user:
                        case_result = CaseService.create_case_from_alert(
                            session=session,
                            alert_id=alert_result.get("alert_id"),
                            case_type="FRAUD_CONFIRMED",
                            assigned_to=analyst_user["id"],
                            summary=f"High-risk transaction: {len(triggered_rules)} rules triggered",
                        )
                        logger.info("Investigation case created")
                except Exception as e:
                    logger.warning(f"Could not create case: {e}")
                    case_result = None
            
            logger.info("Pipeline completed successfully for transaction %s", transaction_id)
            
            # Return comprehensive results
            return {
                "success": True,
                "transaction_id": transaction_id,
                "transaction_external_id": transaction.transaction_id,
                "customer_id": transaction.customer_id,
                "rules_result": {
                    "rules_triggered": len(rules_result.get("triggered_rules", [])),
                    "rule_score": rules_result.get("score", 0),
                    "rules": rules_result.get("triggered_rules", []),
                },
                "ml_result": {
                    "fraud_score": ml_score,
                },
                "risk_result": {
                    "risk_score": risk_result.get("risk_score"),
                    "risk_level": risk_result.get("risk_level"),
                    "alert_required": risk_result.get("alert_required", False),
                    "assessment_id": risk_result.get("assessment_id"),
                },
                "alert_result": alert_result,
                "case_result": case_result,
            }
        except Exception as e:
            logger.error(f"Pipeline error for transaction {transaction_id}: {e}", exc_info=True)
            return {
                "success": False,
                "transaction_id": transaction_id,
                "error": str(e)
            }
    
    @staticmethod
    def batch_process_transactions(
        session: Database,
        transaction_ids: List[int],
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Process multiple transactions.
        
        Args:
            session: Database session
            transaction_ids: List of transaction IDs
            user_id: Optional user ID for audit trail
        
        Returns:
            Dictionary with batch results
        """
        logger.info(f"Starting batch processing for {len(transaction_ids)} transactions")
        
        results = {
            "total_transactions": len(transaction_ids),
            "successful": 0,
            "failed": 0,
            "alerts_created": 0,
            "cases_created": 0,
            "errors": [],
            "transaction_results": [],
        }
        
        for idx, transaction_id in enumerate(transaction_ids, 1):
            try:
                result = PipelineService.process_transaction_pipeline(
                    session=session,
                    transaction_id=transaction_id,
                    user_id=user_id
                )
                
                results["successful"] += 1
                
                if result.get("alert_result"):
                    results["alerts_created"] += 1
                
                if result.get("case_result"):
                    results["cases_created"] += 1
                
                results["transaction_results"].append(result)
                
                logger.info(f"Batch progress: {idx}/{len(transaction_ids)} completed")
                
            except Exception as e:
                results["failed"] += 1
                error_msg = f"Transaction {transaction_id}: {str(e)}"
                results["errors"].append(error_msg)
                logger.error(error_msg)
        
        logger.info(f"Batch processing completed: {results['successful']} successful, {results['failed']} failed")
        
        return results
    
    @staticmethod
    def reprocess_alert(
        session: Database,
        alert_id: int,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Reprocess an alert with latest rules and models.
        Used when rules or models have been updated.
        
        Args:
            session: Database session
            alert_id: Alert ID to reprocess
            user_id: Optional user ID for audit trail
        
        Returns:
            Dictionary with reprocessing results
        """
        logger.info(f"Reprocessing alert {alert_id}")
        
        # Get the alert
        document = session["fraud_alerts"].find_one({"id": alert_id})
        alert = FraudAlert.model_validate(from_bson(document)) if document else None
        
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        
        # Reprocess the transaction
        result = PipelineService.process_transaction_pipeline(
            session=session,
            transaction_id=alert.transaction_id,
            user_id=user_id
        )
        
        logger.info(f"Alert {alert_id} reprocessing completed")
        
        return {
            "success": True,
            "alert_id": alert_id,
            "pipeline_result": result
        }
