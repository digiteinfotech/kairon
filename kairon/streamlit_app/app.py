import os
import sys

# Ensure repository root is in sys.path for Streamlit execution
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
from kairon.streamlit_app.components.styles import inject_enterprise_styles

st.set_page_config(
    page_title="Kairon AI ↔ Frappe CRM Platform Portal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_enterprise_styles()

# Initialize Session State Variables
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "kairon_user" not in st.session_state:
    st.session_state["kairon_user"] = ""
if "kairon_user_name" not in st.session_state:
    st.session_state["kairon_user_name"] = "Guest User"
if "kairon_bot" not in st.session_state:
    st.session_state["kairon_bot"] = ""
if "available_bots" not in st.session_state:
    st.session_state["available_bots"] = {}
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
if "events_stream" not in st.session_state:
    st.session_state["events_stream"] = []

def perform_logout():
    st.session_state["kairon_user"] = ""
    st.session_state["kairon_user_name"] = "Guest User"
    st.session_state["kairon_bot"] = ""
    st.session_state["available_bots"] = {}
    st.session_state["authenticated"] = False
    st.session_state["chat_history"] = []
    st.session_state["events_stream"] = []
    if "user_email_input" in st.session_state:
        st.session_state["user_email_input"] = ""

# ==========================================
# 1. AUTHENTICATED SIDEBAR & BOT CONTEXT
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style="padding: 10px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 16px;">
            <div style="font-size: 1.25rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
                <span style="color: #6366F1;">⚡</span> KAIRON ↔ CRM
            </div>
            <div style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px;">
                Integration Framework v1.1.0
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Logged In Kairon User Account Context
    user_email_input = st.sidebar.text_input(
        "Kairon Account Email",
        value=st.session_state.get("kairon_user", ""),
        placeholder="e.g. your_email@domain.com",
        key="user_email_input"
    )
    if user_email_input and user_email_input != st.session_state.get("kairon_user"):
        st.session_state["kairon_user"] = user_email_input.strip()
        st.session_state["kairon_user_name"] = user_email_input.split("@")[0].title()
        st.session_state["authenticated"] = True
        # Dynamically refresh user's available bots from MongoDB
        try:
            from kairon.streamlit_app.services.tenant_service import TenantService
            user_bots = TenantService.get_available_bots(user_email=user_email_input.strip())
            if user_bots:
                st.session_state["available_bots"] = user_bots
                st.session_state["kairon_bot"] = list(user_bots.keys())[0]
        except Exception:
            pass
        st.rerun()

    st.markdown(f"""
        <div class="metric-card" style="padding: 12px; margin-bottom: 16px; border-left: 3px solid #6366F1;">
            <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">LOGGED IN KAIRON USER</div>
            <div style="font-size: 0.92rem; font-weight: 700; color: #FFFFFF;">{st.session_state.get('kairon_user_name', 'User')}</div>
            <div style="font-size: 0.78rem; color: #94A3B8;">{st.session_state.get('kairon_user', 'Not Logged In')}</div>
        </div>
    """, unsafe_allow_html=True)

    # Active Bot Context Dropdown
    bot_options = st.session_state["available_bots"]
    bot_keys = list(bot_options.keys())
    default_idx = 0
    if st.session_state.get("kairon_bot") in bot_keys:
        default_idx = bot_keys.index(st.session_state["kairon_bot"])

    selected_bot_id = st.selectbox(
        "Select Active Bot",
        options=bot_keys,
        format_func=lambda x: bot_options[x],
        index=default_idx
    )
    st.session_state["kairon_bot"] = selected_bot_id

    st.markdown("""
        <div style="margin-top: 8px; margin-bottom: 16px;">
            <span style='color: #34D399; font-size: 0.8rem; font-weight: 600;'>● Lead Sync Active (enable_lead_sync)</span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick System Info
    st.markdown("""
        <div class="metric-card" style="padding: 10px 14px; margin-bottom: 16px;">
            <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">GATEWAY VERSION</div>
            <div style="font-size: 0.85rem; font-weight: 700; color: #60A5FA;">v1.1.0-enterprise-hardening</div>
            <div style="font-size: 0.70rem; color: #34D399; margin-top: 2px;">● Webhook Endpoint Ready</div>
        </div>
    """, unsafe_allow_html=True)

    st.button("🚪 Logout Account", on_click=perform_logout, use_container_width=True)

# ==========================================
# 2. MULTI-PAGE NAVIGATION
# ==========================================
try:
    pg = st.navigation({
        "👑 PHASE 1: ADMIN SETUP & PROVISIONING": [
            st.Page("views/1_Dashboard.py", title="Executive Dashboard", icon="🏠"),
            st.Page("views/7_Tenant_Provisioning.py", title="Tenant Provisioning", icon="🚀"),
            st.Page("views/5_Integration_Status.py", title="Integration & Health Status", icon="⚙️"),
        ],
        "💬 PHASE 2: CUSTOMER DEMO (AI CHAT)": [
            st.Page("views/2_AI_Chat.py", title="Public AI Sales Assistant", icon="💬"),
        ],
        "📊 PHASE 3: CRM VERIFICATION & AUDIT": [
            st.Page("views/4_CRM_Leads.py", title="Synced CRM Leads Directory", icon="👥"),
            st.Page("views/3_Live_Event_Monitor.py", title="Live Telemetry Monitor", icon="📊"),
            st.Page("views/6_Audit_Logs.py", title="Webhook Audit & Replay", icon="📜"),
        ]
    })
    pg.run()
except Exception as ex:
    st.switch_page("views/1_Dashboard.py")
