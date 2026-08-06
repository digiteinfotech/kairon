import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
import time
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_plan_preview, render_terminal_logs, render_status_badge
from kairon.streamlit_app.services.provisioning_service import StreamlitProvisioningService
from kairon.streamlit_app.services.tenant_service import TenantService

inject_enterprise_styles()

render_header("Tenant Provisioning Platform", "Strategy-based automated deployment for Standalone Apps (Tier 1) and Monolithic ERP Suites (Tier 2).", icon="🚀")

current_bot = st.session_state.get("kairon_bot", "bot_enterprise_01")
is_bot_crm_enabled = TenantService.get_bot_crm_status(current_bot)

if not is_bot_crm_enabled:
    st.error(f"🚫 **CRM Capability is DISABLED in MongoDB** (`conversations.bot_settings`) for Bot `{current_bot}`. You must toggle **Enable CRM / ERPNext for Bot** in the sidebar to enable company creation.")
    st.stop()

# Check if a CRM is already provisioned for this bot
current_user = st.session_state.get("kairon_user", "admin@kairon.io")
user_tenants = TenantService.get_all_tenants(user_email=current_user)
existing_tenant = next((t for t in user_tenants if t.get("bot") == current_bot), None)

if existing_tenant:
    curr_status = existing_tenant.get("onboarding_status", "PENDING")
    st.info(f"An active CRM deployment already exists for this bot. \n\n**Company:** {existing_tenant.get('company_name')} \n**Site URL:** {existing_tenant.get('site_name')} \n**Status:** {curr_status}")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Tenant Configuration")
    with st.form("provision_form"):
        company_name = st.text_input("Company Name", value="Acme Enterprise", help="Legal or display name of the customer company.")
        abbr = st.text_input("Abbreviation", value="AE", help="2-4 character short code used in Frappe/ERPNext.")
        
        col_cnt, col_curr = st.columns(2)
        with col_cnt:
            country = st.selectbox("Country", ["United States", "India", "United Kingdom", "Germany", "Canada", "Australia"])
        with col_curr:
            currency = st.selectbox("Default Currency", ["USD", "INR", "EUR", "GBP", "AUD", "CAD"])

        default_user = st.session_state.get("kairon_user", "admin@acme.com")
        default_bot = st.session_state.get("kairon_bot", "bot_enterprise_01")
        admin_email = st.text_input("Administrator Email", value=default_user)
        admin_password = st.text_input("Administrator Password", value="Password@123", type="password")
        bot_id = st.text_input("Associated Bot ID", value=default_bot)

        st.markdown("<br><b>Application & Feature Selection</b>", unsafe_allow_html=True)
        feature_options = {
            "crm": "Frappe CRM (Standalone / Suite)",
            "pos": "ERPNext Point of Sale (POS)",
            "helpdesk": "Helpdesk & Customer Service",
            "selling": "ERPNext Selling & Sales Pipeline",
            "hr": "ERPNext HR & Payroll",
            "accounts": "ERPNext Accounting & Finance",
            "manufacturing": "ERPNext Manufacturing & Work Orders",
            "projects": "ERPNext Project Management",
            "inventory": "ERPNext Stock & Warehouse"
        }


        selected_features = st.multiselect(
            "Select Desired Modules",
            options=list(feature_options.keys()),
            default=["crm"],
            format_func=lambda x: feature_options[x]
        )

        submit_btn = st.form_submit_button("⚡ Provision Tenant", use_container_width=True)

with col2:
    st.subheader("Automated Strategy Resolution")
    if selected_features:
        try:
            plan = StreamlitProvisioningService.resolve_plan(selected_features)
            render_plan_preview(
                tier=plan.tier,
                strategy_key=plan.strategy_key,
                apps=plan.apps,
                home_page=plan.home_page,
                default_roles=plan.default_roles,
                dependencies=plan.dependencies,
                upgrade_supported=plan.upgrade_supported
            )
        except Exception as e:
            st.error(f"Error resolving features: {str(e)}")
    else:
        st.warning("Please select at least one feature module to resolve provisioning plan.")

# Form Submission Execution Flow
if submit_btn and selected_features:
    if not TenantService.get_bot_crm_status(bot_id):
        st.error(f"🚫 **Provisioning Blocked:** CRM capability is currently **DISABLED** in MongoDB (`conversations.bot_settings`) for Bot `{bot_id}`. Please toggle **Enable CRM / ERPNext for Bot** in the sidebar first.")
        st.stop()

    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.subheader("Provisioning Execution Pipeline")

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
        clean_site = f"{company_name.lower().replace(' ', '_')}.localhost"
        log_and_update("Phase 0: Executing Pre-flight environment & schema validation...", 15)
        preflight_logs = StreamlitProvisioningService.validate_preflight(clean_site, plan, is_upgrade=False)
        for l in preflight_logs:
            exec_logs.append(f"{time.strftime('%H:%M:%S')} | {l}")

        log_and_update(f"Phase 1: Instantiating strategy '{plan.strategy_key}' (Tier {plan.tier})...", 35)
        log_and_update(f"Executing Bench site creation & app installation ('{','.join(plan.apps)}')...", 60)

        res = StreamlitProvisioningService.provision_tenant(
            company_name=company_name,
            abbr=abbr,
            selected_features=selected_features,
            currency=currency,
            country=country,
            admin_password=admin_password,
            bot=bot_id,
            user_email=st.session_state.get("kairon_user")
        )

        log_and_update("Phase 2: Post-provisioning setup wizard bypass & encryption key configuration...", 85)
        log_and_update("Phase 3: Worker reload signal issued. Provisioning completed successfully!", 100)

        st.toast(f"Site {res.get('site_name')} provisioned successfully!", icon="✅")

        st.markdown("<br>", unsafe_allow_html=True)
        rcol1, rcol2, rcol3, rcol4 = st.columns(4)
        with rcol1:
            st.metric("Site URL", res.get("site_name", clean_site))
        with rcol2:
            st.metric("Tier Level", f"Tier {res.get('tier', plan.tier)}")
        with rcol3:
            st.metric("Installed Apps", ", ".join(res.get("installed_apps", plan.apps)))
        with rcol4:
            st.metric("Provisioning Time", f"{res.get('provisioning_time', 'N/A')}s")

    except Exception as e:
        exec_logs.append(f"{time.strftime('%H:%M:%S')} | [ERROR] Provisioning failed: {str(e)}")
        with logs_container:
            render_terminal_logs(exec_logs)
        st.error(f"Provisioning Failed: {str(e)}")
