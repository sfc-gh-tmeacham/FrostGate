"""FrostGate - Cortex Code Credit Usage Limit Manager.

Main entry point for the Streamlit multi-page application. Establishes
the Snowflake session and configures top-level navigation.
"""

import os
import sys
import logging
import streamlit as st

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("frostgate")

st.set_page_config(page_title="FrostGate", page_icon="\u2744\ufe0f", layout="wide", initial_sidebar_state="collapsed")

# Hide sidebar when using top navigation
st.html("""
<style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
</style>
""")

st.title(":material/ac_unit: FrostGate")

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
st.session_state["session"] = conn.session()
logger.info("Session established")

page = st.navigation([
    st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("app_pages/dashboard.py", title="Usage Dashboard", icon=":material/bar_chart:"),
    st.Page("app_pages/top_users.py", title="Top Users", icon=":material/leaderboard:"),
    st.Page("app_pages/account_limits.py", title="Account Limits", icon=":material/tune:"),
    st.Page("app_pages/user_limits.py", title="User Limits", icon=":material/person:"),
    st.Page("app_pages/bulk_update.py", title="Bulk User Update", icon=":material/group:"),
], position="top")

page.run()
