"""Interface Access page.

Manage which Snowflake interfaces users are allowed to access via the
ALLOWED_INTERFACES user property. Supports single-user and bulk updates.
"""

import logging
import pandas as pd
import streamlit as st

from app_pages.common import get_user_list, get_users_df

logger = logging.getLogger("frostgate")
session = st.session_state["session"]

# Valid ALLOWED_INTERFACES combinations
INTERFACE_OPTIONS: dict[str, list[str]] = {
    "ALL — All interfaces (default)": ["ALL"],
    "SNOWFLAKE_INTELLIGENCE — Snowflake CoWork only": ["SNOWFLAKE_INTELLIGENCE"],
    "STREAMLIT — Streamlit apps only": ["STREAMLIT"],
    "SNOWFLAKE_INTELLIGENCE + STREAMLIT — CoWork and Streamlit apps": ["SNOWFLAKE_INTELLIGENCE", "STREAMLIT"],
}


def get_user_interfaces(username: str) -> list[str]:
    """Fetch the current ALLOWED_INTERFACES setting for a user.

    Uses collect_nowait() for async execution.
    Returns a list of interface strings, or ['ALL'] if not explicitly set.
    """
    safe_user = username.replace('"', '""')
    try:
        job = session.sql(f'DESCRIBE USER "{safe_user}"').collect_nowait()
        rows = job.result()
        for row in rows:
            row_dict = row.as_dict()
            prop_name = str(row_dict.get("property", "")).upper()
            if prop_name == "ALLOWED_INTERFACES":
                raw_value = str(row_dict.get("value", "")).strip()
                if raw_value and raw_value.upper() != "ALL":
                    return [v.strip().strip("'\"") for v in raw_value.strip("[]()").split(",") if v.strip()]
                return ["ALL"]
        return ["ALL"]
    except Exception as e:
        logger.error("Failed to get interfaces for %s: %s", username, e)
        return ["ALL"]


def _interfaces_to_label(interfaces: list[str]) -> str:
    """Map a list of interface values to the corresponding radio label."""
    iface_set = set(i.upper() for i in interfaces)
    for label, values in INTERFACE_OPTIONS.items():
        if set(values) == iface_set:
            return label
    return list(INTERFACE_OPTIONS.keys())[0]


# --- Page layout ---

@st.dialog("Confirm Interface Change")
def confirm_single_user(username: str, chosen_label: str, chosen_values: list[str]):
    st.markdown(f"Are you sure you want to change interface access for **{username}**?")
    st.markdown(f"New setting: **{chosen_label}**")
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Confirm", type="primary", icon=":material/check:", use_container_width=True):
            safe_user = username.replace('"', '""')
            try:
                if chosen_values == ["ALL"]:
                    job = session.sql(f'ALTER USER "{safe_user}" UNSET ALLOWED_INTERFACES').collect_nowait()
                else:
                    iface_list = ", ".join(f"'{v}'" for v in chosen_values)
                    job = session.sql(f'ALTER USER "{safe_user}" SET ALLOWED_INTERFACES = ({iface_list})').collect_nowait()
                job.result()
                app_user = st.session_state.get("current_user", "UNKNOWN")
                logger.info("[%s] Set interfaces for %s: %s", app_user, username, chosen_values)
                st.success(f"Interface access for **{username}** set to: **{chosen_label}**")
                st.rerun()
            except Exception as e:
                logger.error("Failed to set interfaces for %s: %s", username, e)
                st.error(f"Failed to set interfaces: {e}")
    with col_no:
        if st.button("Cancel", type="secondary", use_container_width=True):
            st.rerun()


@st.dialog("Confirm Bulk Interface Change")
def confirm_bulk_update(users: list[str], chosen_label: str, chosen_values: list[str]):
    st.markdown(f"Are you sure you want to change interface access for **{len(users)} user(s)**?")
    st.markdown(f"New setting: **{chosen_label}**")
    with st.expander(f"Show {len(users)} affected user(s)"):
        st.write(", ".join(users))
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Confirm", type="primary", icon=":material/check_circle:", use_container_width=True, key="bulk_confirm_yes"):
            app_user = st.session_state.get("current_user", "UNKNOWN")
            # Fire all ALTER USER statements asynchronously
            jobs = {}
            for user in users:
                safe_user = user.replace('"', '""')
                if chosen_values == ["ALL"]:
                    jobs[user] = session.sql(f'ALTER USER "{safe_user}" UNSET ALLOWED_INTERFACES').collect_nowait()
                else:
                    iface_list = ", ".join(f"'{v}'" for v in chosen_values)
                    jobs[user] = session.sql(f'ALTER USER "{safe_user}" SET ALLOWED_INTERFACES = ({iface_list})').collect_nowait()
            # Collect results
            changes = []
            for user, job in jobs.items():
                try:
                    job.result()
                    changes.append(user)
                except Exception as e:
                    st.error(f"Failed to set interfaces for {user}: {e}")
            if changes:
                logger.info("[%s] Bulk set interfaces for %d users: %s", app_user, len(changes), chosen_values)
                st.success(f"Set interface access for {len(changes)} user(s) to: **{chosen_label}**")
                st.rerun()
    with col_no:
        if st.button("Cancel", type="secondary", use_container_width=True, key="bulk_confirm_no"):
            st.rerun()

