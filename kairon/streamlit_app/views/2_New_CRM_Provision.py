import streamlit as st
import time
from components.ui import inject_custom_css, render_sidebar, get_status_badge
from services.crm import CrmService

# Page configuration
st.set_page_config(page_title="Provision CRM", page_icon="🆕", layout="wide")
inject_custom_css()
render_sidebar()

# Check authentication
token = st.session_state.get("access_token")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()

selected_bot_id = st.session_state.get("selected_bot_id")
selected_bot_name = st.session_state.get("selected_bot_name", "None")

st.markdown('# 🆕 New CRM <span class="gradient-text">Provisioning Wizard</span>', unsafe_allow_html=True)
st.markdown("---")

if not selected_bot_id:
    st.info("No active bot context selected. Please select a bot in the sidebar.")
    st.stop()

# Check if CRM is enabled for this bot
try:
    bot_settings = CrmService.get_bot_settings(selected_bot_id)
    crm_enabled = bot_settings.get("enable_crm", False)
except Exception as e:
    st.error(f"Error checking CRM settings: {e}")
    crm_enabled = False

if not crm_enabled:
    st.warning(f"CRM is currently disabled for bot: **{selected_bot_name}**.")
    if st.button("Enable CRM and Continue", use_container_width=True):
        with st.spinner("Enabling CRM..."):
            CrmService.enable_crm(selected_bot_id, enable=True)
            st.success("CRM Enabled!")
            st.rerun()
    st.stop()

# Retrieve user info to pre-populate details
user_info = st.session_state.get("user_info", {})
user_email = user_info.get("email", "")
first_name = user_info.get("first_name", "")
last_name = user_info.get("last_name", "")

# Check if there is an existing provisioning request
existing_details = CrmService.get_crm_details(selected_bot_id)
if existing_details:
    curr_status = existing_details.get("onboarding_status", "PENDING")
    st.info(f"An active CRM deployment exists for this bot. Company: **{existing_details.get('company_name')}** (Status: **{curr_status}**).")
    
    if curr_status != "COMPLETED" and "FAILED" not in curr_status:
        st.info("Onboarding is still running. You can poll the current job below:")
        if st.button("Poll Active Deployment"):
            st.session_state["polling_active"] = True
            st.session_state["polling_bot_id"] = selected_bot_id
            st.rerun()

    st.warning("If you want to start a new deployment, you must delete the current project configuration first.")
    
    col_del_1, col_del_2 = st.columns([3, 1])
    with col_del_1:
        st.write("Deleting this project will clear the Kairon configuration database record.")
    with col_del_2:
        if st.button("Delete CRM Project", type="secondary", use_container_width=True):
            with st.spinner("Deleting project..."):
                try:
                    CrmService.delete_crm_project(selected_bot_id, existing_details.get("company_name"))
                    st.success("Project configuration deleted successfully!")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to delete: {e}")
    st.stop()

