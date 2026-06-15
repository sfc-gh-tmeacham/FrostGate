"""Top Users page.

Displays the top 20 users by AI credit consumption for Snowsight, CLI, and
Desktop Cortex Code surfaces over a configurable time period.
"""

import logging
import traceback
import streamlit as st
import pandas as pd

logger = logging.getLogger("frostgate")
session = st.session_state["session"]

# ACCOUNT_USAGE views for each Cortex Code surface
USAGE_VIEWS = {
    "Snowsight": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY",
    "CLI": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY",
    "Desktop": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY",
}

# Configurable lookback windows for the time period selector
TIME_PERIODS = {
    "Last 7 days": 7,
    "Last 14 days": 14,
    "Last 30 days": 30,
    "Last 60 days": 60,
    "Last 90 days": 90,
    "Last 365 days": 365,
}


def _build_top_users_sql(view_name, days):
    """Build SQL for top 20 users by total credits consumed.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days to look back.

    Returns:
        SQL string producing top 20 users with credits and request counts.
    """
    return f"""
    WITH usage AS (
        SELECT
            USER_NAME,
            ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS,
            COUNT(*) AS TOTAL_REQUESTS,
            COUNT(DISTINCT DATE(USAGE_TIME)) AS ACTIVE_DAYS,
            ROUND(SUM(TOKEN_CREDITS) / NULLIF(COUNT(DISTINCT DATE(USAGE_TIME)), 0), 2) AS AVG_CREDITS_PER_DAY
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME
        ORDER BY TOTAL_CREDITS DESC
        LIMIT 20
    )
    SELECT
        u.USER_NAME,
        COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, u.USER_NAME) AS DISPLAY_NAME,
        u.TOTAL_CREDITS,
        u.TOTAL_REQUESTS,
        u.ACTIVE_DAYS,
        u.AVG_CREDITS_PER_DAY
    FROM usage u
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS usr
        ON u.USER_NAME = usr.NAME
        AND usr.DELETED_ON IS NULL
    ORDER BY u.TOTAL_CREDITS DESC
    """


def _build_user_trends_sql(view_name, days):
    """Build SQL for daily credit trends of the top 10 users.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days to look back.

    Returns:
        SQL string producing daily credits per user for trending.
    """
    return f"""
    WITH top_users AS (
        SELECT USER_NAME
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME
        ORDER BY SUM(TOKEN_CREDITS) DESC
        LIMIT 10
    )
    SELECT
        DATE(h.USAGE_TIME) AS USAGE_DATE,
        COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, h.USER_NAME) AS DISPLAY_NAME,
        ROUND(SUM(h.TOKEN_CREDITS), 2) AS DAILY_CREDITS
    FROM {view_name} h
    INNER JOIN top_users t ON h.USER_NAME = t.USER_NAME
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS usr
        ON h.USER_NAME = usr.NAME
        AND usr.DELETED_ON IS NULL
    WHERE h.USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
    GROUP BY DATE(h.USAGE_TIME), COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, h.USER_NAME)
    ORDER BY USAGE_DATE
    """


def _build_pareto_sql(view_name, days):
    """Build SQL to identify power users via Pareto principle (80/20 rule).

    Ranks users by total credits descending and computes cumulative percentage.
    Returns all users with their rank, credits, percentage, and cumulative percentage.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days to look back.

    Returns:
        SQL string producing ranked users with cumulative credit percentages.
    """
    return f"""
    WITH user_totals AS (
        SELECT
            USER_NAME,
            ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('day', -{days}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME
        HAVING TOTAL_CREDITS > 0
    ),
    ranked AS (
        SELECT
            USER_NAME,
            TOTAL_CREDITS,
            ROUND(TOTAL_CREDITS / NULLIF(SUM(TOTAL_CREDITS) OVER (), 0) * 100, 1) AS PCT_OF_TOTAL,
            ROUND(SUM(TOTAL_CREDITS) OVER (ORDER BY TOTAL_CREDITS DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                  / NULLIF(SUM(TOTAL_CREDITS) OVER (), 0) * 100, 1) AS CUMULATIVE_PCT,
            COUNT(*) OVER () AS TOTAL_USERS
        FROM user_totals
    )
    SELECT
        r.USER_NAME,
        COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, r.USER_NAME) AS DISPLAY_NAME,
        r.TOTAL_CREDITS,
        r.PCT_OF_TOTAL,
        r.CUMULATIVE_PCT,
        r.TOTAL_USERS
    FROM ranked r
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS usr
        ON r.USER_NAME = usr.NAME
        AND usr.DELETED_ON IS NULL
    ORDER BY r.TOTAL_CREDITS DESC
    """


