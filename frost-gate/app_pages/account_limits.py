"""Account-Level Limits page.

Displays and allows modification of the three Cortex Code daily credit
limit parameters at the account level. These serve as defaults for all
users unless overridden per-user.
"""

import logging
import streamlit as st

logger = logging.getLogger("frostgate")
session = st.session_state["session"]

# Snowflake parameter names for daily AI credit limits per surface.
# These are the parameters set via ALTER ACCOUNT SET / UNSET.
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

    Submits all SHOW PARAMETERS queries asynchronously via Snowpark
    collect_nowait() and collects results in parallel.

    Returns:
        Dict mapping surface labels (CLI, Desktop, Snowsight) to dicts
        containing 'value', 'level', and 'param' keys.
    """
    logger.info("Fetching account-level parameters (async)")

    # Submit all queries asynchronously
    async_jobs = {}
    for label, param in PARAMS.items():
        sql = f"SHOW PARAMETERS LIKE '{param}' IN ACCOUNT"
        async_jobs[label] = session.sql(sql).collect_nowait()

    # Collect results
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
                logger.info("Account param %s: value=%s, level=%s", label, value, level)
            else:
                results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
        except Exception as e:
            logger.error("Failed to fetch account param %s: %s", label, e)
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
    return results


def display_limit_value(value):
    """Format a limit value for display.

    Args:
        value: The raw parameter value as a string or number.

    Returns:
        Human-readable string (e.g. "Unlimited (default)", "20 AI credits/day").
    """
    try:
        v = float(value)
        if v == -1:
            return "Unlimited (default)"
        elif v == 0:
            return "Blocked (0)"
        else:
            return f"{v:g} AI credits/day"
    except (ValueError, TypeError):
        return str(value)


# --- Page layout ---

st.title("Account-Level Limits")
st.markdown("These apply to **all users** unless overridden at the user level.")
st.info(
    "Account-level limits set the default daily AI credit cap for all users on each Cortex Code surface. "
    "A value of -1 (unlimited) means no cap is enforced. Setting a limit to 0 blocks usage entirely. "
    "Individual users can be given different limits on the User Limits page.",
    icon=":material/info:",
)

account_params = get_account_params()

cols = st.columns(3)
for i, (label, info) in enumerate(account_params.items()):
    with cols[i]:
        st.metric(label=f"{label}", value=display_limit_value(info["value"]), border=True, help=f"Current {label} daily AI credit limit for all users.")
        if info["level"] == "ACCOUNT":
            st.caption("Set at account level")
        else:
            st.caption("Using default (unlimited)")

st.divider()
st.subheader("Update Account Limits")

with st.form("account_form"):
    st.caption("Choose an action for each surface. The AI credits/day value only applies when 'Set limit' is selected.")
    form_cols = st.columns(3)
    account_actions = {}
    account_inputs = {}
    for i, (label, info) in enumerate(account_params.items()):
        with form_cols[i]:
            account_actions[label] = st.selectbox(
                f"{label}",
                options=["No change", "Set limit", "Set unlimited", "Block usage", "Unset (unlimited)"],
                key=f"account_action_{label}",
                help=f"Choose an action for the {label} daily AI credit limit.",
            )
            account_inputs[label] = st.number_input(
                f"AI Credits/day for {label}",
                min_value=0,
                value=25,
                step=1,
                key=f"account_val_{label}",
                help="Only applies when 'Set limit' is selected above.",
            )

    submitted = st.form_submit_button("Apply Account Changes")
    if submitted:
        app_user = st.session_state.get("current_user", "UNKNOWN")
        logger.info("[%s] Account form submitted", app_user)
        changes_made = []
        # Process each surface's selected action and execute the corresponding SQL
        for label in PARAMS:
            action = account_actions[label]
            param = PARAMS[label]
            if action == "No change":
                continue
            elif action == "Unset (unlimited)":
                logger.info("[%s] Unsetting account param: %s", app_user, param)
                try:
                    session.sql(f"ALTER ACCOUNT UNSET {param}").collect()
                    logger.info("[%s] Successfully unset account param: %s", app_user, param)
                    changes_made.append(f"**{label}**: unset (unlimited)")
                except Exception as e:
                    logger.error("[%s] Failed to unset account param %s: %s", app_user, param, e)
                    st.error(f"Failed to unset {label}: {e}")
            elif action == "Set unlimited":
                logger.info("[%s] Setting account param %s = -1 (unlimited)", app_user, param)
                try:
                    session.sql(f"ALTER ACCOUNT SET {param} = -1").collect()
                    logger.info("[%s] Successfully set account param %s = -1", app_user, param)
                    changes_made.append(f"**{label}**: set to unlimited (-1)")
                except Exception as e:
                    logger.error("[%s] Failed to set account param %s = -1: %s", app_user, param, e)
                    st.error(f"Failed to set {label} unlimited: {e}")
            elif action == "Block usage":
                logger.info("[%s] Blocking account param: %s (setting to 0)", app_user, param)
                try:
                    session.sql(f"ALTER ACCOUNT SET {param} = 0").collect()
                    logger.info("[%s] Successfully blocked account param: %s", app_user, param)
                    changes_made.append(f"**{label}**: blocked (0)")
                except Exception as e:
                    logger.error("[%s] Failed to block account param %s: %s", app_user, param, e)
                    st.error(f"Failed to block {label}: {e}")
            else:
                val = account_inputs[label]
                logger.info("[%s] Setting account param %s = %d", app_user, param, int(val))
                try:
                    session.sql(f"ALTER ACCOUNT SET {param} = {int(val)}").collect()
                    logger.info("[%s] Successfully set account param %s = %d", app_user, param, int(val))
                    changes_made.append(f"**{label}**: set to {int(val)} AI credits/day")
                except Exception as e:
                    logger.error("[%s] Failed to set account param %s = %d: %s", app_user, param, int(val), e)
                    st.error(f"Failed to set {label}: {e}")
        if changes_made:
            st.success("Account limits updated successfully:\n\n" + "\n\n".join(changes_made))
        else:
            st.info("No changes selected.")
