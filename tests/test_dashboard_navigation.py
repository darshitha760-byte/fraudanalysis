from unittest.mock import Mock
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

from components.api_client import APIClient
from config import PAGES, ROLE_PERMISSIONS, UserRole
from page_loader import load_page_main
from components.auth_handler import AuthHandler
from streamlit.testing.v1 import AppTest
import page_loader
import streamlit as st


def test_analytics_permission_matches_all_configured_page_roles():
    for role in PAGES["Risk Analytics"]["roles"]:
        assert "view_analytics" in ROLE_PERMISSIONS[UserRole(role)]
    assert "train_models" in ROLE_PERMISSIONS[UserRole.ADMIN]
    assert "train_models" in ROLE_PERMISSIONS[UserRole.ANALYST]
    assert "train_models" not in ROLE_PERMISSIONS[UserRole.VIEWER]


def test_viewer_has_access_to_viewer_pages_but_not_admin_pages():
    viewer_permissions = ROLE_PERMISSIONS[UserRole.VIEWER]

    assert "view_dashboard" in viewer_permissions
    assert "view_transactions" in viewer_permissions
    assert "view_analytics" in viewer_permissions
    assert "manage_rules" not in viewer_permissions
    assert "manage_users" not in viewer_permissions


def test_configured_pages_load_from_the_pages_directory():
    for page in PAGES.values():
        if page.get("show_in_nav") is False:
            continue
        assert callable(load_page_main(page["file"]))


def test_dashboard_statistics_use_existing_analytics_endpoints():
    client = APIClient(base_url="http://api.test")
    response = Mock(status_code=200)
    response.json.return_value = {}
    client.session.get = Mock(return_value=response)

    client.get_transaction_stats(days=14)
    assert client.session.get.call_args.args[0] == (
        "http://api.test/api/analytics/transactions"
    )
    assert client.session.get.call_args.kwargs["params"] == {"days": 14}

    client.get_alert_stats()
    assert client.session.get.call_args.args[0] == (
        "http://api.test/api/analytics/alerts"
    )

    client.get_transaction_trends()
    assert client.session.get.call_args.args[0] == (
        "http://api.test/api/analytics/trends"
    )


def test_transaction_filters_follow_backend_pagination_and_response_contract():
    client = APIClient(base_url="http://api.test")
    response = Mock(status_code=200)
    response.json.return_value = {"data": [], "pagination": {"total": 0}}
    client.session.get = Mock(return_value=response)

    result = client.get_transactions(
        skip=40,
        limit=20,
        customer_id="123",
        start_date="2026-10-01T00:00:00",
        end_date="2026-10-21T23:59:59.999999",
        risk_level="high",
        transaction_id="TXN_FRAUD",
    )

    assert result["data"] == []
    assert client.session.get.call_args.args[0] == (
        "http://api.test/api/transactions"
    )
    assert client.session.get.call_args.kwargs["params"] == {
        "page": 3,
        "limit": 20,
        "customer_id": 123,
        "start_date": "2026-10-01T00:00:00",
        "end_date": "2026-10-21T23:59:59.999999",
        "risk_level": "high",
        "transaction_id": "TXN_FRAUD",
    }


def test_transaction_search_rejects_non_numeric_customer_id():
    client = APIClient(base_url="http://api.test")
    client.session.get = Mock()

    result = client.get_transactions(customer_id="customer-1")

    assert result == {"error": "Customer ID must be a number."}
    client.session.get.assert_not_called()


def test_static_sidebar_lists_viewer_pages_and_switches_without_logout(monkeypatch):
    monkeypatch.setattr(AuthHandler, "restore_browser_session", lambda: None)
    monkeypatch.setattr(
        page_loader,
        "load_page_main",
        lambda filename: lambda: st.write(f"Loaded {filename}"),
    )
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
    )
    app.session_state["token"] = "test-viewer-token"
    app.session_state["user"] = {"email": "viewer@example.com", "role": "viewer"}
    app.run()

    assert not app.exception
    assert len(app.sidebar.selectbox) == 0
    assert app.sidebar.radio[0].options == [
        f"{PAGES[name]['icon']}  {name}"
        for name in ("Dashboard", "Transactions", "Risk Analytics")
    ]
    app.sidebar.radio[0].set_value("Transactions").run()

    assert not app.exception
    assert app.session_state["page_selector"] == "Transactions"
    assert app.session_state["token"] == "test-viewer-token"
    assert any(
        item.value == "Loaded 02_Transaction_Explorer.py" for item in app.markdown
    )


def test_static_sidebar_lists_admin_pages_and_resets_inaccessible_selection(monkeypatch):
    monkeypatch.setattr(AuthHandler, "restore_browser_session", lambda: None)
    monkeypatch.setattr(page_loader, "load_page_main", lambda filename: lambda: None)
    app = AppTest.from_file(
        str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")
    )
    app.session_state["token"] = "test-admin-token"
    app.session_state["user"] = {"email": "admin@example.com", "role": "admin"}
    app.run()

    assert not app.exception
    assert len(app.sidebar.radio[0].options) == 8
    app.sidebar.radio[0].set_value("User Management").run()
    assert not app.exception
    assert app.session_state["page_selector"] == "User Management"

    app.session_state["user"] = {"email": "viewer@example.com", "role": "viewer"}
    app.run()

    assert not app.exception
    assert app.session_state["page_selector"] == "Dashboard"
    assert len(app.sidebar.radio[0].options) == 3
