# Setup Requirements: FrostGate Current State

## Prerequisites

### Permissions Required

| Privilege | Purpose |
|-----------|---------|
| ACCOUNTADMIN role (or equivalent) | ALTER ACCOUNT SET/UNSET parameters, ALTER USER, view ACCOUNT_USAGE |
| IMPORTED PRIVILEGES on SNOWFLAKE db | Query ACCOUNT_USAGE views |
| USAGE on a warehouse | Query execution (FROSTGATE_WH) |
| Access to SYSTEM_COMPUTE_POOL_CPU | Container Runtime for Streamlit |

### Account Requirements

- Snowflake account with Cortex Code enabled
- Container Runtime (SPCS) available for Streamlit apps
- `SYSTEM_COMPUTE_POOL_CPU` compute pool accessible
- ACCOUNT_USAGE views accessible (latency: ~45 min for Cortex Code views)

---

## Snowflake Objects

### Database and Schema

```sql
CREATE DATABASE IF NOT EXISTS FROSTGATE;
CREATE SCHEMA IF NOT EXISTS FROSTGATE.APP;
```

### Warehouse

```sql
CREATE WAREHOUSE IF NOT EXISTS FROSTGATE_WH
    WAREHOUSE_SIZE = 'XSMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE
    COMMENT = 'Query warehouse for FrostGate Streamlit app';
```

### Streamlit App Object

The app is deployed via `snowflake.yml`:

```sql
-- Created automatically by Snowflake CLI / Workspace deploy
-- Equivalent manual DDL:
CREATE STREAMLIT IF NOT EXISTS FROSTGATE.APP.FROST_GATE
    ROOT_LOCATION = '@FROSTGATE.APP.FROST_GATE_STAGE'
    MAIN_FILE = 'streamlit_app.py'
    QUERY_WAREHOUSE = 'FROSTGATE_WH'
    COMMENT = 'FrostGate - Cortex Code Credit Usage Limit Manager';
```

---

## ACCOUNT_USAGE Views Used

### Cortex Code Usage History

| View | Surface | Key Columns |
|------|---------|-------------|
| `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY` | CLI | USER_NAME, TOKEN_CREDITS, USAGE_TIME |
| `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY` | Desktop | USER_NAME, TOKEN_CREDITS, USAGE_TIME |
| `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY` | Snowsight | USER_NAME, TOKEN_CREDITS, USAGE_TIME |

### Supporting Views

| View | Purpose |
|------|---------|
| `SNOWFLAKE.ACCOUNT_USAGE.USERS` | User display names, join with usage data |
| `SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS` | Role-based filtering for bulk operations |
| `SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES` | Tag-based filtering for bulk operations |

---

## Account Parameters Managed

| Parameter | Controls |
|-----------|----------|
| `CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER` | Daily AI credit cap for CLI surface |
| `CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER` | Daily AI credit cap for Desktop surface |
| `CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER` | Daily AI credit cap for Snowsight surface |

### Parameter Values

| Value | Meaning |
|-------|---------|
| -1 | Unlimited (no cap enforced) |
| 0 | Blocked (usage completely prevented) |
| N (positive integer) | N AI credits/day rolling 24h cap |

### Parameter Levels

| Level | Set Via | Meaning |
|-------|---------|---------|
| DEFAULT | (not explicitly set) | Uses Snowflake default (-1, unlimited) |
| ACCOUNT | `ALTER ACCOUNT SET ...` | Account-wide default for all users |
| USER | `ALTER USER SET ...` | Per-user override (takes precedence) |

---

## Validation Queries

Use these to confirm the environment is correctly configured:

```sql
-- Verify ACCOUNT_USAGE access
SELECT 1 FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY LIMIT 0;

-- Check current account-level limits
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' IN ACCOUNT;

-- Check if usage data exists
SELECT COUNT(*) AS ROW_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY
WHERE USAGE_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP());

-- Verify current role
SELECT CURRENT_ROLE();

-- Verify warehouse exists
SHOW WAREHOUSES LIKE 'FROSTGATE_WH';

-- Verify compute pool access
SHOW COMPUTE POOLS LIKE 'SYSTEM_COMPUTE_POOL_CPU';
```

---

## Dependencies (pyproject.toml)

The app uses only packages bundled with Snowflake's Streamlit runtime:
- `streamlit` (built-in)
- `snowflake-snowpark-python` (built-in)
- `pandas` (built-in)

No external packages required.

---

## Deployment

The app is deployed from the workspace via `snowflake.yml`:

```yaml
definition_version: 2
entities:
  streamlit_app:
    type: streamlit
    identifier:
      database: FROSTGATE
      schema: APP
      name: FROST_GATE
    title: frost-gate
    query_warehouse: FROSTGATE_WH
    compute_pool: SYSTEM_COMPUTE_POOL_CPU
    run_mode: SpcsOnly
    execute_as: OWNER
    main_file: streamlit_app.py
    artifacts:
      - pyproject.toml
      - streamlit_app.py
      - .streamlit/config.toml
      - app_pages/common.py
      - app_pages/home.py
      - app_pages/dashboard.py
      - app_pages/top_users.py
      - app_pages/account_limits.py
      - app_pages/user_limits.py
      - app_pages/bulk_update.py
      - app_pages/interface_access.py
      - app_pages/sql_reference.py
```

---

## Teardown (If Needed)

```sql
-- Drop the Streamlit app
DROP STREAMLIT IF EXISTS FROSTGATE.APP.FROST_GATE;

-- Drop the warehouse
DROP WAREHOUSE IF EXISTS FROSTGATE_WH;

-- Drop the schema and database
DROP SCHEMA IF EXISTS FROSTGATE.APP;
DROP DATABASE IF EXISTS FROSTGATE;
```

Note: Dropping the app does NOT affect any account/user parameters that were
set through the app — those persist independently.
