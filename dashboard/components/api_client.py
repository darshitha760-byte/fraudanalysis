"""
API Client for backend communication
"""
import requests
import streamlit as st
from typing import Dict, List, Optional, Any, Union
from config import API_BASE_URL, API_TIMEOUT


class APIClient:
    """Centralized API client for backend communication."""

    def __init__(self, base_url: str = API_BASE_URL, token: Optional[str] = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.timeout = API_TIMEOUT

    def set_token(self, token: str):
        """Set authentication token."""
        self.token = token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _handle_response(self, response: requests.Response) -> Dict[str, Any]:
        """Handle API response and errors."""
        if response.status_code == 401:
            if self.token:
                from components.browser_session import clear_authentication

                clear_authentication()
                st.session_state.auth_notice = (
                    "Your login has expired or is no longer valid. Please log in again."
                )
                st.rerun()
            return {"error": "Invalid email or password.", "status_code": 401}

        try:
            if response.status_code == 403:
                return {"error": "Access denied. You don't have permission for this action."}
            elif response.status_code == 404:
                return {"error": "Resource not found."}
            elif response.status_code >= 500:
                return {"error": "Server error. Please try again later."}
            elif response.status_code >= 400:
                try:
                    detail = response.json().get("detail", "Request failed")
                    if isinstance(detail, list):
                        detail = "; ".join(
                            f"{'.'.join(str(part) for part in item.get('loc', []))}: "
                            f"{item.get('msg', 'Invalid value')}"
                            for item in detail
                        )
                    return {"error": str(detail), "status_code": response.status_code}
                except (ValueError, AttributeError):
                    return {"error": f"Request failed: {response.text}"}

            if response.status_code == 204:
                return {"success": True}

            return response.json()
        except Exception as e:
            return {"error": f"Error processing response: {str(e)}"}

    # Authentication Endpoints
    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Login with email and password."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Login failed: {str(e)}"}

    def register(self, email: str, full_name: str, password: str) -> Dict[str, Any]:
        """Register a viewer account."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/register",
                json={
                    "email": email,
                    "full_name": full_name,
                    "password": password,
                },
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Registration failed: {str(e)}"}

    def get_current_user(self) -> Dict[str, Any]:
        """Get current authenticated user info."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/auth/me",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch user: {str(e)}"}

    def logout(self) -> Dict[str, Any]:
        """Logout current user."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/logout",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Logout failed: {str(e)}"}

    # Transaction Endpoints
    def get_transactions(
        self,
        skip: int = 0,
        limit: int = 20,
        customer_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        merchant_id: Optional[str] = None,
        risk_level: Optional[str] = None,
        transaction_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get transactions with filters."""
        try:
            params: Dict[str, Any] = {
                "page": skip // limit + 1,
                "limit": limit,
            }
            if customer_id:
                try:
                    params["customer_id"] = int(customer_id)
                except ValueError:
                    return {"error": "Customer ID must be a number."}
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            if min_amount is not None:
                params["min_amount"] = min_amount
            if max_amount is not None:
                params["max_amount"] = max_amount
            if merchant_id:
                params["merchant_id"] = merchant_id
            if risk_level:
                params["risk_level"] = risk_level
            if transaction_id:
                params["transaction_id"] = transaction_id

            response = self.session.get(
                f"{self.base_url}/api/transactions",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch transactions: {str(e)}"}

    def get_transaction(self, transaction_id: str) -> Dict[str, Any]:
        """Get single transaction with assessment details."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/transactions/{transaction_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch transaction: {str(e)}"}

    def get_transaction_stats(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """Get transaction statistics."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/analytics/transactions",
                params={"days": days},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch stats: {str(e)}"}

    def get_transaction_trends(
        self,
        days: int = 30,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Get daily transaction trends for dashboard charts."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/analytics/trends",
                params={"days": days},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch transaction trends: {str(e)}"}

    # Alert Endpoints
    def get_alerts(
        self,
        skip: int = 0,
        limit: int = 20,
        status: Optional[str] = None,
        risk_level: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get fraud alerts with filters."""
        try:
            params = {"skip": skip, "limit": limit}
            if status:
                params["status"] = status
            if risk_level:
                params["risk_level"] = risk_level
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self.session.get(
                f"{self.base_url}/api/alerts",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch alerts: {str(e)}"}

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        """Get single alert details."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/alerts/{alert_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch alert: {str(e)}"}

    def review_alert(
        self,
        alert_id: str,
        decision: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Review and make decision on alert."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/alerts/{alert_id}/review",
                json={"decision": decision, "notes": notes},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to review alert: {str(e)}"}

    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/analytics/alerts",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch alert stats: {str(e)}"}

    # Rule Endpoints
    def get_fraud_rules(self) -> Dict[str, Any]:
        """Get all fraud detection rules."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/rules",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch rules: {str(e)}"}

    def get_rule(self, rule_id: str) -> Dict[str, Any]:
        """Get single rule details."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/rules/{rule_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch rule: {str(e)}"}

    def create_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new fraud rule."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/rules",
                json=rule_data,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to create rule: {str(e)}"}

    def update_rule(self, rule_id: str, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing fraud rule."""
        try:
            response = self.session.put(
                f"{self.base_url}/api/rules/{rule_id}",
                json=rule_data,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to update rule: {str(e)}"}

    def delete_rule(self, rule_id: str) -> Dict[str, Any]:
        """Delete (soft) fraud rule."""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/rules/{rule_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to delete rule: {str(e)}"}

    # Model Endpoints
    def train_models(self, algorithms: List[str], source: str, sample_limit: int) -> Dict[str, Any]:
        """Train and persist evaluation models through the API."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/models/train",
                json={"algorithms": algorithms, "source": source, "sample_limit": sample_limit},
                headers=self._get_headers(),
                timeout=300,
            )
            return self._handle_response(response)
        except requests.RequestException as exc:
            return {"error": f"Training request failed: {exc}. Refresh models before retrying; training may still be running."}

    def get_models(self) -> Dict[str, Any]:
        """Get all models."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/models",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch models: {str(e)}"}

    def get_model_metrics(self, model_id: str) -> Dict[str, Any]:
        """Get model performance metrics."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/models/{model_id}/metrics",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch model metrics: {str(e)}"}

    # User Endpoints
    def get_users(self, skip: int = 0, limit: int = 100) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Get all users."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/users",
                params={"skip": skip, "limit": limit},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch users: {str(e)}"}

    def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new user."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/users",
                json=user_data,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to create user: {str(e)}"}

    def get_user(self, user_id: int) -> Dict[str, Any]:
        """Get an account's persisted profile."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/users/{user_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch user: {str(e)}"}

    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update user information."""
        try:
            response = self.session.put(
                f"{self.base_url}/api/users/{user_id}",
                json=user_data,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to update user: {str(e)}"}

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        """Delete user."""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/users/{user_id}",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to delete user: {str(e)}"}

    # Audit Log Endpoints
    def get_audit_logs(
        self,
        skip: int = 0,
        limit: int = 50,
        actor: Optional[str] = None,
        action: Optional[str] = None,
        target_entity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get audit logs with filters."""
        try:
            params = {"skip": skip, "limit": limit}
            if actor:
                params["actor"] = actor
            if action:
                params["action"] = action
            if target_entity:
                params["target_entity"] = target_entity
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date

            response = self.session.get(
                f"{self.base_url}/api/audit-logs",
                params=params,
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch audit logs: {str(e)}"}

    def get_compliance_report(
        self, report_type: str, start_date: str, end_date: str
    ) -> Dict[str, Any]:
        """Get a summary of persisted audit events for a UTC date range."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/audit-logs/compliance-report",
                params={"report_type": report_type, "start_date": start_date, "end_date": end_date},
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch compliance report: {str(e)}"}

    # Customer Risk Endpoints
    def get_customer_risk_profile(self, customer_id: str) -> Dict[str, Any]:
        """Get customer risk profile."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/customers/{customer_id}/risk-profile",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch customer profile: {str(e)}"}

    def get_transaction_patterns(self) -> Dict[str, Any]:
        """Get transaction patterns and analytics."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/analytics/patterns",
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            return self._handle_response(response)
        except requests.RequestException as e:
            return {"error": f"Failed to fetch patterns: {str(e)}"}
