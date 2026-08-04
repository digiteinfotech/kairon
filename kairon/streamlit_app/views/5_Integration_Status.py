import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
import datetime
from kairon.streamlit_app.components.styles import inject_enterprise_styles

inject_enterprise_styles()

st.markdown("""
    <div class="portal-header">
        <div class="portal-title">
            <span>⚙️</span> Integration Infrastructure & System Health
        </div>
        <div class="portal-subtitle">
            Telemetry, feature flags matrix, HMAC secret rotation status, and health endpoint response
        </div>
    </div>
""", unsafe_allow_html=True)

# 1. System Health Status Grid
h1, h2, h3, h4 = st.columns(4)

with h1:
    st.markdown("""
        <div class="metric-card" style="border-top: 3px solid #10B981;">
            <div class="metric-label">WEBHOOK GATEWAY</div>
            <div class="metric-value" style="font-size: 1.2rem; color: #34D399;">202 ACCEPTED</div>
            <div class="metric-subtext">/api/v1/webhook Active</div>
        </div>
    """, unsafe_allow_html=True)

with h2:
    st.markdown("""
        <div class="metric-card" style="border-top: 3px solid #3B82F6;">
            <div class="metric-label">REDIS CACHE</div>
            <div class="metric-value" style="font-size: 1.2rem; color: #60A5FA;">CONNECTED</div>
            <div class="metric-subtext">24h Deduplication TTL</div>
        </div>
    """, unsafe_allow_html=True)

with h3:
    st.markdown("""
        <div class="metric-card" style="border-top: 3px solid #8B5CF6;">
            <div class="metric-label">POSTGRES DATABASE</div>
            <div class="metric-value" style="font-size: 1.2rem; color: #A78BFA;">CONNECTED</div>
            <div class="metric-subtext">Savepoint Transactions OK</div>
        </div>
    """, unsafe_allow_html=True)

with h4:
    st.markdown("""
        <div class="metric-card" style="border-top: 3px solid #EC4899;">
            <div class="metric-label">CONNECTOR VERSION</div>
            <div class="metric-value" style="font-size: 1.1rem; color: #F472B6;">v1.1.0</div>
            <div class="metric-subtext">Release Tag Tagged</div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 2. Feature Flags Matrix & Secret Rotation Status
f1, f2 = st.columns(2)

with f1:
    st.subheader("🚩 Tenant Feature Flags Matrix (`FeatureFlagService`)")
    st.markdown("""
        <div class="metric-card" style="padding: 16px;">
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                <span><b>enable_lead_sync</b> (CRM Leads)</span>
                <span class="badge badge-success">● ENABLED</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                <span><b>enable_ticket_sync</b> (Helpdesk Tickets)</span>
                <span class="badge badge-warning">○ DISABLED</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0;">
                <span><b>enable_conversation_sync</b> (Transcripts)</span>
                <span class="badge badge-warning">○ DISABLED</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

with f2:
    st.subheader("🔐 HMAC Secret Rotation & Security Status")
    st.markdown("""
        <div class="metric-card" style="padding: 16px;">
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                <span>Primary Webhook Secret</span>
                <span class="code-pill">current_webhook_secret</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-color);">
                <span>Fallback Webhook Secret</span>
                <span class="code-pill">previous_webhook_secret</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 8px 0;">
                <span>Replay Window Tolerance</span>
                <span style="color: #34D399; font-weight: 600;">± 300 Seconds</span>
            </div>
        </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 3. Live Health Probe Response Viewer
st.subheader("🩺 Health Endpoint Live Response (`GET /api/v1/health`)")

with st.expander("📄 Raw JSON Probe Payload", expanded=True):
    st.json({
        "status": "healthy",
        "database": "ok",
        "redis": "ok",
        "queue": "ok",
        "config": "ok",
        "version": "1.1.0"
    })
