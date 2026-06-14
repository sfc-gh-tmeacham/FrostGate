"""Bulk Update page.

Apply the same credit limit changes to multiple users at once,
and view all users who currently have per-user overrides.
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


def get_users(sess):
    """Fetch list of user names from the account."""
    rows = sess.sql("SHOW USERS").collect()
    return sorted([r["name"] for r in rows])


def get_user_params(user):
    """Fetch current per-user Cortex Code credit limit parameters."""
    safe_user = user.replace("'", "''")
    async_jobs = {}
    for label, param in PARAMS.items():
        sql = f"SHOW PARAMETERS LIKE '{param}' FOR USER \"{user}\""
        async_jobs[label] = session.sql(sql).collect_nowait()

    results = {}
    for label, job in async_jobs.items():
        param = PARAMS[label]
        try:
            rows = job.result()
            if rows:
                row = rows[0].as_dict()
                row_lower = {k.lower(): v for k, v in row.items()}
                value = str(row_lower.get("value", "-1"))
                level = str(row_lower.get("level", "")).upper()
                results[label] = {"value": value, "level": level, "param": param}
            else:
                results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
        except Exception as e:
            logger.error("Failed to fetch param %s for %s: %s", label, user, e)
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
    return results


def display_limit_value(value):
    """Format a limit value for display."""
    try:
        v = float(value)
        if v == -1:
            return "Unlimited"
        elif v == 0:
            return "Blocked"
        else:
            return f"{v:g}"
    except (ValueError, TypeError):
        return str(value)


# --- Page layout ---

st.title("Bulk User Update")
st.info(
    "Use this page to apply the same limit changes to multiple users at once. "
    "Select users below, choose an action for each surface, and submit to update them all in one operation.",
    icon=":material/group:",
)

users = get_users(session)

bulk_users = st.multiselect("Select users to update", options=users, key="bulk_user_select", help="Select one or more users to apply the same limit changes to all of them.")

if bulk_users:
    with st.form("bulk_user_form"):
        st.markdown(f"**Apply the same limits to {len(bulk_users)} selected user(s):**")
        st.caption("Choose an action for each surface. The AI credits/day value only applies when 'Set limit' is selected.")
        bulk_cols = st.columns(3)
        bulk_actions = {}
        bulk_inputs = {}
        for i, (label, param) in enumerate(PARAMS.items()):
            with bulk_cols[i]:
                bulk_actions[label] = st.selectbox(
                    f"{label}",
                    options=["No change", "Set limit", "Block usage", "Unset (inherit account)"],
                    key=f"bulk_action_{label}",
                    help=f"Action to apply for {label} across all selected users.",
                )
                bulk_inputs[label] = st.number_input(
                    f"AI Credits/day for {label}",
                    min_value=0,
                    value=25,
                    step=1,
                    key=f"bulk_val_{label}",
                    help="Only applies when 'Set limit' is selected above.",
                )

        bulk_submitted = st.form_submit_button("Apply to All Selected Users")
        if bulk_submitted:
            logger.info("Bulk update submitted for %d users", len(bulk_users))
            changes_made = False
            for user in bulk_users:
                safe_user = user.replace('"', '""')
                for label in PARAMS:
                    action = bulk_actions[label]
                    param = PARAMS[label]
                    if action == "No change":
                        continue
                    elif action == "Unset (inherit account)":
                        try:
                            session.sql(f'ALTER USER "{safe_user}" UNSET {param}').collect()
                            logger.info("Unset %s for %s", param, user)
                            changes_made = True
                        except Exception as e:
                            logger.error("Failed: %s for %s: %s", param, user, e)
                            st.error(f"Failed to unset {label} for {user}: {e}")
                    elif action == "Block usage":
                        try:
                            session.sql(f'ALTER USER "{safe_user}" SET {param} = 0').collect()
                            logger.info("Blocked %s for %s", param, user)
                            changes_made = True
                        except Exception as e:
                            logger.error("Failed to block %s for %s: %s", param, user, e)
                            st.error(f"Failed to block {label} for {user}: {e}")
                    else:
                        val = bulk_inputs[label]
                        try:
                            session.sql(f'ALTER USER "{safe_user}" SET {param} = {int(val)}').collect()
                            logger.info("Set %s = %d for %s", param, int(val), user)
                            changes_made = True
                        except Exception as e:
                            logger.error("Failed: %s = %d for %s: %s", param, int(val), user, e)
                            st.error(f"Failed to set {label} for {user}: {e}")
            if changes_made:
                st.success(f"Limits applied to {len(bulk_users)} user(s).")
                st.rerun()
            else:
                st.info("No changes selected.")

st.divider()
st.subheader("All Users with Overrides")
st.caption("Scan all users to find those with per-user limit overrides.")
st.info(
    "This table shows users who have a per-user daily credit limit set (overriding the account default). "
    "Values represent the maximum estimated AI credits per day allowed for that surface. "
    "'—' means no override is set for that surface (inherits account default).",
    icon=":material/info:",
)

if st.button("Scan Users", key="scan_btn"):
    logger.info("Bulk scan initiated")
    user_overrides = {}
    for user in users:
        uparams = get_user_params(user)
        row = {}
        for label, info in uparams.items():
            if info["level"] == "USER":
                row[label] = display_limit_value(info["value"])
        if row:
            user_overrides[user] = row
    logger.info("Bulk scan complete: found %d users with overrides", len(user_overrides))
    if user_overrides:
        table_data = []
        for user, limits in user_overrides.items():
            table_data.append({
                "User": user,
                "CLI (AI credits/day)": limits.get("CLI", "—"),
                "Desktop (AI credits/day)": limits.get("Desktop", "—"),
                "Snowsight (AI credits/day)": limits.get("Snowsight", "—"),
            })
        st.dataframe(table_data, use_container_width=True)
    else:
        st.info("No user-level overrides found.")
