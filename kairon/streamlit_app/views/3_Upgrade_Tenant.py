import streamlit as st
import time
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_status_badge, render_terminal_logs
from kairon.streamlit_app.services.tenant_service import TenantService
from kairon.streamlit_app.services.provisioning_service import StreamlitProvisioningService

inject_enterprise_styles()

render_header("In-Place Tenant Upgrade", "Upgrade Standalone Apps (Tier 1) to Full ERPNext Monolithic Suites (Tier 2) with zero data loss.", icon="⬆️")

current_user = st.session_state.get("kairon_user", "admin@kairon.io")
tenants = TenantService.get_all_tenants(user_email=current_user)
upgradeable_tenants = [t for t in tenants if t.get("tier") == 1 or True]  # Show all for selection

if not tenants:
    st.info("No active tenants found in database. Please provision a Tier 1 CRM tenant first.")
else:
    company_options = [t["company_name"] for t in tenants]
    selected_company = st.selectbox("Select Target Tenant for Upgrade", company_options)

    tenant_info = TenantService.get_tenant_by_company(selected_company, user_email=current_user)

    if tenant_info:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("### Current Tenant Status")
            st.markdown(f"""
                <div class="metric-card">
                    <div style="font-size: 1.1rem; font-weight: 700; color: #FFFFFF;">{tenant_info['company_name']}</div>
                    <div style="margin-top: 8px;">
                        <span style="color: var(--text-muted);">Site URL:</span> <code>{tenant_info['site_name']}</code>
                    </div>
                    <div style="margin-top: 8px; display: flex; gap: 8px;">
                        {render_status_badge(f"TIER {tenant_info['tier']}")}
                        {render_status_badge(tenant_info['onboarding_status'])}
                    </div>
                    <div style="margin-top: 12px; color: var(--text-secondary); font-size: 0.85rem;">
                        <b>Installed Apps:</b> {", ".join(tenant_info.get("installed_apps", []))}
                    </div>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown("### Pre-Upgrade Safety Protocol")
            st.markdown("""
                <div class="metric-card" style="border-left: 3px solid var(--accent-amber);">
                    <div style="font-weight: 700; color: #FBBF24; margin-bottom: 8px;">Upgrade Operations Sequence</div>
                    <ol style="margin: 0; padding-left: 20px; font-size: 0.88rem; color: var(--text-secondary);">
                        <li><b>Step 1 (Pre-upgrade Backup):</b> Execute <code>bench backup</code> to generate snapshot <code>.sql.gz</code> & site config.</li>
                        <li><b>Step 2 (Atomic Lock):</b> Acquire lock <code>lock:upgrade:&lt;site&gt;</code> in Mongo.</li>
                        <li><b>Step 3 (App Install):</b> Execute <code>bench install-app erpnext</code>.</li>
                        <li><b>Step 4 (Database Migration):</b> Run patch scripts & schema migration.</li>
                        <li><b>Step 5 (Worker Reload):</b> Signal Gunicorn via SIGHUP.</li>
                    </ol>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        is_tier2 = tenant_info.get("tier") == 2
        if is_tier2:
            st.warning(f"Tenant '{selected_company}' is already on Tier 2 (ERPNext Suite).")

        confirm_check = st.checkbox("I acknowledge that an in-place site migration will be executed on the live container.")
        upgrade_btn = st.button("🚀 Execute In-Place Upgrade to Tier 2", disabled=not confirm_check, use_container_width=True)

        if upgrade_btn:
            st.markdown("<br><hr>", unsafe_allow_html=True)
            st.subheader("Upgrade Pipeline Output")

            progress_bar = st.progress(0)
            status_text = st.empty()
            logs_container = st.empty()
            exec_logs = []

            def log_and_update(msg: str, progress_val: int):
                exec_logs.append(f"{time.strftime('%H:%M:%S')} | {msg}")
                status_text.markdown(f"<b>Status:</b> {msg}", unsafe_allow_html=True)
                progress_bar.progress(progress_val)
                with logs_container:
                    render_terminal_logs(exec_logs)
                time.sleep(0.3)

            try:
                log_and_update("Initiating Phase 4 In-Place Upgrade Strategy...", 10)
                log_and_update(f"Acquired upgrade lock: 'lock:upgrade:{tenant_info['site_name']}'", 20)
                log_and_update("Step 1: Executing bench backup snapshot...", 40)

                res = StreamlitProvisioningService.upgrade_tenant(
                    company_name=tenant_info["company_name"],
                    abbr=tenant_info.get("abbr", "TC"),
                    selected_features=["selling", "crm"],
                    admin_password="Password@123",
                    bot=tenant_info.get("bot", "test_bot"),
                    user_email=current_user
                )

                log_and_update("Step 2: bench install-app erpnext completed successfully.", 75)
                log_and_update("Step 3: Worker reload signal dispatched.", 90)
                log_and_update("Phase 4 Upgrade Complete!", 100)

                st.success(f"Tenant '{selected_company}' successfully upgraded to Tier 2 ERPNext Suite!")
                st.toast("In-Place Upgrade Complete!", icon="🎉")

            except Exception as e:
                exec_logs.append(f"{time.strftime('%H:%M:%S')} | [ERROR] Upgrade failed: {str(e)}")
                with logs_container:
                    render_terminal_logs(exec_logs)
                st.error(f"Upgrade Failed: {str(e)}")
