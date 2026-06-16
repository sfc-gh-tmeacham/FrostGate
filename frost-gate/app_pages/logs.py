"""Logs page.

Displays application logs from the account's configured event table.
Segregates parameter/interface change audit entries from general app logs.
"""

import logging
import pandas as pd
import streamlit as st

logger = logging.getLogger("frostgate")
session = st.session_state["session"]


def get_event_table() -> str | None:
    """Auto-detect the account's event table from the EVENT_TABLE parameter."""
    try:
        job = session.sql("SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT").collect_nowait()
        rows = job.result()
        for row in rows:
            row_dict = row.as_dict()
            val = row_dict.get("value") or row_dict.get("VALUE", "")
            if val:
                return val
    except Exception as e:
        logger.error("Failed to detect event table: %s", e)
    return None


def build_query(event_table: str, interval: str, severity_clause: str, audit_only: bool) -> str:
    """Build the event table query with optional audit filter."""
    # Audit logs match patterns like "[USER] Setting...", "[USER] Set interfaces..."
    if audit_only:
        audit_clause = "AND REGEXP_LIKE(TRY_PARSE_JSON(VALUE):message::VARCHAR, '.*frostgate:.*\\\\[.+\\\\] (Set|Unsetting|Setting|Bulk set|Reset).*')"
    else:
        audit_clause = ""

    return f"""
        SELECT
            TIMESTAMP,
            UPPER(TRY_PARSE_JSON(VALUE):level::VARCHAR) AS SEVERITY,
            RESOURCE_ATTRIBUTES['snow.executable.name']::VARCHAR AS SOURCE,
            TRY_PARSE_JSON(VALUE):message::VARCHAR AS MESSAGE
        FROM {event_table}
        WHERE TIMESTAMP >= TIMESTAMPADD({interval}, CURRENT_TIMESTAMP())
          AND RECORD_TYPE = 'LOG'
          AND RESOURCE_ATTRIBUTES['snow.executable.type']::VARCHAR = 'STREAMLIT'
          AND TRY_PARSE_JSON(VALUE):message::VARCHAR LIKE '%frostgate:%'
          {severity_clause}
          {audit_clause}
        ORDER BY TIMESTAMP DESC
        LIMIT 500
    """


def render_log_table(df: pd.DataFrame):
    """Render a styled log dataframe."""
    if "TIMESTAMP" in df.columns:
        df["TIMESTAMP"] = pd.to_datetime(df["TIMESTAMP"], errors="coerce")
        df = df.sort_values("TIMESTAMP", ascending=False).reset_index(drop=True)
        df["TIMESTAMP"] = df["TIMESTAMP"].dt.strftime("%Y-%m-%d %H:%M:%S")

    st.caption(f"Showing {len(df)} log entries (max 500)")

    def highlight_severity(val):
        colors = {
            "ERROR": "color: #ff4b4b;",
            "FATAL": "color: #ff4b4b; font-weight: bold;",
            "WARN": "color: #ffa726;",
            "WARNING": "color: #ffa726;",
            "INFO": "",
            "DEBUG": "color: #90a4ae;",
        }
        return colors.get(val, "")

    styled_df = df.style.map(highlight_severity, subset=["SEVERITY"])
    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# --- Page layout ---

st.title(":material/terminal: Logs")
st.markdown("View application logs from the account's event table.")

event_table = get_event_table()

if not event_table:
    st.error(
        "No event table configured for this account. "
        "Set one with: `ALTER ACCOUNT SET EVENT_TABLE = 'DB.SCHEMA.TABLE';`",
        icon=":material/error:",
    )
    st.stop()

st.caption(f"Event table: `{event_table}`")

st.divider()

# --- Filters ---
filter_cols = st.columns([2, 2, 1])

with filter_cols[0]:
    time_range = st.selectbox(
        "Time range",
        options=["Last 1 hour", "Last 6 hours", "Last 24 hours", "Last 7 days"],
        index=2,
        key="logs_time_range",
    )

with filter_cols[1]:
    severity = st.multiselect(
        "Severity",
        options=["INFO", "WARN", "ERROR", "FATAL", "DEBUG"],
        default=["INFO", "WARN", "ERROR", "FATAL"],
        key="logs_severity",
    )

with filter_cols[2]:
    st.write("")
    st.write("")
    if st.button("Refresh", key="logs_refresh", type="tertiary", icon=":material/refresh:"):
        st.rerun()

# Map time range to interval
time_map = {
    "Last 1 hour": "HOUR, -1",
    "Last 6 hours": "HOUR, -6",
    "Last 24 hours": "HOUR, -24",
    "Last 7 days": "DAY, -7",
}
interval = time_map[time_range]

# Build severity filter
if severity:
    severity_list = ", ".join(f"'{s}'" for s in severity)
    severity_clause = f"AND UPPER(TRY_PARSE_JSON(VALUE):level::VARCHAR) IN ({severity_list})"
else:
    severity_clause = ""

# --- Tabs: Audit Log vs All Logs ---
# Fire both queries in parallel using collect_nowait()
audit_query = build_query(event_table, interval, severity_clause, audit_only=True)
all_query = build_query(event_table, interval, severity_clause, audit_only=False)

audit_job = session.sql(audit_query).collect_nowait()
all_job = session.sql(all_query).collect_nowait()

tab_audit, tab_all = st.tabs([":material/history: Audit Log", ":material/list: All Logs"])

with tab_audit:
    st.caption("Parameter and interface access changes made through FrostGate.")
    try:
        rows = audit_job.result()

        if not rows:
            st.info("No audit entries found for the selected filters.", icon=":material/info:")
        else:
            df = pd.DataFrame([r.as_dict() for r in rows])
            df.columns = [c.upper() for c in df.columns]
            render_log_table(df)
    except Exception as e:
        logger.error("Failed to query audit logs: %s", e)
        st.error(f"Failed to query audit logs: {e}", icon=":material/error:")

with tab_all:
    st.caption("All FrostGate application logs.")
    try:
        rows = all_job.result()

        if not rows:
            st.info("No log entries found for the selected filters.", icon=":material/info:")
        else:
            df = pd.DataFrame([r.as_dict() for r in rows])
            df.columns = [c.upper() for c in df.columns]
            render_log_table(df)
    except Exception as e:
        logger.error("Failed to query event table: %s", e)
        st.error(f"Failed to query event table: {e}", icon=":material/error:")
