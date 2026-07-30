import streamlit as st
import pandas as pd
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_status_badge
from kairon.streamlit_app.services.tenant_service import TenantService

inject_enterprise_styles()

render_header("Tenant Directory & Management", "Manage, inspect, and monitor all provisioned Frappe CRM and ERPNext tenant instances.", icon="🏢")

current_user = st.session_state.get("kairon_user", "admin@kairon.io")
tenants = TenantService.get_all_tenants(user_email=current_user)

# Search & Filters
col_search, col_tier, col_status = st.columns([2, 1, 1])

with col_search:
    search_query = st.text_input("🔍 Search by Company or Subdomain", value="")
with col_tier:
    tier_filter = st.selectbox("Filter Tier", ["All Tiers", "Tier 1 (Standalone)", "Tier 2 (ERP Suite)"])
with col_status:
    status_filter = st.selectbox("Filter Status", ["All Statuses", "SITE_CREATED", "UPGRADING_TO_TIER_2", "FAILED_UPGRADE"])

# Filter logic
filtered_tenants = tenants
if search_query:
    filtered_tenants = [t for t in filtered_tenants if search_query.lower() in t["company_name"].lower() or search_query.lower() in t["site_name"].lower()]

if tier_filter != "All Tiers":
    target_tier = 1 if "Tier 1" in tier_filter else 2
    filtered_tenants = [t for t in filtered_tenants if t.get("tier") == target_tier]

if status_filter != "All Statuses":
    filtered_tenants = [t for t in filtered_tenants if t.get("onboarding_status") == status_filter]

st.markdown("<br>", unsafe_allow_html=True)

if not filtered_tenants:
    st.info("No tenants match the specified search filters.")
else:
    df = pd.DataFrame(filtered_tenants)
    # Prepend http:// and port 8080 to ensure links work properly for the Frappe frontend
    df["site_name"] = df["site_name"].apply(lambda x: f"http://{x}:8080" if not x.startswith("http") else x)
    
    display_df = df[["company_name", "site_name", "tier", "onboarding_status", "installed_apps", "bot", "created_at"]]
    display_df.columns = ["Company Name", "Site URL", "Tier", "Status", "Installed Apps", "Bot ID", "Created At"]
    
    st.dataframe(
        display_df, 
        use_container_width=True,
        column_config={
            "Site URL": st.column_config.LinkColumn(
                "Site URL",
                help="Click to open the live tenant site",
                display_text="Open Site"
            )
        }
    )

    st.markdown("<br>### Tenant Actions", unsafe_allow_html=True)
    selected_comp = st.selectbox("Select Tenant to Manage", [t["company_name"] for t in filtered_tenants])

    act1, act2, act3 = st.columns(3)
    with act1:
        if st.button("👁️ View Full Details", use_container_width=True):
            st.session_state["selected_tenant_details"] = selected_comp
            st.switch_page("pages/5_Tenant_Details.py")
    with act2:
        if st.button("⬆️ Upgrade to Tier 2", use_container_width=True):
            st.switch_page("pages/3_Upgrade_Tenant.py")
    with act3:
        if st.button("🗑️ Delete Tenant Record", use_container_width=True):
            if TenantService.delete_tenant(selected_comp, user_email=current_user):
                st.success(f"Tenant '{selected_comp}' record removed.")
                st.rerun()
            else:
                st.error("Failed to delete tenant record.")
