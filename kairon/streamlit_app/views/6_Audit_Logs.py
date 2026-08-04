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
            <span>📜</span> Webhook Audit Logs & Replay Center
        </div>
        <div class="portal-subtitle">
            Historical audit log directory with operational event replay execution (MAX_REPLAY_LIMIT = 5)
        </div>
    </div>
""", unsafe_allow_html=True)

# Status Filter Bar
col_status, col_search = st.columns([2, 2])

with col_status:
    selected_status = st.selectbox(
        "Filter by Webhook Status",
        ["All Logs", "Success", "Failed", "Ignored", "Replayed"]
    )

with col_search:
    search_query = st.text_input("Search by Event ID or Correlation ID", placeholder="evt_...")

st.markdown("<br>", unsafe_allow_html=True)

# Mock Audit Logs Directory Data
audit_logs = [
    {
        "Log Name": "LOG-2026-0001",
        "Event ID": "evt_a1b2c3d4e5f6",
        "Event Type": "lead.qualified",
        "Status": "Success",
        "Replay Count": 0,
        "Timestamp": "2026-07-30 15:20:00",
        "Last Replay": "Never"
    },
    {
        "Log Name": "LOG-2026-0002",
        "Event ID": "evt_b2c3d4e5f6a1",
        "Event Type": "lead.created",
        "Status": "Success",
        "Replay Count": 0,
        "Timestamp": "2026-07-30 15:08:00",
        "Last Replay": "Never"
    },
    {
        "Log Name": "LOG-2026-0003",
        "Event ID": "evt_c3d4e5f6a1b2",
        "Event Type": "lead.qualified",
        "Status": "Failed",
        "Replay Count": 2,
        "Timestamp": "2026-07-30 14:15:00",
        "Last Replay": "2026-07-30 14:45:00 (Success)"
    },
    {
        "Log Name": "LOG-2026-0004",
        "Event ID": "evt_d4e5f6a1b2c3",
        "Event Type": "ticket.created",
        "Status": "Ignored",
        "Replay Count": 0,
        "Timestamp": "2026-07-30 13:10:00",
        "Last Replay": "Never"
    }
]

# Apply Filters
filtered_logs = audit_logs
if selected_status != "All Logs":
    if selected_status == "Replayed":
        filtered_logs = [l for l in audit_logs if l["Replay Count"] > 0]
    else:
        filtered_logs = [l for l in audit_logs if l["Status"] == selected_status]

if search_query.strip():
    q = search_query.strip().lower()
    filtered_logs = [l for l in filtered_logs if q in l["Event ID"].lower() or q in l["Log Name"].lower()]

# Render Audit Logs Table & Replay Action
for log in filtered_logs:
    c_info, c_action = st.columns([3.5, 1])

    status_badge_class = "badge-success" if log["Status"] == "Success" else ("badge-warning" if log["Status"] == "Ignored" else "badge-failed")

    with c_info:
        st.markdown(f"""
            <div class="metric-card" style="padding: 14px; margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="font-weight: 700; color: #FFFFFF;">{log['Log Name']}</span>
                        <span class="code-pill" style="margin-left: 10px;">{log['Event ID']}</span>
                        <span style="color: #818CF8; font-size: 0.85rem; margin-left: 10px;">{log['Event Type']}</span>
                        <span class="{status_badge_class}" style="margin-left: 10px;">● {log['Status']}</span>
                    </div>
                    <div style="font-size: 0.78rem; color: #9CA3AF;">{log['Timestamp']}</div>
                </div>
                <div style="font-size: 0.78rem; color: #6B7280; margin-top: 6px;">
                    Replay Count: <b>{log['Replay Count']} / 5</b> | Last Replay: {log['Last Replay']}
                </div>
            </div>
        """, unsafe_allow_html=True)

    with c_action:
        if st.button(f"🔄 Replay Event", key=f"btn_replay_{log['Log Name']}", use_container_width=True):
            st.toast(f"Triggered ReplayService for '{log['Log Name']}' (Replay Attempt {log['Replay Count'] + 1})", icon="🔄")
            st.success(f"Replay Executed: EventRouter routed log '{log['Log Name']}' successfully!")
