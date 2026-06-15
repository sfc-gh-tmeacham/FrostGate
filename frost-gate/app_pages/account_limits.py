"""Account-Level Limits page.

Displays and allows modification of the three Cortex Code daily credit
limit parameters at the account level. These serve as defaults for all
users unless overridden per-user.
"""

import streamlit as st

from app_pages.common import PARAMS, display_limit_value, fetch_params_async, apply_limit_action

session = st.session_state["session"]


# --- Page layout ---

st.title("Account-Level Limits")
st.markdown("These apply to **all users** unless overridden at the user level.")
st.info(
    "Account-level limits set the default daily AI credit cap for all users on each Cortex Code surface. "
    "A value of -1 (unlimited) means no cap is enforced. Setting a limit to 0 blocks usage entirely. "
    "Individual users can be given different limits on the User Limits page.",
    icon=":material/info:",
)

account_params = fetch_params_async(session, "IN ACCOUNT")

cols = st.columns(3)
for i, (label, info) in enumerate(account_params.items()):
    with cols[i]:
        st.metric(label=f"{label}", value=display_limit_value(info["value"], verbose=True), border=True, help=f"Current {label} daily AI credit limit for all users.")
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
        changes_made = []
        for label in PARAMS:
            if account_actions[label] == "No change":
                continue
            try:
                result = apply_limit_action(
                    session,
                    account_actions[label],
                    PARAMS[label],
                    label,
                    account_inputs[label],
                    "ACCOUNT",
                    app_user,
                )
                if result:
                    changes_made.append(result)
            except Exception as e:
                st.error(f"Failed to update {label}: {e}")
        if changes_made:
            st.success("Account limits updated successfully:\n\n" + "\n\n".join(changes_made))
        elif not any(a != "No change" for a in account_actions.values()):
            st.info("No changes selected.")