st.title(":material/devices: Interface Access")
st.markdown("Control which Snowflake interfaces each user is allowed to access.")
st.info(
    "The `ALLOWED_INTERFACES` user property controls which interfaces a user can access. "
    "Valid values are: `ALL` (Snowsight and all other interfaces), `SNOWFLAKE_INTELLIGENCE` (Snowflake CoWork), "
    "and `STREAMLIT` (Streamlit apps via app-viewer URLs). "
    "Setting this to `ALL` (the default) allows access to Snowsight and all other specifiable interfaces.\n\n"
    "**Note:** This is a best-effort restriction and should not be relied upon as the sole security boundary.",
    icon=":material/info:",
)
st.success(
    "**Tip:** The most common configuration is **SNOWFLAKE_INTELLIGENCE + STREAMLIT** — this prevents "
    "business users from accessing Snowsight directly while still giving them access to Streamlit apps "
    "and Snowflake CoWork.",
    icon=":material/lightbulb:",
)

st.divider()

# --- Current user info ---
current_app_user = st.session_state.get("current_user", "UNKNOWN")
st.caption(f"Logged in as: **{current_app_user}**")

# --- Single User Section ---
st.subheader("Single User")

users = get_user_list(session)

col_user, col_refresh = st.columns([4, 1])
with col_user:
    selected_user = st.selectbox(
        "Select user",
        options=users,
        key="iface_user_select",
        help="Choose a user to view or modify their interface access.",
    )
with col_refresh:
    st.write("")
    st.write("")
    if st.button("Refresh", key="iface_refresh_users", type="tertiary", icon=":material/refresh:"):
        get_user_list.clear()
        st.rerun()

if selected_user:
    current_interfaces = get_user_interfaces(selected_user)
    current_label = _interfaces_to_label(current_interfaces)

    st.caption(f"Current setting: **{current_label}**")

    if selected_user.upper() == current_app_user.upper():
        st.warning("You cannot modify your own interface access.", icon=":material/block:")
    else:
        st.markdown(f"**Update interfaces for `{selected_user}`:**")

        with st.form("iface_user_form"):
            chosen_label = st.radio(
                "Allowed interfaces",
                options=list(INTERFACE_OPTIONS.keys()),
                index=list(INTERFACE_OPTIONS.keys()).index(current_label),
                key="iface_user_radio",
            )

            submitted = st.form_submit_button("Apply", type="primary", icon=":material/check:")
            if submitted:
                chosen_values = INTERFACE_OPTIONS[chosen_label]

                if chosen_values == current_interfaces:
                    st.info("No changes — already set to this value.")
                else:
                    confirm_single_user(selected_user, chosen_label, chosen_values)

st.divider()

# --- Bulk User Section ---
st.subheader("Bulk Update")
st.caption("Apply the same interface access settings to multiple users at once.")

users_df = get_users_df(session)

# Submit roles and tags queries asynchronously
roles_job = session.sql("SHOW ROLES").collect_nowait()
tags_job = session.sql("""
    SELECT DISTINCT TAG_NAME, TAG_DATABASE, TAG_SCHEMA
    FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
    WHERE DOMAIN = 'USER' AND OBJECT_DELETED IS NULL
""").collect_nowait()

# Collect roles result
roles_df = pd.DataFrame([r.as_dict() for r in roles_job.result()])
roles_col_map = {c.upper(): c for c in roles_df.columns}
roles_col = roles_col_map.get("NAME", roles_df.columns[1] if len(roles_df.columns) > 1 else roles_df.columns[0])
roles_list = sorted(roles_df[roles_col].dropna().tolist())

# Collect tags result
tags_rows = tags_job.result()
tags_df = pd.DataFrame([r.as_dict() for r in tags_rows]) if tags_rows else pd.DataFrame()
tags_df.columns = [c.upper() for c in tags_df.columns] if not tags_df.empty else tags_df.columns

filter_cols = st.columns(2)
with filter_cols[0]:
    role_filter = st.multiselect(
        "Filter by role",
        options=roles_list,
        key="iface_bulk_role_filter",
        help="Only show users who have been granted one or more of these roles.",
    )
with filter_cols[1]:
    if not tags_df.empty:
        tag_options = sorted((tags_df["TAG_DATABASE"] + "." + tags_df["TAG_SCHEMA"] + "." + tags_df["TAG_NAME"]).unique().tolist())
    else:
        tag_options = []
    tag_filter = st.multiselect(
        "Filter by tag",
        options=tag_options,
        key="iface_bulk_tag_filter",
        help="Only show users who have one of these tags assigned.",
    )

# Apply filters — fire both filter queries asynchronously if both are active
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
    key="iface_bulk_user_table",
)

selected_rows = selection.selection.rows if selection.selection else []
bulk_users = display_df.iloc[selected_rows]["User"].tolist() if selected_rows else []

if bulk_users:
    if current_app_user.upper() in [u.upper() for u in bulk_users]:
        st.warning("Your own account has been excluded from the selection — you cannot modify your own interface access.", icon=":material/block:")
        bulk_users = [u for u in bulk_users if u.upper() != current_app_user.upper()]

    if bulk_users:
        st.caption(f"{len(bulk_users)} user(s) selected")
        with st.form("iface_bulk_form"):
            st.markdown(f"**Apply interface settings to {len(bulk_users)} selected user(s):**")

            bulk_chosen_label = st.radio(
                "Allowed interfaces",
                options=list(INTERFACE_OPTIONS.keys()),
                key="iface_bulk_radio",
            )

            bulk_submitted = st.form_submit_button("Apply to All Selected Users", type="primary", icon=":material/check_circle:")
            if bulk_submitted:
                chosen_values = INTERFACE_OPTIONS[bulk_chosen_label]
                confirm_bulk_update(bulk_users, bulk_chosen_label, chosen_values)
