"""Admin-only account creation and management."""

import streamlit as st

from components import AuthHandler, create_user_table, display_user_detail
from utils import show_error_message


def main():
    if not AuthHandler.is_authenticated():
        st.error("Please login to access this page")
        return
    if not AuthHandler.has_permission("manage_users"):
        st.error("You don't have permission to manage users")
        return

    if st.session_state.pop("reset_new_user", False):
        for key in ("new_email", "new_password", "confirm_password", "new_name", "new_role"):
            st.session_state.pop(key, None)
    if notice := st.session_state.pop("user_management_notice", None):
        st.success(notice)
    client = AuthHandler.get_api_client()
    st.markdown("## 👥 User Management")
    listing, creation, details = st.tabs(["Users List", "Create User", "View Details"])
    with listing:
        if st.button("🔄 Refresh Users", use_container_width=True):
            st.session_state.pop("users", None)
        if st.session_state.get("users") is None:
            response = client.get_users()
            if isinstance(response, dict) and "error" in response:
                show_error_message("Unable to load users", response["error"])
            else:
                st.session_state.users = response
        users = st.session_state.get("users") or []
        if users:
            st.dataframe(create_user_table(users), use_container_width=True, hide_index=True)
            user_id = st.selectbox(
                "Select user", [user["id"] for user in users],
                format_func=lambda value: next(user["email"] for user in users if user["id"] == value),
                key="select_user",
            )
            if st.button("View / Edit User", use_container_width=True):
                st.session_state.selected_user_id = user_id
        else:
            st.info("No users loaded.")

    with creation:
        st.markdown("### Create New User")
        with st.form("create_user_form"):
            left, right = st.columns(2)
            with left:
                email = st.text_input("Email", key="new_email")
                password = st.text_input(
                    "Initial Password", type="password",
                    help="At least 8 characters.", key="new_password",
                )
            with right:
                role = st.selectbox("Role", ["Viewer", "Analyst", "Admin"], key="new_role")
                confirmation = st.text_input(
                    "Confirm Password", type="password", key="confirm_password"
                )
            name = st.text_input("Full Name", key="new_name")
            st.caption("Welcome emails and departments are not configured. Share credentials securely.")
            submitted = st.form_submit_button("✅ Create User", use_container_width=True)
        if submitted:
            if not email.strip() or not password or not name.strip():
                st.error("Email, full name and password are required")
            elif password != confirmation:
                st.error("Passwords don't match")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters")
            else:
                result = client.create_user({
                    "email": email.strip().lower(), "password": password,
                    "full_name": name.strip(), "role": role.lower(),
                })
                if "error" in result:
                    show_error_message("Unable to create user", result["error"])
                else:
                    st.session_state.user_management_notice = f"User {result['email']} created"
                    st.session_state.reset_new_user = True
                    st.session_state.pop("users", None)
                    st.rerun()

    with details:
        selected_id = st.session_state.get("selected_user_id")
        if selected_id is None:
            st.info("Select View / Edit User in the Users List tab.")
            return
        user = client.get_user(selected_id)
        if "error" in user:
            show_error_message("Unable to load user", user["error"])
            return
        display_user_detail(user)
        with st.form(f"edit_user_{selected_id}"):
            name = st.text_input("Full Name", value=user["full_name"])
            email = st.text_input("Email", value=user["email"])
            roles = ["viewer", "analyst", "admin"]
            role = st.selectbox("Role", roles, index=roles.index(user["role"]))
            active = st.checkbox("Active", value=user["is_active"])
            save = st.form_submit_button("💾 Save Changes")
        if save:
            result = client.update_user(selected_id, {
                "full_name": name, "email": email, "role": role, "is_active": active,
            })
            if "error" in result:
                show_error_message("Unable to update user", result["error"])
            else:
                st.session_state.pop("users", None)
                st.session_state.user_management_notice = "User updated"
                st.rerun()
        confirmed = st.checkbox("Confirm permanent account deletion", key=f"delete_confirm_{selected_id}")
        if st.button("Delete User", disabled=not confirmed):
            result = client.delete_user(selected_id)
            if "error" in result:
                show_error_message("Unable to delete user", result["error"])
            else:
                st.session_state.pop("users", None)
                st.session_state.pop("selected_user_id", None)
                st.session_state.user_management_notice = "User deleted"
                st.rerun()


if __name__ == "__main__":
    main()
