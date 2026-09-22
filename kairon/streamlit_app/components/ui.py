import os
import streamlit as st
from services.crm import CrmService

# Path to styles.css relative to app.py
CSS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "styles.css"))

def inject_custom_css():
    """Load and inject custom styles.css into the Streamlit app."""
    if os.path.exists(CSS_PATH):
        with open(CSS_PATH, "r") as f:
            css = f.read()
            st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    else:
        st.warning("Custom CSS file not found.")

def render_sidebar():
    """Render standard sidebar header, logged-in status, bot selection, and navigation links."""
    st.sidebar.markdown(
        '# <span class="gradient-text">Kairon CRM</span>',
        unsafe_allow_html=True
    )
    st.sidebar.markdown("---")

    token = st.session_state.get("access_token")
    if not token:
        st.sidebar.info("Please log in to continue.")
        return

    # Fetch and show user info
    try:
        user_info = st.session_state.get("user_info")
        if not user_info:
            user_info = CrmService.get_user_details()
            st.session_state["user_info"] = user_info
        
        email = user_info.get("email", "User")
        name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip() or email
        
        st.sidebar.write("Logged in as:")
        st.sidebar.subheader(name)
        st.sidebar.caption(email)

        # Bot Selection Dropdown
        bots = CrmService.get_bots()
        if bots:
            bot_options = {b["_id"]: b["name"] for b in bots}
            selected_bot_id = st.sidebar.selectbox(
                "Active Bot Context",
                options=list(bot_options.keys()),
                format_func=lambda x: bot_options[x],
                index=0 if "selected_bot_id" not in st.session_state else list(bot_options.keys()).index(st.session_state["selected_bot_id"])
            )
            st.session_state["selected_bot_id"] = selected_bot_id
            st.session_state["selected_bot_name"] = bot_options[selected_bot_id]
        else:
            st.sidebar.warning("No bots found for this account.")
            
    except Exception as e:
        st.sidebar.error(f"Error loading profile: {e}")

    st.sidebar.markdown("---")
    
    # Logout action
    if st.sidebar.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

def get_status_badge(status: str) -> str:
    """Return HTML content for a colored status badge."""
    if not status:
        return ""
    
    status_lower = status.lower()
    
    if "completed" in status_lower or "healthy" in status_lower:
        badge_class = "badge-completed"
    elif "fail" in status_lower or "error" in status_lower:
        badge_class = "badge-failed"
    elif "run" in status_lower or "creat" in status_lower:
        badge_class = "badge-running"
    else:
        badge_class = "badge-pending"
        
    return f'<span class="badge {badge_class}">{status}</span>'

def glass_card(title: str, value: str, subtitle: str = "", icon: str = "📊"):
    """Render a premium glassmorphism metric card."""
    st.markdown(
        f"""
        <div class="glass-card">
            <div style="display: flex; align-items: center; gap: 15px;">
                <div style="font-size: 2rem;">{icon}</div>
                <div class="metric-container">
                    <div class="metric-title">{title}</div>
                    <div class="metric-value">{value}</div>
                    {"<div class='metric-subtitle'>" + subtitle + "</div>" if subtitle else ""}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
