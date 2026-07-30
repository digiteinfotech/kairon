import os
import sys
import streamlit as st
import pandas as pd

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))

from components.ui import inject_custom_css, render_sidebar
from services.crm import CrmService

st.set_page_config(page_title="CRM Users", page_icon="👥", layout="wide")
inject_custom_css()
render_sidebar()

if not st.session_state.get("access_token"):
    st.warning("Please log in to view this page.")
    st.stop()

st.title("👥 ERPNext Users")
st.markdown("View all users currently registered in the provisioned ERPNext instance.")

bot_id = st.session_state.get("selected_bot_id")
if not bot_id:
    st.warning("Please select an active bot context from the sidebar.")
    st.stop()

with st.spinner("Fetching ERPNext users..."):
    try:
        users = CrmService.get_users(bot_id)
        if not users:
            st.info("No users found for this instance.")
        else:
            df = pd.DataFrame(users)
            
            # Format the dataframe for better display
            if not df.empty:
                # Rename columns for presentation
                display_df = df.rename(columns={
                    "name": "User ID",
                    "email": "Email Address",
                    "first_name": "First Name",
                    "last_name": "Last Name",
                    "enabled": "Status",
                    "role_profile_name": "Role Profile",
                    "creation": "Created At"
                })
                
                # Format status column
                if "Status" in display_df.columns:
                    display_df["Status"] = display_df["Status"].apply(
                        lambda x: "🟢 Active" if x == 1 else "🔴 Inactive"
                    )
                
                # Reorder columns
                cols = ["Email Address", "First Name", "Last Name", "Role Profile", "Status", "User ID", "Created At"]
                cols = [c for c in cols if c in display_df.columns]
                
                st.dataframe(
                    display_df[cols],
                    use_container_width=True,
                    hide_index=True
                )
    except Exception as e:
        st.error(f"Failed to fetch users: {str(e)}")
