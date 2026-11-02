"""MongoDB-backed audit logging for compliance and forensics."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pymongo.database import Database

from app.db.database import from_bson, insert_document, to_bson
from app.models import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    """Persist audit entries as independent, append-only documents."""

    @staticmethod
    def log_action(
        db: Database,
        action: str,
        action_category: str,
        target_type: str,
        target_id: Optional[str] = None,
        target_name: Optional[str] = None,
        actor_id: Optional[int] = None,
        status: str = "success",
        status_message: Optional[str] = None,
        http_method: Optional[str] = None,
        http_path: Optional[str] = None,
        ip_address: Optional[str] = None,
        request_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        changes_before: Optional[Dict[str, Any]] = None,
        changes_after: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        now = datetime.now(timezone.utc)
        values = {
            "actor_id": actor_id, "action": action,
            "action_category": action_category, "target_type": target_type,
            "target_id": target_id, "target_name": target_name,
            "action_status": status, "status_message": status_message,
            "http_method": http_method, "http_path": http_path,
            "ip_address": ip_address, "request_id": request_id,
            "action_timestamp": now, "metadata": metadata,
            "changes_before": changes_before, "changes_after": changes_after,
        }
        try:
            return AuditLog.model_validate(insert_document(db, "audit_logs", values))
        except Exception:
            logger.exception("Failed to create audit log for action %s", action)
            # Audit failures should not turn a successful business operation into
            # a failure, matching the existing service contract.
            return AuditLog(**values)

    @staticmethod
    def log_login(db, actor_id, email, success, ip_address=None):
        return AuditService.log_action(
            db, "login", "authentication", "user",
            target_id=str(actor_id) if actor_id else email,
            target_name=email, actor_id=actor_id,
            status="success" if success else "failure",
            status_message="Login successful" if success else "Invalid credentials",
            ip_address=ip_address, metadata={"email": email},
        )

    @staticmethod
    def log_transaction_creation(db, actor_id, transaction_id, customer_id, amount, ip_address=None):
        return AuditService.log_action(
            db, "create_transaction", "transaction", "transaction",
            target_id=transaction_id, target_name=f"Transaction {transaction_id}",
            actor_id=actor_id, ip_address=ip_address,
            metadata={"customer_id": customer_id, "amount": amount},
        )

    @staticmethod
    def log_fraud_assessment(db, actor_id, transaction_id, risk_score, risk_category):
        return AuditService.log_action(
            db, "assess_transaction", "fraud_detection", "fraud_assessment",
            target_id=str(transaction_id),
            target_name=f"Assessment for transaction {transaction_id}",
            actor_id=actor_id,
            metadata={"risk_score": risk_score, "risk_category": risk_category},
        )

    @staticmethod
    def log_alert_review(db, actor_id, alert_id, decision, notes=None):
        return AuditService.log_action(
            db, "review_alert", "fraud_detection", "fraud_alert",
            target_id=str(alert_id), target_name=f"Alert {alert_id}",
            actor_id=actor_id, metadata={"decision": decision, "notes": notes},
        )

    @staticmethod
    def log_rule_modification(db, actor_id, rule_id, action_type, changes_before=None, changes_after=None):
        return AuditService.log_action(
            db, f"{action_type}_rule", "rule_management", "fraud_rule",
            target_id=rule_id, target_name=f"Rule {rule_id}", actor_id=actor_id,
            changes_before=changes_before, changes_after=changes_after,
        )

    @staticmethod
    def log_model_training(db, actor_id, model_version, dataset_id, success, metrics=None):
        return AuditService.log_action(
            db, "train_model", "ml_model", "ml_model",
            target_id=model_version, target_name=f"Model {model_version}",
            actor_id=actor_id, status="success" if success else "failure",
            metadata={"dataset_id": dataset_id, "metrics": metrics},
        )

    @staticmethod
    def log_batch_import(db, actor_id, row_count, idempotency_key):
        return AuditService.log_action(
            db, "bulk_import_transactions", "transaction", "batch_import",
            target_id=idempotency_key, target_name=f"Batch import {idempotency_key}",
            actor_id=actor_id,
            metadata={"row_count": row_count, "idempotency_key": idempotency_key},
        )

    @staticmethod
    def log_alert_event(db, alert_id, event_type, analyst_id, details=None,
                        status="success", status_message=None):
        descriptions = {
            "CREATED": "Alert created",
            "STATUS_CHANGED": "Alert status changed",
            "DECISION_RECORDED": "Analyst decision recorded",
            "REVIEWED": "Alert marked for review",
            "ESCALATED": "Alert escalated",
        }
        return AuditService.log_action(
            db, f"alert_{event_type.lower()}", "alert_management", "fraud_alert",
            target_id=str(alert_id), target_name=f"Alert {alert_id}",
            actor_id=analyst_id, status=status, status_message=status_message,
            metadata={"event_type": event_type,
                      "description": descriptions.get(event_type, event_type),
                      "details": details or {}},
        )

    @staticmethod
    def log_alert_status_change(db, alert_id, old_status, new_status, analyst_id):
        return AuditService.log_alert_event(
            db, alert_id, "STATUS_CHANGED", analyst_id,
            {"previous_status": old_status, "new_status": new_status},
        )

    @staticmethod
    def log_analyst_decision(db, alert_id, decision, justification, analyst_id):
        return AuditService.log_alert_event(
            db, alert_id, "DECISION_RECORDED", analyst_id,
            {"decision": decision, "justification": justification[:500]},
        )

    @staticmethod
    def get_alert_history(session: Database, alert_id: int, limit: int = 100):
        docs = session["audit_logs"].find(
            {"target_type": "fraud_alert", "target_id": str(alert_id)}
        ).sort("action_timestamp", -1).limit(limit)
        return [AuditLog.model_validate(from_bson(doc)) for doc in docs]

    @staticmethod
    def get_analyst_actions(db: Database, analyst_id: int,
                            start_date=None, end_date=None,
                            action_category=None, limit: int = 100):
        start_date = start_date or datetime.now(timezone.utc) - timedelta(days=30)
        end_date = end_date or datetime.now(timezone.utc)
        query = {"actor_id": analyst_id,
                 "action_timestamp": {"$gte": start_date, "$lte": end_date}}
        if action_category:
            query["action_category"] = action_category
        docs = db["audit_logs"].find(query).sort("action_timestamp", -1).limit(limit)
        return [AuditLog.model_validate(from_bson(doc)) for doc in docs]
