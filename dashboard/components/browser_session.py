"""Synchronize browser-persistent authentication with Streamlit sessions."""

from pathlib import Path
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components


_storage = components.declare_component(
    "fraud_detection_session",
    path=str(Path(__file__).parent / "session_storage"),
)


def request_storage(action: str, token: str = "") -> None:
    st.session_state.auth_storage_request = {
        "id": uuid4().hex,
        "action": action,
        "token": token,
    }


def clear_authentication() -> None:
    """Discard both server-side state and the browser's saved credential."""
    st.session_state.token = None
    st.session_state.user = None
    st.session_state.last_activity = None
    request_storage("clear")


def synchronize_storage():
    """Wait for a browser acknowledgement before rendering authenticated content."""
    if "auth_storage_request" not in st.session_state:
        request_storage("read")

    request = st.session_state.auth_storage_request
    result = _storage(
        request=request,
        key="persistent_auth",
        default=None,
    )
    if not isinstance(result, dict) or result.get("id") != request["id"]:
        st.stop()
    if result.get("error"):
        st.error(
            "Unable to access browser login storage. Allow site storage "
            "for this application and reload the page."
        )
        st.stop()
    return result
