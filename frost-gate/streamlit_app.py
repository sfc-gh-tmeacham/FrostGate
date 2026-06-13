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

conn = st.connection("snowflake", ttl=os.getenv("SNOWFLAKE_CONNECTION_TTL"))
session = conn.session()
logger.info("Session established")

PARAMS = {
    "CLI": "CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Desktop": "CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Snowsight": "CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER",
}


def _show_param_result(sql):
    rows = session.sql(sql).collect()
    if not rows:
        return None
    row = rows[0].as_dict()
    logger.info("Row dict: %s", row)
    row_lower = {k.lower(): v for k, v in row.items()}
    return row_lower


def get_account_params():
    logger.info("Fetching account-level parameters")
    results = {}
    for label, param in PARAMS.items():
        row_lower = _show_param_result(f"SHOW PARAMETERS LIKE '{param}' IN ACCOUNT")
        if row_lower:
            value = str(row_lower.get("value", "-1"))
            level = str(row_lower.get("level", "")).upper()
            results[label] = {"value": value, "level": level, "param": param}
            logger.info("Account param %s: value=%s, level=%s", label, value, level)
        else:
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
            logger.info("Account param %s: not set (default)", label)
    return results


@st.cache_data(ttl=60)
def get_users():
    logger.info("Fetching user list")
    df = session.sql("SHOW USERS").to_pandas()
    col_map = {c.lower(): c for c in df.columns}
    name_col = col_map.get("name", df.columns[0])
    users = sorted(df[name_col].tolist())
    logger.info("Found %d users", len(users))
    return users


def get_user_params(username):
    logger.info("Fetching parameters for user: %s", username)
    results = {}
    safe_user = username.replace('"', '""')
    for label, param in PARAMS.items():
        row_lower = _show_param_result(f"SHOW PARAMETERS LIKE '{param}' IN USER \"{safe_user}\"")
        if row_lower:
            value = str(row_lower.get("value", "-1"))
            level = str(row_lower.get("level", "")).upper()
            results[label] = {"value": value, "level": level, "param": param}
            logger.info("User %s param %s: value=%s, level=%s", username, label, value, level)
        else:
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
            logger.info("User %s param %s: not set (default)", username, label)
    return results


def display_limit_value(value):
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


st.set_page_config(page_title="FrostGate", page_icon="\u2744\ufe0f", layout="wide")
st.title("\u2744\ufe0f FrostGate")
st.caption("Cortex Code Daily Credit Usage Limit Manager")

if st.button("Refresh Data", key="refresh_all"):
    logger.info("Manual cache refresh triggered")
    get_users.clear()
    st.rerun()

tab_account, tab_users = st.tabs(["Account-Level Limits", "User-Level Overrides"])

with tab_account:
    st.subheader("Account-Level Default Limits")
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
        new_values = {}
        for i, (label, info) in enumerate(account_params.items()):
            with form_cols[i]:
                action = st.selectbox(
                    f"{label}",
                    options=["No change", "Set limit", "Unset (unlimited)"],
                    key=f"account_action_{label}",
                )
                if action == "Set limit":
                    new_values[label] = st.number_input(
                        f"Credits/day for {label}",
                        min_value=0,
                        value=20,
                        step=1,
                        key=f"account_val_{label}",
                    )
                else:
                    new_values[label] = action

        submitted = st.form_submit_button("Apply Account Changes")
        if submitted:
            logger.info("Account form submitted")
            changes_made = False
            for label, val in new_values.items():
                param = PARAMS[label]
                if val == "No change":
                    continue
                elif val == "Unset (unlimited)":
                    logger.info("Unsetting account param: %s", param)
                    try:
                        session.sql(f"ALTER ACCOUNT UNSET {param}").collect()
                        logger.info("Successfully unset account param: %s", param)
                        changes_made = True
                    except Exception as e:
                        logger.error("Failed to unset account param %s: %s", param, e)
                        st.error(f"Failed to unset {label}: {e}")
                else:
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

with tab_users:
    st.subheader("Per-User Credit Limit Overrides")
    st.markdown("User-level settings **override** account-level defaults for that user.")

    users = get_users()

    selected_user = st.selectbox("Select user", options=users, key="user_select")

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
            new_user_values = {}
            for i, (label, info) in enumerate(user_params.items()):
                with form_cols[i]:
                    action = st.selectbox(
                        f"{label}",
                        options=["No change", "Set limit", "Unset (inherit account)"],
                        key=f"user_action_{label}",
                    )
                    if action == "Set limit":
                        new_user_values[label] = st.number_input(
                            f"Credits/day for {label}",
                            min_value=0,
                            value=10,
                            step=1,
                            key=f"user_val_{label}",
                        )
                    else:
                        new_user_values[label] = action

            user_submitted = st.form_submit_button("Apply User Changes")
            if user_submitted:
                logger.info("User form submitted for user: %s", selected_user)
                changes_made = False
                safe_user = selected_user.replace('"', '""')
                for label, val in new_user_values.items():
                    param = PARAMS[label]
                    if val == "No change":
                        continue
                    elif val == "Unset (inherit account)":
                        logger.info("Unsetting user %s param: %s", selected_user, param)
                        try:
                            session.sql(f'ALTER USER "{safe_user}" UNSET {param}').collect()
                            logger.info("Successfully unset user %s param: %s", selected_user, param)
                            changes_made = True
                        except Exception as e:
                            logger.error("Failed to unset user %s param %s: %s", selected_user, param, e)
                            st.error(f"Failed to unset {label} for {selected_user}: {e}")
                    else:
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
    with st.expander("Bulk View: All Users with Overrides"):
        st.caption("Scanning users for per-user overrides (may take a moment)...")
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