# Provision Form
st.markdown("### Onboarding Details")
with st.form("provision_form", clear_on_submit=False):
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        company_name = st.text_input("Company Name", placeholder="e.g. Acme Corporation")
        abbr = st.text_input("Company Abbreviation", placeholder="e.g. ACME", max_chars=5, help="Used for naming database tables.")
    with col_f2:
        country = st.selectbox("Country", ["United States", "United Kingdom", "Germany", "India", "Canada", "Australia", "Singapore"], index=0)
        currency = st.selectbox("Currency", ["USD", "EUR", "GBP", "INR", "CAD", "AUD", "SGD"], index=0)

    st.markdown("---")
    st.markdown("#### 🧩 ERPNext Business Modules & Workspaces")
    st.write("Select which business modules should be visible and accessible in the provisioned ERPNext instance:")

    # Available modules list
    available_data = CrmService.get_available_modules(selected_bot_id)
    avail_modules = available_data.get("modules", [])
    if not avail_modules:
        # Static fallback list
        avail_modules = [
            {"key": "CRM", "workspace": "CRM", "description": "Leads, Deals, Campaigns, and Opportunity Pipeline"},
            {"key": "POS", "workspace": "POS", "description": "Point of Sale retail transactions and cash registers"},
            {"key": "HR", "workspace": "HR", "description": "Employees, Leaves, Attendance, and Payroll"},
            {"key": "Projects", "workspace": "Projects", "description": "Tasks, Timesheets, and Project Tracking"},
            {"key": "Support", "workspace": "Support", "description": "Service Tickets and Issue Management"},
            {"key": "Quality", "workspace": "Quality", "description": "Quality Inspections and Action Plans"},
            {"key": "Buying", "workspace": "Buying", "description": "Purchase Orders, Suppliers, and Invoices"},
            {"key": "Selling", "workspace": "Selling", "description": "Sales Orders, Quotations, and Customers"},
            {"key": "Stock", "workspace": "Stock", "description": "Inventory, Warehouses, and Material Transfers"},
            {"key": "Manufacturing", "workspace": "Manufacturing", "description": "Bill of Materials and Work Orders"},
            {"key": "Assets", "workspace": "Assets", "description": "Asset Tracking and Depreciation"},
            {"key": "Maintenance", "workspace": "Maintenance", "description": "Equipment Schedules and Service Requests"}
        ]

    module_options = {m["key"]: f"**{m['key']}** — {m['description']}" for m in avail_modules}
    
    selected_module_keys = st.multiselect(
        "Choose Business Modules",
        options=list(module_options.keys()),
        default=["CRM"],
        format_func=lambda k: f"{k} ({module_options[k].split(' — ')[1]})"
    )

    st.markdown("---")
    st.markdown("#### Administrator Identity")
    st.write("The ERPNext instances use the Kairon user identity as the default administrator account:")
    
    col_u1, col_u2, col_u3 = st.columns(3)
    with col_u1:
        st.text_input("First Name", value=first_name, disabled=True)
    with col_u2:
        st.text_input("Last Name", value=last_name, disabled=True)
    with col_u3:
        st.text_input("Email", value=user_email, disabled=True)

    submit = st.form_submit_button("Deploy CRM Instance")

    if submit:
        if not company_name:
            st.error("Company Name is required.")
        elif not selected_module_keys:
            st.error("Please select at least one business module.")
        else:
            if not abbr:
                # Generate default abbreviation
                abbr = "".join([w[0].upper() for w in company_name.split() if w])[:5]
            
            with st.spinner("Triggering CRM onboarding workflow..."):
                try:
                    res = CrmService.onboard_crm(
                        selected_bot_id,
                        company_name,
                        country,
                        currency,
                        abbr,
                        selected_modules=selected_module_keys
                    )
                    st.success("Deployment triggered successfully!")
                    st.session_state["polling_active"] = True
                    st.session_state["polling_bot_id"] = selected_bot_id
                    st.rerun()
                except Exception as e:
                    st.error(f"Deployment failed to trigger: {e}")

# Polling Area
if st.session_state.get("polling_active") and st.session_state.get("polling_bot_id") == selected_bot_id:
    st.markdown("---")
    st.markdown("### 🔄 Real-time Deployment Tracker")
    
    # Progress status definitions
    status_steps = [
        "PENDING", 
        "PROJECT_CREATED", 
        "BENCH_RUNNING", 
        "SITE_CREATED", 
        "SITE_HEALTHY", 
        "COMPANY_CREATED", 
        "USER_CREATED", 
        "COMPLETED"
    ]
    
    status_container = st.empty()
    log_container = st.empty()
    stop_button = st.button("Stop Tracking")
    
    if stop_button:
        st.session_state["polling_active"] = False
        st.rerun()
        
    polling = True
    while polling:
        try:
            status_data = CrmService.get_crm_status(selected_bot_id)
            current_status = status_data.get("onboarding_status", "PENDING")
            last_error = status_data.get("last_error")
            
            # Find status step index
            step_idx = 0
            if current_status in status_steps:
                step_idx = status_steps.index(current_status)
            elif "FAILED" in current_status:
                step_idx = -1
                
            with status_container.container():
                st.write(f"Current Status: {get_status_badge(current_status)}", unsafe_allow_html=True)
                
                # Render visual timeline steps
                if step_idx >= 0:
                    progress_val = float(step_idx + 1) / len(status_steps)
                    st.progress(progress_val)
                    st.info(f"Step {step_idx + 1} of {len(status_steps)}: Working on {current_status}...")
                else:
                    st.progress(1.0)
                    st.error(f"Deployment failed at: **{current_status}**")
                    if last_error:
                        st.markdown(f"**Error Details:** `{last_error}`")
                    polling = False
                    st.session_state["polling_active"] = False
                    break
                    
                if current_status == "COMPLETED":
                    st.balloons()
                    st.success("🎉 CRM instance is fully provisioned and ready for use!")
                    polling = False
                    st.session_state["polling_active"] = False
                    break
            
            # Wait before polling again
            time.sleep(5)
            
        except Exception as e:
            status_container.error(f"Status Polling Error: {e}")
            time.sleep(10)
