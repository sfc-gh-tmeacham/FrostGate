# Page Specifications: FrostGate Current State

## Page 1: Home (`app_pages/home.py`)

### Purpose
Welcome page with app overview, feature summary, and quick navigation.

---

## Page 2: Usage Dashboard (`app_pages/dashboard.py`)

### Purpose
Visualize Cortex Code AI credit consumption across all three surfaces
with daily trends, monthly totals, and configurable time periods.

### Data Sources
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`
- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`

### Key Queries

```sql
-- Total credits and requests per surface
SELECT
    ROUND(COALESCE(SUM(TOKEN_CREDITS), 0), 2) AS TOTAL_CREDITS,
    COUNT(*) AS TOTAL_REQUESTS,
    COUNT(DISTINCT USER_NAME) AS UNIQUE_USERS,
    COUNT(DISTINCT DATE(USAGE_TIME)) AS ACTIVE_DAYS
FROM <usage_view>
WHERE USAGE_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP());

-- Daily trend
SELECT
    DATE(USAGE_TIME) AS USAGE_DATE,
    ROUND(SUM(TOKEN_CREDITS), 2) AS DAILY_CREDITS
FROM <usage_view>
WHERE USAGE_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1;

-- Monthly totals
SELECT
    DATE_TRUNC('month', USAGE_TIME) AS USAGE_MONTH,
    ROUND(SUM(TOKEN_CREDITS), 2) AS MONTHLY_CREDITS,
    COUNT(*) AS MONTHLY_REQUESTS,
    COUNT(DISTINCT USER_NAME) AS UNIQUE_USERS
FROM <usage_view>
WHERE USAGE_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1;
```

### Features
- Per-surface metric cards (credits, requests, unique users, active days)
- Daily credit line charts (one per surface)
- Monthly totals bar chart
- Configurable time period (7/14/30/60/90/365 days)
- 30-minute cache with manual refresh button

---

## Page 3: Top Users (`app_pages/top_users.py`)

### Purpose
Identify top 20 consumers per surface with Pareto analysis,
daily trend lines, and month-over-month growth tracking.

### Key Queries

```sql
-- Top 20 users by credits
SELECT
    USER_NAME,
    COALESCE(usr.DISPLAY_NAME, usr.FIRST_NAME || ' ' || usr.LAST_NAME, u.USER_NAME) AS DISPLAY_NAME,
    ROUND(SUM(TOKEN_CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(*) AS TOTAL_REQUESTS,
    COUNT(DISTINCT DATE(USAGE_TIME)) AS ACTIVE_DAYS,
    ROUND(SUM(TOKEN_CREDITS) / NULLIF(COUNT(DISTINCT DATE(USAGE_TIME)), 0), 2) AS AVG_CREDITS_PER_DAY
FROM <usage_view>
WHERE USAGE_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY USER_NAME
ORDER BY TOTAL_CREDITS DESC LIMIT 20;

-- Pareto analysis (cumulative credit percentages)
SELECT
    USER_NAME, DISPLAY_NAME, TOTAL_CREDITS,
    ROUND(TOTAL_CREDITS / NULLIF(SUM(TOTAL_CREDITS) OVER (), 0) * 100, 1) AS PCT_OF_TOTAL,
    ROUND(SUM(TOTAL_CREDITS) OVER (ORDER BY TOTAL_CREDITS DESC
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
          / NULLIF(SUM(TOTAL_CREDITS) OVER (), 0) * 100, 1) AS CUMULATIVE_PCT
FROM user_totals;

-- Month-over-month growth
SELECT USER_NAME, PREV_MONTH_CREDITS, CURR_MONTH_CREDITS,
    ROUND(((CURR - PREV) / NULLIF(PREV, 0)) * 100, 1) AS GROWTH_RATE_PCT
FROM pivoted
ORDER BY GROWTH_RATE_PCT DESC LIMIT 20;

-- Daily trends for top 10 users
SELECT DATE(USAGE_TIME), DISPLAY_NAME, ROUND(SUM(TOKEN_CREDITS), 2)
FROM <usage_view>
WHERE USER_NAME IN (top 10)
GROUP BY 1, 2 ORDER BY 1;
```

### Features
- 12 parallel queries (4 per surface × 3 surfaces)
- Power Users panel (who accounts for 80% of credits)
- Top 20 table + horizontal bar chart
- Daily trend multi-series line chart (top 10 users)
- Month-over-month growth rate table

---

## Page 4: Account Limits (`app_pages/account_limits.py`)

### Purpose
View and modify account-level daily AI credit limits for all three surfaces.

### UI Layout

```
┌─────────────────────────────────────────────────────────┐
│ Account-Level Limits                                    │
├─────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│ │ CLI      │ │ Desktop  │ │ Snowsight│                 │
│ │ -1       │ │ -1       │ │ 25       │                 │
│ │ Unlimited│ │ Unlimited│ │ credits  │                 │
│ └──────────┘ └──────────┘ └──────────┘                 │
├─────────────────────────────────────────────────────────┤
│ Update Account Limits                                   │
│ [CLI: No change ▼] [Desktop: No change ▼] [Snowsight ▼]│
│ [CLI credits: 25]  [Desktop credits: 25]  [Snwsght: 25]│
│ [Apply Account Changes]                                 │
└─────────────────────────────────────────────────────────┘
```

