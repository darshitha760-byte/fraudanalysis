"""Regression coverage for account creation and audit visibility."""

from datetime import datetime
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from app.core.permissions import UserRole
from app.core.security import hash_password, verify_password
from app.models import AuditLog, User
from tests.conftest import insert_test_document

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))
from components.api_client import APIClient
from components.auth_handler import AuthHandler
from config import ROLE_PERMISSIONS, UserRole as DashboardRole


@pytest.fixture
def admin_headers(test_client, test_session):
    admin = User(
        email="admin.flow@example.com", full_name="Flow Admin",
        password_hash=hash_password("AdminFlowTest123"), role=UserRole.ADMIN,
        is_active=True,
    )
    insert_test_document(test_session, admin)
    response = test_client.post(
        "/api/auth/login",
        json={"email": admin.email, "password": "AdminFlowTest123"},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def account_payload():
    return {
        "email": "New.Person@example.com", "full_name": "New Person",
        "password": "SecureAccount123", "role": "analyst",
    }


def test_admin_creates_lists_reads_and_updates_real_account(test_client, test_session, admin_headers):
    created = test_client.post("/api/users", json=account_payload(), headers=admin_headers)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["email"] == "new.person@example.com"
    assert data["role"] == "analyst"
    assert data["is_active"] is True
    assert "password_hash" not in data and "password" not in data
    user = test_session["users"].find_one({"id": data["id"]})
    assert user is not None
    assert verify_password("SecureAccount123", user["password_hash"])
    assert test_client.get("/api/users", headers=admin_headers).status_code == 200
    assert test_client.get(f"/api/users/{user['id']}", headers=admin_headers).json()["id"] == user["id"]
    assert test_client.get("/api/users/me", headers=admin_headers).status_code == 200
    updated = test_client.put(
        f"/api/users/{user['id']}", headers=admin_headers,
        json={"role": "viewer", "is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["role"] == "viewer"
    assert updated.json()["is_active"] is False
    login = test_client.post(
        "/api/auth/login",
        json={"email": data["email"], "password": "SecureAccount123"},
    )
    assert login.status_code == 403
    audit = test_client.get(
        "/api/audit-logs", headers=admin_headers,
        params={"action": "create", "target_entity": "user"},
    ).json()
    assert audit["total"] == 1
    assert audit["items"][0]["target_id"] == str(user["id"])
    assert "SecureAccount123" not in str(audit)


def test_invalid_and_duplicate_accounts_do_not_report_success(test_client, admin_headers):
    payload = account_payload()
    assert test_client.post("/api/users", json=payload, headers=admin_headers).status_code == 201
    assert test_client.post("/api/users", json=payload, headers=admin_headers).status_code == 409
    for invalid in (
        {"password": "short"}, {"email": "not-an-email"},
        {"role": "superuser"}, {"full_name": "  "},
    ):
        response = test_client.post("/api/users", json={**payload, **invalid}, headers=admin_headers)
        assert response.status_code == 422, response.text


def test_delete_account_is_audited(test_client, admin_headers):
    data = test_client.post("/api/users", json=account_payload(), headers=admin_headers).json()
    response = test_client.delete(f"/api/users/{data['id']}", headers=admin_headers)
    assert response.status_code == 204, response.text
    audit = test_client.get("/api/audit-logs", headers=admin_headers, params={"action": "delete"}).json()
    assert audit["items"][0]["target_id"] == str(data["id"])


@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.ANALYST])
def test_non_admins_cannot_manage_accounts_or_read_admin_audit(test_client, test_session, role):
    user = User(
        email=f"{role.value}.flow@example.com", full_name="Non Admin",
        password_hash=hash_password("NonAdminTest123"), role=role, is_active=True,
    )
    insert_test_document(test_session, user)
    token = test_client.post(
        "/api/auth/login", json={"email": user.email, "password": "NonAdminTest123"}
    ).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    assert test_client.get("/api/users", headers=headers).status_code == 403
    assert test_client.post("/api/users", json=account_payload(), headers=headers).status_code == 403
    assert test_client.get("/api/audit-logs", headers=headers).status_code == 403
    assert test_client.get(
        "/api/audit-logs/compliance-report", headers=headers,
        params={"report_type": "data_changes", "start_date": "2026-01-01", "end_date": "2026-12-31"},
    ).status_code == 403
    assert test_client.get(f"/api/users/{user.id}", headers=headers).status_code == 200


def test_audit_filters_include_whole_end_day_and_report_counts(test_client, test_session, admin_headers):
    actor = test_session["users"].find_one({"email": "admin.flow@example.com"})
    assert actor is not None
    for day in (20, 21, 22):
        insert_test_document(test_session, AuditLog(
            actor_id=actor["id"], action="create_user", action_category="user_management",
            target_type="user", target_id=f"test-{day}", action_status="success",
            action_timestamp=datetime(2026, 9, day, 23, 59, 59),
        ))
    params = {
        "actor": actor["email"], "action": "create", "target_entity": "user",
        "start_date": "2026-09-20", "end_date": "2026-09-21", "limit": 1,
    }
    response = test_client.get("/api/audit-logs", headers=admin_headers, params=params)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 2
    assert response.json()["items"][0]["target_id"] == "test-21"
    report = test_client.get(
        "/api/audit-logs/compliance-report", headers=admin_headers,
        params={"report_type": "data_changes", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    assert report.status_code == 200, report.text
    assert report.json()["summary"] == {
        "total_events": 2, "unique_users": 1, "failed_actions": 0, "exceptions": 0,
    }
    assert test_client.get(
        "/api/audit-logs", headers=admin_headers,
        params={"start_date": "2026-09-22", "end_date": "2026-09-20"},
    ).status_code == 422


def test_login_attempts_are_persisted(test_client, test_session, admin_headers):
    assert test_session["audit_logs"].count_documents({"action": "login", "action_status": "success"}) == 1
    response = test_client.post(
        "/api/auth/login", json={"email": "unknown@example.com", "password": "IncorrectPass123"}
    )
    assert response.status_code == 401
    assert test_session["audit_logs"].count_documents({"action": "login", "action_status": "failure"}) == 1


def test_admin_endpoints_require_login(test_client):
    assert test_client.get("/api/users").status_code == 401
    assert test_client.post("/api/users", json=account_payload()).status_code == 401
    assert test_client.get("/api/audit-logs").status_code == 401


def test_client_marks_validation_and_duplicate_responses_as_errors():
    client = APIClient(base_url="http://test")
    response = Mock(status_code=422)
    response.json.return_value = {
        "detail": [{"loc": ["body", "password"], "msg": "Must be at least 8 characters"}]
    }
    assert "password" in client._handle_response(response)["error"]
    response.status_code = 409
    response.json.return_value = {"detail": "Email already exists"}
    assert client._handle_response(response)["error"] == "Email already exists"


def admin_page(monkeypatch, filename, client):
    monkeypatch.setattr(AuthHandler, "get_api_client", lambda: client)
    app = AppTest.from_file(str(
        Path(__file__).resolve().parents[1] / "dashboard" / "pages" / filename
    ))
    app.session_state["token"] = "test"
    app.session_state["user"] = {"role": "admin", "email": "admin@example.com"}
    return app.run()


def fill_creation(app, password="SecureAccount123"):
    app.text_input(key="new_email").set_value("new.person@example.com")
    app.text_input(key="new_password").set_value(password)
    app.text_input(key="confirm_password").set_value(password)
    app.text_input(key="new_name").set_value("New Person")
    app.selectbox(key="new_role").set_value("Analyst")
    next(button for button in app.button if "Create User" in button.label).click().run()


def test_creation_form_submits_all_fields_and_refreshes_list(monkeypatch):
    client = Mock()
    client.get_users.return_value = []
    client.create_user.return_value = {"id": 2, "email": "new.person@example.com"}
    app = admin_page(monkeypatch, "07_User_Management.py", client)
    fill_creation(app)
    assert not app.exception
    client.create_user.assert_called_once_with({
        "email": "new.person@example.com", "password": "SecureAccount123",
        "full_name": "New Person", "role": "analyst",
    })
    assert any("created" in success.value for success in app.success)
    assert app.text_input(key="new_password").value == ""


def test_creation_form_validates_short_password_and_shows_api_errors(monkeypatch):
    client = Mock()
    client.get_users.return_value = []
    app = admin_page(monkeypatch, "07_User_Management.py", client)
    fill_creation(app, password="short")
    assert not app.exception
    client.create_user.assert_not_called()
    assert any("8 characters" in error.value for error in app.error)
    client.create_user.return_value = {"error": "Email already exists"}
    fill_creation(app)
    assert not app.exception
    assert not app.success
    assert any("Email already exists" in error.value for error in app.error)


def test_admin_can_search_and_inspect_audit_logs_after_rerun(monkeypatch):
    assert "view_audit_logs" in ROLE_PERMISSIONS[DashboardRole.ADMIN]
    client = Mock()
    client.get_audit_logs.return_value = {
        "total": 1, "items": [{
            "id": 1, "timestamp": "2026-10-22T12:00:00",
            "actor": "admin@example.com", "action": "create_user",
            "target_type": "user", "target_id": "2", "success": True, "details": "",
        }],
    }
    app = admin_page(monkeypatch, "08_Audit_Logs.py", client)
    assert not app.error
    next(button for button in app.button if "Search Logs" in button.label).click().run()
    assert not app.exception
    assert len(app.dataframe) == 1
    app.run()
    assert len(app.dataframe) == 1
    assert client.get_audit_logs.call_args.kwargs["action"] is None


def test_admin_user_details_accept_integer_ids_and_real_status(monkeypatch):
    client = Mock()
    user = {
        "id": 2, "email": "person@example.com", "full_name": "Person",
        "role": "analyst", "is_active": True, "created_at": "2026-10-22T00:00:00",
    }
    client.get_users.return_value = [user]
    client.get_user.return_value = user
    app = admin_page(monkeypatch, "07_User_Management.py", client)
    next(button for button in app.button if "View / Edit" in button.label).click().run()
    assert not app.exception
    assert any("Active" in metric.value for metric in app.metric)


def test_audit_report_uses_date_parameters_and_remains_exportable(monkeypatch):
    client = Mock()
    client.get_compliance_report.return_value = {
        "summary": {"total_events": 3, "unique_users": 1, "failed_actions": 1, "exceptions": 0},
        "findings": [],
    }
    app = admin_page(monkeypatch, "08_Audit_Logs.py", client)
    next(button for button in app.button if "Generate Report" in button.label).click().run()
    assert not app.exception
    assert app.metric[0].value == "3"
    assert len(client.get_compliance_report.call_args.kwargs["end_date"]) == 10
    app.run()
    assert app.metric[0].value == "3"


@pytest.mark.parametrize("filename", ["07_User_Management.py", "08_Audit_Logs.py"])
def test_viewer_cannot_open_admin_pages(monkeypatch, filename):
    client = Mock()
    app = admin_page(monkeypatch, filename, client)
    app.session_state["user"] = {"role": "viewer", "email": "viewer@example.com"}
    app.run()
    assert not app.exception
    assert any("permission" in error.value for error in app.error)
