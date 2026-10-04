import streamlit as st
from components.ui import inject_custom_css, render_sidebar
from components.auth import require_login

inject_custom_css()
render_sidebar()
require_login()

st.markdown(
    '# Kairon <span class="gradient-text">Platform</span>',
    unsafe_allow_html=True,
)
st.caption("Available integrations for the selected bot.")
st.markdown("---")

user_info = st.session_state.get("user_info", {})
name = f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}".strip() or user_info.get("email", "User")
st.markdown(f"Logged in as **{name}** ({user_info.get('email', 'unknown')})")

st.markdown("<br>", unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    st.markdown(
        """
        <div class="glass-card" style="border-left:3px solid #10B981;">
            <h3>🏢 CRM &amp; ERPNext</h3>
            <p>Authentication, bot verification, and end-to-end ERPNext CRM tenant onboarding.</p>
            <span class="badge badge-completed">STATUS: AVAILABLE</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Open CRM & ERPNext →", use_container_width=True, type="primary"):
        st.switch_page("views/2_CRM_Onboarding.py")

with col2:
    st.markdown(
        """
        <div class="glass-card" style="opacity:0.55;">
            <h3>🍽️ POS</h3>
            <p>Point-of-sale tenant onboarding and menu management.</p>
            <span class="badge badge-pending">COMING SOON</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Open POS", use_container_width=True, disabled=True)

col3, col4 = st.columns(2)
with col3:
    st.markdown(
        """
        <div class="glass-card" style="opacity:0.55;">
            <h3>🧾 KOT</h3>
            <p>Kitchen order ticket tenant onboarding and station management.</p>
            <span class="badge badge-pending">COMING SOON</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Open KOT", use_container_width=True, disabled=True)

with col4:
    st.markdown(
        """
        <div class="glass-card" style="opacity:0.55;">
            <h3>🔮 Future Integration</h3>
            <p>Additional Kairon-native integrations, reserved for future tiers.</p>
            <span class="badge badge-pending">COMING SOON</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.button("Open Integration", use_container_width=True, disabled=True)
