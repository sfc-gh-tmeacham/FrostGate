"""Usage Dashboard page.

Displays daily credit usage statistics for Cortex Code across Snowsight,
CLI, and Desktop surfaces. Queries are executed asynchronously via Snowpark
collect_nowait() and cached for 30 minutes.
"""

import logging
import traceback
import streamlit as st
import pandas as pd

from app_pages.common import USAGE_VIEWS, TIME_PERIODS

logger = logging.getLogger("frostgate")
session = st.session_state["session"]


def _build_stats_sql(view_name, days):
    """Build SQL for daily usage statistics grouped by date.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days to look back.

    Returns:
        SQL string that produces daily aggregated stats.
    """
    return f"""
    WITH daily_user AS (
        SELECT
            USER_NAME,
            DATE(USAGE_TIME) AS USAGE_DATE,
            SUM(TOKEN_CREDITS) AS DAILY_CREDITS,
            COUNT(*) AS DAILY_CALLS
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME, DATE(USAGE_TIME)
    )
    SELECT
        USAGE_DATE,
        AVG(DAILY_CREDITS) AS AVG_CREDITS,
        MEDIAN(DAILY_CREDITS) AS MEDIAN_CREDITS,
        MIN(DAILY_CREDITS) AS MIN_CREDITS,
        MAX(DAILY_CREDITS) AS MAX_CREDITS,
        COUNT(DISTINCT USER_NAME) AS ACTIVE_USERS,
        SUM(DAILY_CREDITS) AS TOTAL_CREDITS,
        SUM(DAILY_CALLS) AS TOTAL_CALLS
    FROM daily_user
    GROUP BY USAGE_DATE
    ORDER BY USAGE_DATE
    """


def _build_summary_sql(view_name, days):
    """Build SQL for overall usage summary across the time window.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days to look back.

    Returns:
        SQL string that produces a single-row summary.
    """
    return f"""
    WITH daily_user AS (
        SELECT
            USER_NAME,
            DATE(USAGE_TIME) AS USAGE_DATE,
            SUM(TOKEN_CREDITS) AS DAILY_CREDITS,
            COUNT(*) AS DAILY_CALLS
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME, DATE(USAGE_TIME)
    )
    SELECT
        ROUND(AVG(DAILY_CREDITS), 1) AS AVG_CREDITS_PER_USER_DAY,
        ROUND(MEDIAN(DAILY_CREDITS), 1) AS MEDIAN_CREDITS_PER_USER_DAY,
        ROUND(MIN(DAILY_CREDITS), 1) AS MIN_CREDITS_PER_USER_DAY,
        ROUND(MAX(DAILY_CREDITS), 1) AS MAX_CREDITS_PER_USER_DAY,
        COUNT(DISTINCT USER_NAME) AS DISTINCT_USERS,
        ROUND(SUM(DAILY_CREDITS), 1) AS TOTAL_CREDITS,
        SUM(DAILY_CALLS) AS TOTAL_REQUESTS
    FROM daily_user
    """


@st.cache_data(ttl=1800)
def fetch_all_dashboard_data(_session, days):
    """Submit all dashboard queries asynchronously and collect results.

    Fires summary and stats queries for each usage surface in parallel
    using Snowpark's collect_nowait(), then waits for all results.

    Args:
        _session: Snowpark session (underscore prefix for st.cache_data).
        days: Number of days to look back.

    Returns:
        Dict mapping "{surface}_summary" and "{surface}_stats" keys to
        DataFrames (on success) or Exception instances (on failure).
    """
    logger.info("Launching async queries for all surfaces, days=%d", days)

    # Fire all queries in parallel using collect_nowait() — two per surface
    # (summary for headline metrics, stats for daily time-series chart)
    async_jobs = {}
    for surface, view in USAGE_VIEWS.items():
        summary_sql = _build_summary_sql(view, days)
        stats_sql = _build_stats_sql(view, days)

        logger.info("Submitting async summary for %s", surface)
        async_jobs[f"{surface}_summary"] = _session.sql(summary_sql).collect_nowait()

        logger.info("Submitting async stats for %s", surface)
        async_jobs[f"{surface}_stats"] = _session.sql(stats_sql).collect_nowait()

    # Wait for all async results; store exceptions rather than raising so the
    # UI can show partial results if only one surface fails
    results = {}
    for key, job in async_jobs.items():
        logger.info("Waiting for async result: %s (query_id=%s)", key, job.query_id)
        try:
            rows = job.result()
            if rows:
                df = pd.DataFrame([row.as_dict() for row in rows])
            else:
                df = pd.DataFrame()
            logger.info("Result for %s: %d rows, columns=%s", key, len(df), list(df.columns))
            results[key] = df
        except Exception as e:
            logger.error("Async query failed for %s: %s\n%s", key, e, traceback.format_exc())
            results[key] = e

    return results


# --- Page layout ---

