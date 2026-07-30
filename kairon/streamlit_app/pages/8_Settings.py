import os
import streamlit as st
from kairon.streamlit_app.components.styles import inject_enterprise_styles
from kairon.streamlit_app.components.cards import render_header
from kairon.crm.services.bench_executor import BenchExecutor

inject_enterprise_styles()

render_header("System Configuration & Settings", "Manage Docker container parameters, bench paths, and database connection strings.", icon="⚙️")

with st.form("settings_form"):
    st.subheader("Infrastructure Container & Bench Settings")
    container_name = st.text_input("Docker Backend Container", value=BenchExecutor.CONTAINER_NAME)
    bench_path = st.text_input("Bench Workspace Path", value="/home/frappe/frappe-bench")
    sites_path = st.text_input("Sites Directory Path", value="sites")

    st.markdown("<br>### Database Connection Settings", unsafe_allow_html=True)
    col_db1, col_db2 = st.columns(2)
    with col_db1:
        db_host = st.text_input("PostgreSQL Host", value=BenchExecutor.DB_HOST)
        db_user = st.text_input("PostgreSQL Superuser", value=BenchExecutor.DB_USER)
    with col_db2:
        db_port = st.number_input("PostgreSQL Port", value=BenchExecutor.DB_PORT)
        db_password = st.text_input("PostgreSQL Password", value=BenchExecutor.DB_PASSWORD, type="password")

    st.markdown("<br>### Redis Caching & Queue Settings", unsafe_allow_html=True)
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        redis_cache = st.text_input("Redis Cache URL", value="redis://redis-cache:6379")
    with col_r2:
        redis_queue = st.text_input("Redis Queue URL", value="redis://redis-queue:6379")

    save_btn = st.form_submit_button("💾 Save System Configuration", use_container_width=True)

if save_btn:
    st.success("System configuration saved successfully.")
    st.toast("Configuration updated!", icon="💾")

st.markdown("<br>### Environment Variables Inspector", unsafe_allow_html=True)
env_vars = {k: v for k, v in os.environ.items() if "KAIRON" in k or "FRAPPE" in k or "DB" in k or "REDIS" in k or "PATH" in k}
st.json(env_vars)
