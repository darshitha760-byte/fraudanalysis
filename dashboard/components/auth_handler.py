"""
Authentication Handler
"""
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from components.api_client import APIClient
from components.browser_session import (
    clear_authentication,
    request_storage,
    synchronize_storage,
)
from config import API_BASE_URL, UserRole, ROLE_PERMISSIONS


class AuthHandler:
    """Handles authentication and authorization."""

    @staticmethod
    def initialize_session_state():
        """Initialize session state variables."""
        if "token" not in st.session_state:
            st.session_state.token = None
        if "user" not in st.session_state:
            st.session_state.user = None
        if "last_activity" not in st.session_state:
            st.session_state.last_activity = datetime.now()
        if "login_attempts" not in st.session_state:
            st.session_state.login_attempts = 0
        if "locked_until" not in st.session_state:
            st.session_state.locked_until = None

    @staticmethod
    def restore_browser_session():
        """Restore browser logins only after the API validates the saved token."""
        result = synchronize_storage()
        request = st.session_state.auth_storage_request
        if st.session_state.get("auth_storage_processed") == request["id"]:
            return

        if request["action"] == "read" and result.get("token"):
            client = APIClient(base_url=API_BASE_URL, token=result["token"])
            user = client.get_current_user()
            if "error" in user or "detail" in user:
                st.error(user.get("error", user.get("detail")))
                st.stop()
            st.session_state.token = result["token"]
            st.session_state.user = user

        st.session_state.auth_storage_processed = request["id"]

    @staticmethod
    def check_session_timeout() -> bool:
        """Keep valid logins active without a dashboard inactivity deadline."""
        return st.session_state.get("token") is not None

    @staticmethod
    def login(email: str, password: str) -> bool:
        """Authenticate user with email and password."""
        # Check if account is locked
        if st.session_state.locked_until:
            if datetime.now() < st.session_state.locked_until:
                st.error("Account locked due to too many login attempts. Please try again later.")
                return False
            else:
                st.session_state.locked_until = None
                st.session_state.login_attempts = 0

        if not email or not password:
            st.error("Please enter both email and password.")
            return False

        client = APIClient(base_url=API_BASE_URL)
        response = client.login(email, password)

        if "error" in response or "detail" in response:
            st.session_state.login_attempts += 1

            from config import MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION_MINUTES

            if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
                st.session_state.locked_until = datetime.now() + timedelta(
                    minutes=LOCKOUT_DURATION_MINUTES
                )
                st.error(
                    f"Too many failed attempts. Account locked for {LOCKOUT_DURATION_MINUTES} minutes."
                )
            else:
                remaining = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
                st.error(
                    f"Login failed: {response.get('error', response.get('detail'))}. "
                    f"({remaining} attempts remaining)"
                )
            return False

        if "access_token" in response:
            st.session_state.token = response["access_token"]
            st.session_state.login_attempts = 0
            st.session_state.locked_until = None

            # Fetch user info
            client.set_token(st.session_state.token)
            user_response = client.get_current_user()

            if "error" not in user_response and "detail" not in user_response:
                st.session_state.user = user_response
                st.session_state.last_activity = datetime.now()
                request_storage("write", st.session_state.token)
                return True
            else:
                st.error("Could not fetch user information.")
                st.session_state.token = None
                return False

        st.error("Invalid response from authentication service.")
        return False

    @staticmethod
    def register(email: str, full_name: str, password: str) -> bool:
        """Create a new viewer account through the authentication API."""
        client = APIClient(base_url=API_BASE_URL)
        response = client.register(email, full_name, password)
        if "error" in response or "detail" in response:
            st.error(response.get("detail", response.get("error", "Registration failed.")))
            return False

        st.success("Account created. You can now log in.")
        return True

    @staticmethod
    def is_authenticated() -> bool:
        """Check if user is currently authenticated."""
        AuthHandler.initialize_session_state()
        return st.session_state.token is not None and AuthHandler.check_session_timeout()

    @staticmethod
    def get_current_user() -> Optional[Dict[str, Any]]:
        """Get current authenticated user."""
        if AuthHandler.is_authenticated():
            return st.session_state.user
        return None

    @staticmethod
    def get_user_role() -> Optional[str]:
        """Get current user's role."""
        user = AuthHandler.get_current_user()
        if user:
            role = user.get("role", UserRole.VIEWER)
            if isinstance(role, UserRole):
                return role.value
            return str(role).lower()
        return None

    @staticmethod
    def get_user_email() -> Optional[str]:
        """Get current user's email."""
        user = AuthHandler.get_current_user()
        if user:
            return user.get("email")
        return None

    @staticmethod
    def has_permission(permission: str) -> bool:
        """Check if user has specific permission."""
        role = AuthHandler.get_user_role()
        if not role:
            return False

        try:
            normalized_role = UserRole(str(role).lower())
        except ValueError:
            return False
        permissions = ROLE_PERMISSIONS.get(normalized_role, [])
        return permission in permissions

    @staticmethod
    def can_access_page(page_roles: list) -> bool:
        """Check if user can access page based on roles."""
        role = AuthHandler.get_user_role()
        if not role:
            return False
        normalized_role = role.lower()
        return normalized_role in {
            str(page_role).lower() for page_role in page_roles
        }

    @staticmethod
    def logout():
        """Logout current user."""
        if st.session_state.token:
            client = APIClient(base_url=API_BASE_URL, token=st.session_state.token)
            client.logout()

        clear_authentication()
        st.rerun()

    @staticmethod
    def get_api_client() -> APIClient:
        """Get configured API client with current user's token."""
        token = st.session_state.token if st.session_state.token else None
        return APIClient(base_url=API_BASE_URL, token=token)
