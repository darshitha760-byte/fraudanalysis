from datetime import datetime

from app.core.security import create_access_token
from app.models import Customer, FraudAssessment, FraudRule, Transaction, TriggeredRule, User
from tests.conftest import insert_test_document


def test_detail_includes_persisted_assessment_and_triggered_rule(test_client, test_session):
    user = User(email="details@example.com", full_name="Details Test", role="analyst",
                password_hash="unused-token-test", is_active=True)
    customer = Customer(customer_id="DETAIL-CUSTOMER", name="Details Customer")
    rule = FraudRule(rule_id="DETAIL-RULE", name="Large payment",
                     description="Review large payments", rule_type="high_value",
                     severity="high", risk_weight=80)
    insert_test_document(test_session, user)
    insert_test_document(test_session, customer)
    insert_test_document(test_session, rule)
    transaction = Transaction(
        transaction_id="DETAIL-TXN", customer_id=customer.id, amount=5000,
        transaction_date=datetime.now(), transaction_type="purchase",
    )
    insert_test_document(test_session, transaction)
    assessment = FraudAssessment(
        transaction_id=transaction.id, risk_score=80, risk_category="high", rules_triggered_count=1,
    )
    insert_test_document(test_session, assessment)
    insert_test_document(test_session, TriggeredRule(
        assessment_id=assessment.id, transaction_id=transaction.id,
        rule_id=rule.id, rule_explanation="Amount exceeded the configured threshold",
    ))
    token = create_access_token({"sub": str(user.id), "role": "analyst"})
    path = f"/transactions/{transaction.id}"
    assert test_client.get(path).status_code == 401
    response = test_client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["assessment"] == {
        "risk_score": 80, "risk_level": "high",
        "triggered_rules": [{
            "rule_id": "DETAIL-RULE", "rule_name": "Large payment",
            "explanation": "Amount exceeded the configured threshold",
        }],
    }
