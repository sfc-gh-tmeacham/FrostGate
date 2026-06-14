"""Account-Level Limits page.

Displays and allows modification of the three Cortex Code daily credit
limit parameters at the account level. These serve as defaults for all
users unless overridden per-user.
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


def get_account_params():
    """Fetch current account-level Cortex Code credit limit parameters.

    Returns:
        Dict mapping surface labels (CLI, Desktop, Snowsight) to dicts
        containing 'value', 'level', and 'param' keys.
    """
    logger.info("Fetching account-level parameters")
    results = {}
    for label, param in PARAMS.items():
        row_lower = _get_param_value(f"SHOW PARAMETERS LIKE '{param}' IN ACCOUNT")
        if row_lower:
            value = str(row_lower.get("value", "-1"))
            level = str(row_lower.get("level", "")).upper()
            results[label] = {"value": value, "level": level, "param": param}
            logger.info("Account param %s: value=%s, level=%s", label, value, level)
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

st.title("Account-Level Limits")
st.markdown("These apply to **all users** unless overridden at the user level.")

account_params = get_account_params()

cols = st.columns(3)
for i, (label, info) in enumerate(account_params.items()):
    with cols[i]:
        st.metric(label=f"{label}", value=display_limit_value(info["value"]))
        if info["level"] == "ACCOUNT":
            st.caption("Set at account level")
        else:
            st.caption("Using default (unlimited)")

st.divider()
st.subheader("Update Account Limits")

with st.form("account_form"):
    form_cols = st.columns(3)
    account_actions = {}
    account_inputs = {}
    for i, (label, info) in enumerate(account_params.items()):
        with form_cols[i]:
            account_actions[label] = st.selectbox(
                f"{label}",
                options=["No change", "Set limit", "Unset (unlimited)"],
                key=f"account_action_{label}",
                help=f"Choose an action for the {label} daily credit limit.",
            )
            account_inputs[label] = st.number_input(
                f"Credits/day for {label}",
                min_value=0,
                value=20,
                step=1,
                key=f"account_val_{label}",
            )

    submitted = st.form_submit_button("Apply Account Changes")
    if submitted:
        logger.info("Account form submitted")
        changes_made = False
        for label in PARAMS:
            action = account_actions[label]
            param = PARAMS[label]
            if action == "No change":
                continue
            elif action == "Unset (unlimited)":
                logger.info("Unsetting account param: %s", param)
                try:
                    session.sql(f"ALTER ACCOUNT UNSET {param}").collect()
                    logger.info("Successfully unset account param: %s", param)
                    changes_made = True
                except Exception as e:
                    logger.error("Failed to unset account param %s: %s", param, e)
                    st.error(f"Failed to unset {label}: {e}")
            else:
                val = account_inputs[label]
                logger.info("Setting account param %s = %d", param, int(val))
                try:
                    session.sql(f"ALTER ACCOUNT SET {param} = {int(val)}").collect()
                    logger.info("Successfully set account param %s = %d", param, int(val))
                    changes_made = True
                except Exception as e:
                    logger.error("Failed to set account param %s = %d: %s", param, int(val), e)
                    st.error(f"Failed to set {label}: {e}")
        if changes_made:
            st.success("Account limits updated.")
            st.rerun()
        else:
            st.info("No changes selected.")
