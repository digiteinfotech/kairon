import streamlit as st
from components.ui import inject_custom_css, render_sidebar, get_status_badge, glass_card
from services.crm import CrmService

# Page configuration
st.set_page_config(page_title="Provision Details", page_icon="🔍", layout="wide")
inject_custom_css()
render_sidebar()

# Check authentication
token = st.session_state.get("access_token")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()

# Handle Bot ID from Query Parameter (for History Log links)
query_params = st.query_params
param_bot_id = query_params.get("bot_id")

if param_bot_id:
    st.session_state["selected_bot_id"] = param_bot_id
    st.query_params.clear()
    st.rerun()

inspect_bot_id = st.session_state.get("selected_bot_id")

st.markdown('# 🔍 CRM Instance <span class="gradient-text">Inspector</span>', unsafe_allow_html=True)
st.markdown("---")

if not inspect_bot_id:
    st.info("Please select a chatbot context in the sidebar or from the History list to inspect details.")
    st.stop()

# Load details
with st.spinner("Fetching configuration metadata..."):
    details = CrmService.get_crm_details(inspect_bot_id)

if not details:
    st.warning(f"No CRM provisioning configurations found for Bot ID: `{inspect_bot_id}`.")
    st.stop()

# Header Information
st.markdown(f"## 🏢 {details.get('company_name')} Details")
st.caption(f"Bot ID: `{inspect_bot_id}` | Abbr: `{details.get('abbr')}`")

col_meta, col_conn = st.columns(2)

with col_meta:
    started_at = details.get("workflow_started_at")
    completed_at = details.get("workflow_completed_at")
    started_str = started_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(started_at, "strftime") else str(started_at or "N/A")
    completed_str = completed_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(completed_at, "strftime") else str(completed_at or "N/A")
    last_err = details.get("last_error")
    lock_html = f"<p><b>Lock Timestamp:</b> {details.get('lock_timestamp')}</p>" if details.get("lock") else ""
    err_html = f"<div style='color:#ef4444; border:1px solid #fca5a5; background-color:#fee2e2; padding:10px; border-radius:6px; margin-top:10px;'><b>Last Recorded Error:</b> {last_err}</div>" if last_err else ""

    st.markdown(
        f"""
        <div class="glass-card">
            <h3>📋 Provisioning Metadata</h3>
            <p><b>Status:</b> {get_status_badge(details.get('onboarding_status'))}</p>
            <p><b>Provision ID:</b> <code>{details.get('provisioning_id', 'N/A')}</code></p>
            <p><b>Deployment Started:</b> {started_str}</p>
            <p><b>Deployment Completed:</b> {completed_str}</p>
            <p><b>Operation Lock:</b> {'Locked' if details.get('lock') else 'Unlocked'}</p>
            {lock_html}
            {err_html}
        </div>
        """,
        unsafe_allow_html=True
    )

