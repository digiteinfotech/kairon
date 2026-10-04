import streamlit as st
from components.ui import inject_custom_css, render_sidebar, get_status_badge
from components.auth import require_login
from services.crm import CrmService

inject_custom_css()
render_sidebar()
require_login()

st.markdown('# ✉️ Invite User to <span class="gradient-text">CRM</span>', unsafe_allow_html=True)
st.caption("Uses ERPNext's native user invitation flow. No custom invitation logic is built here.")
st.markdown("---")

bot_id = st.session_state.get("selected_bot_id")
bot_name = st.session_state.get("selected_bot_name", "Selected Bot")

if not bot_id:
    st.info("Select a bot from the sidebar to continue.")
    st.stop()

with st.spinner("Loading tenant details..."):
    try:
        details = CrmService.get_crm_details(bot_id)
    except Exception as e:
        st.error(f"Could not reach the Kairon backend: {e}")
        st.stop()

if not details:
    st.warning(f"No CRM tenant has been provisioned yet for **{bot_name}**.")
    st.page_link("views/2_CRM_Onboarding.py", label="Go to CRM Onboarding", icon="🏢")
    st.stop()

status = details.get("onboarding_status")
company_name = details.get("company_name", "N/A")
site_name = details.get("site_name", "N/A")

st.markdown(
    f"""
    <div class="glass-card">
        <p><b>Company:</b> {company_name} &nbsp;|&nbsp; <b>Site:</b> <code>{site_name}</code></p>
        <p><b>Status:</b> {get_status_badge(status)}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if status != "COMPLETED":
    st.error(f"Cannot invite users until the tenant is fully provisioned (current status: {status}).")
    st.stop()

AVAILABLE_ROLES = ["Sales User", "Sales Manager", "CRM User", "CRM Manager", "System Manager"]

with st.form("invite_user_form"):
    email = st.text_input("Email", placeholder="colleague@company.com")
    roles = st.multiselect("CRM Role(s)", options=AVAILABLE_ROLES, default=["Sales User"])
    submitted = st.form_submit_button(
        "Send Invitation", type="primary", use_container_width=True,
        disabled=st.session_state.get("invite_inflight", False),
    )

if submitted:
    if not email or not email.strip():
        st.error("Email is required.")
    elif not roles:
        st.error("Select at least one role.")
    else:
        st.session_state["invite_inflight"] = True
        try:
            with st.spinner(f"Sending invitation to {email}..."):
                res = CrmService.invite_crm_user(bot_id, email.strip(), roles)
            data = res.get("data") or {}
            inv_status = data.get("status")
            if inv_status == "invited":
                st.success(f"Invitation dispatched to {email}. Check Mailpit / the recipient's inbox for the setup link.")
            elif inv_status == "already_pending":
                st.info(f"An invitation is already pending for {email}.")
            elif inv_status == "already_accepted":
                st.warning(f"{email} has already accepted their invitation.")
            else:
                st.success(res.get("message", "Invitation processed."))
        except Exception as e:
            st.error(f"Failed to send invitation: {e}")
        finally:
            st.session_state["invite_inflight"] = False
