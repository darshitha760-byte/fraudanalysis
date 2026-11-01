"""MongoDB document service for fraud-alert lifecycle and analyst workflows."""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.db.database import from_bson, insert_document, to_bson
from app.models.fraud_alert import FraudAlert

logger = logging.getLogger(__name__)


class AlertService:
    PRIORITY_MAPPING = {"HIGH": (71, 100), "MEDIUM": (31, 70), "LOW": (0, 30)}
    ALERT_TYPE_MAPPING = {
        "rule_triggered": "RULE_TRIGGERED",
        "ml_predicted": "ML_PREDICTED",
        "combined": "COMBINED",
    }
    VALID_TRANSITIONS = {
        "pending": ["under_review", "resolved", "dismissed"],
        "under_review": ["resolved", "dismissed", "pending"],
        "resolved": [],
        "dismissed": [],
    }

    @staticmethod
    def create_fraud_alert(
        session: Database, transaction_id: int, customer_id: int,
        assessment_id: int, risk_score: float, risk_level: str,
        alert_reason: str, triggered_rules_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not session["fraud_assessments"].find_one({"id": assessment_id}):
            raise ValueError(f"Assessment {assessment_id} not found")
        if not session["transactions"].find_one({"id": transaction_id}):
            raise ValueError(f"Transaction {transaction_id} not found")
        severity = "high" if risk_score >= 71 else "medium" if risk_score >= 31 else "low"
        document = insert_document(session, "fraud_alerts", {
            "transaction_id": transaction_id,
            "customer_id": customer_id,
            "assessment_id": assessment_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "alert_severity": severity,
            "alert_status": "pending",
            "alert_reason": alert_reason,
            "triggered_rules_summary": triggered_rules_summary,
            "alert_created_at": datetime.now(timezone.utc),
        })
        return AlertService._format_alert_response(FraudAlert.model_validate(document))

    @staticmethod
    def _find(session: Database, alert_id: int) -> Optional[FraudAlert]:
        document = session["fraud_alerts"].find_one({"id": alert_id})
        return FraudAlert.model_validate(from_bson(document)) if document else None

    @staticmethod
    def get_alert(session: Database, alert_id: int) -> Optional[Dict[str, Any]]:
        alert = AlertService._find(session, alert_id)
        return AlertService._format_alert_response(alert) if alert else None

    @staticmethod
    def _list(session: Database, query: dict, limit: int, offset: int,
              sort_field: str = "alert_created_at"):
        collection = session["fraud_alerts"]
        total = collection.count_documents(query)
        cursor = collection.find(query).sort(sort_field, -1).skip(offset).limit(limit)
        return ([AlertService._format_alert_response(FraudAlert.model_validate(from_bson(doc)))
                 for doc in cursor], total)

    @staticmethod
    def get_pending_alerts(session: Database, limit: int = 100, offset: int = 0):
        return AlertService._list(
            session, {"alert_status": {"$regex": "^pending$", "$options": "i"}}, limit, offset
        )

    @staticmethod
    def get_alerts_by_status(session: Database, status: str, limit: int = 100, offset: int = 0):
        allowed = ("pending", "under_review", "resolved", "dismissed")
        status = status.lower()
        if status not in allowed:
            raise ValueError(f"Invalid status: {status}. Must be one of {list(allowed)}")
        return AlertService._list(
            session, {"alert_status": {"$regex": f"^{re.escape(status)}$", "$options": "i"}},
            limit, offset,
        )

    @staticmethod
    def get_alerts_by_customer(session: Database, customer_id: int, limit: int = 100, offset: int = 0):
        return AlertService._list(session, {"customer_id": customer_id}, limit, offset)

    @staticmethod
    def update_alert_status(
        session: Database, alert_id: int, new_status: str,
        reviewed_by_user_id: Optional[int] = None,
        review_decision: Optional[str] = None, review_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        alert = AlertService._find(session, alert_id)
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        current_status = alert.alert_status.lower()
        new_status = new_status.lower()
        allowed = AlertService.VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Invalid status transition from {alert.alert_status} to {new_status}. "
                f"Valid transitions: {allowed}"
            )
        now = datetime.now(timezone.utc)
        changes = {"alert_status": new_status, "updated_at": now}
        if review_decision is not None:
            changes["review_decision"] = review_decision
        if review_notes is not None:
            changes["review_notes"] = review_notes
        if reviewed_by_user_id is not None:
            changes["reviewed_by"] = reviewed_by_user_id
            changes["review_timestamp"] = now
        if new_status in ("resolved", "dismissed"):
            changes["alert_resolved_at"] = now
        result = session["fraud_alerts"].update_one(
            {"id": alert_id, "alert_status": alert.alert_status},
            {"$set": to_bson(changes)},
        )
        if result.modified_count != 1:
            raise ValueError(f"Alert {alert_id} changed during update")
        return AlertService.get_alert(session, alert_id)

    @staticmethod
    def dismiss_alert(session, alert_id, reviewed_by_user_id, reason):
        return AlertService.update_alert_status(
            session, alert_id, "dismissed", reviewed_by_user_id, "dismissed", reason
        )

    @staticmethod
    def approve_alert(session, alert_id, reviewed_by_user_id, action_taken, notes=None):
        return AlertService.update_alert_status(
            session, alert_id, "resolved", reviewed_by_user_id, "approved",
            f"Action: {action_taken}. {notes or ''}",
        )

    @staticmethod
    def _format_alert_response(alert) -> Dict[str, Any]:
        data = alert.model_dump() if isinstance(alert, FraudAlert) else from_bson(alert)
        score = data.get("risk_score")
        return {
            "alert_id": data.get("id"),
            "transaction_id": data.get("transaction_id"),
            "customer_id": data.get("customer_id"),
            "assessment_id": data.get("assessment_id"),
            "risk_score": float(score) if score is not None else 0.0,
            "risk_level": data.get("risk_level") or "low",
            "ml_score": float(data["ml_score"]) if data.get("ml_score") is not None else None,
            "alert_severity": data.get("alert_severity", "low"),
            "alert_status": data.get("alert_status", "pending"),
            "alert_reason": data.get("alert_reason", ""),
            "triggered_rules_summary": data.get("triggered_rules_summary"),
            "reviewed_by": data.get("reviewed_by"),
            "review_timestamp": data.get("review_timestamp"),
            "review_decision": data.get("review_decision"),
            "review_notes": data.get("review_notes"),
            "alert_created_at": data.get("alert_created_at") or data.get("created_at"),
            "created_at": data.get("alert_created_at") or data.get("created_at"),
            "alert_resolved_at": data.get("alert_resolved_at"),
        }

    @staticmethod
    def get_alert_statistics(session: Database) -> Dict[str, Any]:
        collection = session["fraud_alerts"]
        statuses = ("pending", "under_review", "resolved", "dismissed")
        severities = ("low", "medium", "high")
        return {
            "total_alerts": collection.count_documents({}),
            "status_counts": {value: collection.count_documents({
                                  "alert_status": {"$regex": f"^{value}$", "$options": "i"}})
                              for value in statuses},
            "severity_counts": {value: collection.count_documents({
                                    "alert_severity": {"$regex": f"^{value}$", "$options": "i"}})
                                for value in severities},
        }

    @staticmethod
    def record_analyst_decision(session, alert_id, decision, justification, analyst_id):
        if decision not in ("APPROVED", "REJECTED", "NEEDS_REVIEW"):
            raise ValueError(f"Invalid decision: {decision}")
        alert = AlertService._find(session, alert_id)
        if not alert:
            raise ValueError(f"Alert {alert_id} not found")
        status_value = "under_review" if decision == "NEEDS_REVIEW" else "resolved"
        now = datetime.now(timezone.utc)
        session["fraud_alerts"].update_one({"id": alert_id}, {"$set": {
            "review_decision": decision.lower(),
            "alert_status": status_value,
            "review_notes": justification,
            "reviewed_by": analyst_id,
            "review_timestamp": now,
            "alert_resolved_at": now if status_value == "resolved" else None,
            "updated_at": now,
        }})
        return AlertService.get_alert(session, alert_id)

    @staticmethod
    def get_alerts_by_priority(session, priority, limit=100, offset=0):
        priority = priority.lower()
        if priority not in ("low", "medium", "high"):
            raise ValueError(f"Invalid priority: {priority}")
        return AlertService._list(session, {"alert_severity": priority}, limit, offset)

    @staticmethod
    def get_analyst_alerts(session, analyst_id, limit=100, offset=0):
        return AlertService._list(session, {"reviewed_by": analyst_id}, limit, offset, "review_timestamp")

    @staticmethod
    def search_alerts(session, query_text, filters=None, limit=100, offset=0):
        query = AlertService._search_query(query_text, filters)
        return AlertService._list(session, query, limit, offset)

    @staticmethod
    def _search_query(query_text, filters=None):
        query = {}
        if query_text:
            pattern = {"$regex": re.escape(query_text), "$options": "i"}
            query["$or"] = [{"alert_reason": pattern}, {"review_notes": pattern}]
        for key, field in (("status", "alert_status"), ("severity", "alert_severity"),
                           ("analyst_id", "reviewed_by"), ("customer_id", "customer_id"),
                           ("priority", "alert_severity")):
            value = (filters or {}).get(key)
            if value is not None:
                query[field] = ({"$regex": f"^{re.escape(str(value))}$", "$options": "i"}
                                if key in {"status", "severity", "priority"} else value)
        bounds = {}
        if (filters or {}).get("min_risk_score") is not None:
            bounds["$gte"] = to_bson((filters or {})["min_risk_score"])
        if (filters or {}).get("max_risk_score") is not None:
            bounds["$lte"] = to_bson((filters or {})["max_risk_score"])
        if bounds:
            query["risk_score"] = bounds
        return query

    @staticmethod
    def get_pending_alerts_paginated(session, limit=50, offset=0):
        return AlertService.get_pending_alerts(session, limit, offset)

    @staticmethod
    def get_analyst_alerts_paginated(session, analyst_id, limit=50, offset=0):
        return AlertService.get_analyst_alerts(session, analyst_id, limit, offset)

    @staticmethod
    def get_alerts_by_status_paginated(session, status, limit=50, offset=0):
        return AlertService._list(
            session, {"alert_status": {"$regex": f"^{re.escape(status)}$", "$options": "i"}},
            limit, offset,
        )

    @staticmethod
    def get_alerts_by_priority_paginated(session, priority, limit=50, offset=0):
        return AlertService._list(
            session, {"alert_severity": {"$regex": f"^{re.escape(priority)}$", "$options": "i"}},
            limit, offset,
        )

    @staticmethod
    def search_alerts_paginated(session, query_text=None, filters=None, limit=50, offset=0):
        return AlertService._list(
            session, AlertService._search_query(query_text, filters), limit, offset
        )
