"""FrostGate - Cortex Code Credit Usage Limit Manager.

Main entry point for the Streamlit multi-page application. Establishes
the Snowflake session and configures top-level navigation.
"""

import os
import sys
import logging
import streamlit as st

# Configure structured logging to stdout for observability in container runtime
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("frostgate")

st.set_page_config(page_title="FrostGate", page_icon="\u2744\ufe0f", layout="wide", initial_sidebar_state="collapsed")

# Hide the default sidebar since we use top-positioned navigation tabs instead
st.html("""
<style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
</style>
""")

st.title(":material/ac_unit: FrostGate")

# Establish Snowflake connection using the built-in Streamlit connector.
# TTL is configurable via env var to control session refresh frequency.
conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))

# Store Snowpark session and current user in session_state so all pages can access them
st.session_state["session"] = conn.session()
st.session_state["current_user"] = conn.session().sql("SELECT CURRENT_USER()").collect()[0][0]
logger.info("Session established for user: %s", st.session_state["current_user"])

# Verify the user has sufficient privileges (ACCOUNTADMIN or equivalent)
try:
    current_role = conn.session().sql("SELECT CURRENT_ROLE()").collect()[0][0]
    conn.session().sql(
        "SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY LIMIT 0"
    ).collect()
except Exception:
    st.error(
        f"**Insufficient privileges.** Your current role (`{current_role}`) does not have access "
        "to the `SNOWFLAKE.ACCOUNT_USAGE` views required by FrostGate.\n\n"
        "This app requires the **ACCOUNTADMIN** role (or a custom role with "
        "`IMPORTED PRIVILEGES` on the `SNOWFLAKE` database) to read usage history "
        "and modify account/user parameters.\n\n"
        "Switch to an authorized role and reload the page.",
        icon=":material/shield:",
    )
    st.stop()

# Define the multi-page navigation structure with top-positioned tabs
page = st.navigation([
    st.Page("app_pages/home.py", title="Home", icon=":material/home:", default=True),
    st.Page("app_pages/dashboard.py", title="Usage Dashboard", icon=":material/bar_chart:"),
    st.Page("app_pages/top_users.py", title="Top Users", icon=":material/leaderboard:"),
    st.Page("app_pages/account_limits.py", title="Account Limits", icon=":material/tune:"),
    st.Page("app_pages/user_limits.py", title="User Limits", icon=":material/person:"),
    st.Page("app_pages/bulk_update.py", title="Bulk User Update", icon=":material/group:"),
    st.Page("app_pages/sql_reference.py", title="SQL Reference", icon=":material/code:"),
], position="top")

page.run()
