import os
import sys

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import streamlit as st
from components.ui import inject_custom_css
from components.auth import is_authenticated, render_login_form

st.set_page_config(
    page_title="Kairon Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded" if is_authenticated() else "collapsed",
)
inject_custom_css()

if not is_authenticated():
    render_login_form()
    st.stop()

pg = st.navigation(
    {
        "Kairon Platform": [
            st.Page("views/1_Tier_Selection.py", title="Tier Selection", icon="⚡"),
        ],
        "Tier 1 — CRM & ERPNext": [
            st.Page("views/2_CRM_Onboarding.py", title="CRM Onboarding", icon="🏢"),
            st.Page("views/3_Invite_User.py", title="Invite User", icon="✉️"),
        ],
    }
)
pg.run()
