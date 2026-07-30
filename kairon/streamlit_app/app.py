import streamlit as st
from kairon.streamlit_app.components.styles import inject_enterprise_styles

st.set_page_config(
    page_title="Kairon CRM & ERPNext Provisioning Portal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

inject_enterprise_styles()

# Initialize Session State Variables
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "kairon_user" not in st.session_state:
    st.session_state["kairon_user"] = "admin@kairon.io"
if "kairon_user_name" not in st.session_state:
    st.session_state["kairon_user_name"] = "Kairon Admin"
if "kairon_bot" not in st.session_state:
    st.session_state["kairon_bot"] = "bot_enterprise_01"
if "available_bots" not in st.session_state:
    st.session_state["available_bots"] = {
        "bot_enterprise_01": "Enterprise Sales Bot (bot_enterprise_01)",
        "bot_sales_crm": "Sales & Leads Bot (bot_sales_crm)",
        "bot_customer_support": "Customer Support Bot (bot_customer_support)"
    }
if "crm_enabled_bots" not in st.session_state:
    st.session_state["crm_enabled_bots"] = {"bot_enterprise_01": True}

# ==========================================
# 1. KAIRON LOGIN SCREEN (WHEN NOT LOGGED IN)
# ==========================================
if not st.session_state["authenticated"]:
    st.markdown("<br><br>", unsafe_allow_html=True)
    lcol1, lcol2, lcol3 = st.columns([1, 1.8, 1])

    with lcol2:
        st.markdown("""
            <div class="metric-card" style="padding: 30px; border-top: 4px solid #6366F1; text-align: center;">
                <div style="font-size: 2.5rem; margin-bottom: 10px;">⚡</div>
                <h2 style="color: #FFFFFF; font-weight: 800; margin-bottom: 4px;">Kairon Platform Login</h2>
                <p style="color: #94A3B8; font-size: 0.9rem; margin-bottom: 24px;">Sign in with your Kairon User credentials to manage CRM & ERPNext tenant provisioning.</p>
            </div>
        """, unsafe_allow_html=True)

        with st.form("kairon_login_form"):
            user_preset = st.selectbox(
                "Select Kairon User Account",
                ["admin@kairon.io", "arya@kairon.ai", "harsh@kairon.ai", "soham@kairon.ai", "aditya@kairon.ai", "geet_demo@kairon.ai", "test@demo.in"],
                help="Select your registered Kairon user to load your specific bots from MongoDB."
            )
            user_email = st.text_input("Kairon User Email / Username", value=user_preset)
            user_password = st.text_input("Password", value="••••••••••••", type="password")

            st.markdown("<br>", unsafe_allow_html=True)
            login_submit = st.form_submit_button("🔑 Sign In to Kairon", use_container_width=True)

            if login_submit:
                if user_email and user_password:
                    st.session_state["authenticated"] = True
                    st.session_state["kairon_user"] = user_email.strip()
                    st.session_state["kairon_user_name"] = user_email.split("@")[0].title()
                    st.session_state["access_token"] = "mock_kairon_jwt_token_12345"
                    st.success(f"Authenticated as {user_email}! Loading user's bots from MongoDB...")
                    st.rerun()
                else:
                    st.error("Please enter valid username and password.")

        st.markdown("<br>", unsafe_allow_html=True)
        dev_bypass = st.button("⚡ Quick Dev Login (Demo Access)", use_container_width=True)
        if dev_bypass:
            st.session_state["authenticated"] = True
            st.session_state["kairon_user"] = "admin@kairon.io"
            st.session_state["kairon_user_name"] = "Admin User"
            st.session_state["access_token"] = "dev_kairon_token"
            st.rerun()

    st.stop()


# ==========================================
# 2. AUTHENTICATED SIDEBAR & BOT CONTEXT
# ==========================================
with st.sidebar:
    st.markdown("""
        <div style="padding: 10px 0; border-bottom: 1px solid var(--border-color); margin-bottom: 16px;">
            <div style="font-size: 1.2rem; font-weight: 800; color: #FFFFFF; display: flex; align-items: center; gap: 8px;">
                <span>⚡</span> KAIRON ADMIN
            </div>
            <div style="font-size: 0.78rem; color: var(--text-secondary); margin-top: 2px;">
                Hybrid Provisioning Platform
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Logged In User Card
    st.markdown(f"""
        <div class="metric-card" style="padding: 12px; margin-bottom: 16px; border-left: 3px solid #6366F1;">
            <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">LOGGED IN USER</div>
            <div style="font-size: 0.9rem; font-weight: 700; color: #FFFFFF;">{st.session_state.get('kairon_user_name', 'User')}</div>
            <div style="font-size: 0.78rem; color: #94A3B8;">{st.session_state.get('kairon_user', 'admin@kairon.io')}</div>
        </div>
    """, unsafe_allow_html=True)

    # Active Bot Context Dropdown (Filtered for logged-in user from MongoDB 'conversations.bot')
    st.subheader("Active Bot Context")
    from kairon.streamlit_app.services.tenant_service import TenantService

    current_user_email = st.session_state.get("kairon_user", "admin@kairon.io")
    real_bots = TenantService.get_available_bots(user_email=current_user_email)
    bot_options = real_bots if real_bots else {"bot_enterprise_01": "Enterprise Sales Bot (bot_enterprise_01)"}

    default_idx = 0
    bot_keys = list(bot_options.keys())
    if st.session_state.get("kairon_bot") in bot_keys:
        default_idx = bot_keys.index(st.session_state["kairon_bot"])

    selected_bot_id = st.selectbox(
        "Select Active Bot",
        options=bot_keys,
        format_func=lambda x: bot_options[x],
        index=default_idx
    )
    st.session_state["kairon_bot"] = selected_bot_id

    # Dynamic MongoDB CRM Capability Status Check
    mongo_crm_enabled = TenantService.get_bot_crm_status(selected_bot_id)
    crm_toggle = st.toggle("Enable CRM / ERPNext for Bot (Sync MongoDB)", value=mongo_crm_enabled, key=f"toggle_{selected_bot_id}")

    if crm_toggle != mongo_crm_enabled:
        TenantService.set_bot_crm_status(selected_bot_id, crm_toggle)
        st.toast(f"MongoDB updated: enable_crm = {crm_toggle} for Bot {selected_bot_id}", icon="💾")
        st.rerun()

    if crm_toggle:
        st.markdown("<span style='color: #34D399; font-size: 0.8rem;'>● CRM Capability Active (MongoDB: True)</span>", unsafe_allow_html=True)
    else:
        st.markdown("<span style='color: #F87171; font-size: 0.8rem;'>○ CRM Capability Disabled (MongoDB: False)</span>", unsafe_allow_html=True)

    st.markdown("---")

    # Logout Button
    if st.button("🚪 Logout from Kairon", use_container_width=True):
        st.session_state["authenticated"] = False
        st.session_state.pop("access_token", None)
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("""
        <div class="metric-card" style="padding: 10px 14px;">
            <div style="font-size: 0.72rem; color: var(--text-muted); font-weight: 600;">BACKEND CONTAINER</div>
            <div style="font-size: 0.85rem; font-weight: 700; color: #60A5FA;">frappe-backend-1</div>
            <div style="font-size: 0.70rem; color: #34D399; margin-top: 2px;">● Docker Connected</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='font-size: 0.72rem; color: var(--text-muted); margin-top: 10px;'>KAIRON PLATFORM v2.4</div>", unsafe_allow_html=True)


# ==========================================
# 3. PAGE NAVIGATION
# ==========================================
try:
    pg = st.navigation([
        st.Page("pages/1_Dashboard.py", title="Dashboard", icon="📊"),
        st.Page("pages/2_Provision_New_Tenant.py", title="Provision New Tenant", icon="🚀"),
        st.Page("pages/3_Upgrade_Tenant.py", title="Upgrade Tenant", icon="⬆️"),
        st.Page("pages/4_Tenants.py", title="Tenants Directory", icon="🏢"),
        st.Page("pages/5_Tenant_Details.py", title="Tenant Details", icon="🔍"),
        st.Page("pages/6_Logs.py", title="System Logs", icon="📜"),
        st.Page("pages/7_Health.py", title="Infrastructure Health", icon="🩺"),
        st.Page("pages/8_Settings.py", title="Settings", icon="⚙️")
    ])
    pg.run()
except AttributeError:
    st.switch_page("pages/1_Dashboard.py")
