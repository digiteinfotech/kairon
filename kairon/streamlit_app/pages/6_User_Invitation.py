import streamlit as st
from components.ui import inject_custom_css, render_sidebar, glass_card, get_status_badge
from services.crm import CrmService

# Page configuration
st.set_page_config(page_title="Invite User", page_icon="✉️", layout="wide")
inject_custom_css()
render_sidebar()

# Check authentication
token = st.session_state.get("access_token")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()

st.markdown('# ✉️ ERPNext <span class="gradient-text">User Invitation</span>', unsafe_allow_html=True)
st.markdown("Invite new collaborators to tenant ERPNext instances using ERPNext's native `UserInvitation` flow.")
st.markdown("---")

bot_id = st.session_state.get("selected_bot_id")
bot_name = st.session_state.get("selected_bot_name", "Selected Bot")

if not bot_id:
    st.info("⚠️ Please select a chatbot context from the sidebar to send an invitation.")
    st.stop()

# Fetch site details to confirm site is provisioned
with st.spinner("Loading site metadata..."):
    details = CrmService.get_crm_details(bot_id)

if not details:
    st.warning(f"No provisioned ERPNext site found for Bot: **{bot_name}** (`{bot_id}`). Please complete provisioning first.")
    st.stop()

status = details.get("onboarding_status")
company_name = details.get("company_name", "N/A")
site_name = details.get("site_name", "N/A")

# Header card
st.markdown(
    f"""
    <div class="glass-card">
        <h3>🏢 Target Tenant: {company_name}</h3>
        <p><b>Bot ID:</b> <code>{bot_id}</code> | <b>Site:</b> <code>{site_name}</code></p>
        <p><b>Status:</b> {get_status_badge(status)}</p>
    </div>
    """,
    unsafe_allow_html=True
)

st.markdown("<br>", unsafe_allow_html=True)

if status != "COMPLETED":
    st.error(f"Cannot send invitations while onboarding status is **{status}**. Site must be fully provisioned (`COMPLETED`).")
    st.stop()

col_form, col_info = st.columns([3, 2])

with col_form:
    st.markdown("### 📩 Send Native User Invitation")
    
    with st.form("invite_user_form", clear_on_submit=False):
        invite_email = st.text_input(
            "User Email Address",
            placeholder="colleague@company.com",
            help="ERPNext will send a password setup link directly to this email address."
        )
        
        available_roles = [
            "Sales User",
            "Sales Manager",
            "CRM User",
            "CRM Manager",
            "Projects User",
            "Accounts User",
            "System Manager",
        ]
        
        selected_roles = st.multiselect(
            "ERPNext Roles",
            options=available_roles,
            default=["Sales User"],
            help="Select one or more roles to assign to the invited user upon setup."
        )
        
        custom_company = st.text_input(
            "Company Name (Optional Override)",
            value="",
            placeholder=company_name,
            help="Leave empty to use default provisioned company name."
        )
        
        submit_btn = st.form_submit_button("✉️ Dispatch Invitation", use_container_width=True)
        
        if submit_btn:
            if not invite_email or not invite_email.strip():
                st.error("Please enter a valid email address.")
            elif not selected_roles:
                st.error("Please select at least one role for the user.")
            else:
                with st.spinner(f"Dispatching invitation to {invite_email}..."):
                    try:
                        override_company = custom_company.strip() if custom_company.strip() else None
                        res = CrmService.invite_crm_user(
                            bot_id=bot_id,
                            email=invite_email.strip(),
                            roles=selected_roles,
                            company_name=override_company
                        )
                        
                        data = res.get("data") or {}
                        inv_status = data.get("status")
                        
                        if inv_status == "invited":
                            st.success(f"✅ Invitation successfully dispatched to **{invite_email}**! ERPNext has sent the password setup email.")
                        elif inv_status == "already_pending":
                            st.info(f"ℹ️ An invitation is already pending for **{invite_email}**.")
                        elif inv_status == "already_accepted":
                            st.warning(f"⚠️ User **{invite_email}** has already accepted their invitation.")
                        else:
                            st.success(f"Result: {res.get('message', 'Invitation processed')}")
                            
                    except Exception as e:
                        st.error(f"Failed to dispatch invitation: {e}")

with col_info:
    st.markdown(
        """
        <div class="glass-card">
            <h4>💡 How ERPNext Invitations Work</h4>
            <ol>
                <li><b>Email Invitation Dispatched</b>: Kairon invokes ERPNext's native <code>UserInvitation</code> API. ERPNext automatically generates and emails a password setup link.</li>
                <li><b>Password Setup</b>: The recipient clicks the setup link in their email to set their password.</li>
                <li><b>Automated Webhook Sync</b>: On acceptance, ERPNext fires an <code>on_update</code> webhook to Kairon's receiver. Kairon automatically grants company permissions (<b>User Permission</b>).</li>
                <li><b>Safety Net Reconciler</b>: A background job checks pending invitations every 30 minutes to catch any missed webhooks.</li>
            </ol>
        </div>
        """,
        unsafe_allow_html=True
    )
