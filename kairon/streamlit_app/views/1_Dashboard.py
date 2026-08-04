import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
import datetime
from kairon.streamlit_app.components.styles import inject_enterprise_styles

inject_enterprise_styles()

st.markdown("""
    <div class="portal-header">
        <div class="portal-title">
            <span>🏠</span> Executive Operations Dashboard
        </div>
        <div class="portal-subtitle">
            Kairon AI Conversational Engine ↔ Frappe CRM Deep Integration Framework (v1.1.0)
        </div>
    </div>
""", unsafe_allow_html=True)

# 1. Dynamic Tenant Lookup
from kairon.streamlit_app.services.tenant_service import TenantService

current_user = st.session_state.get("kairon_user", "")
active_bot = st.session_state.get("kairon_bot", "")
user_tenants = TenantService.get_all_tenants(user_email=current_user) if current_user else []

tenant_info = next((t for t in user_tenants if t.get("bot") == active_bot), None)
if not tenant_info and user_tenants:
    tenant_info = user_tenants[0]

company_display = tenant_info.get("company_name", "No Active Company") if tenant_info else ("Please Log In" if not current_user else "No Active Company")
site_display = tenant_info.get("site_name", "72.60.10.158:8000") if tenant_info else "No Active Site"
active_bot_display = active_bot if active_bot else "No Bot Connected"

if not current_user:
    st.info("🔒 **Welcome to Kairon ↔ Frappe CRM Portal**. Enter your **Kairon Account Email** in the sidebar to load your company & CRM resources.")

# Summary Header Cards
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #6366F1;">
            <div class="metric-label">TENANT COMPANY</div>
            <div class="metric-value" style="font-size: 1.3rem;">{company_display}</div>
            <div class="metric-subtext">User: {current_user}</div>
        </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #10B981;">
            <div class="metric-label">PROVISIONED CRM SITE</div>
            <div class="metric-value" style="font-size: 1.1rem; color: #60A5FA;">{site_display}</div>
            <div class="metric-subtext"><span class="badge badge-healthy">● Site Active</span></div>
        </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
        <div class="metric-card" style="border-top: 3px solid #F59E0B;">
            <div class="metric-label">CONNECTED KAIRON BOT</div>
            <div class="metric-value" style="font-size: 1.1rem; color: #FBBF24;">{active_bot}</div>
            <div class="metric-subtext">AI Sales Representative</div>
        </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown("""
        <div class="metric-card" style="border-top: 3px solid #EC4899;">
            <div class="metric-label">FRAMEWORK HEALTH</div>
            <div class="metric-value" style="font-size: 1.3rem; color: #34D399;">100% HEALTHY</div>
            <div class="metric-subtext">v1.1.0-enterprise-hardening</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 2. Key Metrics Row
m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown("""
        <div class="metric-card">
            <div class="metric-label">TOTAL CRM LEADS</div>
            <div class="metric-value">12</div>
            <div class="metric-subtext" style="color: #34D399;">↑ Automatically ingested from Bot</div>
        </div>
    """, unsafe_allow_html=True)

with m2:
    st.markdown("""
        <div class="metric-card">
            <div class="metric-label">WEBHOOK INGESTION</div>
            <div class="metric-value" style="color: #60A5FA;">202 OK</div>
            <div class="metric-subtext">HMAC Signed Gateway</div>
        </div>
    """, unsafe_allow_html=True)

with m3:
    st.markdown("""
        <div class="metric-card">
            <div class="metric-label">DEDUPLICATION</div>
            <div class="metric-value" style="color: #A78BFA;">Redis Active</div>
            <div class="metric-subtext">Transport & Business Idempotent</div>
        </div>
    """, unsafe_allow_html=True)

with m4:
    st.markdown("""
        <div class="metric-card">
            <div class="metric-label">REPLAY SERVICE</div>
            <div class="metric-value" style="color: #34D399;">0 Failures</div>
            <div class="metric-subtext">MAX_REPLAY_LIMIT = 5 Safeguard</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 3. Quick Action Cards Shortcuts
st.subheader("⚡ Integration Shortcuts & Quick Actions")
qa1, qa2, qa3 = st.columns(3)

with qa1:
    st.markdown("""
        <div class="metric-card" style="padding: 20px; border-left: 4px solid #6366F1;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #FFFFFF;">💬 AI Chatbot Demonstrator</div>
            <p style="color: #9CA3AF; font-size: 0.85rem; margin-top: 6px;">Test the AI sales bot conversation flow. When a lead is qualified, it automatically dispatches signed events to Frappe CRM.</p>
        </div>
    """, unsafe_allow_html=True)
    if st.button("🚀 Open AI Chatbot", use_container_width=True, key="btn_chat"):
        st.switch_page("views/2_AI_Chat.py")

with qa2:
    st.markdown("""
        <div class="metric-card" style="padding: 20px; border-left: 4px solid #10B981;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #FFFFFF;">👥 CRM Leads Directory</div>
            <p style="color: #9CA3AF; font-size: 0.85rem; margin-top: 6px;">View real-time leads created in the PostgreSQL database of your provisioned CRM tenant site.</p>
        </div>
    """, unsafe_allow_html=True)
    if st.button("📊 View CRM Leads", use_container_width=True, key="btn_leads"):
        st.switch_page("views/4_CRM_Leads.py")

with qa3:
    st.markdown("""
        <div class="metric-card" style="padding: 20px; border-left: 4px solid #3B82F6;">
            <div style="font-size: 1.2rem; font-weight: 700; color: #FFFFFF;">🌐 Open CRM Web Portal</div>
            <p style="color: #9CA3AF; font-size: 0.85rem; margin-top: 6px;">Launch the live Frappe CRM application user interface in a new browser tab.</p>
        </div>
    """, unsafe_allow_html=True)
    st.link_button("🔗 Open Frappe CRM Site", "http://72.60.10.158:8000", use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# 4. Recent Integration Activity Table
st.subheader("📋 Recent Lead Ingestion Summary")
demo_leads = [
    {"Time": "Just Now", "Lead Name": "Sarah Connor", "Email": "sarah.c@cyberdyne.io", "Company": "Cyberdyne Systems", "Source": "Kairon Chatbot", "Status": "Qualified", "Conversation ID": "conv_998877"},
    {"Time": "12 mins ago", "Lead Name": "Alexander Wright", "Email": "a.wright@apextech.com", "Company": "Apex Technologies", "Source": "Kairon Chatbot", "Status": "Qualified", "Conversation ID": "conv_998876"},
    {"Time": "45 mins ago", "Lead Name": "Elena Rostova", "Email": "elena@vanguard.de", "Company": "Vanguard GmbH", "Source": "Kairon Chatbot", "Status": "Contacted", "Conversation ID": "conv_998875"},
    {"Time": "2 hours ago", "Lead Name": "Marcus Vance", "Email": "marcus@innovate.co", "Company": "Innovate Labs", "Source": "Kairon Chatbot", "Status": "Qualified", "Conversation ID": "conv_998874"},
]

st.dataframe(demo_leads, use_container_width=True)
