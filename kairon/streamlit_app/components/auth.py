"""
Authentication & session-state helpers for the Kairon Streamlit demo portal.

This module is a thin UI wrapper around the real Kairon authentication API
(``POST /api/auth/login`` and ``GET /api/user/details``) via ``services.crm.CrmService``.
No credentials are ever hardcoded and no password is stored in session state -
only the short-lived JWT access token returned by the backend is kept, exactly
as the backend already scopes it (per-user, per-bot via token claims).
"""
import streamlit as st
from services.crm import CrmService

SESSION_KEYS = [
    "access_token",
    "user_info",
    "selected_bot_id",
    "selected_bot_name",
    "crm_enabled",
    "onboarding_step",
    "provisioning_inflight",
    "provisioning_result",
    "last_onboard_request_key",
]


def is_authenticated() -> bool:
    return bool(st.session_state.get("access_token"))


def do_login(username: str, password: str) -> None:
    """Authenticate against the real Kairon backend. Raises on failure."""
    CrmService.login(username.strip(), password)
    # Populate user profile immediately so the rest of the app has real data.
    st.session_state["user_info"] = CrmService.get_user_details()


def do_logout() -> None:
    """Clear all authentication/session state. Does not touch the backend session store."""
    for key in SESSION_KEYS:
        st.session_state.pop(key, None)
    from services.api import ApiClient
    ApiClient.clear_token()


def require_login():
    """Stop page execution and render nothing further if the user is not authenticated."""
    if not is_authenticated():
        st.warning("Please log in to continue.")
        st.stop()


def render_login_form():
    """Renders the Kairon login form. Returns True if login just succeeded (for a rerun)."""
    st.markdown(
        """
        <div style="max-width:420px;margin:8vh auto 0 auto;">
            <div style="text-align:center;margin-bottom:28px;">
                <div style="font-size:2rem;">⚡</div>
                <div style="font-size:1.6rem;font-weight:800;color:#F3F4F6;">Kairon Platform</div>
                <div style="color:#9CA3AF;font-size:0.9rem;margin-top:4px;">Sign in with your Kairon account</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        with st.form("kairon_login_form", clear_on_submit=False):
            username = st.text_input("Email", placeholder="you@company.com")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submitted:
            if not username.strip() or not password:
                st.error("Email and password are required.")
                return False
            with st.spinner("Authenticating with Kairon..."):
                try:
                    do_login(username, password)
                    st.rerun()
                except Exception as e:
                    msg = str(e)
                    if "credential" in msg.lower() or "auth" in msg.lower() or "password" in msg.lower():
                        st.error("Invalid Kairon credentials.")
                    else:
                        st.error(f"Login failed: {msg}")
                    return False
    return False
