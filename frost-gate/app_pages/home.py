"""Home page.

Landing page for FrostGate that explains the application's purpose
and guides new users on how to use each section.
"""

import logging
import streamlit as st

logger = logging.getLogger("frostgate")
session = st.session_state["session"]

PARAMS = {
    "CLI": "CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Desktop": "CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Snowsight": "CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER",
}

USAGE_VIEWS = {
    "CLI": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY",
    "Desktop": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY",
    "Snowsight": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY",
}


@st.cache_data(ttl=3600)
def get_system_health(_session):
    """Fetch account limit status and 7-day usage summary for the homepage."""
    # Get account limits
    limit_jobs = {}
    for label, param in PARAMS.items():
        limit_jobs[label] = _session.sql(f"SHOW PARAMETERS LIKE '{param}' IN ACCOUNT").collect_nowait()

    # Get 7-day usage totals per surface
    usage_jobs = {}
    for label, view in USAGE_VIEWS.items():
        usage_jobs[label] = _session.sql(f"""
            SELECT
                ROUND(COALESCE(SUM(TOKEN_CREDITS), 0), 2) AS TOTAL_CREDITS,
                COUNT(*) AS TOTAL_REQUESTS,
                COUNT(DISTINCT USER_NAME) AS ACTIVE_USERS
            FROM {view}
            WHERE USAGE_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
        """).collect_nowait()

    # Collect limits
    limits = {}
    for label, job in limit_jobs.items():
        try:
            rows = job.result()
            if rows:
                row = {k.lower(): v for k, v in rows[0].as_dict().items()}
                value = str(row.get("value", "-1"))
                level = str(row.get("level", "")).upper()
                limits[label] = {"value": value, "level": level}
            else:
                limits[label] = {"value": "-1", "level": "DEFAULT"}
        except Exception:
            limits[label] = {"value": "-1", "level": "DEFAULT"}

    # Collect usage
    usage = {}
    for label, job in usage_jobs.items():
        try:
            rows = job.result()
            if rows:
                row = {k.lower(): v for k, v in rows[0].as_dict().items()}
                usage[label] = {
                    "credits": float(row.get("total_credits", 0)),
                    "requests": int(row.get("total_requests", 0)),
                    "users": int(row.get("active_users", 0)),
                }
            else:
                usage[label] = {"credits": 0.0, "requests": 0, "users": 0}
        except Exception:
            usage[label] = {"credits": 0.0, "requests": 0, "users": 0}

    return limits, usage

st.markdown("")

st.subheader("Cortex Code AI Credit Usage Limit Manager", anchor=False)
st.markdown(
    "Monitor consumption, set daily caps, and identify power users across "
    "all Cortex Code surfaces — from a single pane of glass."
)
st.caption("Use the navigation tabs at the top of the page to switch between sections.")

st.markdown("")

# --- Quick stats ---
stat_cols = st.columns(3)
with stat_cols[0]:
    st.metric("Surfaces Monitored", "3", border=True, help="Snowsight, CLI, and Desktop")
with stat_cols[1]:
    st.metric("Control Levels", "2", border=True, help="Account-wide defaults and per-user overrides")
with stat_cols[2]:
    st.metric("Data Latency", "~45 min", border=True, help="ACCOUNT_USAGE views may lag up to 45 minutes behind real-time")

st.divider()

# --- System Health ---
st.markdown("##### System Health")
st.caption("Live account limit status and 7-day usage summary. Cached for 1 hour.")

limits, usage = get_system_health(session)

# Account limit status
st.markdown("**Account Limits**")
limit_cols = st.columns(3)
for i, (label, info) in enumerate(limits.items()):
    with limit_cols[i]:
        val = info["value"]
        try:
            v = float(val)
            if v == -1:
                display_val = "Unlimited"
                delta = None
            elif v == 0:
                display_val = "Blocked"
                delta = "usage blocked"
            else:
                display_val = f"{v:g}"
                delta = "AI credits/day"
        except (ValueError, TypeError):
            display_val = val
            delta = None
        st.metric(
            label=f"{label} Limit",
            value=display_val,
            delta=delta,
            border=True,
            help=f"Current account-level daily AI credit cap for {label}. Level: {info['level']}",
        )

# 7-day usage summary
st.markdown("**Last 7 Days Usage**")
usage_cols = st.columns(3)
for i, (label, data) in enumerate(usage.items()):
    with usage_cols[i]:
        st.metric(
            label=f"{label}",
            value=f"{data['credits']:.1f} AI credits",
            delta=f"{data['users']} users · {data['requests']:,} requests",
            delta_color="off",
            border=True,
            help=f"Total AI credits consumed via {label} in the last 7 days, with active user and request counts.",
        )

st.divider()

# --- What is FrostGate ---
st.markdown("##### What is FrostGate?")
st.markdown(
    "Cortex Code consumes **AI credits** (separate from warehouse compute credits) each time a user "
    "interacts with it. Snowflake exposes account-level and user-level parameters to cap daily usage. "
    "FrostGate wraps these controls in a friendly UI with usage dashboards, trend analysis, and bulk management."
)

st.divider()

# --- Pages guide ---
st.markdown("##### Pages")

row1 = st.columns(3)
with row1[0]:
    with st.container(border=True):
        st.markdown(":material/bar_chart: **Usage Dashboard**")
        st.caption("Daily metrics with sparklines, request counts, and active users over configurable periods.")

with row1[1]:
    with st.container(border=True):
        st.markdown(":material/leaderboard: **Top Users**")
        st.caption("Top 20 consumers, trend charts, MoM growth, and Pareto analysis for cost drivers.")

with row1[2]:
    with st.container(border=True):
        st.markdown(":material/tune: **Account Limits**")
        st.caption("View and set account-wide daily AI credit caps that apply to all users by default.")

row2 = st.columns(3)
with row2[0]:
    with st.container(border=True):
        st.markdown(":material/person: **User Limits**")
        st.caption("Inspect user details, current limits, and usage. Set per-user overrides.")

with row2[1]:
    with st.container(border=True):
        st.markdown(":material/group: **Bulk User Update**")
        st.caption("Apply limit changes to multiple users at once. Scan for existing overrides.")

with row2[2]:
    st.markdown("")

st.divider()

# --- Key Concepts ---
st.markdown("##### Key Concepts")

col_l, col_r = st.columns(2)
with col_l:
    with st.container(border=True):
        st.markdown(":material/token: **AI Credits**")
        st.caption("Unit of Cortex Code consumption. Separate from warehouse compute credits.")
    with st.container(border=True):
        st.markdown(":material/devices: **Surfaces**")
        st.caption("Snowsight (web), CLI (terminal), Desktop (VS Code / IDE).")
    with st.container(border=True):
        st.markdown(":material/schedule: **Data Latency**")
        st.caption("ACCOUNT_USAGE views may lag up to 45 minutes behind real-time usage.")

with col_r:
    with st.container(border=True):
        st.markdown(":material/domain: **Account Limits**")
        st.caption("Default daily caps for all users. -1 = unlimited, 0 = blocked.")
    with st.container(border=True):
        st.markdown(":material/person_edit: **User Overrides**")
        st.caption("Per-user limits override account defaults. Unset to revert.")
    with st.container(border=True):
        st.markdown(":material/bolt: **Pareto Principle**")
        st.caption("Identifies the ~20% of users who drive ~80% of AI credit consumption.")

st.divider()
st.warning(
    "This application requires the **ACCOUNTADMIN** role (or a role with equivalent privileges) "
    "to view and modify credit limit parameters.",
    icon=":material/shield:",
)
