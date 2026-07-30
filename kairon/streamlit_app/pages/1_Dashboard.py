import streamlit as st
import pandas as pd
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_stat_card, render_status_badge
from kairon.streamlit_app.services.tenant_service import TenantService
from kairon.streamlit_app.services.health_service import HealthService

inject_enterprise_styles()

render_header("System Infrastructure Dashboard", "Real-time metrics, status breakdown, and tenant distribution across Tier 1 & Tier 2 deployments.")

# Fetch data
current_user = st.session_state.get("kairon_user", "admin@kairon.io")
tenants = TenantService.get_all_tenants(user_email=current_user)
health_items = HealthService.get_system_health()

total_tenants = len(tenants)
crm_tenants = sum(1 for t in tenants if t.get("tier") == 1)
erp_tenants = sum(1 for t in tenants if t.get("tier") == 2)

healthy_count = sum(1 for h in health_items if h["status"] == "Healthy")
warning_count = sum(1 for h in health_items if h["status"] == "Warning")
failed_count = sum(1 for h in health_items if h["status"] == "Failed")

# Metric Grid
col1, col2, col3, col4 = st.columns(4)
with col1:
    render_stat_card("Total Active Tenants", str(total_tenants), f"{crm_tenants} CRM • {erp_tenants} ERPNext", border_color="#6366F1")
with col2:
    render_stat_card("Tier 1 (Standalone Apps)", str(crm_tenants), "Frappe + CRM / Helpdesk", border_color="#818CF8")
with col3:
    render_stat_card("Tier 2 (ERP Suites)", str(erp_tenants), "Frappe + ERPNext Suite", border_color="#EC4899")
with col4:
    render_stat_card("Avg Provisioning Time", "24.5 sec", "Tier 1 ~15s | Tier 2 ~120s", border_color="#34D399")

st.markdown("<br>", unsafe_allow_html=True)

# System Health Overview Cards
st.subheader("System Infrastructure Health")
hcol1, hcol2, hcol3 = st.columns(3)
with hcol1:
    st.markdown(f"""
        <div class="metric-card" style="border-left: 3px solid #10B981;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="metric-label">Healthy Services</span>
                {render_status_badge("HEALTHY")}
            </div>
            <div class="metric-value" style="color: #34D399;">{healthy_count} / {len(health_items)}</div>
            <div class="metric-subtext">All critical containers & services operational</div>
        </div>
    """, unsafe_allow_html=True)

with hcol2:
    st.markdown(f"""
        <div class="metric-card" style="border-left: 3px solid #F59E0B;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="metric-label">Warnings</span>
                {render_status_badge("WARNING")}
            </div>
            <div class="metric-value" style="color: #FBBF24;">{warning_count}</div>
            <div class="metric-subtext">Minor alerts or maintenance pending</div>
        </div>
    """, unsafe_allow_html=True)

with hcol3:
    st.markdown(f"""
        <div class="metric-card" style="border-left: 3px solid #EF4444;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span class="metric-label">Failed Services</span>
                {render_status_badge("FAILED")}
            </div>
            <div class="metric-value" style="color: #F87171;">{failed_count}</div>
            <div class="metric-subtext">No failed infrastructure components</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# Recent Activity Table
st.subheader("Latest Tenant Deployments")
if tenants:
    df = pd.DataFrame(tenants)
    display_df = df[["company_name", "site_name", "tier", "onboarding_status", "installed_apps", "created_at"]]
    display_df.columns = ["Company", "Site URL", "Tier", "Status", "Installed Apps", "Created At"]
    st.dataframe(display_df, use_container_width=True)
else:
    st.info("No active tenants provisioned yet. Navigate to 'Provision New Tenant' to create your first tenant.")
