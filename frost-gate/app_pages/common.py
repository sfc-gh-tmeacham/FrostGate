"""Shared constants and utility functions for FrostGate pages.

Centralizes duplicated definitions so changes only need to happen in one place.
"""

from __future__ import annotations

import logging
from typing import Any, Union

import streamlit as st
from snowflake.snowpark import Session

logger: logging.Logger = logging.getLogger("frostgate")

# Snowflake account parameters that control daily AI credit caps per surface.
# Used by ALTER ACCOUNT SET / ALTER USER SET commands.
PARAMS: dict[str, str] = {
    "CLI": "CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Desktop": "CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER",
    "Snowsight": "CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER",
}

# ACCOUNT_USAGE views that track credit consumption for each Cortex Code surface
USAGE_VIEWS: dict[str, str] = {
    "CLI": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY",
    "Desktop": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY",
    "Snowsight": "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY",
}

# Selectable lookback windows for time period filters
TIME_PERIODS: dict[str, int] = {
    "Last 7 days": 7,
    "Last 14 days": 14,
    "Last 30 days": 30,
    "Last 60 days": 60,
    "Last 90 days": 90,
    "Last 365 days": 365,
}


def get_param_value(session: Session, sql: str) -> dict[str, Any] | None:
    """Execute a SHOW PARAMETERS query and return the first row as a dict.

    Uses collect_nowait() for async execution.

    Args:
        session: Active Snowpark session.
        sql: The SHOW PARAMETERS SQL statement to execute.

    Returns:
        A dict with lowercase keys from the result row, or None if empty.
    """
    job = session.sql(sql).collect_nowait()
    rows = job.result()
    if not rows:
        return None
    row = rows[0].as_dict()
    return {k.lower(): v for k, v in row.items()}


def display_limit_value(value: Union[str, int, float, None], verbose: bool = False) -> str:
    """Format a limit parameter value for display.

    Args:
        value: The raw parameter value as a string or number.
        verbose: If True, include extra context (e.g. "AI credits/day").

    Returns:
        Human-readable string.
    """
    try:
        v = float(value)
        if v == -1:
            return "Unlimited (default)" if verbose else "Unlimited"
        elif v == 0:
            return "Blocked (0)" if verbose else "Blocked"
        else:
            return f"{v:g} AI credits/day" if verbose else f"{v:g}"
    except (ValueError, TypeError):
        return str(value)


def normalize_row(row) -> dict[str, Any]:
    """Convert a Snowpark Row to a dict with lowercase keys.

    Args:
        row: A Snowpark Row object.

    Returns:
        Dict with lowercase keys.
    """
    return {k.lower(): v for k, v in row.as_dict().items()}


def fetch_params_async(session: Session, target: str) -> dict[str, dict[str, str]]:
    """Fetch Cortex Code credit limit parameters asynchronously.

    Submits SHOW PARAMETERS queries for each surface in parallel via
    collect_nowait() and collects results.

    Args:
        session: Active Snowpark session.
        target: SQL target clause, e.g. 'IN ACCOUNT' or 'IN USER "TOM"'.

    Returns:
        Dict mapping surface labels to dicts with 'value', 'level', 'param'.
    """
    logger.info("Fetching parameters: %s", target)

    async_jobs = {}
    for label, param in PARAMS.items():
        sql = f"SHOW PARAMETERS LIKE '{param}' {target}"
        async_jobs[label] = session.sql(sql).collect_nowait()

    results: dict[str, dict[str, str]] = {}
    for label, job in async_jobs.items():
        param = PARAMS[label]
        try:
            rows = job.result()
            if rows:
                row_lower = normalize_row(rows[0])
                value = str(row_lower.get("value", "-1"))
                level = str(row_lower.get("level", "")).upper()
                results[label] = {"value": value, "level": level, "param": param}
                logger.info("Param %s [%s]: value=%s, level=%s", label, target, value, level)
            else:
                results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
        except Exception as e:
            logger.error("Failed to fetch param %s [%s]: %s", label, target, e)
            results[label] = {"value": "-1", "level": "DEFAULT", "param": param}
    return results


