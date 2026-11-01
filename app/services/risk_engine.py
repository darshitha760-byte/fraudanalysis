"""MongoDB-backed combined rule/ML risk assessment workflow."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from pymongo.database import Database

from app.db.database import from_bson, insert_document
from app.models.fraud_alert import FraudAssessment
from app.models.transaction import Transaction
from app.services.fraud_engine import FraudEngine
from app.services.ml_service import MLService

logger = logging.getLogger(__name__)


class RiskEngine:
    RULE_WEIGHT = 0.60
    ML_WEIGHT = 0.40
    ALERT_THRESHOLD_MIN = 31
    SEVERITY_WEIGHTS = {
        "low": Decimal("10"), "medium": Decimal("20"),
        "high": Decimal("30"), "critical": Decimal("50"),
    }

    def __init__(self):
        self.fraud_engine = FraudEngine()
        self.ml_service = MLService()

    def assess_fraud_risk(
        self, session: Database, transaction_id: int,
        customer_id: Optional[int] = None,
        transaction_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        document = session["transactions"].find_one({"id": transaction_id})
        if not document:
            raise ValueError(f"Transaction {transaction_id} not found")
        transaction = Transaction.model_validate(from_bson(document))
        customer_id = customer_id or transaction.customer_id
        transaction_data = transaction_data or self._prepare_transaction_data(transaction)
        try:
            rule_score, _, triggered_rules = self.fraud_engine.evaluate_transaction(
                session, transaction
            )
            rule_score_value = float(rule_score)
            ml_score = self._get_ml_score(session, transaction_data)
            combined = self._calculate_combined_score(rule_score_value, ml_score)
            level = self.calculate_risk_level(combined)
            now = datetime.now(timezone.utc)
            assessment = FraudAssessment(
                transaction_id=transaction_id,
                risk_score=Decimal(str(round(combined, 2))),
                risk_category=level,
                rules_triggered_count=len(triggered_rules),
                ml_score=Decimal(str(round(ml_score / 100.0, 4))) if ml_score > 0 else None,
                ml_model_version="1.0", engine_version="1.0",
                assessment_timestamp=now,
                explanation=self._generate_explanation(
                    combined, rule_score_value, ml_score, level, triggered_rules
                ),
                assessment_metadata={
                    "rule_weight": self.RULE_WEIGHT,
                    "ml_weight": self.ML_WEIGHT,
                    "triggered_rule_count": len(triggered_rules),
                    "assessment_version": "1.0",
                },
            )
            assessment_data = assessment.model_dump(
                exclude={"id", "created_at", "updated_at"}
            )

            def persist_assessment(mongo_session):
                """Keep assessment and all its triggered-rule records atomic."""
                saved = insert_document(
                    session, "fraud_assessments", assessment_data,
                    session=mongo_session,
                )
                persisted_assessment = FraudAssessment.model_validate(saved)
                for rule in triggered_rules:
                    rule_id = self._rule_value(rule, "rule_id")
                    rule_name = self._rule_value(
                        rule, "rule_name", self._rule_value(rule, "name", "")
                    )
                    rule_explanation = self._rule_value(rule, "explanation", "")
                    rule_doc = session["fraud_rules"].find_one(
                        {"rule_id": rule_id}, session=mongo_session
                    )
                    insert_document(session, "triggered_rules", {
                        "assessment_id": persisted_assessment.id,
                        "transaction_id": transaction_id,
                        "rule_id": (rule_doc or {}).get("id", 0),
                        "triggered_rule_id": rule_id,
                        "triggered_rule_name": rule_name,
                        "trigger_timestamp": now,
                        "rule_explanation": rule_explanation,
                        "triggered_values": {},
                    }, session=mongo_session)
                return persisted_assessment

            # The original SQL workflow committed the assessment and its child
            # triggered-rule rows together. Keep the same boundary using an
            # Atlas-compatible replica-set transaction; no non-transactional
            # fallback is allowed in the application.
            with session.client.start_session() as mongo_session:
                assessment = mongo_session.with_transaction(persist_assessment)
            logger.info("Risk assessment complete: score=%s level=%s", combined, level)
            return {
                "assessment_id": assessment.id,
                "transaction_id": transaction_id,
                "customer_id": customer_id,
                "risk_score": float(combined),
                "risk_level": level,
                "rule_score": rule_score_value,
                "ml_score": float(ml_score),
                "triggered_rules": triggered_rules,
                "alert_required": self.should_create_alert(combined, level),
                "created_at": now,
            }
        except Exception:
            logger.exception("Error assessing fraud risk")
            raise

    def _prepare_transaction_data(self, transaction: Transaction) -> Dict[str, Any]:
        return {
            "transaction_id": transaction.transaction_id,
            "customer_id": transaction.customer_id,
            "amount": float(transaction.amount),
            "currency": transaction.currency,
            "merchant_name": transaction.merchant_name,
            "merchant_id": transaction.merchant_id,
            "merchant_category": transaction.merchant_category,
            "transaction_type": transaction.transaction_type,
            "payment_method": transaction.payment_method,
            "transaction_date": transaction.transaction_date,
            "country": transaction.location_country,
            "city": transaction.location_city,
            "status": transaction.status,
        }

    def _calculate_rule_score(self, rule_results: Dict[str, Any]) -> Tuple[float, List[Dict]]:
        rules = rule_results.get("triggered_rules", [])
        score = float(rule_results.get("rule_score", sum(
            self.SEVERITY_WEIGHTS.get(rule.get("severity", "low").lower(), Decimal("10"))
            for rule in rules
        )))
        return min(score, 100.0), [
            {"rule_id": rule.get("rule_id"), "name": rule.get("name"),
             "severity": rule.get("severity", "low").lower(),
             "explanation": rule.get("explanation", ""),
             "triggered_values": rule.get("triggered_values", {})}
            for rule in rules
        ]

    def _get_ml_score(self, session: Database, transaction_data: Dict[str, Any]) -> float:
        try:
            prediction = self.ml_service.predict_fraud(
                session=session, transaction_data=transaction_data
            )
            if not prediction:
                return 0.0
            score = prediction.get("ml_score")
            if score is None:
                score = prediction.get("fraud_probability", prediction.get("probability", 0))
                score = float(score) * 100
            return min(max(float(score), 0.0), 100.0)
        except Exception:
            logger.warning("ML prediction unavailable; using rule score only", exc_info=True)
            return 0.0

    def _calculate_combined_score(self, rule_score: float, ml_score: float) -> float:
        return min(max(rule_score * self.RULE_WEIGHT + ml_score * self.ML_WEIGHT, 0), 100)

    def calculate_risk_level(self, score: float) -> str:
        return "LOW" if score <= 30 else "MEDIUM" if score <= 70 else "HIGH"

    def should_create_alert(self, risk_score: float, risk_level: str) -> bool:
        return risk_score >= self.ALERT_THRESHOLD_MIN

    def _generate_explanation(
        self, combined_score: float, rule_score: float, ml_score: float,
        risk_level: str, triggered_rules: List[Any],
    ) -> str:
        lines = [
            "Risk Assessment Results:",
            f"- Combined Risk Score: {combined_score:.2f}/100 ({risk_level})",
            f"- Rule-Based Score: {rule_score:.2f}/100 ({self.RULE_WEIGHT*100:.0f}% weight)",
            f"- ML-Based Score: {ml_score:.2f}/100 ({self.ML_WEIGHT*100:.0f}% weight)",
        ]
        if triggered_rules:
            lines.append(f"- Triggered Rules ({len(triggered_rules)}):")
            lines.extend(
                f"  • {RiskEngine._rule_value(item, 'rule_name', RiskEngine._rule_value(item, 'name', ''))} "
                f"({RiskEngine._rule_value(item, 'rule_id', '')}): "
                f"{RiskEngine._rule_value(item, 'explanation', '')}"
                for item in triggered_rules
            )
        else:
            lines.append("- No fraud rules triggered")
        return "\n".join(lines)

    @staticmethod
    def _rule_value(rule: Any, key: str, default: Any = None) -> Any:
        """Read rule result fields from either the rule model or API-shaped mappings."""
        if isinstance(rule, dict):
            return rule.get(key, default)
        return getattr(rule, key, default)

    def get_assessment(self, session: Database, assessment_id: int) -> Optional[Dict[str, Any]]:
        document = session["fraud_assessments"].find_one({"id": assessment_id})
        if not document:
            return None
        assessment = FraudAssessment.model_validate(from_bson(document))
        rules = session["triggered_rules"].find(
            {"assessment_id": assessment_id}
        ).sort("trigger_timestamp", 1)
        triggered = []
        for raw in rules:
            rule = from_bson(raw)
            triggered.append({
                "rule_id": rule.get("triggered_rule_id") or rule.get("rule_id"),
                "rule_explanation": rule.get("rule_explanation", ""),
                "trigger_timestamp": rule.get("trigger_timestamp"),
                "triggered_values": rule.get("triggered_values") or {},
            })
        return {
            "assessment_id": assessment.id,
            "transaction_id": assessment.transaction_id,
            "risk_score": float(assessment.risk_score),
            "risk_category": assessment.risk_category,
            "rules_triggered_count": assessment.rules_triggered_count,
            "ml_score": float(assessment.ml_score) if assessment.ml_score is not None else None,
            "ml_model_version": assessment.ml_model_version,
            "engine_version": assessment.engine_version,
            "assessment_timestamp": assessment.assessment_timestamp,
            "explanation": assessment.explanation or "",
            "assessment_metadata": assessment.assessment_metadata or {},
            "triggered_rules": triggered,
        }

    def get_transaction_assessment(self, session: Database, transaction_id: int):
        document = session["fraud_assessments"].find_one({"transaction_id": transaction_id})
        return self.get_assessment(session, document["id"]) if document else None
