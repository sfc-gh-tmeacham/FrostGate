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

    Args:
        session: Active Snowpark session.
        sql: The SHOW PARAMETERS SQL statement to execute.

    Returns:
        A dict with lowercase keys from the result row, or None if empty.
    """
    rows = session.sql(sql).collect()
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


@st.cache_data(ttl=86400)
def get_user_list(_session: Session) -> list[str]:
    """Fetch a sorted list of all usernames in the account.

    Args:
        _session: Snowpark session (underscore prefix for st.cache_data).

    Returns:
        Sorted list of user name strings.
    """
    logger.info("Fetching user list")
    df = _session.sql("SHOW USERS").to_pandas()
    col_map: dict[str, str] = {c.lower(): c for c in df.columns}
    name_col = col_map.get("name", df.columns[0])
    users: list[str] = sorted(df[name_col].tolist())
    logger.info("Found %d users", len(users))
    return users