with col_conn:
    st.markdown(
        f"""
        <div class="glass-card">
            <h3>🗄️ Database Connection</h3>
            <p><b>PostgreSQL Host:</b> <code>{details.get('postgres_host', 'N/A')}</code></p>
            <p><b>PostgreSQL Port:</b> <code>{details.get('postgres_port', '5432')}</code></p>
            <p><b>Database Name:</b> <code>{details.get('db_name', 'N/A')}</code></p>
            <p><b>Database User:</b> <code>{details.get('db_user', 'N/A')}</code></p>
            <p><b>Database Password:</b> <code>••••••••••••</code> <i>(encrypted)</i></p>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("<br>", unsafe_allow_html=True)

# ERPNext configuration details
st.markdown("### 🌐 ERPNext Instance Information")
col_erp1, col_erp2 = st.columns(2)

with col_erp1:
    site_url = details.get("erpnext_site")
    site_link_html = f"<a href='http://{site_url}:8080' target='_blank'>http://{site_url}:8080</a>" if site_url else "Not provisioned yet."
    st.markdown(
        f"""
        <div class="glass-card">
            <h4>🔗 Web Access</h4>
            <p><b>Site URL:</b> {site_link_html}</p>
            <p><b>Local Site Name:</b> <code>{details.get('site_name', 'N/A')}</code></p>
            <p><b>Owner/Admin Email:</b> <code>{details.get('erpnext_owner_email', 'N/A')}</code></p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_erp2:
    st.markdown(
        f"""
        <div class="glass-card">
            <h4>📦 App Environment</h4>
            <p><b>ERPNext User:</b> <code>{details.get('erpnext_user', 'Administrator')}</code></p>
            <p><b>ERPNext Password:</b> <code>{details.get('erpnext_password', 'Password@123')}</code></p>
            <p><b>Installed Apps:</b> <code>frappe, erpnext</code></p>
            <p><b>App Version:</b> <code>v16.x (stable)</code></p>
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown("---")

# Module Configuration Section
st.markdown("### 🧩 Provisioned Business Modules")
selected_mods = details.get("selected_modules") or ["CRM"]
profile_name = details.get("module_profile_name") or f"Kairon CRM Profile ({details.get('company_name')})"

col_mod1, col_mod2 = st.columns([3, 1])
with col_mod1:
    mod_badges = " ".join([f"<span style='background:#3b82f6; color:white; padding:4px 10px; border-radius:12px; font-weight:600; font-size:13px; margin-right:5px;'>{m}</span>" for m in selected_mods])
    st.markdown(
        f"""
        <div class="glass-card">
            <h4>Enabled Modules</h4>
            <div style="margin-top:10px; margin-bottom:10px;">{mod_badges}</div>
            <p><b>ERPNext Module Profile:</b> <code>{profile_name}</code></p>
        </div>
        """,
        unsafe_allow_html=True
    )

with col_mod2:
    if st.button("🔄 Reconcile Drift", use_container_width=True, help="Re-verify and repair workspace hiding & module profile configuration on ERPNext."):
        with st.spinner("Reconciling module configuration on ERPNext..."):
            try:
                report = CrmService.reconcile_modules(inspect_bot_id)
                st.success("Reconciliation complete!")
                st.json(report)
            except Exception as e:
                st.error(f"Reconciliation failed: {e}")

with st.expander("⚙️ Manage Module Selection"):
    available_data = CrmService.get_available_modules(inspect_bot_id)
    avail_modules = available_data.get("modules", [])
    if not avail_modules:
        avail_modules = [
            {"key": "CRM", "workspace": "CRM", "description": "Leads, Deals, Campaigns, and Opportunity Pipeline"},
            {"key": "POS", "workspace": "POS", "description": "Point of Sale retail transactions"},
            {"key": "HR", "workspace": "HR", "description": "Employees, Leaves, and Payroll"},
            {"key": "Projects", "workspace": "Projects", "description": "Tasks and Timesheets"},
            {"key": "Support", "workspace": "Support", "description": "Service Tickets"},
            {"key": "Quality", "workspace": "Quality", "description": "Quality Inspections"},
            {"key": "Buying", "workspace": "Buying", "description": "Purchase Orders"},
            {"key": "Selling", "workspace": "Selling", "description": "Sales Orders"},
            {"key": "Stock", "workspace": "Stock", "description": "Inventory and Warehouses"},
            {"key": "Manufacturing", "workspace": "Manufacturing", "description": "Work Orders"},
            {"key": "Assets", "workspace": "Assets", "description": "Asset Tracking"},
            {"key": "Maintenance", "workspace": "Maintenance", "description": "Equipment Maintenance"}
        ]
    all_keys = [m["key"] for m in avail_modules]
    
    with st.form("update_modules_form"):
        new_selection = st.multiselect(
            "Active Modules",
            options=all_keys,
            default=[k for k in selected_mods if k in all_keys]
        )
        submit_mod_update = st.form_submit_button("Save & Update ERPNext Instance")
        
        if submit_mod_update:
            if not new_selection:
                st.error("Select at least one module.")
            else:
                with st.spinner("Applying module changes live on ERPNext..."):
                    try:
                        res = CrmService.configure_modules(inspect_bot_id, new_selection)
                        st.success("Module configuration updated successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to update module selection: {e}")

st.markdown("---")

# Collaborators / Users Manager
st.markdown("### 👥 Collaborators & CRM Roles")

# Create CRM user form
with st.expander("➕ Add Collaborator User"):
    with st.form("add_user_form"):
        new_user_email = st.text_input("User Email", placeholder="collaborator@company.com")
        new_user_role = st.selectbox("CRM Role", ["CRM User", "CRM Manager", "Sales User", "Sales Manager", "System Manager"])
        submit_user = st.form_submit_button("Add User")
        
        if submit_user:
            if not new_user_email:
                st.error("Email is required.")
            else:
                with st.spinner("Adding user to CRM instance..."):
                    try:
                        CrmService.create_crm_user(inspect_bot_id, new_user_email, new_user_role)
                        st.success(f"Successfully added {new_user_email} as {new_user_role}!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to add user: {e}")

# Existing users display
st.markdown("#### Owner & Assigned Roles")
roles_list = details.get("erpnext_roles", [])
admin_email = details.get('erpnext_owner_email') or details.get('db_user') or "N/A"
if roles_list:
    st.write(f"👑 **{admin_email}** — Roles: `{', '.join(roles_list)}`")
else:
    st.write(f"👑 **{admin_email}** (Role: `System Manager`) — *Default Admin*")

st.markdown("---")

# Database Tables Inspector
st.markdown("### 📊 Database Schema & Tables")
with st.expander("🗂️ View Database Tables & Content", expanded=False):
    if st.button("🔄 Fetch / Refresh Tables List"):
        with st.spinner("Querying database tables..."):
            tables = CrmService.get_db_tables(inspect_bot_id)
            st.session_state[f"tables_{inspect_bot_id}"] = tables

    cached_tables = st.session_state.get(f"tables_{inspect_bot_id}")
    if cached_tables is None:
        with st.spinner("Loading database tables..."):
            cached_tables = CrmService.get_db_tables(inspect_bot_id)
            st.session_state[f"tables_{inspect_bot_id}"] = cached_tables

    if cached_tables:
        st.write(f"Found **{len(cached_tables)}** total tables in database `{(details.get('db_name') or 'erpnext')}`:")
        
        col_tbl_select, col_tbl_search = st.columns([2, 1])
        with col_tbl_search:
            search_table = st.text_input("🔍 Filter Tables List", placeholder="e.g. tabCompany, tabUser...")
        
        filtered_tables = [t for t in cached_tables if search_table.lower() in t.lower()] if search_table else cached_tables
        
        default_index = 0
        options_list = ["-- Select a Table --"] + filtered_tables
        if "tabCompany" in filtered_tables and "-- Select a Table --" in options_list:
            default_index = options_list.index("tabCompany")

        with col_tbl_select:
            selected_table = st.selectbox(
                "📋 Select Table to View Content",
                options=options_list,
                index=default_index
            )

        if selected_table and selected_table != "-- Select a Table --":
            st.markdown(f"#### 📄 Content Preview: `{selected_table}`")
            row_limit = st.slider("Max Rows", min_value=5, max_value=200, value=50, step=5)
            
            with st.spinner(f"Loading content for {selected_table}..."):
                table_content = CrmService.get_table_content(inspect_bot_id, selected_table, limit=row_limit)
                
            if table_content:
                st.success(f"Fetched **{len(table_content)}** rows from `{selected_table}`.")
                st.dataframe(table_content, use_container_width=True)
            else:
                st.info(f"Table `{selected_table}` is empty or has no records.")

        st.markdown("---")
        st.markdown("##### 📁 Complete Tables Directory")
        st.dataframe(
            [{"Index": i+1, "Table Name": t} for i, t in enumerate(filtered_tables)],
            use_container_width=True,
            height=200
        )
    else:
        st.info("No tables retrieved or database site not fully initialized.")

