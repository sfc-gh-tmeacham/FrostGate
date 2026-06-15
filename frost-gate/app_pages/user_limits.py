"""User-Level Limits page.

Allows viewing and modifying per-user Cortex Code daily credit limit
overrides. Supports single-user updates, bulk updates across multiple
users, and scanning all users for existing overrides.
"""

import logging
import streamlit as st

from app_pages.common import PARAMS, USAGE_VIEWS, TIME_PERIODS, display_limit_value, get_user_list, fetch_params_async, apply_limit_action, normalize_row

logger = logging.getLogger("frostgate")
session = st.session_state["session"]


@st.cache_data(ttl=86400)
def get_user_details(_session, username):
    """Fetch user properties via DESCRIBE USER and last login via SHOW USERS.

    Returns a dict with display_name, email, default_role, default_warehouse, disabled, type, last_login.
    """
    try:
        rows = _session.sql(f'DESCRIBE USER "{username}"').collect()
        props = {}
        for row in rows:
            row_dict = row.as_dict()
            prop_name = row_dict.get("property", "").upper()
            prop_value = row_dict.get("value", None)
            props[prop_name] = prop_value

        # Get last login from SHOW USERS
        last_login = "—"
        try:
            user_rows = _session.sql(f"SHOW USERS LIKE '{username}'").collect()
            if user_rows:
                user_dict = normalize_row(user_rows[0])
                raw_login = user_dict.get("last_success_login", None)
                if raw_login:
                    from datetime import datetime
                    try:
                        dt = datetime.fromisoformat(str(raw_login))
                        last_login = dt.strftime("%b %d, %Y %I:%M %p")
                    except (ValueError, TypeError):
                        last_login = str(raw_login).split(".")[0]
        except Exception:
            pass

        return {
            "display_name": props.get("DISPLAY_NAME") or "—",
            "email": props.get("EMAIL") or "—",
            "default_role": props.get("DEFAULT_ROLE") or "—",
            "default_warehouse": props.get("DEFAULT_WAREHOUSE") or "—",
            "disabled": props.get("DISABLED", "false"),
            "type": props.get("TYPE") or "—",
            "last_login": last_login,
        }
    except Exception as e:
        logger.error("Failed to describe user %s: %s", username, e)
        return None


def get_user_params(username):
    """Fetch Cortex Code credit limit parameters for a specific user."""
    safe_user = username.replace('"', '""')
    return fetch_params_async(session, f'IN USER "{safe_user}"')





