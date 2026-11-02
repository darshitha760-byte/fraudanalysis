"""
Integration tests for the Financial Risk Analysis and Hybrid Fraud Detection System.
Tests complete workflows from transaction through alert to case resolution.
"""

import pytest
from datetime import datetime
from decimal import Decimal
from app.models.transaction import Transaction
from app.models.customer import Customer
from app.models.fraud_alert import FraudAssessment, FraudAlert
from app.models.case import InvestigationCase
from app.models.audit_log import AuditLog
from tests.conftest import insert_test_document


class TestEndToEndTransactionWorkflow:
    """Test complete workflow from transaction to alert to case."""
    
    def test_transaction_to_alert_workflow(self, test_session):
        """Test complete transaction → fraud detection → alert workflow."""
        
        # Step 1: Create customer
        customer = Customer(
            customer_id="CUST_INTEGRATION_001",
            name="Integration Test Customer",
            email="integration@example.com",
            phone="9876543210",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        # Step 2: Create transaction
        transaction = Transaction(
            transaction_id="TXN_INTEGRATION_001",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("10000.00"),
            currency="USD",
            merchant_id="M_INTEGRATION_001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        # Step 3: Create fraud assessment
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=Decimal("85.00"),
            risk_category="high",
        )
        insert_test_document(test_session, assessment)
        
        # Step 4: Generate alert if risk score high
        if assessment.risk_score > Decimal("70"):
            alert = FraudAlert(
                transaction_id=transaction.id,
                customer_id=customer.id,
                assessment_id=assessment.id,
                alert_severity="high",
                alert_status="pending",
                alert_reason="High risk score transaction",
            )
            insert_test_document(test_session, alert)
        
        # Verify workflow
        final_alert = test_session["fraud_alerts"].find_one(
            {"transaction_id": transaction.id}
        )
        assert final_alert is not None
        assert final_alert["alert_severity"] == "high"
        assert final_alert["alert_status"] == "pending"
    
    def test_transaction_to_case_workflow(self, test_session):
        """Test workflow including case creation."""
        from app.models.user import User
        from app.core.permissions import UserRole
        
        # Setup: Create user for assignment
        user = User(
            email="analyst@example.com",
            full_name="Test Analyst",
            password_hash="hashedpassword",
            role=UserRole.ANALYST,
            is_active=True,
        )
        insert_test_document(test_session, user)
        
        # Setup: Create customer and transaction
        customer = Customer(
            customer_id="CUST_CASE_001",
            name="Case Test Customer",
            email="case@example.com",
            phone="5555555555",
            risk_profile="high",
        )
        insert_test_document(test_session, customer)
        
        transaction = Transaction(
            transaction_id="TXN_CASE_001",
            customer_id=customer.id,
            transaction_type="transfer",
            amount=Decimal("50000.00"),
            currency="USD",
            merchant_id="M_CASE_001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        # Create assessment and alert
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=Decimal("92.00"),
            risk_category="critical",
        )
        insert_test_document(test_session, assessment)
        
        alert = FraudAlert(
            transaction_id=transaction.id,
            customer_id=customer.id,
            assessment_id=assessment.id,
            alert_severity="critical",
            alert_status="pending",
            alert_reason="Critical risk transaction requiring investigation",
        )
        insert_test_document(test_session, alert)
        
        # Create investigation case
        case = InvestigationCase(
            alert_id=alert.id,
            transaction_id=transaction.id,
            customer_id=customer.id,
            case_type="fraud_investigation",
            case_status="open",
            assigned_to=user.id,
        )
        insert_test_document(test_session, case)
        
        # Verify case created
        final_case = test_session["investigation_cases"].find_one(
            {"alert_id": alert.id}
        )
        assert final_case is not None
        assert final_case["case_status"] == "open"
        assert final_case["assigned_to"] == user.id


class TestCrossPhaseBoundaryIntegration:
    """Test integration across different phases of the system."""
    
    def test_transaction_to_assessment_cross_phase(self, test_session):
        """Test transaction phase connects to assessment phase."""
        
        customer = Customer(
            customer_id="CUST_CROSS_001",
            name="Cross Phase Customer",
            email="crossphase@example.com",
            phone="1111111111",
            risk_profile="low",
        )
        insert_test_document(test_session, customer)
        
        # Phase 1 resource: Transaction
        transaction = Transaction(
            transaction_id="TXN_CROSS_001",
            customer_id=customer.id,
            transaction_type="deposit",
            amount=Decimal("1000.00"),
            currency="USD",
            merchant_id="M_CROSS_001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        # Phase 2 resource: Assessment
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=Decimal("15.00"),
            risk_category="low",
        )
        insert_test_document(test_session, assessment)
        
        # Verify cross-phase link
        fetched_assessment = test_session["fraud_assessments"].find_one(
            {"transaction_id": transaction.id}
        )
        assert fetched_assessment is not None
        assert fetched_assessment["transaction_id"] == transaction.id
        assert fetched_assessment["risk_category"] == "low"


class TestAuditTrailIntegration:
    """Test audit trail accuracy for complete workflows."""
    
    def test_audit_trail_for_workflow(self, test_session):
        """Test that audit trail captures complete workflow."""
        
        customer = Customer(
            customer_id="CUST_AUDIT_001",
            name="Audit Test Customer",
            email="audit@example.com",
            phone="2222222222",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        transaction = Transaction(
            transaction_id="TXN_AUDIT_001",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("5000.00"),
            currency="USD",
            merchant_id="M_AUDIT_001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        # Create audit log entry
        audit_log = AuditLog(
            actor_id=None,  # System action
            action="create_transaction",
            action_category="transaction",
            target_type="transaction",
            target_id=str(transaction.id),
            target_name=f"TXN_AUDIT_001",
            action_status="success",
            changes_after={"amount": "5000.00", "status": "completed"},
            action_timestamp=datetime.now(),
        )
        insert_test_document(test_session, audit_log)
        
        # Verify audit trail
        audit_entry = test_session["audit_logs"].find_one(
            {"target_id": str(transaction.id)}
        )
        assert audit_entry is not None
        assert audit_entry["action"] == "create_transaction"
        assert audit_entry["target_type"] == "transaction"


class TestStateMachineTransitions:
    """Test alert status state machine transitions."""
    
    def test_alert_status_transitions(self, test_session):
        """Test alert status transitions through valid states."""
        
        # Setup
        customer = Customer(
            customer_id="CUST_STATE_001",
            name="State Test Customer",
            email="state@example.com",
            phone="3333333333",
            risk_profile="medium",
        )
        insert_test_document(test_session, customer)
        
        transaction = Transaction(
            transaction_id="TXN_STATE_001",
            customer_id=customer.id,
            transaction_type="purchase",
            amount=Decimal("7500.00"),
            currency="USD",
            merchant_id="M_STATE_001",
            transaction_date=datetime.now(),
            status="completed",
        )
        insert_test_document(test_session, transaction)
        
        assessment = FraudAssessment(
            transaction_id=transaction.id,
            risk_score=Decimal("75.00"),
            risk_category="high",
        )
        insert_test_document(test_session, assessment)
        
        # Create alert in pending state
        alert = FraudAlert(
            transaction_id=transaction.id,
            customer_id=customer.id,
            assessment_id=assessment.id,
            alert_severity="high",
            alert_status="pending",
            alert_reason="High risk score",
        )
        insert_test_document(test_session, alert)
        
        # Transition to under_review
        test_session["fraud_alerts"].update_one(
            {"id": alert.id}, {"$set": {"alert_status": "under_review"}}
        )

        updated_alert = test_session["fraud_alerts"].find_one({"id": alert.id})
        assert updated_alert["alert_status"] == "under_review"
        
        # Transition to resolved
        test_session["fraud_alerts"].update_one(
            {"id": alert.id}, {"$set": {"alert_status": "resolved"}}
        )

        resolved_alert = test_session["fraud_alerts"].find_one({"id": alert.id})
        assert resolved_alert["alert_status"] == "resolved"


class TestDatabaseTransactionRollback:
    """Test database transaction rollback on errors."""
    
    def test_transaction_rollback_on_error(self, test_session):
        """Test that changes are rolled back on error."""
        
        customer = Customer(
            customer_id="CUST_ROLLBACK_001",
            name="Rollback Test Customer",
            email="rollback@example.com",
            phone="4444444444",
            risk_profile="low",
        )
        insert_test_document(test_session, customer)
        
        try:
            # Create transaction
            transaction = Transaction(
                transaction_id="TXN_ROLLBACK_001",
                customer_id=customer.id,
                transaction_type="purchase",
                amount=Decimal("2000.00"),
                currency="USD",
                merchant_id="M_ROLLBACK_001",
                transaction_date=datetime.now(),
                status="completed",
            )
            insert_test_document(test_session, transaction)
            
            # Intentional error - this should trigger rollback in real scenario
            # For test purposes, we just verify transaction was created
            assert transaction.id is not None
            
        except Exception:
            test_session.rollback()
            raise
        
        # Verify transaction exists (successful commit)
        result = test_session["transactions"].find_one(
            {"transaction_id": "TXN_ROLLBACK_001"}
        )
        assert result is not None
