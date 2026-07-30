import streamlit as st
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_status_badge, render_terminal_logs
from kairon.streamlit_app.services.tenant_service import TenantService
from kairon.streamlit_app.services.logs_service import LogsService

inject_enterprise_styles()

render_header("Tenant Inspector & Metadata", "Deep inspect Mongo records, API key tokens, backup histories, and execution logs for a tenant.", icon="🔍")

current_user = st.session_state.get("kairon_user", "admin@kairon.io")
tenants = TenantService.get_all_tenants(user_email=current_user)

if not tenants:
    st.info("No active tenants found in database.")
else:
    companies = [t["company_name"] for t in tenants]
    default_index = 0
    if "selected_tenant_details" in st.session_state and st.session_state["selected_tenant_details"] in companies:
        default_index = companies.index(st.session_state["selected_tenant_details"])

    selected_comp = st.selectbox("Select Tenant", companies, index=default_index)
    tenant = TenantService.get_tenant_by_company(selected_comp, user_email=current_user)

    if tenant:
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Tabs breakdown
        tab_meta, tab_db, tab_invite, tab_apps, tab_backups, tab_logs = st.tabs([
            "📋 Metadata & API Keys",
            "🗄️ Database Inspector & Users",
            "✉️ Invite User",
            "🧩 Apps & Roles",
            "💾 Backup History",
            "📜 Execution Logs"
        ])

        with tab_meta:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### Provisioning Metadata")
                st.markdown(f"**Live Tenant URL:** <a href='http://{tenant['site_name']}:8080' target='_blank'>http://{tenant['site_name']}:8080</a>", unsafe_allow_html=True)
                st.json({
                    "Company Name": tenant["company_name"],
                    "Abbreviation": tenant["abbr"],
                    "Site URL": f"http://{tenant['site_name']}:8080",
                    "Tier Level": tenant["tier"],
                    "Onboarding Status": tenant["onboarding_status"],
                    "Bot ID": tenant["bot"],
                    "User": tenant["user"],
                    "Country": tenant["country"],
                    "Currency": tenant["default_currency"],
                    "Created At": tenant["created_at"]
                })
            with col2:
                st.markdown("#### Authentication & API Tokens")
                st.json({
                    "API Key": tenant.get("api_key", "usr_api_key_8f9a2b"),
                    "API Secret": "••••••••••••••••" if tenant.get("api_secret") else "sec_token_9x7c4v",
                    "Integration User": f"kairon-crm@{tenant['site_name']}",
                    "Session Login": "Active"
                })

        with tab_db:
            st.markdown(f"### 🗄️ PostgreSQL Database Inspector: `{tenant['site_name']}`")
            
            # Users Breakdown
            users_list = TenantService.get_tenant_users(tenant["site_name"], user_email=current_user)
            st.markdown(f"#### 👥 Registered Users ({len(users_list)})")
            if users_list:
                for u in users_list:
                    st.markdown(f"""
                        <div class="metric-card" style="padding: 10px 14px; margin-bottom: 8px; border-left: 3px solid #6366F1;">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <strong style="color: #FFFFFF;">{u.get('first_name') or u.get('name')}</strong> 
                                    <span style="color: #94A3B8; font-size: 0.85rem;">({u.get('email')})</span>
                                </div>
                                <div>
                                    <span style="background: rgba(99, 102, 241, 0.2); color: #818CF8; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600;">{u.get('user_type')}</span>
                                </div>
                            </div>
                            <div style="margin-top: 6px; font-size: 0.8rem; color: #CBD5E1;">
                                <strong>Roles:</strong> {', '.join(u.get('roles', [])) if u.get('roles') else 'None'}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No user records retrieved.")

            st.markdown("---")
            st.markdown("#### 🔍 Database Tables Explorer")
            tables = TenantService.get_tenant_db_tables(tenant["site_name"], user_email=current_user)
            if tables:
                st.caption(f"Total Tables in Database: **{len(tables)}**")
                
                # Priority tables at top of dropdown
                priority_tables = ["tabUser", "tabCRM Lead", "tabCRM Deal", "tabCRM Organization", "tabCRM Contact", "tabCompany"]
                sorted_tables = [t for t in priority_tables if t in tables] + sorted([t for t in tables if t not in priority_tables])
                
                selected_table = st.selectbox("Select Database Table to Inspect", sorted_tables)
                if selected_table:
                    table_rows = TenantService.get_table_data(tenant["site_name"], selected_table, limit=50, user_email=current_user)
                    st.markdown(f"**Showing latest rows from `{selected_table}` (Limit: 50):**")
                    if table_rows:
                        st.dataframe(table_rows, use_container_width=True)
                    else:
                        st.info(f"Table `{selected_table}` is currently empty.")
            else:
                st.warning("Could not fetch database tables for site.")

        with tab_invite:
            st.markdown(f"### ✉️ Invite / Create User for `{tenant['company_name']}`")
            st.caption(f"Tenant Site: `{tenant['site_name']}`")
            
            with st.form("invite_user_form"):
                new_user_email = st.text_input("User Email Address", placeholder="sales_agent@kairon.ai")
                new_user_pwd = st.text_input("Initial Password", value="Password@123", type="password")
                selected_roles = st.multiselect(
                    "Assign CRM Roles",
                    ["System Manager", "Sales Manager", "Sales User", "Desk User", "CRM Admin", "CRM User"],
                    default=["System Manager", "Sales Manager", "Sales User", "Desk User"]
                )
                
                st.markdown("<br>", unsafe_allow_html=True)
                invite_submit = st.form_submit_button("🚀 Invite & Provision User", use_container_width=True)
                
                if invite_submit:
                    if new_user_email and selected_roles:
                        with st.spinner("Provisioning user credentials on site..."):
                            res = TenantService.invite_user_to_tenant(
                                site_name=tenant["site_name"],
                                email=new_user_email.strip(),
                                roles=selected_roles,
                                password=new_user_pwd.strip(),
                                user_email=current_user
                            )
                        if res.get("status") == "success":
                            st.success(f"✅ User {new_user_email} successfully provisioned on {tenant['site_name']}!")
                            st.rerun()
                        else:
                            st.error(f"Failed to invite user: {res.get('message')}")
                    else:
                        st.warning("Please provide a valid email and select at least one role.")

        with tab_apps:
            col_a1, col_a2 = st.columns(2)
            with col_a1:
                st.markdown("#### Installed Frappe Apps")
                for app in tenant.get("installed_apps", ["frappe", "crm"]):
                    st.markdown(f"- <code>{app}</code>", unsafe_allow_html=True)

            with col_a2:
                st.markdown("#### Provisioned Roles & Landing Page")
                st.markdown(f"**Landing Route:** <code>workspace/{('CRM' if tenant['tier'] == 1 else 'Selling')}</code>", unsafe_allow_html=True)
                st.markdown("**Assigned Roles:**")
                roles = ["CRM Admin", "CRM User"] if tenant["tier"] == 1 else ["System Manager", "Sales Manager", "HR Manager", "Employee"]
                for r in roles:
                    st.markdown(f"- {r}")

        with tab_backups:
            st.markdown("#### Snapshot & Backup History")
            backup_path = tenant.get("latest_backup_path")
            if backup_path:
                st.success(f"Latest Pre-Upgrade Database Snapshot Available:")
                st.code(f"{backup_path}", language="text")
            else:
                st.info("No pre-upgrade database backups taken yet for this tenant.")

        with tab_logs:
            st.markdown("#### Recent Execution Logs")
            logs = LogsService.get_recent_logs(tenant_filter=tenant["site_name"], user_email=current_user)
            render_terminal_logs(logs)