@st.cache_data(ttl=1800)
def fetch_user_usage(_session, user, days):
    """Fetch usage totals and summary for a user across all surfaces.

    Submits all queries asynchronously and returns results as dicts.
    Cached for 30 minutes.
    """
    safe_user = user.replace("'", "''")
    usage_jobs = {}
    compare_jobs = {}
    for label, view in USAGE_VIEWS.items():
        usage_jobs[label] = _session.sql(f"""
            SELECT
                ROUND(COALESCE(SUM(TOKEN_CREDITS), 0), 2) AS TOTAL_CREDITS,
                COUNT(*) AS TOTAL_REQUESTS
            FROM {view}
            WHERE USER_NAME = '{safe_user}'
              AND USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        """).collect_nowait()
        compare_jobs[label] = _session.sql(f"""
            WITH user_daily AS (
                SELECT DATE(USAGE_TIME) AS USAGE_DATE, SUM(TOKEN_CREDITS) AS DAILY_CREDITS
                FROM {view}
                WHERE USER_NAME = '{safe_user}'
                  AND USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
                GROUP BY DATE(USAGE_TIME)
            ),
            account_daily AS (
                SELECT DATE(USAGE_TIME) AS USAGE_DATE, USER_NAME, SUM(TOKEN_CREDITS) AS DAILY_CREDITS
                FROM {view}
                WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
                GROUP BY DATE(USAGE_TIME), USER_NAME
            )
            SELECT
                ROUND(COALESCE(MAX(u.DAILY_CREDITS), 0), 2) AS USER_MAX_DAY,
                ROUND(COALESCE(AVG(u.DAILY_CREDITS), 0), 2) AS USER_AVG_DAY,
                ROUND(COALESCE((SELECT AVG(DAILY_CREDITS) FROM account_daily), 0), 2) AS ACCOUNT_AVG_DAY
            FROM user_daily u
        """).collect_nowait()

    usage_results = {}
    compare_results = {}
    for label in USAGE_VIEWS:
        try:
            rows = usage_jobs[label].result()
            if rows:
                row_dict = {k.lower(): v for k, v in rows[0].as_dict().items()}
                usage_results[label] = {
                    "total_credits": float(row_dict.get("total_credits", 0)),
                    "total_requests": int(row_dict.get("total_requests", 0)),
                }
            else:
                usage_results[label] = {"total_credits": 0.0, "total_requests": 0}
        except Exception:
            usage_results[label] = None

        try:
            rows = compare_jobs[label].result()
            if rows:
                row_dict = {k.lower(): v for k, v in rows[0].as_dict().items()}
                compare_results[label] = {
                    "user_max_day": float(row_dict.get("user_max_day", 0)),
                    "user_avg_day": float(row_dict.get("user_avg_day", 0)),
                    "account_avg_day": float(row_dict.get("account_avg_day", 0)),
                }
            else:
                compare_results[label] = {"user_max_day": 0, "user_avg_day": 0, "account_avg_day": 0}
        except Exception:
            compare_results[label] = None

    return usage_results, compare_results


# --- Page layout ---

st.title("User-Level Limits")
st.markdown("User-level settings **override** account-level defaults for that user.")
st.info(
    "Set per-user daily AI AI credit limits to override the account default. "
    "If a user has no override, they inherit the account-level limit. "
    "Unsetting a user override returns them to the account default.",
    icon=":material/info:",
)

# Load the full user list (cached 24h) and provide a refresh button
users = get_user_list(session)

col_user, col_refresh = st.columns([4, 1])
with col_user:
    selected_user = st.selectbox("Select user", options=users, key="user_select", help="Choose a user to view or modify their AI credit limits. List is cached for 24 hours.")
with col_refresh:
    st.write("")
    st.write("")
    if st.button("Refresh users", key="refresh_users", help="Clear the user list cache and reload from Snowflake."):
        get_user_list.clear()
        st.rerun()

