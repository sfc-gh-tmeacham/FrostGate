"""SQL Reference page.

Provides SQL examples for manually performing the operations
that FrostGate automates through its UI.
"""

import streamlit as st

st.title("SQL Reference")
st.info(
    "These are the SQL commands that FrostGate runs behind the scenes. "
    "Use them as a reference for manual operations, scripting, or troubleshooting.",
    icon=":material/code:",
)

st.divider()

# --- View Current Account Limits ---
st.markdown("##### View Current Account Limits")
st.caption("Check what limits are currently set at the account level for each surface.")

st.code("""
-- Snowsight
SHOW PARAMETERS LIKE 'CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER' IN ACCOUNT;

-- CLI
SHOW PARAMETERS LIKE 'CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER' IN ACCOUNT;

-- Desktop
SHOW PARAMETERS LIKE 'CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER' IN ACCOUNT;
""", language="sql")

st.divider()

# --- Set Account Limits ---
st.markdown("##### Set Account Limits")
st.caption("Set a daily AI credit cap for all users on a surface. Replace 25 with your desired limit.")

st.code("""
-- Set Snowsight limit to 25 AI credits/day
ALTER ACCOUNT SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 25;

-- Set CLI limit to 25 AI credits/day
ALTER ACCOUNT SET CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER = 25;

-- Set Desktop limit to 25 AI credits/day
ALTER ACCOUNT SET CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER = 25;
""", language="sql")

st.divider()

# --- Block Usage ---
st.markdown("##### Block Usage (Set to 0)")
st.caption("Setting a limit to 0 blocks all usage on that surface.")

st.code("""
-- Block Snowsight usage for all users
ALTER ACCOUNT SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 0;

-- Block a specific user on Snowsight
ALTER USER "USERNAME" SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 0;
""", language="sql")

st.divider()

# --- Unset (Unlimited) ---
st.markdown("##### Unset Limits (Unlimited)")
st.caption("Unsetting a parameter returns it to the default (-1 = unlimited). You can also explicitly set -1.")

st.code("""
-- Remove account-level Snowsight limit (reverts to unlimited)
ALTER ACCOUNT UNSET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER;

-- Or explicitly set to -1 (equivalent to unlimited)
ALTER ACCOUNT SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = -1;

-- Remove per-user override (user inherits account default)
ALTER USER "USERNAME" UNSET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER;

-- Or explicitly set user to unlimited
ALTER USER "USERNAME" SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = -1;
""", language="sql")

st.divider()

# --- Per-User Limits ---
st.markdown("##### Per-User Limits")
st.caption("Set or view limits for a specific user. These override account defaults.")

st.code("""
-- View a user's current limits
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' FOR USER "USERNAME";

-- Set per-user Snowsight limit
ALTER USER "USERNAME" SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 10;

-- Set per-user CLI limit
ALTER USER "USERNAME" SET CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER = 10;

-- Set per-user Desktop limit
ALTER USER "USERNAME" SET CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER = 10;
""", language="sql")

st.divider()

# --- Query Usage History ---
st.markdown("##### Query Usage History")
st.caption("Query the ACCOUNT_USAGE views to see AI credit consumption. Data may lag up to 45 minutes.")

st.code("""
-- Snowsight usage in the last 7 days (per user, per day)
SELECT
    USER_NAME,
    DATE(USAGE_TIME) AS USAGE_DATE,
    ROUND(SUM(TOKEN_CREDITS), 2) AS DAILY_CREDITS,
    COUNT(*) AS REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY USER_NAME, DATE(USAGE_TIME)
ORDER BY DAILY_CREDITS DESC;
""", language="sql")

st.code("""
-- CLI usage in the last 7 days
SELECT
    USER_NAME,
    DATE(USAGE_TIME) AS USAGE_DATE,
    ROUND(SUM(TOKEN_CREDITS), 2) AS DAILY_CREDITS,
    COUNT(*) AS REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY USER_NAME, DATE(USAGE_TIME)
ORDER BY DAILY_CREDITS DESC;
""", language="sql")

st.code("""
-- Desktop usage in the last 7 days
SELECT
    USER_NAME,
    DATE(USAGE_TIME) AS USAGE_DATE,
    ROUND(SUM(TOKEN_CREDITS), 2) AS DAILY_CREDITS,
    COUNT(*) AS REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY USER_NAME, DATE(USAGE_TIME)
ORDER BY DAILY_CREDITS DESC;
""", language="sql")

st.divider()

# --- Total Usage Across All Surfaces ---
st.markdown("##### Total Usage Across All Surfaces")
st.caption("Combine all three surfaces for a holistic view.")

st.code("""
-- Combined usage summary (last 30 days)
SELECT
    'Snowsight' AS SURFACE, USER_NAME,
    ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(*) AS TOTAL_REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY USER_NAME

UNION ALL

SELECT
    'CLI' AS SURFACE, USER_NAME,
    ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(*) AS TOTAL_REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY USER_NAME

UNION ALL

SELECT
    'Desktop' AS SURFACE, USER_NAME,
    ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(*) AS TOTAL_REQUESTS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY USER_NAME

ORDER BY TOTAL_CREDITS DESC;
""", language="sql")

st.divider()

# --- Identify Users with Overrides ---
st.markdown("##### Identify Users with Overrides")
st.caption("Find all users who have per-user limit overrides set.")

st.code("""
-- Check each user for overrides (run per user)
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' FOR USER "USERNAME";

-- Look for rows where LEVEL = 'USER' in the output
-- to identify per-user overrides vs inherited account defaults.
""", language="sql")

st.divider()
st.caption("All parameters use -1 as the default (unlimited). A value of 0 blocks usage entirely.")
