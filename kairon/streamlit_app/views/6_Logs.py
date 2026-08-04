import streamlit as st
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_terminal_logs
from kairon.streamlit_app.services.logs_service import LogsService
from kairon.streamlit_app.services.tenant_service import TenantService

inject_enterprise_styles()

render_header("System & Provisioning Logs", "Live streaming log telemetry across Bench CLI executions, DB migrations, and worker reloads.", icon="📜")

current_user = st.session_state.get("kairon_user", "admin@kairon.io")
tenants = TenantService.get_all_tenants(user_email=current_user)
site_list = ["ALL"] + [t["site_name"] for t in tenants]

col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    selected_site = st.selectbox("Filter by Tenant Site", site_list)
with col2:
    selected_level = st.selectbox("Log Severity Level", ["ALL", "INFO", "WARN", "ERROR"])
with col3:
    limit = st.slider("Log Line Limit", 50, 500, 200, 50)

tenant_filter = None if selected_site == "ALL" else selected_site
logs = LogsService.get_recent_logs(tenant_filter=tenant_filter, level_filter=selected_level, limit=limit, user_email=current_user)

st.markdown("<br>", unsafe_allow_html=True)
render_terminal_logs(logs)

st.markdown("<br>", unsafe_allow_html=True)
log_text = "\n".join(logs)
st.download_button(
    label="📥 Download Filtered Log File",
    data=log_text,
    file_name="kairon_provisioning_logs.txt",
    mime="text/plain",
    use_container_width=True
)
