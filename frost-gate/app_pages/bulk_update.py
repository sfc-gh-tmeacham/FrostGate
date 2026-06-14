"""Bulk Update page.

Apply the same credit limit changes to multiple users at once,
and view all users who currently have per-user overrides.
"""

import logging
import streamlit as st
import pandas as pd

logger = logging.getLogger("frostgate")
session = st.session_state["session"]

PARAMS = {
    "CLI": "CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Desktop": "CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Snowsight": "CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER",
}


def get_users(sess):
    """Fetch user details from the account as a DataFrame."""
    df = pd.DataFrame([r.as_dict() for r in sess.sql("SHOW USERS").collect()])
    col_map = {c.lower(): c for c in df.columns}
    result = pd.DataFrame()
    result["User"] = df[col_map.get("name", "name")]
    result["Display Name"] = df[col_map.get("display_name", "display_name")].fillna("—")
    result["Email"] = df[col_map.get("email", "email")].fillna("—")
    result["Default Role"] = df[col_map.get("default_role", "default_role")].fillna("—")
    result["Last Login"] = df[col_map.get("last_success_login", "last_success_login")].fillna("Never")
    result["Disabled"] = df[col_map.get("disabled", "disabled")].fillna("false")
    return result.sort_values("User").reset_index(drop=True)


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

users_df = get_users(session)

# Role filter
roles_df = session.sql("SHOW ROLES").to_pandas()
roles_col_map = {c.upper(): c for c in roles_df.columns}
roles_col = roles_col_map.get("NAME", roles_df.columns[1] if len(roles_df.columns) > 1 else roles_df.columns[0])
roles_list = sorted(roles_df[roles_col].dropna().tolist())

filter_cols = st.columns(2)
with filter_cols[0]:
    role_filter = st.multiselect(
        "Filter by role",
        options=roles_list,
        key="bulk_role_filter",
        help="Only show users who have been granted one or more of these roles. Leave empty to show all users.",
    )

# Tag filter
with filter_cols[1]:
    tags_df = session.sql("""
        SELECT DISTINCT TAG_NAME, TAG_DATABASE, TAG_SCHEMA
        FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
        WHERE DOMAIN = 'USER' AND OBJECT_DELETED IS NULL
    """).to_pandas()
    tags_df.columns = [c.upper() for c in tags_df.columns]
    if not tags_df.empty:
        tag_options = sorted((tags_df["TAG_DATABASE"] + "." + tags_df["TAG_SCHEMA"] + "." + tags_df["TAG_NAME"]).unique().tolist())
    else:
        tag_options = []
    tag_filter = st.multiselect(
        "Filter by tag",
        options=tag_options,
        key="bulk_tag_filter",
        help="Only show users who have one of these tags assigned. Leave empty to show all users.",
    )

# Apply filters
display_df = users_df

if role_filter:
    placeholders = ", ".join(f"'{r}'" for r in role_filter)
    role_users_df = session.sql(f"""
        SELECT DISTINCT GRANTEE_NAME AS USER_NAME
        FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
        WHERE ROLE IN ({placeholders})
          AND DELETED_ON IS NULL
    """).to_pandas()
    role_users_df.columns = [c.upper() for c in role_users_df.columns]
    filtered_names = set(role_users_df["USER_NAME"].tolist())
    display_df = display_df[display_df["User"].isin(filtered_names)]

if tag_filter:
    tag_conditions = []
    for tag_fqn in tag_filter:
        parts = tag_fqn.split(".")
        if len(parts) == 3:
            tag_conditions.append(f"(TAG_DATABASE = '{parts[0]}' AND TAG_SCHEMA = '{parts[1]}' AND TAG_NAME = '{parts[2]}')")
    if tag_conditions:
        where_clause = " OR ".join(tag_conditions)
        tag_users_df = session.sql(f"""
            SELECT DISTINCT OBJECT_NAME AS USER_NAME
            FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
            WHERE DOMAIN = 'USER'
              AND OBJECT_DELETED IS NULL
              AND ({where_clause})
        """).to_pandas()
        tag_users_df.columns = [c.upper() for c in tag_users_df.columns]
        tag_filtered_names = set(tag_users_df["USER_NAME"].tolist())
        display_df = display_df[display_df["User"].isin(tag_filtered_names)]

display_df = display_df.reset_index(drop=True)

if role_filter or tag_filter:
    st.caption(f"Showing {len(display_df)} of {len(users_df)} users matching selected filter(s)")

st.markdown("**Select users to update:**")
selection = st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    on_select="rerun",
    selection_mode="multi-row",
    key="bulk_user_table",
)

selected_rows = selection.selection.rows if selection.selection else []
bulk_users = display_df.iloc[selected_rows]["User"].tolist() if selected_rows else []

if bulk_users:
    st.caption(f"{len(bulk_users)} user(s) selected")
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
                    options=["No change", "Set limit", "Set unlimited", "Block usage", "Unset (inherit account)"],
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
            app_user = st.session_state.get("current_user", "UNKNOWN")
            logger.info("[%s] Bulk update submitted for %d users", app_user, len(bulk_users))
            changes_made = []
            for user in bulk_users:
                safe_user = user.replace('"', '""')
                user_changes = []
                for label in PARAMS:
                    action = bulk_actions[label]
                    param = PARAMS[label]
                    if action == "No change":
                        continue
                    elif action == "Unset (inherit account)":
                        try:
                            session.sql(f'ALTER USER "{safe_user}" UNSET {param}').collect()
                            logger.info("[%s] Unset %s for %s", app_user, param, user)
                            user_changes.append(f"{label} → unset")
                        except Exception as e:
                            logger.error("[%s] Failed: %s for %s: %s", app_user, param, user, e)
                            st.error(f"Failed to unset {label} for {user}: {e}")
                    elif action == "Set unlimited":
                        try:
                            session.sql(f'ALTER USER "{safe_user}" SET {param} = -1').collect()
                            logger.info("[%s] Set %s = -1 (unlimited) for %s", app_user, param, user)
                            user_changes.append(f"{label} → unlimited (-1)")
                        except Exception as e:
                            logger.error("[%s] Failed to set %s = -1 for %s: %s", app_user, param, user, e)
                            st.error(f"Failed to set {label} unlimited for {user}: {e}")
                    elif action == "Block usage":
                        try:
                            session.sql(f'ALTER USER "{safe_user}" SET {param} = 0').collect()
                            logger.info("[%s] Blocked %s for %s", app_user, param, user)
                            user_changes.append(f"{label} → blocked")
                        except Exception as e:
                            logger.error("[%s] Failed to block %s for %s: %s", app_user, param, user, e)
                            st.error(f"Failed to block {label} for {user}: {e}")
                    else:
                        val = bulk_inputs[label]
                        try:
                            session.sql(f'ALTER USER "{safe_user}" SET {param} = {int(val)}').collect()
                            logger.info("[%s] Set %s = %d for %s", app_user, param, int(val), user)
                            user_changes.append(f"{label} → {int(val)} AI credits/day")
                        except Exception as e:
                            logger.error("[%s] Failed: %s = %d for %s: %s", app_user, param, int(val), user, e)
                            st.error(f"Failed to set {label} for {user}: {e}")
                if user_changes:
                    changes_made.append(f"**{user}**: " + ", ".join(user_changes))
            if changes_made:
                st.success(
                    f"Limits applied to {len(bulk_users)} user(s):\n\n" + "\n\n".join(changes_made)
                )
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
    with st.spinner("Scanning all users for overrides... This may take a moment."):
        user_overrides = {}
        for user in users_df["User"].tolist():
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