def apply_limit_action(
    session: Session,
    action: str,
    param: str,
    label: str,
    value: int,
    alter_target: str,
    app_user: str,
) -> str | None:
    """Execute a limit action (set/unset/block) via ALTER SQL.

    Args:
        session: Active Snowpark session.
        action: One of "Set limit", "Set unlimited", "Block usage",
                "Unset (unlimited)", "Unset (inherit account)", "No change".
        param: The Snowflake parameter name.
        label: Surface label (CLI/Desktop/Snowsight) for logging.
        value: Numeric credit value (used only for "Set limit").
        alter_target: SQL target, e.g. 'ACCOUNT' or 'USER "TOM"'.
        app_user: Current app user for audit logging.

    Returns:
        A markdown summary string on success, or None if no action.

    Raises:
        Exception: If the SQL command fails.
    """
    if action == "No change":
        return None

    unset_actions = {"Unset (unlimited)", "Unset (inherit account)"}
    if action in unset_actions:
        logger.info("[%s] Unsetting %s on %s", app_user, param, alter_target)
        job = session.sql(f"ALTER {alter_target} UNSET {param}").collect_nowait()
        job.result()
        return f"**{label}**: unset (unlimited)"
    elif action == "Set unlimited":
        logger.info("[%s] Setting %s = -1 on %s", app_user, param, alter_target)
        job = session.sql(f"ALTER {alter_target} SET {param} = -1").collect_nowait()
        job.result()
        return f"**{label}**: set to unlimited (-1)"
    elif action == "Block usage":
        logger.info("[%s] Setting %s = 0 on %s", app_user, param, alter_target)
        job = session.sql(f"ALTER {alter_target} SET {param} = 0").collect_nowait()
        job.result()
        return f"**{label}**: blocked (0)"
    else:
        logger.info("[%s] Setting %s = %d on %s", app_user, param, int(value), alter_target)
        job = session.sql(f"ALTER {alter_target} SET {param} = {int(value)}").collect_nowait()
        job.result()
        return f"**{label}**: set to {int(value)} AI credits/day"


@st.cache_data(ttl=86400)
def get_user_list(_session: Session) -> list[str]:
    """Fetch a sorted list of all usernames in the account.

    Uses collect_nowait() for async execution.

    Args:
        _session: Snowpark session (underscore prefix for st.cache_data).

    Returns:
        Sorted list of user name strings.
    """
    logger.info("Fetching user list")
    job = _session.sql("SHOW USERS").collect_nowait()
    rows = job.result()
    import pandas as pd
    df = pd.DataFrame([r.as_dict() for r in rows])
    col_map: dict[str, str] = {c.lower(): c for c in df.columns}
    name_col = col_map.get("name", df.columns[0])
    users: list[str] = sorted(df[name_col].tolist())
    logger.info("Found %d users", len(users))
    return users


def get_users_df(_session: Session):
    """Fetch user details from the account as a DataFrame.

    Uses collect_nowait() to run timezone and user queries in parallel.

    Args:
        _session: Active Snowpark session.

    Returns:
        pandas DataFrame with User, Display Name, Email, Default Role,
        Last Login, and Disabled columns, sorted by User.
    """
    import pandas as pd

    # Fire both queries asynchronously
    tz_job = _session.sql("SHOW PARAMETERS LIKE 'TIMEZONE' IN ACCOUNT").collect_nowait()
    users_job = _session.sql("SHOW USERS").collect_nowait()

    # Get the account's local timezone
    account_tz = "UTC"
    tz_rows = tz_job.result()
    for row in tz_rows:
        row_dict = row.as_dict()
        val = row_dict.get("value") or row_dict.get("VALUE", "")
        if val:
            account_tz = val
            break

    user_rows = users_job.result()
    df = pd.DataFrame([r.as_dict() for r in user_rows])
    col_map = {c.lower(): c for c in df.columns}
    result = pd.DataFrame()
    result["User"] = df[col_map.get("name", "name")]
    result["Display Name"] = df[col_map.get("display_name", "display_name")].fillna("—")
    result["Email"] = df[col_map.get("email", "email")].fillna("—")
    result["Default Role"] = df[col_map.get("default_role", "default_role")].fillna("—")

    # Format Last Login to minute precision in the account's timezone
    last_login_col = df[col_map.get("last_success_login", "last_success_login")]
    last_login_ts = pd.to_datetime(last_login_col, errors="coerce", utc=True)
    last_login_local = last_login_ts.dt.tz_convert(account_tz)
    result["Last Login"] = last_login_local.dt.strftime("%Y-%m-%d %H:%M").fillna("Never")

    result["Disabled"] = df[col_map.get("disabled", "disabled")].fillna("false")
    return result.sort_values("User").reset_index(drop=True)
