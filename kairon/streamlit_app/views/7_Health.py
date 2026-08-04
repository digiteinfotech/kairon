import streamlit as st
import pandas as pd
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header, render_status_badge, render_stat_card
from kairon.streamlit_app.services.health_service import HealthService

inject_enterprise_styles()

render_header("System Diagnostic & Infrastructure Health", "Real-time health verification across Docker containers, PostgreSQL, Redis caches, and Bench services.", icon="🩺")

if st.button("🔄 Run Live Health Diagnostics", use_container_width=True):
    st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

health_results = HealthService.get_system_health()

# Top Metrics
healthy_cnt = sum(1 for h in health_results if h["status"] == "Healthy")
warning_cnt = sum(1 for h in health_results if h["status"] == "Warning")
failed_cnt = sum(1 for h in health_results if h["status"] == "Failed")

col1, col2, col3 = st.columns(3)
with col1:
    render_stat_card("Healthy Components", f"{healthy_cnt} / {len(health_results)}", "All critical components active", border_color="#10B981")
with col2:
    render_stat_card("Service Warnings", str(warning_cnt), "No pending warnings", border_color="#F59E0B")
with col3:
    render_stat_card("Failed Services", str(failed_cnt), "No service downtime", border_color="#EF4444")

st.markdown("<br>### Service Diagnostics Matrix", unsafe_allow_html=True)

for item in health_results:
    st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <span style="font-weight: 700; font-size: 1.05rem; color: #FFFFFF;">{item['service']}</span>
                    <span style="color: var(--text-muted); font-size: 0.85rem; margin-left: 10px;">(<code>{item['target']}</code>)</span>
                </div>
                {render_status_badge(item['status'])}
            </div>
            <div style="color: var(--text-secondary); font-size: 0.85rem; margin-top: 6px;">
                {item['details']}
            </div>
        </div>
    """, unsafe_allow_html=True)
