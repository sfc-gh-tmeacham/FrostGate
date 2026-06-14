"""User-Level Limits page.

Allows viewing and modifying per-user Cortex Code daily credit limit
overrides. Supports single-user updates, bulk updates across multiple
users, and scanning all users for existing overrides.
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


def _get_param_value(sql):
    """Execute a SHOW PARAMETERS query and return the first row as a dict.

    Args:
        sql: The SHOW PARAMETERS SQL statement to execute.

    Returns:
        A dict with lowercase keys from the result row, or None if empty.
    """
    rows = session.sql(sql).collect()
    if not rows:
        return None
    row = rows[0].as_dict()
    row_lower = {k.lower(): v for k, v in row.items()}
    return row_lower


@st.cache_data(ttl=60)
def get_users(_session):
    """Fetch the list of all users in the account.

    Args:
        _session: Snowpark session (underscore prefix for st.cache_data).

    Returns:
        Sorted list of user name strings.
    """
    logger.info("Fetching user list")
    df = _session.sql("SHOW USERS").to_pandas()
    col_map = {c.lower(): c for c in df.columns}
    name_col = col_map.get("name", df.columns[0])
    users = sorted(df[name_col].tolist())
    logger.info("Found %d users", len(users))
    return users


def get_user_params(username):
    """Fetch Cortex Code credit limit parameters for a specific user.

    Args:
        username: The Snowflake username to query.

    Returns:
        Dict mapping surface labels to dicts with 'value', 'level', 'param'.
    """
    logger.info("Fetching parameters for user: %s", username)
    results = {}
    safe_user = username.replace('"', '""')
    for label, param in PARAMS.items():
        row_lower = _get_param_value(f"SHOW PARAMETERS LIKE '{param}' IN USER \"{safe_user}\"")
        if row_lower:
            value = str(row_lower.get("value", "-1"))
            level = str(row_lower.get("level", "")).upper()
            results[label] = {"value": value, "level": level, "param": param}
            logger.info("User %s param %s: value=%s, level=%s", username, label, value, level)
        else:
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
    return results


def display_limit_value(value):
    """Format a limit value for display.

    Args:
        value: The raw parameter value as a string or number.

    Returns:
        Human-readable string (e.g. "Unlimited (default)", "20 credits/day").
    """
    try:
        v = float(value)
        if v == -1:
            return "Unlimited (default)"
        elif v == 0:
            return "Blocked (0)"
        else:
            return f"{v:g} credits/day"
    except (ValueError, TypeError):
        return str(value)


# --- Page layout ---

st.title("User-Level Limits")
st.markdown("User-level settings **override** account-level defaults for that user.")

users = get_users(session)

selected_user = st.selectbox("Select user", options=users, key="user_select", help="Choose a user to view or modify their credit limits.")

if selected_user:
    user_params = get_user_params(selected_user)

    st.markdown(f"**Current limits for `{selected_user}`:**")
    cols = st.columns(3)
    for i, (label, info) in enumerate(user_params.items()):
        with cols[i]:
            st.metric(label=f"{label}", value=display_limit_value(info["value"]))
            if info["level"] == "USER":
                st.caption("User-level override")
            else:
                st.caption("Inheriting account default")

    st.divider()
    st.subheader(f"Update Limits for {selected_user}")

    with st.form("user_form"):
        form_cols = st.columns(3)
        user_actions = {}
        user_inputs = {}
        for i, (label, info) in enumerate(user_params.items()):
            with form_cols[i]:
                user_actions[label] = st.selectbox(
                    f"{label}",
                    options=["No change", "Set limit", "Unset (inherit account)"],
                    key=f"user_action_{label}",
                    help=f"Set a per-user override for {label}, or unset to inherit the account default.",
                )
                user_inputs[label] = st.number_input(
                    f"Credits/day for {label}",
                    min_value=0,
                    value=10,
                    step=1,
                    key=f"user_val_{label}",
                )

        user_submitted = st.form_submit_button("Apply User Changes")
        if user_submitted:
            logger.info("User form submitted for user: %s", selected_user)
            changes_made = False
            safe_user = selected_user.replace('"', '""')
            for label in PARAMS:
                action = user_actions[label]
                param = PARAMS[label]
                if action == "No change":
                    continue
                elif action == "Unset (inherit account)":
                    logger.info("Unsetting user %s param: %s", selected_user, param)
                    try:
                        session.sql(f'ALTER USER "{safe_user}" UNSET {param}').collect()
                        logger.info("Successfully unset user %s param: %s", selected_user, param)
                        changes_made = True
                    except Exception as e:
                        logger.error("Failed to unset user %s param %s: %s", selected_user, param, e)
                        st.error(f"Failed to unset {label} for {selected_user}: {e}")
                else:
                    val = user_inputs[label]
                    logger.info("Setting user %s param %s = %d", selected_user, param, int(val))
                    try:
                        session.sql(f'ALTER USER "{safe_user}" SET {param} = {int(val)}').collect()
                        logger.info("Successfully set user %s param %s = %d", selected_user, param, int(val))
                        changes_made = True
                    except Exception as e:
                        logger.error("Failed to set user %s param %s = %d: %s", selected_user, param, int(val), e)
                        st.error(f"Failed to set {label} for {selected_user}: {e}")
            if changes_made:
                st.success(f"Limits updated for {selected_user}.")
                st.rerun()
            else:
                st.info("No changes selected.")

st.divider()
st.subheader("Bulk Update Multiple Users")

bulk_users = st.multiselect("Select users to update", options=users, key="bulk_user_select", help="Select one or more users to apply the same limit changes to all of them.")

if bulk_users:
    with st.form("bulk_user_form"):
        st.markdown(f"**Apply the same limits to {len(bulk_users)} selected user(s):**")
        bulk_cols = st.columns(3)
        bulk_actions = {}
        bulk_inputs = {}
        for i, (label, param) in enumerate(PARAMS.items()):
            with bulk_cols[i]:
                bulk_actions[label] = st.selectbox(
                    f"{label}",
                    options=["No change", "Set limit", "Unset (inherit account)"],
                    key=f"bulk_action_{label}",
                    help=f"Action to apply for {label} across all selected users.",
                )
                bulk_inputs[label] = st.number_input(
                    f"Credits/day for {label}",
                    min_value=0,
                    value=10,
                    step=1,
                    key=f"bulk_val_{label}",
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
with st.expander("Bulk View: All Users with Overrides"):
    if st.button("Scan Users", key="scan_btn"):
        logger.info("Bulk scan initiated")
        overrides = []
        for user in users:
            uparams = get_user_params(user)
            for label, info in uparams.items():
                if info["level"] == "USER":
                    overrides.append({
                        "User": user,
                        "Surface": label,
                        "Limit": display_limit_value(info["value"]),
                    })
        logger.info("Bulk scan complete: found %d overrides", len(overrides))
        if overrides:
            st.dataframe(overrides, use_container_width=True)
        else:
            st.info("No user-level overrides found.")
