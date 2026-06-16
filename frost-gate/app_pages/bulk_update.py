"""Bulk Update page.

Apply the same credit limit changes to multiple users at once,
and view all users who currently have per-user overrides.
"""

import logging
import streamlit as st

from app_pages.common import PARAMS, display_limit_value, fetch_params_async, apply_limit_action, get_users_df

logger = logging.getLogger("frostgate")
session = st.session_state["session"]


def get_user_params(user):
    """Fetch current per-user Cortex Code credit limit parameters."""
    safe_user = user.replace('"', '""')
    return fetch_params_async(session, f'FOR USER "{safe_user}"')


# --- Page layout ---

st.title(":material/group: Bulk User Update")
st.info(
    "Use this page to apply the same limit changes to multiple users at once. "
    "Select users below, choose an action for each surface, and submit to update them all in one operation.",
    icon=":material/group:",
)

users_df = get_users_df(session)

# --- Filters: narrow down the user list by role grants or tag assignments ---
# Fire both filter-option queries asynchronously
import pandas as pd

roles_job = session.sql("SHOW ROLES").collect_nowait()
tags_job = session.sql("""
    SELECT DISTINCT TAG_NAME, TAG_DATABASE, TAG_SCHEMA
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
    WHERE DOMAIN = 'USER' AND OBJECT_DELETED IS NULL
""").collect_nowait()

roles_rows = roles_job.result()
roles_df = pd.DataFrame([r.as_dict() for r in roles_rows])
roles_col_map = {c.upper(): c for c in roles_df.columns}
roles_col = roles_col_map.get("NAME", roles_df.columns[1] if len(roles_df.columns) > 1 else roles_df.columns[0])
roles_list = sorted(roles_df[roles_col].dropna().tolist())

tags_rows = tags_job.result()
tags_df = pd.DataFrame([r.as_dict() for r in tags_rows]) if tags_rows else pd.DataFrame()
tags_df.columns = [c.upper() for c in tags_df.columns] if not tags_df.empty else tags_df.columns

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

# Apply role and tag filters to narrow the displayed user list
# Fire both filter queries asynchronously if active
display_df = users_df

role_filter_job = None
tag_filter_job = None

if role_filter:
    placeholders = ", ".join(f"'{r}'" for r in role_filter)
    role_filter_job = session.sql(f"""
        SELECT DISTINCT GRANTEE_NAME AS USER_NAME
        FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
        WHERE ROLE IN ({placeholders})
          AND DELETED_ON IS NULL
    """).collect_nowait()

if tag_filter:
    tag_conditions = []
    for tag_fqn in tag_filter:
        parts = tag_fqn.split(".")
        if len(parts) == 3:
            tag_conditions.append(f"(TAG_DATABASE = '{parts[0]}' AND TAG_SCHEMA = '{parts[1]}' AND TAG_NAME = '{parts[2]}')")
    if tag_conditions:
        where_clause = " OR ".join(tag_conditions)
        tag_filter_job = session.sql(f"""
            SELECT DISTINCT OBJECT_NAME AS USER_NAME
            FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
            WHERE DOMAIN = 'USER'
              AND OBJECT_DELETED IS NULL
              AND ({where_clause})
        """).collect_nowait()

if role_filter_job:
    role_users_rows = role_filter_job.result()
    role_users_df = pd.DataFrame([r.as_dict() for r in role_users_rows])
    role_users_df.columns = [c.upper() for c in role_users_df.columns]
    filtered_names = set(role_users_df["USER_NAME"].tolist())
    display_df = display_df[display_df["User"].isin(filtered_names)]

