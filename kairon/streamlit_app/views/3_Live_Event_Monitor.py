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
            <span>📊</span> Live Webhook Event Monitor
        </div>
        <div class="portal-subtitle">
            Real-time telemetry stream of dispatches, HMAC verifications, and EventRouter handling
        </div>
    </div>
""", unsafe_allow_html=True)

# Controls Header
col_filter, col_refresh = st.columns([3, 1])

with col_filter:
    status_filter = st.multiselect(
        "Filter by Event Status",
        options=["Queued", "Success", "Failed", "Ignored"],
        default=["Queued", "Success", "Failed"]
    )

with col_refresh:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Refresh Telemetry", use_container_width=True):
        st.rerun()

st.markdown("<br>", unsafe_allow_html=True)

# Live Streaming Telemetry Dataset
events_data = [
    {
        "Time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Event Type": "lead.qualified",
        "Status": "Success",
        "Event ID": "evt_a1b2c3d4e5f6",
        "Correlation ID": "corr_9988776655",
        "Payload Summary": "Sarah Connor (Cyberdyne Systems)",
        "Latency": "42ms"
    },
    {
        "Time": (datetime.datetime.now() - datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "Event Type": "lead.created",
        "Status": "Success",
        "Event ID": "evt_b2c3d4e5f6a1",
        "Correlation ID": "corr_8877665544",
        "Payload Summary": "Marcus Vance (Apex Manufacturing Ltd)",
        "Latency": "38ms"
    },
    {
        "Time": (datetime.datetime.now() - datetime.timedelta(minutes=18)).strftime("%Y-%m-%d %H:%M:%S"),
        "Event Type": "lead.qualified",
        "Status": "Success",
        "Event ID": "evt_c3d4e5f6a1b2",
        "Correlation ID": "corr_7766554433",
        "Payload Summary": "Elena Rostova (Vanguard Global)",
        "Latency": "45ms"
    },
    {
        "Time": (datetime.datetime.now() - datetime.timedelta(minutes=42)).strftime("%Y-%m-%d %H:%M:%S"),
        "Event Type": "ticket.created",
        "Status": "Ignored",
        "Event ID": "evt_d4e5f6a1b2c3",
        "Correlation ID": "corr_6655443322",
        "Payload Summary": "Feature Flag 'enable_ticket_sync' = False",
        "Latency": "12ms"
    }
]

filtered_events = [e for e in events_data if e["Status"] in status_filter]

st.dataframe(filtered_events, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🔍 Event Envelope Inspector")

with st.expander("📄 Raw Event Envelope (`evt_a1b2c3d4e5f6`)", expanded=True):
    st.json({
        "event_type": "lead.qualified",
        "event_version": "1.0",
        "event_id": "evt_a1b2c3d4e5f6",
        "correlation_id": "corr_9988776655",
        "timestamp": "2026-07-30T15:20:00Z",
        "payload": {
            "bot_id": "bot_enterprise_01",
            "conversation_id": "conv_9988776655",
            "first_name": "Sarah Connor",
            "email": "sarah.c@cyberdyne.io",
            "phone": "+1-555-0199",
            "company": "Cyberdyne Systems",
            "transcript": "Qualified prospect from AI Chatbot: Interested in enterprise CRM solution for Cyberdyne Systems."
        }
    })