if selected_user:
    # Show user profile details (display name, email, role, etc.)
    user_details = get_user_details(session, selected_user)
    if user_details:
        detail_cols = st.columns(6)
        with detail_cols[0]:
            st.caption("Display Name")
            st.markdown(f"**{user_details['display_name']}**")
        with detail_cols[1]:
            st.caption("Email")
            st.markdown(user_details["email"])
        with detail_cols[2]:
            st.caption("Default Role")
            st.markdown(f"`{user_details['default_role']}`")
        with detail_cols[3]:
            st.caption("Default Warehouse")
            st.markdown(f"`{user_details['default_warehouse']}`")
        with detail_cols[4]:
            st.caption("Type")
            st.markdown(user_details["type"])
        with detail_cols[5]:
            st.caption("Last Login")
            st.markdown(user_details["last_login"])
        if user_details["disabled"] == "true":
            st.warning("This user account is disabled.", icon=":material/block:")

    # Fetch and display current limit settings for this user (async per surface)
    user_params = get_user_params(selected_user)

    st.markdown(f"**Current limits for `{selected_user}`:**")
    cols = st.columns(3)
    for i, (label, info) in enumerate(user_params.items()):
        with cols[i]:
            st.metric(label=f"{label}", value=display_limit_value(info["value"], verbose=True), border=True, help=f"Current {label} daily AI credit limit for this user.")
            # Indicate whether this is a per-user override or inherited from account
            if info["level"] == "USER":
                st.caption("User-level override")
            else:
                st.caption("Inheriting account default")

    st.divider()
    st.subheader(f"Update Limits for {selected_user}")

    with st.form("user_form"):
        st.caption("Choose an action for each surface. The AI credits/day value only applies when 'Set limit' is selected.")
        form_cols = st.columns(3)
        user_actions = {}
        user_inputs = {}
        for i, (label, info) in enumerate(user_params.items()):
            with form_cols[i]:
                user_actions[label] = st.selectbox(
                    f"{label}",
                    options=["No change", "Set limit", "Set unlimited", "Block usage", "Unset (inherit account)"],
                    key=f"user_action_{label}",
                    help=f"Set a per-user override for {label}, or unset to inherit the account default.",
                )
                user_inputs[label] = st.number_input(
                    f"AI Credits/day for {label}",
                    min_value=0,
                    value=25,
                    step=1,
                    key=f"user_val_{label}",
                    help="Only applies when 'Set limit' is selected above.",
                )

        user_submitted = st.form_submit_button("Apply User Changes", type="primary", icon=":material/check:")
        if user_submitted:
            app_user = st.session_state.get("current_user", "UNKNOWN")
            safe_user = selected_user.replace('"', '""')
            alter_target = f'USER "{safe_user}"'
            changes_made = []
            for label in PARAMS:
                if user_actions[label] == "No change":
                    continue
                try:
                    result = apply_limit_action(
                        session,
                        user_actions[label],
                        PARAMS[label],
                        label,
                        user_inputs[label],
                        alter_target,
                        app_user,
                    )
                    if result:
                        changes_made.append(result)
                except Exception as e:
                    st.error(f"Failed to update {label} for {selected_user}: {e}")
            if changes_made:
                st.success(f"Limits updated for **{selected_user}**:\n\n" + "\n\n".join(changes_made))
            elif not any(a != "No change" for a in user_actions.values()):
                st.info("No changes selected.")

    st.divider()

    usage_period = st.selectbox(
        "Usage lookback",
        options=list(TIME_PERIODS.keys()),
        index=0,
        key="user_usage_period",
    )
    usage_days = TIME_PERIODS[usage_period]

    st.markdown(f"**Usage for `{selected_user}` ({usage_period.lower()}):**")

    # Fetch usage totals and comparison stats (user vs account average)
    usage_results, compare_results = fetch_user_usage(session, selected_user, usage_days)

    # Display total credits and request count per surface
    usage_cols = st.columns(3)
    for i, label in enumerate(USAGE_VIEWS):
        with usage_cols[i]:
            data = usage_results.get(label)
            if data:
                st.metric(label=f"{label} AI Credits", value=f"{data['total_credits']:.2f}", border=True, help=f"Total estimated AI credits consumed via {label} in the selected period.")
                st.caption(f"{data['total_requests']:,} requests")
            else:
                st.metric(label=f"{label} AI Credits", value="N/A", border=True)
                st.caption("Could not load usage")

    # Display usage summary (peak day, avg/day vs account)
    st.markdown(f"**Usage summary for `{selected_user}` ({usage_period.lower()}):**")
    usage_compare_cols = st.columns(3)
    for i, label in enumerate(USAGE_VIEWS):
        with usage_compare_cols[i]:
            data = compare_results.get(label)
            if data:
                delta = round(data["user_avg_day"] - data["account_avg_day"], 2)
                st.metric(label=f"{label} Peak Day", value=f"{data['user_max_day']:.2f}", border=True, help=f"Highest single-day {label} AI credit usage in the period.")
                st.metric(label=f"{label} Avg/Day", value=f"{data['user_avg_day']:.2f}", delta=f"{delta:+.2f} vs acct avg", border=True, help=f"Average daily {label} AI credits. Delta shows difference from account-wide average.")
            else:
                st.metric(label=f"{label} Peak Day", value="N/A", border=True)
                st.metric(label=f"{label} Avg/Day", value="N/A", border=True)