if tag_filter_job:
    tag_users_rows = tag_filter_job.result()
    tag_users_df = pd.DataFrame([r.as_dict() for r in tag_users_rows])
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

        bulk_submitted = st.form_submit_button("Apply to All Selected Users", type="primary", icon=":material/check_circle:")
        if bulk_submitted:
            app_user = st.session_state.get("current_user", "UNKNOWN")
            logger.info("[%s] Bulk update submitted for %d users", app_user, len(bulk_users))
            # Fire all ALTER statements asynchronously across users and surfaces
            jobs = {}  # (user, label) -> async job
            for user in bulk_users:
                safe_user = user.replace('"', '""')
                alter_target = f'USER "{safe_user}"'
                for label in PARAMS:
                    if bulk_actions[label] == "No change":
                        continue
                    action = bulk_actions[label]
                    param = PARAMS[label]
                    value = bulk_inputs[label]
                    unset_actions = {"Unset (unlimited)", "Unset (inherit account)"}
                    if action in unset_actions:
                        jobs[(user, label)] = session.sql(f"ALTER {alter_target} UNSET {param}").collect_nowait()
                    elif action == "Set unlimited":
                        jobs[(user, label)] = session.sql(f"ALTER {alter_target} SET {param} = -1").collect_nowait()
                    elif action == "Block usage":
                        jobs[(user, label)] = session.sql(f"ALTER {alter_target} SET {param} = 0").collect_nowait()
                    else:
                        jobs[(user, label)] = session.sql(f"ALTER {alter_target} SET {param} = {int(value)}").collect_nowait()

            # Collect results
            changes_made = {}
            for (user, label), job in jobs.items():
                try:
                    job.result()
                    action = bulk_actions[label]
                    value = bulk_inputs[label]
                    if action in {"Unset (unlimited)", "Unset (inherit account)"}:
                        msg = f"{label} → unset (unlimited)"
                    elif action == "Set unlimited":
                        msg = f"{label} → unlimited (-1)"
                    elif action == "Block usage":
                        msg = f"{label} → blocked (0)"
                    else:
                        msg = f"{label} → {int(value)} AI credits/day"
                    changes_made.setdefault(user, []).append(msg)
                    logger.info("[%s] Setting %s for %s: %s", app_user, label, user, action)
                except Exception as e:
                    st.error(f"Failed to update {label} for {user}: {e}")

            if changes_made:
                summary = [f"**{user}**: " + ", ".join(msgs) for user, msgs in changes_made.items()]
                st.success(
                    f"Limits applied to {len(changes_made)} user(s):\n\n" + "\n\n".join(summary)
                )
            elif not any(a != "No change" for a in bulk_actions.values()):
                st.info("No changes selected.")

st.divider()

# --- Override Scanner: find all users with per-user limit overrides ---
st.subheader("All Users with Overrides")
st.caption("Scan all users to find those with per-user limit overrides.")
st.info(
    "This table shows users who have a per-user daily credit limit set (overriding the account default). "
    "Values represent the maximum estimated AI credits per day allowed for that surface. "
    "'—' means no override is set for that surface (inherits account default).",
    icon=":material/info:",
)

if st.button("Scan Users", key="scan_btn", type="secondary", icon=":material/search:"):
    logger.info("Bulk scan initiated")
    with st.spinner("Scanning all users for overrides... This may take a moment."):
        # Fire SHOW PARAMETERS for all users in parallel using collect_nowait()
        all_users = users_df["User"].tolist()
        scan_jobs = {}
        for user in all_users:
            safe_user = user.replace('"', '""')
            scan_jobs[user] = session.sql(
                f"""SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' IN USER "{safe_user}" """
            ).collect_nowait()

        # Collect results and filter for USER-level overrides
        param_to_label = {v: k for k, v in PARAMS.items()}
        user_overrides = {}
        for user, job in scan_jobs.items():
            try:
                rows = job.result()
                for row in rows:
                    rd = row.as_dict()
                    if rd.get("level", "").upper() == "USER":
                        param = rd.get("key", "")
                        value = rd.get("value", "")
                        label = param_to_label.get(param, param)
                        user_overrides.setdefault(user, {})[label] = display_limit_value(value)
            except Exception as e:
                logger.error("Failed to scan params for %s: %s", user, e)

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
