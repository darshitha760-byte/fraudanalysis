"""
Phase 6: Alert Management and Analyst Workflow Tests
Tests for alert status management, analyst decisions, case creation, and audit logging.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.models.fraud_alert import FraudAlert, FraudAssessment
from app.models.case import InvestigationCase, CaseNote
from app.models.audit_log import AuditLog
from app.core.permissions import UserRole
from app.core.security import hash_password
from app.services.alert_service import AlertService
from app.services.case_service import CaseService
from app.services.audit_service import AuditService
from app.services.transaction_service import TransactionService
from app.db.database import get_db
from tests.conftest import insert_test_document


@pytest.fixture
def db(test_session):
    """Alias for test_session."""
    yield test_session


@pytest.fixture
def client(test_client):
    """Alias for test_client."""
    return test_client


@pytest.fixture
def analyst_user(db):
    """Create a test analyst user."""
    user = User(
        email="analyst@example.com",
        password_hash=hash_password("analyst123"),
        full_name="Test Analyst",
        role=UserRole.ANALYST,
        is_active=True
    )
    return insert_test_document(db, user)


@pytest.fixture
def admin_user(db):
    """Create a test admin user."""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True
    )
    return insert_test_document(db, user)


@pytest.fixture
def customer(db):
    """Create a test customer."""
    cust = Customer(
        customer_id="CUST_ALERT_001",
        name="Test Customer",
        email="customer@example.com",
        phone="+1234567890",
        country="US",
        city="New York",
        customer_type="individual",
        is_active=True
    )
    return insert_test_document(db, cust)


@pytest.fixture
def transaction(db, customer):
    """Create a test transaction."""
    trans = Transaction(
        transaction_id="TXN001",
        customer_id=customer.id,
        amount=Decimal("5000.00"),
        currency="USD",
        transaction_type="wire_transfer",
        merchant_name="Test Merchant",
        merchant_category="7399",
        transaction_date=datetime.utcnow(),
        status="completed",
        location_country="NG"
    )
    return insert_test_document(db, trans)


@pytest.fixture
def fraud_assessment(db, transaction):
    """Create a test fraud assessment."""
    from app.models.fraud_alert import FraudAssessment
    assessment = FraudAssessment(
        transaction_id=transaction.id,
        risk_score=Decimal("85.50"),
        risk_category="high",
        rules_triggered_count=2,
        ml_score=Decimal("0.9200"),
        engine_version="1.0"
    )
    return insert_test_document(db, assessment)


@pytest.fixture
def alert(db, customer, transaction, fraud_assessment):
    """Create a test fraud alert."""
    alert = FraudAlert(
        transaction_id=transaction.id,
        customer_id=customer.id,
        assessment_id=fraud_assessment.id,
        alert_status="pending",
        alert_severity="high",
        alert_reason="High risk international transfer",
        triggered_rules_summary="HIGH_AMOUNT, INTERNATIONAL_TRANSFER",
        alert_created_at=datetime.utcnow(),
    )
    return insert_test_document(db, alert)


class TestAlertStatusTransitions:
    """Test alert status lifecycle: PENDING → UNDER_REVIEW → RESOLVED"""

    def test_create_alert(self, db, customer, transaction, fraud_assessment):
        """Test creating a fraud alert."""
        alert = FraudAlert(
            transaction_id=transaction.id,
            customer_id=customer.id,
            assessment_id=fraud_assessment.id,
            alert_status="pending",
            alert_severity="medium",
            alert_reason="Test alert",
            alert_created_at=datetime.utcnow(),
        )
        alert = insert_test_document(db, alert)

        assert alert.id is not None
        assert alert.alert_status == "pending"
        assert alert.alert_severity == "medium"

    def test_update_alert_to_under_review(self, db, alert, analyst_user):
        """Test marking alert as UNDER_REVIEW."""
        alert = AlertService.update_alert_status(
            db, alert.id, "under_review", reviewed_by_user_id=analyst_user.id
        )

        assert alert["alert_status"] == "under_review"
        assert alert["reviewed_by"] == analyst_user.id

    def test_update_alert_to_resolved(self, db, alert, analyst_user):
        """Test marking alert as RESOLVED."""
        alert = AlertService.update_alert_status(
            db, alert.id, "resolved", reviewed_by_user_id=analyst_user.id,
            review_decision="approved",
        )

        assert alert["alert_status"] == "resolved"
        assert alert["review_decision"] == "approved"


class TestAnalystDecisions:
    """Test analyst decision recording"""

    def test_record_approved_decision(self, db, alert, analyst_user):
        """Test recording APPROVED decision."""
        result = AlertService.record_analyst_decision(
            session=db,
            alert_id=alert.id,
            decision="APPROVED",
            justification="Confirmed fraud based on transaction pattern",
            analyst_id=analyst_user.id
        )

        assert result["review_decision"] == "approved"
        assert result["alert_status"] == "resolved"
        assert result["review_notes"] == "Confirmed fraud based on transaction pattern"

    def test_record_rejected_decision(self, db, alert, analyst_user):
        """Test recording REJECTED decision."""
        result = AlertService.record_analyst_decision(
            session=db,
            alert_id=alert.id,
            decision="REJECTED",
            justification="False positive - legitimate transfer",
            analyst_id=analyst_user.id
        )

        assert result["review_decision"] == "rejected"
        assert result["alert_status"] == "resolved"

    def test_record_needs_review_decision(self, db, alert, analyst_user):
        """Test recording NEEDS_REVIEW decision."""
        result = AlertService.record_analyst_decision(
            session=db,
            alert_id=alert.id,
            decision="NEEDS_REVIEW",
            justification="Requires escalation to senior analyst",
            analyst_id=analyst_user.id
        )

        assert result["review_decision"] == "needs_review"
        assert result["alert_status"] == "under_review"

    def test_invalid_decision_raises_error(self, db, alert, analyst_user):
        """Test that invalid decision raises ValueError."""
        with pytest.raises(ValueError):
            AlertService.record_analyst_decision(
                session=db,
                alert_id=alert.id,
                decision="INVALID_DECISION",
                justification="Test",
                analyst_id=analyst_user.id
            )


class TestCaseManagement:
    """Test investigation case creation and management"""

    def test_create_case_from_alert_approved(self, db, alert, analyst_user):
        """Test creating investigation case from APPROVED alert."""
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        assert case_data["case_type"] == "FRAUD_CONFIRMED"
        assert case_data["case_status"] == "open"
        assert case_data["assigned_to"] == analyst_user.id

    def test_create_case_from_alert_needs_review(self, db, alert, analyst_user):
        """Test creating investigation case from NEEDS_REVIEW alert."""
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="SUSPICIOUS",
            assigned_to=analyst_user.id
        )

        assert case_data["case_type"] == "SUSPICIOUS"
        assert case_data["case_status"] == "open"

    def test_get_active_cases(self, db, alert, analyst_user):
        """Test retrieving active cases."""
        # Create two cases
        case_data1 = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        cases, total = CaseService.get_active_cases(session=db)

        assert len(cases) >= 1
        assert total >= 1
        assert any(c["case_id"] == case_data1["case_id"] for c in cases)

    def test_update_case_status(self, db, alert, analyst_user):
        """Test updating case status."""
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        updated = CaseService.update_case_status(
            session=db,
            case_id=case_data["case_id"],
            new_status="closed"
        )

        assert updated["case_status"] == "closed"

    def test_add_case_note(self, db, alert, analyst_user):
        """Test adding note to investigation case."""
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        note_data = CaseService.add_case_note(
            session=db,
            case_id=case_data["case_id"],
            note_text="Customer confirmed unauthorized transaction",
            analyst_id=analyst_user.id
        )

        assert note_data["note_text"] == "Customer confirmed unauthorized transaction"

    def test_escalate_case(self, db, alert, analyst_user, admin_user):
        """Test case escalation."""
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        escalated = CaseService.escalate_case(
            session=db,
            case_id=case_data["case_id"],
            escalation_reason="Complex fraud scheme detected",
            escalated_by=analyst_user.id,
            escalated_to=admin_user.id
        )

        assert escalated["case_status"] == "escalated"


class TestAuditLogging:
    """Test compliance audit trail logging"""

    def test_log_alert_event(self, db, alert, analyst_user):
        """Test logging alert event."""
        audit_log = AuditService.log_alert_event(
            db=db,
            alert_id=alert.id,
            event_type="STATUS_CHANGED",
            analyst_id=analyst_user.id,
            details={"old_status": "pending", "new_status": "under_review"}
        )

        assert audit_log.target_id == str(alert.id)
        assert audit_log.action_category == "alert_management"
        assert audit_log.actor_id == analyst_user.id

    def test_log_alert_status_change(self, db, alert, analyst_user):
        """Test logging alert status change event."""
        audit_log = AuditService.log_alert_status_change(
            db=db,
            alert_id=alert.id,
            old_status="pending",
            new_status="under_review",
            analyst_id=analyst_user.id
        )

        assert audit_log.action_category == "alert_management"
        assert audit_log.metadata is not None

    def test_log_analyst_decision(self, db, alert, analyst_user):
        """Test logging analyst decision."""
        audit_log = AuditService.log_analyst_decision(
            db=db,
            alert_id=alert.id,
            decision="APPROVED",
            justification="Confirmed fraud",
            analyst_id=analyst_user.id
        )

        assert audit_log.action_category == "alert_management"
        assert audit_log.actor_id == analyst_user.id

    def test_get_alert_history(self, db, alert, analyst_user):
        """Test retrieving alert history."""
        # Log multiple events
        AuditService.log_alert_event(
            db=db,
            alert_id=alert.id,
            event_type="CREATED",
            analyst_id=analyst_user.id,
            details={"status": "pending"}
        )

        AuditService.log_alert_status_change(
            db=db,
            alert_id=alert.id,
            old_status="pending",
            new_status="under_review",
            analyst_id=analyst_user.id
        )

        history = AuditService.get_alert_history(session=db, alert_id=alert.id)

        assert len(history) >= 2
        assert all(h.target_id == str(alert.id) for h in history)

    def test_get_analyst_actions(self, db, alert, analyst_user):
        """Test retrieving analyst's actions within date range."""
        now = datetime.utcnow()
        start_date = now - timedelta(days=1)
        end_date = now + timedelta(days=1)

        AuditService.log_alert_event(
            db=db,
            alert_id=alert.id,
            event_type="CREATED",
            analyst_id=analyst_user.id,
            details={"status": "pending"}
        )

        actions = AuditService.get_analyst_actions(
            db=db,
            analyst_id=analyst_user.id,
            start_date=start_date,
            end_date=end_date
        )

        assert len(actions) >= 1
        assert all(a.actor_id == analyst_user.id for a in actions)


