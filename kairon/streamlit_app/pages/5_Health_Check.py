import streamlit as st
from components.ui import inject_custom_css, render_sidebar, get_status_badge
from services.health import HealthService
from config import API_BASE_URL

# Page configuration
st.set_page_config(page_title="Diagnostics", page_icon="🩺", layout="wide")
inject_custom_css()
render_sidebar()

# Check authentication
token = st.session_state.get("access_token")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()

st.markdown('# 🩺 System Diagnostics & <span class="gradient-text">Health Check</span>', unsafe_allow_html=True)
st.markdown("---")

st.write("Run diagnostics on critical backend database servers, cache systems, workers and API gateways.")

# Diagnostics Execution trigger
if st.button("🔄 Run Diagnostics", type="primary", use_container_width=True) or "health_results" not in st.session_state:
    with st.spinner("Executing system connectivity scans..."):
        api_check = HealthService.check_kairon_api(API_BASE_URL)
        redis_check = HealthService.check_redis()
        postgres_check = HealthService.check_postgresql()
        mongo_check = HealthService.check_workers()
        erp_check = HealthService.check_erpnext_api()
        
        st.session_state["health_results"] = {
            "Kairon API Server": api_check,
            "Redis Lock Store": redis_check,
            "PostgreSQL DB Cluster": postgres_check,
            "MongoDB & Event Queue": mongo_check,
            "ERPNext Site API": erp_check
        }

# Render health check grid
health_results = st.session_state.get("health_results", {})

for service_name, result in health_results.items():
    status = result.get("status", "Unknown")
    msg = result.get("message", "N/A")
    details = result.get("details", "")
    
    # Custom container styling based on health
    card_border_color = "rgba(16, 185, 129, 0.4)" if status == "Healthy" else "rgba(239, 68, 68, 0.4)"
    
    st.markdown(
        f"""
        <div class="glass-card" style="border-left: 5px solid {card_border_color};">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="margin: 0; padding-bottom: 5px;">{service_name}</h3>
                    <p style="margin: 0; color: #9ca3af; font-size: 0.95rem;">{msg}</p>
                </div>
                <div>
                    {get_status_badge(status)}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    # Details in expander
    with st.expander("Show Diagnostic Details"):
        st.code(details, language="text")