st.title(":material/bar_chart: Usage Dashboard")
st.caption("Daily AI credit usage statistics across Cortex Code surfaces")
st.info(
    "This dashboard shows estimated AI credit consumption from Cortex Code across Snowsight, CLI, and Desktop. "
    "Data comes from ACCOUNT_USAGE views which may have up to 45 minutes of latency. "
    "Use the time period selector to adjust the lookback window.",
    icon=":material/info:",
)

col_period, col_refresh = st.columns([3, 1])
with col_period:
    period = st.selectbox(
        "Time period",
        options=list(TIME_PERIODS.keys()),
        index=2,
        key="dashboard_period",
        help="Select the lookback window for usage statistics.",
    )
with col_refresh:
    st.write("")
    st.write("")
    if st.button("Refresh", key="refresh_dashboard", type="tertiary", icon=":material/refresh:"):
        fetch_all_dashboard_data.clear()
        st.rerun()

days = TIME_PERIODS[period]
logger.info("Dashboard rendering with period=%s, days=%d", period, days)

# Fetch all data in parallel (cached for 30 min via @st.cache_data)
with st.spinner("Loading usage data..."):
    results = fetch_all_dashboard_data(session, days)

# Render one section per surface (Snowsight, CLI, Desktop)
for surface in USAGE_VIEWS:
    st.subheader(f"{surface} Usage")

    # Extract the single-row summary for headline metrics
    summary_result = results.get(f"{surface}_summary")
    if isinstance(summary_result, Exception):
        st.error(f"Failed to query {surface} summary: {summary_result}")
        continue

    summary_df = summary_result
    if summary_df is None or summary_df.empty:
        st.info(f"No {surface} usage data found for the selected period.")
        continue

    row = summary_df.iloc[0]
    col_map = {c.lower(): c for c in summary_df.columns}

    total_col_name = col_map.get("total_credits", "TOTAL_CREDITS")
    total_val = row[total_col_name]

    if total_val is None:
        st.info(f"No {surface} usage data found for the selected period.")
        continue

    try:
        total_float = float(total_val)
    except (ValueError, TypeError) as e:
        logger.error("Cannot convert total_val for %s: %s (value=%r)", surface, e, total_val)
        st.error(f"Unexpected value for total credits: {total_val!r}")
        continue

    if total_float == 0:
        st.info(f"No {surface} usage data found for the selected period.")
        continue

    try:
        avg_val = float(row[col_map.get("avg_credits_per_user_day", "AVG_CREDITS_PER_USER_DAY")])
        median_val = float(row[col_map.get("median_credits_per_user_day", "MEDIAN_CREDITS_PER_USER_DAY")])
        min_val = float(row[col_map.get("min_credits_per_user_day", "MIN_CREDITS_PER_USER_DAY")])
        max_val = float(row[col_map.get("max_credits_per_user_day", "MAX_CREDITS_PER_USER_DAY")])
        distinct_users = int(row[col_map.get("distinct_users", "DISTINCT_USERS")])
        total_credits = total_float
        total_requests = int(row[col_map.get("total_requests", "TOTAL_REQUESTS")])
    except Exception as e:
        logger.error("Failed to extract metrics for %s: %s\n%s", surface, e, traceback.format_exc())
        st.error(f"Failed to parse metrics for {surface}: {e}")
        continue

    metric_cols = st.columns(7)

    # Build sparkline arrays from daily stats to show trends inside metric cards
    stats_result = results.get(f"{surface}_stats")
    spark_data = {}
    if not isinstance(stats_result, Exception) and stats_result is not None and not stats_result.empty:
        stats_df = stats_result
        col_lower = {c.lower(): c for c in stats_df.columns}
        date_col = col_lower.get("usage_date", "USAGE_DATE")
        sorted_stats = stats_df.sort_values(date_col)
        spark_data["avg"] = pd.to_numeric(sorted_stats[col_lower.get("avg_credits", "AVG_CREDITS")], errors="coerce").fillna(0).tolist()
        spark_data["median"] = pd.to_numeric(sorted_stats[col_lower.get("median_credits", "MEDIAN_CREDITS")], errors="coerce").fillna(0).tolist()
        spark_data["min"] = pd.to_numeric(sorted_stats[col_lower.get("min_credits", "MIN_CREDITS")], errors="coerce").fillna(0).tolist()
        spark_data["max"] = pd.to_numeric(sorted_stats[col_lower.get("max_credits", "MAX_CREDITS")], errors="coerce").fillna(0).tolist()
        spark_data["users"] = pd.to_numeric(sorted_stats[col_lower.get("active_users", "ACTIVE_USERS")], errors="coerce").fillna(0).tolist()
        spark_data["total_credits"] = pd.to_numeric(sorted_stats[col_lower.get("total_credits", "TOTAL_CREDITS")], errors="coerce").fillna(0).tolist()
        calls_col = col_lower.get("total_calls", None)
        if calls_col and calls_col in stats_df.columns:
            spark_data["total_calls"] = pd.to_numeric(sorted_stats[calls_col], errors="coerce").fillna(0).tolist()

    with metric_cols[0]:
        st.metric("Avg/User/Day", f"{avg_val:.1f}", chart_data=spark_data.get("avg"), chart_type="area", border=True, help="Average daily AI credits per active user.")
    with metric_cols[1]:
        st.metric("Median/User/Day", f"{median_val:.1f}", chart_data=spark_data.get("median"), chart_type="area", border=True, help="Median daily AI credits per active user.")
    with metric_cols[2]:
        st.metric("Min/User/Day", f"{min_val:.1f}", chart_data=spark_data.get("min"), chart_type="area", border=True, help="Lowest single-day AI credit usage by any user.")
    with metric_cols[3]:
        st.metric("Max/User/Day", f"{max_val:.1f}", chart_data=spark_data.get("max"), chart_type="area", border=True, help="Highest single-day AI credit usage by any user.")
    with metric_cols[4]:
        st.metric("Active Users", f"{distinct_users}", chart_data=spark_data.get("users"), chart_type="area", border=True, help="Number of distinct users with usage in the period.")
    with metric_cols[5]:
        st.metric("Total AI Credits", f"{total_credits:.1f}", chart_data=spark_data.get("total_credits"), chart_type="area", border=True, help="Sum of all estimated AI credits consumed in the period.")
    with metric_cols[6]:
        st.metric("Total Requests", f"{total_requests:,}", chart_data=spark_data.get("total_calls"), chart_type="area", border=True, help="Total number of Cortex Code requests in the period.")

    # Get daily stats for the time-series line chart
    stats_result = results.get(f"{surface}_stats")
    if isinstance(stats_result, Exception):
        st.error(f"Failed to load daily chart for {surface}: {stats_result}")
        continue

    stats_df = stats_result
    if stats_df is not None and not stats_df.empty:
        try:
            # Map column names case-insensitively (Snowflake returns uppercase)
            col_lower = {c.lower(): c for c in stats_df.columns}
            date_col = col_lower.get("usage_date", "USAGE_DATE")
            avg_col = col_lower.get("avg_credits", "AVG_CREDITS")
            median_col = col_lower.get("median_credits", "MEDIAN_CREDITS")
            min_col = col_lower.get("min_credits", "MIN_CREDITS")
            max_col = col_lower.get("max_credits", "MAX_CREDITS")
            total_col = col_lower.get("total_credits", "TOTAL_CREDITS")
            users_col = col_lower.get("active_users", "ACTIVE_USERS")
            calls_col = col_lower.get("total_calls", None)

            # Build chart DataFrame with friendly column names
            chart_df = stats_df[[date_col, avg_col, median_col, min_col, max_col]].copy()
            chart_df = chart_df.rename(columns={
                date_col: "Date",
                avg_col: "Average",
                median_col: "Median",
                min_col: "Min",
                max_col: "Max",
            })

            for col in ["Average", "Median", "Min", "Max"]:
                chart_df[col] = pd.to_numeric(chart_df[col], errors="coerce")

            chart_df["Date"] = pd.to_datetime(chart_df["Date"])

            # Fill gaps in the timeline so there are no missing days
            full_range = pd.date_range(
                start=chart_df["Date"].min(),
                end=chart_df["Date"].max(),
                freq="D",
            )
            chart_df = chart_df.set_index("Date").reindex(full_range).fillna(0)
            chart_df.index.name = "Date"

            st.line_chart(chart_df)

            with st.expander(f"Daily details — {surface}"):
                if calls_col and calls_col in stats_df.columns:
                    detail_df = stats_df[[date_col, total_col, calls_col, users_col, avg_col, max_col]].copy()
                    detail_df = detail_df.rename(columns={
                        date_col: "Date",
                        total_col: "Total AI Credits",
                        calls_col: "Total Requests",
                        users_col: "Active Users",
                        avg_col: "Avg AI Credits/User",
                        max_col: "Max AI Credits/User",
                    })
                else:
                    detail_df = stats_df[[date_col, total_col, users_col, avg_col, max_col]].copy()
                    detail_df = detail_df.rename(columns={
                        date_col: "Date",
                        total_col: "Total AI Credits",
                        users_col: "Active Users",
                        avg_col: "Avg AI Credits/User",
                        max_col: "Max AI Credits/User",
                    })
                for col in ["Total AI Credits", "Avg AI Credits/User", "Max AI Credits/User"]:
                    detail_df[col] = pd.to_numeric(detail_df[col], errors="coerce").round(2)
                detail_df = detail_df.sort_values("Date", ascending=False)
                st.dataframe(detail_df, use_container_width=True, hide_index=True)

        except Exception as e:
            logger.error("Failed to render chart for %s: %s\n%s", surface, e, traceback.format_exc())
            st.error(f"Failed to render chart for {surface}: {e}")
            st.write("Raw data:")
            st.dataframe(stats_df, use_container_width=True)
    else:
        st.info(f"No daily data available for {surface}.")

    st.divider()

logger.info("Dashboard rendering complete")