### Actions Available
- No change
- Set limit (specific credit value)
- Set unlimited (-1)
- Block usage (0)
- Unset (unlimited — removes explicit setting)

### Key SQL
```sql
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' IN ACCOUNT;
ALTER ACCOUNT SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 25;
ALTER ACCOUNT UNSET CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER;
```

---

## Page 5: User Limits (`app_pages/user_limits.py`)

### Purpose
View and modify per-user daily AI credit limit overrides for a selected user.
Shows usage stats and comparison to account average.

### UI Layout

```
┌─────────────────────────────────────────────────────────┐
│ User-Level Limits                                       │
├─────────────────────────────────────────────────────────┤
│ [Select user ▼ ALICE]  [Refresh users]                  │
├─────────────────────────────────────────────────────────┤
│ Display Name │ Email │ Default Role │ Warehouse         │
├─────────────────────────────────────────────────────────┤
│ Current limits for ALICE:                               │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│ │ CLI: 50  │ │ Desktop  │ │ Snowsight│                 │
│ │ User ovr │ │ Inherited│ │ User ovr │                 │
│ └──────────┘ └──────────┘ └──────────┘                 │
├─────────────────────────────────────────────────────────┤
│ Update Limits for ALICE                                 │
│ [form with actions + credit values per surface]         │
├─────────────────────────────────────────────────────────┤
│ Usage for ALICE (last 7 days):                          │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│ │ CLI: 3.2 │ │ Desktop  │ │ Snowsight│                 │
│ │ 45 reqs  │ │ 0.0 cred │ │ 12.5 cr  │                 │
│ └──────────┘ └──────────┘ └──────────┘                 │
│ Peak Day │ Avg/Day (delta vs account avg)               │
└─────────────────────────────────────────────────────────┘
```

### Key Queries

```sql
-- User parameters (single wildcard query instead of 3 separate)
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' IN USER "username";

-- User usage totals
SELECT ROUND(COALESCE(SUM(TOKEN_CREDITS), 0), 2) AS TOTAL_CREDITS, COUNT(*) AS TOTAL_REQUESTS
FROM <usage_view>
WHERE USER_NAME = 'username' AND USAGE_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP());

-- User vs account comparison
SELECT
    MAX(user_daily_credits) AS USER_MAX_DAY,
    AVG(user_daily_credits) AS USER_AVG_DAY,
    (SELECT AVG(daily_credits) FROM all_users_daily) AS ACCOUNT_AVG_DAY;
```

---

## Page 6: Bulk User Update (`app_pages/bulk_update.py`)

### Purpose
Apply the same credit limit changes to multiple users simultaneously.
Includes role/tag-based filtering and an override scanner.

### Features
- User table with multi-row selection
- Filter by role (queries `GRANTS_TO_USERS`)
- Filter by tag (queries `TAG_REFERENCES`)
- Batch ALTER USER execution (all fired async in parallel)
- Override Scanner: scans all users to find who has per-user overrides

### Key SQL

```sql
-- Filter by role
SELECT DISTINCT GRANTEE_NAME AS USER_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
WHERE ROLE IN ('ROLE1', 'ROLE2') AND DELETED_ON IS NULL;

-- Filter by tag
SELECT DISTINCT OBJECT_NAME AS USER_NAME
FROM SNOWFLAKE.ACCOUNT_USAGE.TAG_REFERENCES
WHERE DOMAIN = 'USER' AND OBJECT_DELETED IS NULL
  AND (TAG_DATABASE = 'DB' AND TAG_SCHEMA = 'SCH' AND TAG_NAME = 'TAG');

-- Bulk scan for overrides (fired per user, all async)
SHOW PARAMETERS LIKE 'CORTEX_CODE_%_DAILY_EST_CREDIT_LIMIT_PER_USER' IN USER "username";
-- Filtered to rows where level = 'USER'
```

---

## Page 7: Interface Access (`app_pages/interface_access.py`)

### Purpose
Manage which Snowflake interfaces users can access via `ALLOWED_INTERFACES`.

### Interface Options
| Label | Value |
|-------|-------|
| ALL (default) | All interfaces |
| SNOWFLAKE_INTELLIGENCE | Snowflake CoWork only |
| STREAMLIT | Streamlit apps only |
| SNOWFLAKE_INTELLIGENCE + STREAMLIT | CoWork and Streamlit |

### Features
- Single user update with confirmation dialog
- Bulk update with role/tag filtering
- Self-protection (cannot modify your own access)
- Same filter pattern as Bulk User Update page

### Key SQL

```sql
-- Read current setting
DESCRIBE USER "username";  -- look for property = ALLOWED_INTERFACES

-- Set interfaces
ALTER USER "username" SET ALLOWED_INTERFACES = ('SNOWFLAKE_INTELLIGENCE', 'STREAMLIT');

-- Revert to all
ALTER USER "username" UNSET ALLOWED_INTERFACES;
```

---

## Page 8: Logs (`app_pages/logs.py`)

### Purpose
Display FrostGate application logs for troubleshooting.

---

## Page 9: FAQs (`app_pages/faq.py`)

### Purpose
In-app help documentation with common questions and answers.

---

## Page 10: SQL Reference (`app_pages/sql_reference.py`)

### Purpose
Reference SQL commands for manual administration outside the app.