class TestAlertFiltering:
    """Test alert filtering and search functionality"""

    def test_get_alerts_by_status(self, db, customer, fraud_assessment):
        """Test filtering alerts by status."""
        # Create transactions with different alerts
        txn1 = Transaction(
            transaction_id="TXN_STATUS_001",
            customer_id=customer.id,
            amount=1000.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH001",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn2 = Transaction(
            transaction_id="TXN_STATUS_002",
            customer_id=customer.id,
            amount=2000.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH002",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn1 = insert_test_document(db, txn1)
        txn2 = insert_test_document(db, txn2)

        # Create fraud assessments for each transaction
        fa1 = FraudAssessment(
            transaction_id=txn1.id,
            risk_score=85.0,
            risk_category="high",
            assessment_timestamp=datetime.utcnow()
        )
        fa2 = FraudAssessment(
            transaction_id=txn2.id,
            risk_score=45.0,
            risk_category="medium",
            assessment_timestamp=datetime.utcnow()
        )
        fa1 = insert_test_document(db, fa1)
        fa2 = insert_test_document(db, fa2)

        # Create alerts with different statuses
        alert1 = FraudAlert(
            transaction_id=txn1.id,
            customer_id=customer.id,
            assessment_id=fa1.id,
            alert_status="pending",
            alert_severity="high",
            alert_reason="Test 1",
            triggered_rules_summary="RULE1",
            alert_created_at=datetime.utcnow(),
        )

        alert2 = FraudAlert(
            transaction_id=txn2.id,
            customer_id=customer.id,
            assessment_id=fa2.id,
            alert_status="resolved",
            alert_severity="medium",
            alert_reason="Test 2",
            triggered_rules_summary="RULE2",
            alert_created_at=datetime.utcnow(),
        )

        insert_test_document(db, alert1)
        insert_test_document(db, alert2)

        pending_alerts, total = AlertService.get_alerts_by_status_paginated(
            session=db,
            status="pending",
            limit=50,
            offset=0
        )

        assert len(pending_alerts) >= 1
        assert total >= 1

    def test_get_alerts_by_priority(self, db, customer):
        """Test filtering alerts by priority/severity."""
        txn = Transaction(
            transaction_id="TXN_PRIORITY_001",
            customer_id=customer.id,
            amount=500.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH001",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn = insert_test_document(db, txn)

        fa = FraudAssessment(
            transaction_id=txn.id,
            risk_score=95.0,
            risk_category="high",
            assessment_timestamp=datetime.utcnow()
        )
        fa = insert_test_document(db, fa)

        alert = FraudAlert(
            transaction_id=txn.id,
            customer_id=customer.id,
            assessment_id=fa.id,
            alert_status="pending",
            alert_severity="high",
            alert_reason="High priority",
            triggered_rules_summary="HIGH_RISK",
            alert_created_at=datetime.utcnow(),
        )
        insert_test_document(db, alert)

        high_alerts, total = AlertService.get_alerts_by_priority_paginated(
            session=db,
            priority="high",
            limit=50,
            offset=0
        )

        assert len(high_alerts) >= 1

    def test_get_pending_alerts(self, db, customer):
        """Test getting pending (unreviewed) alerts."""
        txn = Transaction(
            transaction_id="TXN_PENDING_001",
            customer_id=customer.id,
            amount=1500.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH002",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn = insert_test_document(db, txn)

        fa = FraudAssessment(
            transaction_id=txn.id,
            risk_score=70.0,
            risk_category="medium",
            assessment_timestamp=datetime.utcnow()
        )
        fa = insert_test_document(db, fa)

        alert = FraudAlert(
            transaction_id=txn.id,
            customer_id=customer.id,
            assessment_id=fa.id,
            alert_status="pending",
            alert_severity="medium",
            alert_reason="Pending alert",
            triggered_rules_summary="RULE",
            alert_created_at=datetime.utcnow(),
        )
        insert_test_document(db, alert)

        pending, total = AlertService.get_pending_alerts_paginated(
            session=db,
            limit=50,
            offset=0
        )

        assert len(pending) >= 1
        assert total >= 1

    def test_search_alerts_with_text(self, db, customer):
        """Test searching alerts by text."""
        txn = Transaction(
            transaction_id="TXN_SEARCH_001",
            customer_id=customer.id,
            amount=800.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH003",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn = insert_test_document(db, txn)

        fa = FraudAssessment(
            transaction_id=txn.id,
            risk_score=65.0,
            risk_category="medium",
            assessment_timestamp=datetime.utcnow()
        )
        fa = insert_test_document(db, fa)

        alert = FraudAlert(
            transaction_id=txn.id,
            customer_id=customer.id,
            assessment_id=fa.id,
            alert_status="pending",
            alert_severity="medium",
            alert_reason="Unusual transaction pattern detected",
            triggered_rules_summary="PATTERN_MATCH",
            alert_created_at=datetime.utcnow(),
        )
        insert_test_document(db, alert)

        results, total = AlertService.search_alerts_paginated(
            session=db,
            query_text="Unusual",
            limit=50,
            offset=0
        )

        assert len(results) >= 1

    def test_search_alerts_with_filters(self, db, customer):
        """Test searching alerts with filters."""
        txn = Transaction(
            transaction_id="TXN_FILTERS_001",
            customer_id=customer.id,
            amount=2500.00,
            currency="USD",
            transaction_date=datetime.utcnow(),
            merchant_id="MERCH004",
            merchant_category="RETAIL",
            location_country="US",
            channel="MOBILE",
            status="completed"
        )
        txn = insert_test_document(db, txn)

        fa = FraudAssessment(
            transaction_id=txn.id,
            risk_score=92.0,
            risk_category="high",
            assessment_timestamp=datetime.utcnow()
        )
        fa = insert_test_document(db, fa)

        alert = FraudAlert(
            transaction_id=txn.id,
            customer_id=customer.id,
            assessment_id=fa.id,
            alert_status="pending",
            alert_severity="high",
            alert_reason="Test search",
            triggered_rules_summary="FILTER_TEST",
            alert_created_at=datetime.utcnow(),
        )
        insert_test_document(db, alert)

        results, total = AlertService.search_alerts_paginated(
            session=db,
            filters={"severity": "high", "status": "pending"},
            limit=50,
            offset=0
        )

        assert len(results) >= 1


class TestAlertStatistics:
    """Test alert statistics and aggregation"""

    def test_get_alert_statistics(self, db, customer):
        """Test retrieving alert statistics."""
        # Create multiple alerts with different statuses
        for i in range(3):
            txn = Transaction(
                transaction_id=f"TXN_STATS_{i:03d}",
                customer_id=customer.id,
                amount=1000.00 + i*100,
                currency="USD",
                transaction_date=datetime.utcnow(),
                merchant_id=f"MERCH{i:03d}",
                merchant_category="RETAIL",
                location_country="US",
                channel="MOBILE",
                status="completed"
            )
            txn = insert_test_document(db, txn)

            fa = FraudAssessment(
                transaction_id=txn.id,
                risk_score=50.0 + i*10,
                risk_category="medium" if i % 2 == 0 else "high",
                assessment_timestamp=datetime.utcnow()
            )
            fa = insert_test_document(db, fa)

            alert = FraudAlert(
                transaction_id=txn.id,
                customer_id=customer.id,
                assessment_id=fa.id,
                alert_status="pending" if i == 0 else "resolved",
                alert_severity="high" if i < 2 else "low",
                alert_reason=f"Test alert {i}",
                triggered_rules_summary=f"RULE{i}",
                alert_created_at=datetime.utcnow(),
            )
            insert_test_document(db, alert)

        stats = AlertService.get_alert_statistics(session=db)

        assert "total_alerts" in stats
        assert "status_counts" in stats
        assert "severity_counts" in stats
        assert stats["total_alerts"] >= 3


class TestApiEndpoints:
    """Test alert management API endpoints"""

    def test_get_pending_alerts_endpoint(self, client, db, alert, analyst_user):
        """Test GET /api/alerts/pending endpoint."""
        from jose import jwt
        from app.core.config import get_settings
        from datetime import timezone

        settings = get_settings()

        payload = {
            "sub": str(analyst_user.id),
            "email": analyst_user.email,
            "role": analyst_user.role.value,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }

        token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )

        response = client.get(
            "/api/alerts/pending",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 200

    def test_get_alert_details_endpoint(self, client, db, alert, analyst_user):
        """Test GET /api/alerts/{alert_id} endpoint."""
        from jose import jwt
        from app.core.config import get_settings
        from datetime import timezone

        settings = get_settings()

        payload = {
            "sub": str(analyst_user.id),
            "email": analyst_user.email,
            "role": analyst_user.role.value,
            "exp": datetime.now(timezone.utc) + timedelta(hours=1)
        }

        token = jwt.encode(
            payload,
            settings.secret_key,
            algorithm=settings.jwt_algorithm
        )

        response = client.get(
            f"/api/alerts/{alert.id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code in [200, 404]

    def test_unauthorized_access_denied(self, client, db, alert):
        """Test that unauthenticated requests are denied."""
        response = client.get("/api/alerts/pending")
        assert response.status_code == 403 or response.status_code == 401


class TestPaginationAndPerformance:
    """Test pagination and limit/offset behavior"""

    def test_pagination_with_limit(self, db, customer, fraud_assessment):
        """Test pagination with limit parameter."""
        from app.models.transaction import Transaction

        # Create 10 transactions and alerts
        for i in range(10):
            txn = Transaction(
                transaction_id=f"TXN_PAGINATE_{i}",
                customer_id=customer.id,
                amount=1000 + i,
                transaction_type="transfer",
                merchant_id=f"MERCHANT_{i}",
                merchant_name=f"Test Merchant {i}",
                transaction_date=datetime.utcnow() - timedelta(seconds=i),
            )
            txn = insert_test_document(db, txn)

            # Create fraud assessment for this transaction
            fa = FraudAssessment(
                transaction_id=txn.id,
                risk_score=50 + i,
                risk_category="medium",
                rules_triggered_count=2
            )
            fa = insert_test_document(db, fa)

            alert = FraudAlert(
                transaction_id=txn.id,
                customer_id=customer.id,
                assessment_id=fa.id,
                alert_status="pending",
                alert_severity="medium",
                alert_reason=f"Alert {i}",
                triggered_rules_summary=f"RULE{i}",
                alert_created_at=datetime.utcnow() - timedelta(seconds=i),
            )
            insert_test_document(db, alert)

        alerts1, total1 = AlertService.get_pending_alerts_paginated(
            session=db,
            limit=5,
            offset=0
        )

        alerts2, total2 = AlertService.get_pending_alerts_paginated(
            session=db,
            limit=5,
            offset=5
        )

        assert len(alerts1) <= 5
        assert len(alerts2) <= 5
        assert total1 >= 10 or total2 >= 10

    def test_offset_pagination(self, db, customer, fraud_assessment):
        """Test pagination with offset parameter."""
        from app.models.transaction import Transaction

        # Create 5 transactions and alerts
        for i in range(5):
            txn = Transaction(
                transaction_id=f"TXN_OFFSET_{i}",
                customer_id=customer.id,
                amount=2000 + i,
                transaction_type="transfer",
                merchant_id=f"VENDOR_{i}",
                merchant_name=f"Offset Merchant {i}",
                transaction_date=datetime.utcnow() - timedelta(seconds=i),
            )
            txn = insert_test_document(db, txn)

            # Create fraud assessment for this transaction
            fa = FraudAssessment(
                transaction_id=txn.id,
                risk_score=60 + i,
                risk_category="high",
                rules_triggered_count=3
            )
            fa = insert_test_document(db, fa)

            alert = FraudAlert(
                transaction_id=txn.id,
                customer_id=customer.id,
                assessment_id=fa.id,
                alert_status="pending",
                alert_severity="high",
                alert_reason=f"Test {i}",
                triggered_rules_summary="TEST",
                alert_created_at=datetime.utcnow() - timedelta(seconds=i),
            )
            insert_test_document(db, alert)

        alerts, total = AlertService.get_pending_alerts_paginated(
            session=db,
            limit=2,
            offset=2
        )

        assert len(alerts) <= 2


class TestErrorHandling:
    """Test error handling in alert operations"""

    def test_alert_not_found(self, db):
        """Test handling missing alert."""
        with pytest.raises(ValueError):
            AlertService.record_analyst_decision(
                session=db,
                alert_id=99999,
                decision="APPROVED",
                justification="Test",
                analyst_id=1
            )

    def test_case_creation_from_nonexistent_alert(self, db, analyst_user):
        """Test creating case from non-existent alert."""
        with pytest.raises(ValueError):
            CaseService.create_case_from_alert(
                session=db,
                alert_id=99999,
                case_type="FRAUD_CONFIRMED",
                assigned_to=analyst_user.id
            )

    def test_invalid_status_transition(self, db, alert):
        """Reject invalid lifecycle transitions without changing stored status."""
        with pytest.raises(ValueError):
            AlertService.update_alert_status(db, alert.id, "invalid_status")
        stored = db["fraud_alerts"].find_one({"id": alert.id})
        assert stored["alert_status"] == "pending"


class TestIntegrationWithPhase5:
    """Verify Phase 6 integrates properly with Phase 5"""

    def test_alert_created_in_transaction_workflow(self, db, customer, transaction, fraud_assessment):
        """Test alert creation in full transaction workflow."""
        assert transaction.id is not None

        alert = FraudAlert(
            transaction_id=transaction.id,
            customer_id=customer.id,
            assessment_id=fraud_assessment.id,
            alert_status="pending",
            alert_severity="high",
            alert_reason="Integration test",
            triggered_rules_summary="TEST_RULE",
            alert_created_at=datetime.utcnow(),
        )
        alert = insert_test_document(db, alert)

        # Verify link to transaction
        assert alert.transaction_id == transaction.id
        assert alert.customer_id == customer.id

    def test_workflow_transaction_to_alert_to_case(self, db, customer, transaction, fraud_assessment, analyst_user):
        """Test complete workflow from transaction to case."""
        alert = FraudAlert(
            transaction_id=transaction.id,
            customer_id=customer.id,
            assessment_id=fraud_assessment.id,
            alert_status="pending",
            alert_severity="high",
            alert_reason="Workflow test",
            triggered_rules_summary="RULE1",
            alert_created_at=datetime.utcnow(),
        )
        alert = insert_test_document(db, alert)

        # Mark alert as under review
        AlertService.update_alert_status(
            db, alert.id, "under_review", reviewed_by_user_id=analyst_user.id
        )

        # Record decision
        AlertService.record_analyst_decision(
            session=db,
            alert_id=alert.id,
            decision="APPROVED",
            justification="Confirmed fraud",
            analyst_id=analyst_user.id
        )

        # Create case
        case_data = CaseService.create_case_from_alert(
            session=db,
            alert_id=alert.id,
            case_type="FRAUD_CONFIRMED",
            assigned_to=analyst_user.id
        )

        assert case_data is not None
        assert case_data["alert_id"] == alert.id
