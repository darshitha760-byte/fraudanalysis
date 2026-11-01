from datetime import datetime, timedelta
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dashboard"))

from components import auth_handler, browser_session
from components.api_client import APIClient
from components.auth_handler import AuthHandler


class SessionState(dict):
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class RerunRequested(BaseException):
    pass


class StopRequested(BaseException):
    pass


@pytest.fixture
def state(monkeypatch):
    state = SessionState()
    monkeypatch.setattr(auth_handler.st, "session_state", state)
    monkeypatch.setattr(auth_handler.st, "error", Mock())
    monkeypatch.setattr(
        auth_handler.st, "rerun", Mock(side_effect=RerunRequested)
    )
    monkeypatch.setattr(
        auth_handler.st, "stop", Mock(side_effect=StopRequested)
    )
    AuthHandler.initialize_session_state()
    return state


def test_old_activity_does_not_log_out_authenticated_user(state):
    state.token = "valid-token"
    state.user = {"email": "viewer@example.test", "role": "viewer"}
    state.last_activity = datetime.now() - timedelta(days=7)

    assert AuthHandler.is_authenticated()
    assert AuthHandler.get_user_role() == "viewer"


def test_restore_waits_for_browser_response(state, monkeypatch):
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=None))

    with pytest.raises(StopRequested):
        AuthHandler.restore_browser_session()

    assert state.token is None


def test_refresh_restores_saved_login_after_api_validation(state, monkeypatch):
    browser_session.request_storage("read")
    result = {"id": state.auth_storage_request["id"], "token": "saved-token"}
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=result))
    client = Mock()
    client.get_current_user.return_value = {
        "email": "viewer@example.test",
        "role": "viewer",
    }
    factory = Mock(return_value=client)
    monkeypatch.setattr(auth_handler, "APIClient", factory)

    AuthHandler.restore_browser_session()
    AuthHandler.restore_browser_session()

    assert state.token == "saved-token"
    assert state.user["role"] == "viewer"
    factory.assert_called_once_with(
        base_url=auth_handler.API_BASE_URL, token="saved-token"
    )
    client.get_current_user.assert_called_once()


def test_fresh_browser_without_saved_login_remains_logged_out(state, monkeypatch):
    browser_session.request_storage("read")
    result = {"id": state.auth_storage_request["id"], "token": None}
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=result))

    AuthHandler.restore_browser_session()

    assert not AuthHandler.is_authenticated()


def test_storage_failure_blocks_login_instead_of_silently_losing_it(state, monkeypatch):
    browser_session.request_storage("read")
    result = {"id": state.auth_storage_request["id"], "error": "storage disabled"}
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=result))

    with pytest.raises(StopRequested):
        AuthHandler.restore_browser_session()

    auth_handler.st.error.assert_called_once()


def test_transient_profile_failure_does_not_delete_saved_browser_login(state, monkeypatch):
    browser_session.request_storage("read")
    result = {"id": state.auth_storage_request["id"], "token": "saved-token"}
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=result))
    client = Mock()
    client.get_current_user.return_value = {"error": "Server unavailable"}
    monkeypatch.setattr(auth_handler, "APIClient", Mock(return_value=client))

    with pytest.raises(StopRequested):
        AuthHandler.restore_browser_session()

    assert state.auth_storage_request["action"] == "read"
    assert state.token is None
    assert "auth_storage_processed" not in state


def test_login_queues_browser_persistence(state, monkeypatch):
    client = Mock()
    client.login.return_value = {"access_token": "new-token"}
    client.get_current_user.return_value = {"role": "viewer"}
    monkeypatch.setattr(auth_handler, "APIClient", Mock(return_value=client))

    assert AuthHandler.login("viewer@example.test", "test-password")
    assert state.auth_storage_request["action"] == "write"
    assert state.auth_storage_request["token"] == "new-token"


def test_logout_clears_state_and_queues_browser_deletion(state, monkeypatch):
    state.token = "saved-token"
    state.user = {"role": "viewer"}
    client = Mock()
    client.logout.return_value = {"message": "Logged out"}
    monkeypatch.setattr(auth_handler, "APIClient", Mock(return_value=client))

    with pytest.raises(RerunRequested):
        AuthHandler.logout()

    assert state.token is None
    assert state.user is None
    assert state.auth_storage_request["action"] == "clear"
    assert state.auth_storage_request["token"] == ""
    client.logout.assert_called_once()


def test_failed_login_does_not_rerun_or_delete_browser_state(state):
    client = APIClient(base_url="http://api.test")
    response = Mock(status_code=401)

    result = client._handle_response(response)

    assert result["status_code"] == 401
    assert "error" in result
    assert "auth_storage_request" not in state
    auth_handler.st.rerun.assert_not_called()


def test_expired_token_clears_browser_credential_and_requires_login(state):
    state.token = "expired-token"
    state.user = {"role": "viewer"}
    client = APIClient(base_url="http://api.test", token="expired-token")

    with pytest.raises(RerunRequested):
        client._handle_response(Mock(status_code=401))

    assert state.token is None
    assert state.user is None
    assert state.auth_storage_request["action"] == "clear"
    assert "expired" in state.auth_notice


def test_stale_browser_acknowledgement_cannot_restore_logout_token(state, monkeypatch):
    browser_session.request_storage("read")
    stale_result = {"id": state.auth_storage_request["id"], "token": "old-token"}
    browser_session.clear_authentication()
    monkeypatch.setattr(browser_session, "_storage", Mock(return_value=stale_result))

    with pytest.raises(StopRequested):
        AuthHandler.restore_browser_session()

    assert state.token is None
    assert state.auth_storage_request["action"] == "clear"
