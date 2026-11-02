"""
Fraud detection rules engine.
Implements 10 fraud detection rules with configurable thresholds.
"""

import logging
from decimal import Decimal
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pymongo.database import Database

from app.db.database import from_bson, to_bson
from app.models.transaction import Transaction
from app.models.fraud_rule import FraudRule
from app.models.customer import Customer

logger = logging.getLogger(__name__)


class RuleResult:
    """Result of a single rule evaluation."""
    
    def __init__(
        self,
        rule_id: str,
        rule_name: str,
        triggered: bool,
        severity: str,
        risk_weight: Decimal,
        explanation: str = ""
    ):
        self.rule_id = rule_id
        self.rule_name = rule_name
        self.triggered = triggered
        self.severity = severity
        self.risk_weight = risk_weight
        self.explanation = explanation


class FraudEngine:
    """Fraud detection rules engine."""
    
    # Default rule configurations
    DEFAULT_RULES = {
        "R01": {
            "name": "High-Value Transaction",
            "description": "Transaction amount exceeds threshold",
            "rule_type": "high_value",
            "threshold_value": Decimal("5000.00"),
            "threshold_unit": "amount",
            "severity": "high",
            "risk_weight": Decimal("25"),
        },
        "R02": {
            "name": "Rapid Transactions",
            "description": "Multiple transactions within short time window",
            "rule_type": "velocity",
            "threshold_value": Decimal("3"),
            "threshold_unit": "count",
            "threshold_config": {"time_window_minutes": 10},
            "severity": "high",
            "risk_weight": Decimal("20"),
        },
        "R03": {
            "name": "Geographic Anomaly",
            "description": "Transaction from unexpected country",
            "rule_type": "geographic",
            "threshold_value": None,
            "severity": "medium",
            "risk_weight": Decimal("15"),
        },
        "R04": {
            "name": "Duplicate Transaction",
            "description": "Same merchant, amount within time window",
            "rule_type": "duplicate",
            "threshold_value": Decimal("5"),
            "threshold_unit": "minutes",
            "severity": "medium",
            "risk_weight": Decimal("15"),
        },
        "R05": {
            "name": "Late-Night Transaction",
            "description": "Transaction during unusual hours (2-5 AM)",
            "rule_type": "time_anomaly",
            "threshold_value": None,
            "severity": "low",
            "risk_weight": Decimal("8"),
        },
        "R06": {
            "name": "Unusual Merchant Category",
            "description": "Merchant category unusual for this customer",
            "rule_type": "merchant_anomaly",
            "threshold_value": None,
            "severity": "low",
            "risk_weight": Decimal("10"),
        },
        "R07": {
            "name": "High Transaction Count",
            "description": "More than threshold transactions in 24 hours",
            "rule_type": "velocity",
            "threshold_value": Decimal("20"),
            "threshold_unit": "count",
            "threshold_config": {"time_window_hours": 24},
            "severity": "medium",
            "risk_weight": Decimal("15"),
        },
        "R08": {
            "name": "Amount Deviation",
            "description": "Transaction amount significantly exceeds customer average",
            "rule_type": "amount_anomaly",
            "threshold_value": Decimal("3"),
            "threshold_unit": "multiplier",
            "severity": "medium",
            "risk_weight": Decimal("12"),
        },
        "R09": {
            "name": "Blocked Merchant Category",
            "description": "Merchant category is on blocked list",
            "rule_type": "merchant_blocked",
            "threshold_value": None,
            "severity": "critical",
            "risk_weight": Decimal("30"),
        },
        "R10": {
            "name": "New Customer High-Value",
            "description": "New customer making high-value transaction",
            "rule_type": "new_customer_risk",
            "threshold_value": Decimal("2000.00"),
            "threshold_unit": "amount",
            "threshold_config": {"days_threshold": 7},
            "severity": "high",
            "risk_weight": Decimal("20"),
        },
    }
    
    BLOCKED_MERCHANT_CATEGORIES = {"gambling", "adult_content", "cryptocurrency"}
    
    @staticmethod
    def evaluate_transaction(
        db: Database,
        transaction: Transaction
    ) -> Tuple[Decimal, str, List[RuleResult]]:
        """
        Evaluate transaction against all enabled rules.
        
        Args:
            db: Database session
            transaction: Transaction to evaluate
            
        Returns:
            Tuple of (risk_score, risk_level, triggered_rules)
        """
        triggered_rules = []
        total_risk_weight = Decimal("0")
        
        # Get all enabled rules
        rules = [FraudRule.model_validate(from_bson(doc))
                 for doc in db["fraud_rules"].find({"is_enabled": True})]
        
        # Create rule lookup for quick access
        rule_map = {rule.rule_id: rule for rule in rules}
        
        # Evaluate each rule
        rule_results = [
            FraudEngine._evaluate_r01(db, transaction, rule_map.get("R01")),
            FraudEngine._evaluate_r02(db, transaction, rule_map.get("R02")),
            FraudEngine._evaluate_r03(db, transaction, rule_map.get("R03")),
            FraudEngine._evaluate_r04(db, transaction, rule_map.get("R04")),
            FraudEngine._evaluate_r05(db, transaction, rule_map.get("R05")),
            FraudEngine._evaluate_r06(db, transaction, rule_map.get("R06")),
            FraudEngine._evaluate_r07(db, transaction, rule_map.get("R07")),
            FraudEngine._evaluate_r08(db, transaction, rule_map.get("R08")),
            FraudEngine._evaluate_r09(db, transaction, rule_map.get("R09")),
            FraudEngine._evaluate_r10(db, transaction, rule_map.get("R10")),
        ]
        
        # Aggregate results
        for result in rule_results:
            if result and result.triggered:
                triggered_rules.append(result)
                total_risk_weight += result.risk_weight
        
        # Calculate risk score (0-100)
        risk_score = min(Decimal("100"), total_risk_weight)
        
        # Determine risk level
        if risk_score >= Decimal("70"):
            risk_level = "high"
        elif risk_score >= Decimal("40"):
            risk_level = "medium"
        else:
            risk_level = "low"
        
        return risk_score, risk_level, triggered_rules
    
    @staticmethod
    def _evaluate_r01(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R01: High-value transaction (> threshold)."""
        threshold = Decimal("5000.00")
        if rule and rule.threshold_value:
            threshold = rule.threshold_value
        
        triggered = transaction.amount > threshold
        
        return RuleResult(
            rule_id="R01",
            rule_name="High-Value Transaction",
            triggered=triggered,
            severity=rule.severity if rule else "high",
            risk_weight=rule.risk_weight if rule else Decimal("25"),
            explanation=f"Transaction amount {transaction.amount} exceeds threshold {threshold}"
            if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r02(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R02: Rapid transactions (>3 within 10 mins)."""
        time_window = 10
        count_threshold = 4  # >3 means 4 or more
        
        if rule and rule.threshold_config:
            time_window = rule.threshold_config.get("time_window_minutes", 10)
        if rule and rule.threshold_value:
            count_threshold = int(rule.threshold_value)
        
        cutoff_time = transaction.transaction_date - timedelta(minutes=time_window)
        
        recent_count = db["transactions"].count_documents({
            "customer_id": transaction.customer_id,
            "transaction_date": {"$gte": cutoff_time, "$lte": transaction.transaction_date},
            "status": "completed",
        })
        
        triggered = recent_count > 3  # >3 means strictly greater than 3
        
        return RuleResult(
            rule_id="R02",
            rule_name="Rapid Transactions",
            triggered=triggered,
            severity=rule.severity if rule else "high",
            risk_weight=rule.risk_weight if rule else Decimal("20"),
            explanation=f"Found {recent_count} transactions in {time_window} minutes"
            if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r03(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R03: Geographic anomaly."""
        # Check if transaction location differs from customer's usual location
        customer_doc = db["customers"].find_one({"id": transaction.customer_id})
        customer = (
            Customer.model_validate(from_bson(customer_doc))
            if customer_doc else None
        )
        if not transaction.location_country or not customer:
            return RuleResult(
                rule_id="R03",
                rule_name="Geographic Anomaly",
                triggered=False,
                severity=rule.severity if rule else "medium",
                risk_weight=rule.risk_weight if rule else Decimal("15"),
                explanation="Missing location or customer data"
            )
        
        triggered = False
        explanation = ""
        
        # Check if location differs from customer's country
        if customer.country and transaction.location_country != customer.country:
            # Only flag if customer has a registered country
            triggered = True
            explanation = f"Transaction in {transaction.location_country}, customer from {customer.country}"
        
        return RuleResult(
            rule_id="R03",
            rule_name="Geographic Anomaly",
            triggered=triggered,
            severity=rule.severity if rule else "medium",
            risk_weight=rule.risk_weight if rule else Decimal("15"),
            explanation=explanation
        )
    
    @staticmethod
    def _evaluate_r04(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R04: Duplicate transaction (same merchant, amount within time window)."""
        time_window = 5
        if rule and rule.threshold_value:
            time_window = int(rule.threshold_value)
        
        cutoff_time = transaction.transaction_date - timedelta(minutes=time_window)
        
        duplicate = db["transactions"].find_one({
            "customer_id": transaction.customer_id,
            "amount": to_bson(transaction.amount),
            "merchant_id": transaction.merchant_id,
            "transaction_date": {"$gte": cutoff_time, "$lt": transaction.transaction_date},
            "status": "completed",
        })
        
        triggered = duplicate is not None
        
        return RuleResult(
            rule_id="R04",
            rule_name="Duplicate Transaction",
            triggered=triggered,
            severity=rule.severity if rule else "medium",
            risk_weight=rule.risk_weight if rule else Decimal("15"),
            explanation=f"Duplicate found {time_window} minutes ago" if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r05(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R05: Late-night transaction (2-5 AM)."""
        hour = transaction.transaction_date.hour
        triggered = 2 <= hour < 5
        
        return RuleResult(
            rule_id="R05",
            rule_name="Late-Night Transaction",
            triggered=triggered,
            severity=rule.severity if rule else "low",
            risk_weight=rule.risk_weight if rule else Decimal("8"),
            explanation=f"Transaction at {hour}:00 (unusual hours)" if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r06(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R06: Unusual merchant category for customer."""
        if not transaction.merchant_category or not db["customers"].find_one({"id": transaction.customer_id}):
            return RuleResult(
                rule_id="R06",
                rule_name="Unusual Merchant Category",
                triggered=False,
                severity=rule.severity if rule else "low",
                risk_weight=rule.risk_weight if rule else Decimal("10"),
                explanation="Missing merchant category or customer data"
            )
        
        # Check if this is a new merchant category for customer
        prev_transaction = db["transactions"].find_one({
            "customer_id": transaction.customer_id,
            "merchant_category": transaction.merchant_category,
            "transaction_date": {"$lt": transaction.transaction_date},
            "status": "completed",
        })
        
        triggered = prev_transaction is None
        
        return RuleResult(
            rule_id="R06",
            rule_name="Unusual Merchant Category",
            triggered=triggered,
            severity=rule.severity if rule else "low",
            risk_weight=rule.risk_weight if rule else Decimal("10"),
            explanation=f"First {transaction.merchant_category} transaction"
            if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r07(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R07: High transaction count in 24 hours (>20)."""
        count_threshold = 20
        if rule and rule.threshold_value:
            count_threshold = int(rule.threshold_value)
        
        cutoff_time = transaction.transaction_date - timedelta(hours=24)
        
        transaction_count = db["transactions"].count_documents({
            "customer_id": transaction.customer_id,
            "transaction_date": {"$gte": cutoff_time, "$lte": transaction.transaction_date},
            "status": "completed",
        })
        
        triggered = transaction_count > count_threshold
        
        return RuleResult(
            rule_id="R07",
            rule_name="High Transaction Count",
            triggered=triggered,
            severity=rule.severity if rule else "medium",
            risk_weight=rule.risk_weight if rule else Decimal("15"),
            explanation=f"Found {transaction_count} transactions in 24 hours"
            if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r08(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R08: Amount deviation from customer average (>3x)."""
        deviation_multiplier = Decimal("3")
        if rule and rule.threshold_value:
            deviation_multiplier = rule.threshold_value
        
        # Calculate customer's average transaction amount (excluding this one)
        averages = list(db["transactions"].aggregate([
            {"$match": {"customer_id": transaction.customer_id,
                        "status": "completed", "id": {"$ne": transaction.id}}},
            {"$group": {"_id": None, "average": {"$avg": "$amount"}}},
        ]))
        avg_result = averages[0]["average"] if averages else None
        if hasattr(avg_result, "to_decimal"):
            avg_result = avg_result.to_decimal()
        
        if not avg_result or avg_result == 0:
            return RuleResult(
                rule_id="R08",
                rule_name="Amount Deviation",
                triggered=False,
                severity=rule.severity if rule else "medium",
                risk_weight=rule.risk_weight if rule else Decimal("12"),
                explanation="Insufficient transaction history"
            )
        
        avg_amount = Decimal(str(avg_result))
        triggered = transaction.amount > (avg_amount * deviation_multiplier)
        
        return RuleResult(
            rule_id="R08",
            rule_name="Amount Deviation",
            triggered=triggered,
            severity=rule.severity if rule else "medium",
            risk_weight=rule.risk_weight if rule else Decimal("12"),
            explanation=f"Amount {transaction.amount} > {deviation_multiplier}x average ({avg_amount})"
            if triggered else ""
        )
    
    @staticmethod
    def _evaluate_r09(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R09: Blocked merchant category."""
        triggered = False
        explanation = ""
        
        if transaction.merchant_category:
            if transaction.merchant_category.lower() in FraudEngine.BLOCKED_MERCHANT_CATEGORIES:
                triggered = True
                explanation = f"Merchant category '{transaction.merchant_category}' is blocked"
        
        return RuleResult(
            rule_id="R09",
            rule_name="Blocked Merchant Category",
            triggered=triggered,
            severity=rule.severity if rule else "critical",
            risk_weight=rule.risk_weight if rule else Decimal("30"),
            explanation=explanation
        )
    
    @staticmethod
    def _evaluate_r10(
        db: Database,
        transaction: Transaction,
        rule: Optional[FraudRule]
    ) -> RuleResult:
        """R10: New customer high-value transaction."""
        threshold_amount = Decimal("2000.00")
        days_threshold = 7
        
        if rule:
            if rule.threshold_value:
                threshold_amount = rule.threshold_value
            if rule.threshold_config:
                days_threshold = rule.threshold_config.get("days_threshold", 7)
        
        customer_doc = db["customers"].find_one({"id": transaction.customer_id})
        if not customer_doc:
            return RuleResult(
                rule_id="R10",
                rule_name="New Customer High-Value",
                triggered=False,
                severity=rule.severity if rule else "high",
                risk_weight=rule.risk_weight if rule else Decimal("20"),
                explanation="Customer not found"
            )
        
        customer = Customer.model_validate(from_bson(customer_doc))
        customer_age = (datetime.now(customer.created_at.tzinfo) - customer.created_at).days
        
        triggered = (
            customer_age < days_threshold and
            transaction.amount > threshold_amount
        )
        
        return RuleResult(
            rule_id="R10",
            rule_name="New Customer High-Value",
            triggered=triggered,
            severity=rule.severity if rule else "high",
            risk_weight=rule.risk_weight if rule else Decimal("20"),
            explanation=f"New customer ({customer_age} days) with amount {transaction.amount}"
            if triggered else ""
        )
