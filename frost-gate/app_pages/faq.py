"""FAQs & Troubleshooting page.

Common questions and solutions for FrostGate administrators.
"""

import streamlit as st


st.title(":material/help: FAQs & Troubleshooting")
st.markdown("Common questions and solutions for managing Cortex Code AI credit limits and interface access.")

st.divider()

# --- FAQs ---
st.subheader("Frequently Asked Questions")

with st.expander("What are AI credits and how do they differ from compute credits?"):
    st.markdown("""
AI credits are a separate unit of consumption for Cortex Code interactions. They are **not** the same
as warehouse compute credits. Each time a user interacts with Cortex Code (in Snowsight, CLI, or Desktop),
AI credits are consumed. FrostGate helps you monitor and cap this usage.
""")

with st.expander("What happens when a user hits their daily credit limit?"):
    st.markdown("""
Snowflake will block further Cortex Code requests for that user until the daily counter resets
(every 24 hours). The user will see an error message indicating they've reached their limit.
Other Snowflake functionality (queries, warehouses, etc.) is **not** affected.
""")

with st.expander("What does a limit value of -1 mean?"):
    st.markdown("""
A value of **-1** means **unlimited** — no cap is enforced. This is the default for all parameters.
A value of **0** means **blocked** — the user cannot use that surface at all.
Any positive integer sets the maximum estimated AI credits per day.
""")

with st.expander("What's the difference between account-level and user-level limits?"):
    st.markdown("""
- **Account-level limits** are the default for all users in the account.
- **User-level limits** override the account default for a specific user.

If no user-level override is set, the user inherits the account-level limit.
Use user-level overrides to grant power users higher limits or to restrict specific users below the account default.
""")

with st.expander("What does ALLOWED_INTERFACES do?"):
    st.markdown("""
The `ALLOWED_INTERFACES` user property controls which Snowflake interfaces a user can access:

| Value | Access |
|-------|--------|
| `ALL` (default) | Snowsight and all other interfaces |
| `SNOWFLAKE_INTELLIGENCE` | Snowflake CoWork only |
| `STREAMLIT` | Streamlit apps via app-viewer URLs only |
| `SNOWFLAKE_INTELLIGENCE` + `STREAMLIT` | CoWork and Streamlit apps (no Snowsight) |

**Note:** This is a best-effort restriction and should not be relied upon as the sole security boundary.
""")

with st.expander("Why would I restrict a user to SNOWFLAKE_INTELLIGENCE + STREAMLIT?"):
    st.markdown("""
This is the most common configuration for business users who:
- Need access to Snowflake CoWork for AI-assisted data exploration
- Need access to Streamlit apps built by your team
- Should **not** have direct access to Snowsight (SQL worksheets, object browser, etc.)

This keeps them in a guided experience without exposing the full Snowsight interface.
""")

with st.expander("Can I change my own interface access?"):
    st.markdown("""
No. FrostGate prevents you from modifying your own `ALLOWED_INTERFACES` setting to avoid
accidentally locking yourself out. Another administrator must make changes to your account.
""")

with st.expander("Where do FrostGate logs go?"):
    st.markdown("""
FrostGate logs to the account's configured **event table** using Python's standard `logging` module.
All log messages are prefixed with `frostgate:` and include the acting user in brackets (e.g., `[TOM] Setting...`).

To view logs:
1. Go to the **Logs** page in FrostGate
2. Or query the event table directly (see **SQL Reference** for examples)

If no event table is configured, set one with:
```sql
ALTER ACCOUNT SET EVENT_TABLE = 'DB.SCHEMA.TABLE';
```
""")

st.divider()

# --- Troubleshooting ---
st.subheader("Troubleshooting")

with st.expander("I get 'Insufficient privileges' when opening FrostGate"):
    st.markdown("""
FrostGate requires the **ACCOUNTADMIN** role (or a custom role with `IMPORTED PRIVILEGES` on the
`SNOWFLAKE` database). Make sure your active role has access to:
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`

Switch to ACCOUNTADMIN and reload the page.
""")

with st.expander("Changes I make don't seem to take effect"):
    st.markdown("""
- **Credit limits** take effect immediately but are evaluated on the *next* Cortex Code request.
  If a user is mid-session, they may not see the limit until their next interaction.
- **Interface access** changes take effect on the user's next login or session refresh.
- **Account-level changes** only affect users who don't have a per-user override set.
  Check the **User Limits** page to see if the user has an override.
""")

with st.expander("The Usage Dashboard shows no data"):
    st.markdown("""
Possible causes:
1. **No Cortex Code usage yet** — if no one has used Cortex Code, there's nothing to display.
2. **Latency** — `ACCOUNT_USAGE` views have up to a 45-minute delay. Recent usage may not appear immediately.
3. **Time period** — try selecting a longer time range (e.g., "Last 30 days").
4. **Permissions** — ensure your role has access to the usage history views.
""")

with st.expander("The Logs page shows 'No event table configured'"):
    st.markdown("""
Your account doesn't have an event table set. Configure one with:
```sql
ALTER ACCOUNT SET EVENT_TABLE = 'MY_DB.MY_SCHEMA.MY_EVENT_TABLE';
```

If you need to create an event table first:
```sql
CREATE DATABASE IF NOT EXISTS MY_DB;
CREATE SCHEMA IF NOT EXISTS MY_DB.MY_SCHEMA;
CREATE EVENT TABLE IF NOT EXISTS MY_DB.MY_SCHEMA.MY_EVENT_TABLE;
ALTER ACCOUNT SET EVENT_TABLE = 'MY_DB.MY_SCHEMA.MY_EVENT_TABLE';
```
""")

with st.expander("The Logs page shows entries but the Audit Log tab is empty"):
    st.markdown("""
The Audit Log tab only shows entries that match parameter or interface change patterns
(e.g., `[USER] Setting...`, `[USER] Set interfaces...`). If no changes have been made
through FrostGate in the selected time range, the tab will be empty.

Try expanding the time range to "Last 7 days" to capture older audit entries.
""")

with st.expander("Bulk update is slow or timing out"):
    st.markdown("""
Bulk operations execute `ALTER USER` statements sequentially for each selected user.
While each individual ALTER is fast (it's a metadata operation, no warehouse needed),
updating many users (100+) can add up due to network round-trips.

Tips:
- Use role or tag filters to narrow the selection
- Apply changes in smaller batches if updating a large number of users
""")

with st.expander("I accidentally set the wrong limit — how do I undo it?"):
    st.markdown("""
- **To reset to unlimited:** Set the limit to `-1` (or select "Reset to unlimited" in the UI)
- **To remove a per-user override:** Use "Reset to unlimited" on the User Limits page — this
  unsets the user-level parameter so they inherit the account default again
- **To restore interface access:** Select "ALL — All interfaces (default)" which unsets the
  `ALLOWED_INTERFACES` property entirely
""")
