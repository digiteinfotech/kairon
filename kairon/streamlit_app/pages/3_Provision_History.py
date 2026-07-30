import streamlit as st
import pandas as pd
from components.ui import inject_custom_css, render_sidebar, get_status_badge
from services.crm import CrmService

# Page configuration
st.set_page_config(page_title="Provision History", page_icon="📜", layout="wide")
inject_custom_css()
render_sidebar()

# Check authentication
token = st.session_state.get("access_token")
if not token:
    st.warning("Please log in from the main page.")
    st.stop()

st.markdown('# 📜 Provisioning <span class="gradient-text">History Log</span>', unsafe_allow_html=True)
st.markdown("---")

# Retrieve and process details across all bots
with st.spinner("Fetching deployment history..."):
    bots = CrmService.get_bots()
    history_data = []

    for b in bots:
        try:
            details = CrmService.get_crm_details(b["_id"])
            if details:
                # Format timestamps safely
                started_at = details.get("workflow_started_at")
                completed_at = details.get("workflow_completed_at")
                
                # Format timestamps if they exist (usually floats or datetimes)
                started_str = started_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(started_at, "strftime") else str(started_at or "N/A")
                completed_str = completed_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(completed_at, "strftime") else str(completed_at or "N/A")

                history_data.append({
                    "Bot ID": b["_id"],
                    "Bot Name": b["name"],
                    "Company Name": details.get("company_name", "N/A"),
                    "Abbreviation": details.get("abbr", "N/A"),
                    "Status": details.get("onboarding_status", "PENDING"),
                    "Database": details.get("db_name", "N/A"),
                    "Site Name": details.get("site_name", "N/A"),
                    "Created Time": started_str,
                    "Completed Time": completed_str,
                    "Provision ID": details.get("provisioning_id") or "N/A"
                })
        except Exception:
            pass

if history_data:
    df = pd.DataFrame(history_data)

    # Filter Controls
    col_ctrl1, col_ctrl2 = st.columns(2)
    with col_ctrl1:
        search_query = st.text_input("🔍 Search by Company or Bot Name", "")
    with col_ctrl2:
        status_options = ["ALL", "COMPLETED", "PENDING", "FAILED", "RUNNING"]
        selected_status = st.selectbox("Status Filter", status_options)

    # Apply search filter
    if search_query:
        df = df[df["Company Name"].str.contains(search_query, case=False) | df["Bot Name"].str.contains(search_query, case=False)]

    # Apply status filter
    if selected_status != "ALL":
        if selected_status == "RUNNING":
            df = df[df["Status"].str.contains("RUN|CREAT|BENCH", case=False)]
        elif selected_status == "FAILED":
            df = df[df["Status"].str.contains("FAIL|ERR", case=False)]
        else:
            df = df[df["Status"] == selected_status]

    if not df.empty:
        # Draw header row
        hcols = st.columns([1.5, 1, 2, 1.2, 1.8, 1.8, 1, 1.2])
        hcols[0].markdown("**Job/Provision ID**")
        hcols[1].markdown("**Bot Name**")
        hcols[2].markdown("**Company**")
        hcols[3].markdown("**Status**")
        hcols[4].markdown("**Started At**")
        hcols[5].markdown("**Completed At**")
        hcols[6].markdown("**Database**")
        hcols[7].markdown("**Inspect**")
        st.markdown("<hr style='margin: 8px 0; border: none; border-bottom: 1px solid rgba(255,255,255,0.1);'>", unsafe_allow_html=True)
        
        for index, row in df.iterrows():
            short_id = row['Provision ID']
            if len(short_id) > 12:
                short_id = short_id[:12] + "..."
            
            cols = st.columns([1.5, 1, 2, 1.2, 1.8, 1.8, 1, 1.2])
            cols[0].code(short_id)
            cols[1].write(row['Bot Name'])
            cols[2].write(f"{row['Company Name']} ({row['Abbreviation']})")
            cols[3].markdown(get_status_badge(row['Status']), unsafe_allow_html=True)
            cols[4].write(row['Created Time'])
            cols[5].write(row['Completed Time'])
            cols[6].code(row['Database'])
            if cols[7].button("Details ➜", key=f"det_{row['Bot ID']}_{index}", use_container_width=True):
                st.session_state["selected_bot_id"] = row["Bot ID"]
                st.session_state["selected_bot_name"] = row["Bot Name"]
                st.switch_page("pages/4_Provision_Details.py")
            st.markdown("<hr style='margin: 4px 0; border: none; border-bottom: 1px solid rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
    else:
        st.info("No matching records found for the active filter settings.")

else:
    st.info("No CRM history logs found. Deploy an instance to create history records.")
