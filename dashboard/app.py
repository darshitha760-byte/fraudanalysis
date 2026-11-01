"""
Main Streamlit Dashboard Application
"""
import streamlit as st
from components.auth_handler import AuthHandler
from config import DASHBOARD_TITLE, PAGES

# Page configuration
st.set_page_config(
    page_title=DASHBOARD_TITLE,
    page_icon="🔐",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
AuthHandler.initialize_session_state()

# Custom styling
st.markdown("""
<style>
    :root {
        --ink: #142238;
        --muted: #64748b;
        --brand: #2563eb;
        --surface: #ffffff;
        --canvas: #f4f7fb;
    }
    [data-testid="stAppViewContainer"] {
        background:
            radial-gradient(ellipse at 85% 0%, rgba(219, 234, 254, .45), transparent 34%),
            var(--canvas);
        color: var(--ink);
    }
    [data-testid="stHeader"] {
        background: rgba(244, 247, 251, .82);
    }
    [data-testid="stMainBlockContainer"] {
        max-width: 1440px;
        padding-top: 2rem;
        padding-bottom: 3rem;
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #101c32 0%, #172943 100%);
    }
    [data-testid="stSidebar"] * {
        color: #e7eefb;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #cbd5e1;
    }
    [data-testid="stSidebar"] {
        border-right: 1px solid #263953;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 1rem;
    }
    .sidebar-brand {
        padding: .5rem 0 1.25rem;
    }
    .sidebar-brand strong {
        display: block;
        font-size: 1.4rem;
        letter-spacing: -.04em;
        color: #f8fafc;
    }
    .sidebar-brand span {
        display: block;
        margin-top: .35rem;
        color: #94a9c5;
        font-size: .78rem;
        letter-spacing: .08em;
        text-transform: uppercase;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] {
        gap: .4rem;
    }
    [data-testid="stSidebar"] .st-key-page_selector {
        width: 100%;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] [role="radiogroup"] > div {
        width: 100%;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input) {
        width: 100%;
        max-width: none;
        box-sizing: border-box;
        margin: 0;
        padding: .7rem .85rem;
        border: 1px solid transparent;
        border-radius: 11px;
        transition: background .15s ease, border-color .15s ease;
    }
    /* Keep the native input accessible while using the whole row as the menu item. */
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input) > div > div:first-child:not([data-testid="stMarkdownContainer"]) {
        display: none;
    }
    [data-testid="stSidebar"] a {
        color: #c7dcff;
        text-decoration: none;
        overflow-wrap: anywhere;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
        background: #233650;
        border-color: #3b5270;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
        background: linear-gradient(100deg, #2459cb, #254a91);
        border-color: #5185e5;
        box-shadow: 0 4px 14px rgba(0, 0, 0, .14);
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label:focus-within {
        outline: 2px solid #93c5fd;
        outline-offset: 2px;
    }
    [data-testid="stSidebar"] [data-testid="stRadio"] label p {
        color: #f1f5f9;
        font-weight: 550;
        font-size: .92rem;
    }
    [data-testid="stSidebar"] hr {
        border-color: #2a3e58;
        margin: 1rem 0;
    }
    [data-testid="stSidebar"] .stButton > button {
        background: #223651;
        border: 1px solid #3a506f;
        color: #f1f5f9;
    }
    [data-testid="stMetric"] {
        background: var(--surface);
        border: 1px solid #e3eaf3;
        border-radius: 16px;
        padding: 1.1rem 1.25rem;
        box-shadow: 0 8px 24px rgba(23, 41, 67, .055);
        min-height: 125px;
    }
    [data-testid="stMetricLabel"] {
        color: var(--muted);
        font-size: .88rem;
        font-weight: 600;
    }
    [data-testid="stMetricValue"] {
        color: var(--ink);
        font-weight: 700;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #e3eaf3;
        border-radius: 16px;
        background: rgba(255, 255, 255, .88);
    }
    [data-testid="stTabs"] button[role="tab"] {
        font-weight: 600;
    }
    .stButton > button, [data-testid="stFormSubmitButton"] > button {
        border-radius: 10px;
        font-weight: 650;
        transition: transform .15s ease, box-shadow .15s ease;
    }
    .stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(37, 99, 235, .18);
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #e3eaf3;
        border-radius: 12px;
        overflow: hidden;
    }
    h1, h2, h3 {
        color: var(--ink);
        letter-spacing: -.025em;
    }
    .page-banner {
        padding: 1.6rem 1.75rem;
        margin-bottom: 1.5rem;
        border: 1px solid #e3eaf3;
        border-radius: 18px;
        background: linear-gradient(110deg, #fff 15%, #eff6ff 100%);
        box-shadow: 0 10px 28px rgba(23, 41, 67, .05);
        border-left: 4px solid var(--brand);
    }
    .page-banner .eyebrow {
        color: var(--brand);
        font-size: .72rem;
        font-weight: 750;
        letter-spacing: .14em;
        text-transform: uppercase;
    }
    .page-banner h1 {
        margin: .3rem 0 0;
        font-size: 1.9rem;
    }
    .login-brand {
        padding: 1.5rem;
        margin-bottom: 1rem;
        border-radius: 18px;
        background: linear-gradient(130deg, #10213d, #1d4ed8);
        color: white;
    }
    .login-brand h1, .login-brand p {
        color: white;
        margin-bottom: .35rem;
    }
    .login-brand p {
        color: #dbeafe;
    }
    @media (max-width: 768px) {
        [data-testid="stMainBlockContainer"] {
            padding: 1rem 1rem 2rem;
        }
        .page-banner h1 {
            font-size: 1.5rem;
        }
    }
</style>
""", unsafe_allow_html=True)


def show_login_page():
    """Display login page."""
    _, col2, _ = st.columns([1, 2, 1])

    with col2:
        st.markdown(
            """
            <div class="login-brand">
                <h1>◈ Risk intelligence</h1>
                <p>Financial monitoring and hybrid fraud detection</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        login_tab, register_tab = st.tabs(["Log in", "Create account"])
        with login_tab:
            st.subheader("Login to Dashboard")
            with st.form("login_form"):
                email = st.text_input("Email", key="login_email")
                password = st.text_input(
                    "Password",
                    type="password",
                    key="login_password",
                )
                submitted = st.form_submit_button("Log in", use_container_width=True)
            if submitted:
                with st.spinner("Authenticating..."):
                    if AuthHandler.login(email, password):
                        st.success("Login successful! Redirecting...")
                        st.rerun()

        with register_tab:
            st.subheader("Create a viewer account")
            st.caption("New accounts have viewer access. An administrator can change your role.")
            with st.form("registration_form"):
                full_name = st.text_input("Full name", max_chars=255)
                register_email = st.text_input("Email address")
                register_password = st.text_input(
                    "Password (at least 8 characters)",
                    type="password",
                    max_chars=128,
                )
                confirm_password = st.text_input(
                    "Confirm password",
                    type="password",
                    max_chars=128,
                )
                submitted = st.form_submit_button(
                    "Create account",
                    use_container_width=True,
                )
            if submitted:
                if not full_name.strip() or not register_email.strip():
                    st.error("Enter your full name and email address.")
                elif len(register_password) < 8:
                    st.error("Password must be at least 8 characters.")
                elif register_password != confirm_password:
                    st.error("Passwords do not match.")
                elif AuthHandler.register(
                    register_email.strip(),
                    full_name.strip(),
                    register_password,
                ):
                    st.info("Log in with the email and password you just registered.")


def show_dashboard():
    """Display main dashboard with navigation."""
    # Sidebar
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <strong>◈ Risk intelligence</strong>
                <span>Fraud &amp; financial monitoring</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # User info
        user = AuthHandler.get_current_user()
        if user:
            st.markdown(f"**{user.get('email', 'User')}**")
            st.caption(f"Role: {user.get('role', 'Viewer').title()}")
            st.divider()

        # Navigation pages
        page_options = []
        page_files = {}

        for page_name, page_info in PAGES.items():
            # Skip login page
            if page_name == "Login":
                continue

            # Check role access
            allowed_roles = page_info.get("roles", [])
            if AuthHandler.can_access_page(allowed_roles):
                page_options.append(page_name)
                page_files[page_name] = page_info["file"]

        st.caption("WORKSPACE")
        if page_options:
            if st.session_state.get("page_selector") not in page_options:
                st.session_state.page_selector = page_options[0]
            selected_page = st.radio(
                "Workspace navigation",
                page_options,
                format_func=lambda name: f"{PAGES[name]['icon']}  {name}",
                key="page_selector",
                label_visibility="collapsed",
            )
        else:
            st.warning("No pages available for your role")
            selected_page = None

        st.divider()

        # Session info
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        with col2:
            if st.button("🚪 Logout", use_container_width=True):
                AuthHandler.logout()

        st.divider()

        # Footer
        st.caption("Financial Fraud Detection System v1.0")
        st.caption("Signed in · Your session survives refresh")

    # Main content
    if not AuthHandler.is_authenticated():
        st.warning("Session expired. Please login again.")
        show_login_page()
        return

    if selected_page:
        try:
            from page_loader import load_page_main

            st.markdown(
                f"""
                <div class="page-banner">
                    <div class="eyebrow">Financial risk platform</div>
                    <h1>{selected_page}</h1>
                </div>
                """,
                unsafe_allow_html=True,
            )
            load_page_main(page_files[selected_page])()

        except ImportError as e:
            st.error(f"Error loading page: {str(e)}")
        except Exception as e:
            st.error(f"Error: {str(e)}")


# Main app entry point
if __name__ == "__main__":
    def main():
        AuthHandler.restore_browser_session()
        if notice := st.session_state.pop("auth_notice", None):
            st.warning(notice)
        if AuthHandler.is_authenticated():
            show_dashboard()
        else:
            show_login_page()

    st.navigation(
        [st.Page(main, title=DASHBOARD_TITLE, default=True)],
        position="hidden",
    ).run()