def _build_mom_growth_sql(view_name, days):
    """Build SQL for month-over-month credit consumption growth by user.

    Compares the current month's credits to the previous month's credits
    and calculates growth rate. Returns top 20 users by growth rate.
    Uses at least a 60-day lookback to ensure spanning 2 calendar months.

    Args:
        view_name: Fully qualified Snowflake view name.
        days: Number of days in the selected lookback period.

    Returns:
        SQL string producing MoM growth rates per user.
    """
    lookback_months = max(2, (days // 30) + 1)
    return f"""
    WITH monthly AS (
        SELECT
            USER_NAME,
            DATE_TRUNC('month', USAGE_TIME) AS USAGE_MONTH,
            ROUND(SUM(TOKEN_CREDITS), 2) AS MONTHLY_CREDITS
        FROM {view_name}
        WHERE USAGE_TIME >= DATEADD('month', -{lookback_months}, CURRENT_TIMESTAMP())
        GROUP BY USER_NAME, DATE_TRUNC('month', USAGE_TIME)
    ),
    pivoted AS (
        SELECT
            USER_NAME,
            MAX(CASE WHEN USAGE_MONTH = DATE_TRUNC('month', DATEADD('month', -1, CURRENT_TIMESTAMP()))
                     THEN MONTHLY_CREDITS END) AS PREV_MONTH_CREDITS,
            MAX(CASE WHEN USAGE_MONTH = DATE_TRUNC('month', CURRENT_TIMESTAMP())
                     THEN MONTHLY_CREDITS END) AS CURR_MONTH_CREDITS
        FROM monthly
        GROUP BY USER_NAME
        HAVING PREV_MONTH_CREDITS IS NOT NULL AND CURR_MONTH_CREDITS IS NOT NULL
    )
    SELECT
        p.USER_NAME,
        COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, p.USER_NAME) AS DISPLAY_NAME,
        p.PREV_MONTH_CREDITS,
        p.CURR_MONTH_CREDITS,
        ROUND(p.CURR_MONTH_CREDITS - p.PREV_MONTH_CREDITS, 2) AS CREDIT_CHANGE,
        ROUND(((p.CURR_MONTH_CREDITS - p.PREV_MONTH_CREDITS) / NULLIF(p.PREV_MONTH_CREDITS, 0)) * 100, 1) AS GROWTH_RATE_PCT
    FROM pivoted p
    LEFT JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS usr
        ON p.USER_NAME = usr.NAME
        AND usr.DELETED_ON IS NULL
    ORDER BY GROWTH_RATE_PCT DESC
    LIMIT 20
    """


@st.cache_data(ttl=1800)
def fetch_top_users(_session, days):
    """Submit top users and trend queries for all surfaces asynchronously.

    Args:
        _session: Snowpark session (underscore prefix for st.cache_data).
        days: Number of days to look back.

    Returns:
        Dict mapping surface names to DataFrames or Exception instances.
        Keys: "{surface}" for rankings, "{surface}_trends" for daily trends,
        "{surface}_growth" for MoM growth rates, "{surface}_pareto" for Pareto analysis.
    """
    logger.info("Fetching top users for all surfaces, days=%d", days)

    # Submit 4 async queries per surface (top users, trends, MoM growth, Pareto)
    # for a total of 12 parallel queries
    async_jobs = {}
    for surface, view in USAGE_VIEWS.items():
        sql = _build_top_users_sql(view, days)
        logger.info("Submitting async top users for %s", surface)
        async_jobs[surface] = _session.sql(sql).collect_nowait()

        trends_sql = _build_user_trends_sql(view, days)
        logger.info("Submitting async trends for %s", surface)
        async_jobs[f"{surface}_trends"] = _session.sql(trends_sql).collect_nowait()

        growth_sql = _build_mom_growth_sql(view, days)
        logger.info("Submitting async MoM growth for %s", surface)
        async_jobs[f"{surface}_growth"] = _session.sql(growth_sql).collect_nowait()

        pareto_sql = _build_pareto_sql(view, days)
        logger.info("Submitting async pareto for %s", surface)
        async_jobs[f"{surface}_pareto"] = _session.sql(pareto_sql).collect_nowait()

    # Collect all results; store exceptions for graceful per-section error handling
    results = {}
    for key, job in async_jobs.items():
        logger.info("Waiting for result: %s (query_id=%s)", key, job.query_id)
        try:
            rows = job.result()
            if rows:
                df = pd.DataFrame([row.as_dict() for row in rows])
            else:
                df = pd.DataFrame()
            logger.info("Result for %s: %d rows", key, len(df))
            results[key] = df
        except Exception as e:
            logger.error("Query failed for %s: %s\n%s", key, e, traceback.format_exc())
            results[key] = e

    return results


# --- Page layout ---

st.title("Top Users")
st.caption("Top 20 users by AI credit consumption across Cortex Code surfaces")
st.info(
    "Identify the highest-consuming users by estimated daily AI credits. "
    "The month-over-month trend table shows growth rates to help spot increasing usage patterns. "
    "Data comes from ACCOUNT_USAGE views which may have up to 45 minutes of latency.",
    icon=":material/info:",
)

col_period, col_refresh = st.columns([3, 1])
with col_period:
    period = st.selectbox(
        "Time period",
        options=list(TIME_PERIODS.keys()),
        index=2,
        key="top_users_period",
        help="Select the lookback window for top user rankings.",
    )
with col_refresh:
    st.write("")
    st.write("")
    if st.button("Refresh", key="refresh_top_users"):
        fetch_top_users.clear()
        st.rerun()

days = TIME_PERIODS[period]

with st.spinner("Loading top users..."):
    results = fetch_top_users(session, days)

# Render sections for each surface: Pareto analysis, top 20 table, bar chart,
# daily trend line chart, and month-over-month growth table
for surface in USAGE_VIEWS:
    st.subheader(f"{surface}")

    # --- Power Users (Pareto) section ---
    pareto_result = results.get(f"{surface}_pareto")
    if isinstance(pareto_result, Exception):
        st.error(f"Failed to load power users for {surface}: {pareto_result}")
    elif pareto_result is not None and not pareto_result.empty:
        pareto_df = pareto_result.copy()
        p_col_map = {c.lower(): c for c in pareto_df.columns}

        cum_col = p_col_map.get("cumulative_pct", "CUMULATIVE_PCT")
        total_users_col = p_col_map.get("total_users", "TOTAL_USERS")

        pareto_df[cum_col] = pd.to_numeric(pareto_df[cum_col], errors="coerce")
        # "Power users" = users who collectively account for 80% of total credits
        power_users_df = pareto_df[pareto_df[cum_col] <= 80]

        # If no users hit 80% threshold, take at least the top user
        if power_users_df.empty:
            power_users_df = pareto_df.head(1)

        total_users = int(pareto_df[total_users_col].iloc[0]) if total_users_col in pareto_df.columns else len(pareto_df)
        power_count = len(power_users_df)
        pct_of_users = round(power_count / total_users * 100, 1) if total_users > 0 else 0

        st.markdown("#### Power Users (Pareto Principle)")
        st.info(
            "The Pareto principle (80/20 rule) identifies the small number of users who account for "
            "the majority of AI credit consumption. These 'power users' drive most of the cost.",
            icon=":material/bolt:",
        )

        pareto_cols = st.columns(3)
        with pareto_cols[0]:
            st.metric("Power Users", f"{power_count}", border=True, help="Number of users who collectively account for ~80% of total AI credits.")
        with pareto_cols[1]:
            st.metric("% of All Users", f"{pct_of_users}%", border=True, help="What percentage of all active users are power users.")
        with pareto_cols[2]:
            st.metric("Concentration", f"{power_count} of {total_users}", border=True, help="Ratio of power users to total active users for this surface.")

        # Display the power users table
        power_display = power_users_df.rename(columns={
            p_col_map.get("display_name", "DISPLAY_NAME"): "Name",
            p_col_map.get("user_name", "USER_NAME"): "Username",
            p_col_map.get("total_credits", "TOTAL_CREDITS"): "Total AI Credits",
            p_col_map.get("pct_of_total", "PCT_OF_TOTAL"): "% of Total",
            p_col_map.get("cumulative_pct", "CUMULATIVE_PCT"): "Cumulative %",
        })
        for col in ["Total AI Credits", "% of Total", "Cumulative %"]:
            if col in power_display.columns:
                power_display[col] = pd.to_numeric(power_display[col], errors="coerce").round(2)
        # Drop internal columns
        drop_cols = [c for c in power_display.columns if c.upper() in ("TOTAL_USERS",)]
        power_display = power_display.drop(columns=drop_cols, errors="ignore")
        st.dataframe(power_display, use_container_width=True, hide_index=True)

    st.markdown("#### Top 20 Users")

    result = results.get(surface)
    if isinstance(result, Exception):
        st.error(f"Failed to query top users for {surface}: {result}")
        continue

    if result is None or result.empty:
        st.info(f"No {surface} usage data found for the selected period.")
        continue

    df = result.copy()
    col_map = {c.lower(): c for c in df.columns}

    display_df = df.rename(columns={
        col_map.get("display_name", "DISPLAY_NAME"): "Name",
        col_map.get("user_name", "USER_NAME"): "Username",
        col_map.get("total_credits", "TOTAL_CREDITS"): "Total AI Credits",
        col_map.get("total_requests", "TOTAL_REQUESTS"): "Total Requests",
        col_map.get("active_days", "ACTIVE_DAYS"): "Active Days",
        col_map.get("avg_credits_per_day", "AVG_CREDITS_PER_DAY"): "Avg AI Credits/Day",
    })

    # Ensure numeric formatting
    for col in ["Total AI Credits", "Avg AI Credits/Day"]:
        if col in display_df.columns:
            display_df[col] = pd.to_numeric(display_df[col], errors="coerce").round(2)

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Horizontal bar chart of credits by user
    if "Name" in display_df.columns and "Total AI Credits" in display_df.columns:
        chart_df = display_df[["Name", "Total AI Credits"]].sort_values("Total AI Credits")
        st.bar_chart(chart_df, x="Name", y="Total AI Credits", horizontal=True)

    # Daily credit trends for top users over time (line chart)
    trends_result = results.get(f"{surface}_trends")
    if isinstance(trends_result, Exception):
        st.error(f"Failed to load trends for {surface}: {trends_result}")
    elif trends_result is not None and not trends_result.empty:
        st.markdown(f"#### {surface} — Daily Credit Trends (Top 10 Users)")
        trends_df = trends_result.copy()
        t_col_map = {c.lower(): c for c in trends_df.columns}

        date_col = t_col_map.get("usage_date", "USAGE_DATE")
        name_col = t_col_map.get("display_name", "DISPLAY_NAME")
        credits_col = t_col_map.get("daily_credits", "DAILY_CREDITS")

        # Pivot from long-form (one row per user per day) to wide-form
        # (one column per user) for the multi-series line chart
        trends_df[date_col] = pd.to_datetime(trends_df[date_col])
        trends_df[credits_col] = pd.to_numeric(trends_df[credits_col], errors="coerce")
        pivot_df = trends_df.pivot_table(
            index=date_col, columns=name_col, values=credits_col, fill_value=0
        )

        # Fill timeline gaps so every day appears on the x-axis
        if not pivot_df.empty:
            full_range = pd.date_range(
                start=pivot_df.index.min(),
                end=pivot_df.index.max(),
                freq="D",
            )
            pivot_df = pivot_df.reindex(full_range).fillna(0)
            pivot_df.index.name = "Date"

            # Filter out users with negligible total usage
            pivot_df = pivot_df.loc[:, pivot_df.sum() > 0.5]

            if not pivot_df.empty:
                st.line_chart(pivot_df)

    # Month-over-month growth rates
    growth_result = results.get(f"{surface}_growth")
    if isinstance(growth_result, Exception):
        st.error(f"Failed to load MoM growth for {surface}: {growth_result}")
    elif growth_result is not None and not growth_result.empty:
        st.markdown(f"#### {surface} — Month-over-Month Growth (Top 20)")
        growth_df = growth_result.copy()
        g_col_map = {c.lower(): c for c in growth_df.columns}

        growth_display = growth_df.rename(columns={
            g_col_map.get("display_name", "DISPLAY_NAME"): "Name",
            g_col_map.get("user_name", "USER_NAME"): "Username",
            g_col_map.get("prev_month_credits", "PREV_MONTH_CREDITS"): "Last Month",
            g_col_map.get("curr_month_credits", "CURR_MONTH_CREDITS"): "This Month",
            g_col_map.get("credit_change", "CREDIT_CHANGE"): "Change",
            g_col_map.get("growth_rate_pct", "GROWTH_RATE_PCT"): "Growth %",
        })

        for col in ["Last Month", "This Month", "Change"]:
            if col in growth_display.columns:
                growth_display[col] = pd.to_numeric(growth_display[col], errors="coerce").round(2)

        st.dataframe(growth_display, use_container_width=True, hide_index=True)
    else:
        st.info(f"Usage found only in one calendar month for {surface} — MoM growth requires data in at least two separate months.")

    st.divider()

logger.info("Top users page rendering complete")
