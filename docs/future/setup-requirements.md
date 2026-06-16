# Setup Requirements: AI Functions Monitoring + Native Budgets

> **Note:** These are additional requirements for the new AI Functions pages.
> The existing FrostGate setup (FROSTGATE database, FROSTGATE_WH, compute pool)
> is assumed to already be in place. See `docs/current/setup-requirements.md`.

## Prerequisites

### Permissions Required

| Privilege | Purpose |
|-----------|---------|
| ACCOUNTADMIN (or equivalent) | View ACCOUNT_USAGE, create budgets, tag users |
| IMPORTED PRIVILEGES on SNOWFLAKE db | Query ACCOUNT_USAGE views |
| CREATE TAG ON SCHEMA | Create tags for user grouping |
| CREATE BUDGET ON SCHEMA | Create budget objects |
| CREATE INTEGRATION ON ACCOUNT | Email notification integration (optional) |

### Account Requirements

- Snowflake Enterprise Edition or higher (for budgets)
- `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` view accessible (automatic with IMPORTED PRIVILEGES)
- Shared Resource Budgets feature available (GA April 2026)

---

## Step 1: Create Tag Infrastructure

```sql
-- Create a database/schema for cost management objects
CREATE DATABASE IF NOT EXISTS COST_MANAGEMENT;
CREATE SCHEMA IF NOT EXISTS COST_MANAGEMENT.TAGS;
CREATE SCHEMA IF NOT EXISTS COST_MANAGEMENT.BUDGETS;

-- Create tags for grouping users into cost centers
CREATE TAG IF NOT EXISTS COST_MANAGEMENT.TAGS.COST_CENTER
    COMMENT = 'Cost center for AI budget attribution';

CREATE TAG IF NOT EXISTS COST_MANAGEMENT.TAGS.TEAM
    COMMENT = 'Team name for AI budget attribution';
```

## Step 2: Tag Users

```sql
-- Tag users by their cost center / team
ALTER USER alice SET TAG COST_MANAGEMENT.TAGS.TEAM = 'ENGINEERING';
ALTER USER bob SET TAG COST_MANAGEMENT.TAGS.TEAM = 'DATA_SCIENCE';
ALTER USER charlie SET TAG COST_MANAGEMENT.TAGS.TEAM = 'FINANCE';

-- Verify tags
SELECT
    u.NAME,
    SYSTEM$GET_TAG('COST_MANAGEMENT.TAGS.TEAM', u.NAME, 'USER') AS TEAM
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS u
WHERE u.DELETED_ON IS NULL
ORDER BY u.NAME;
```

## Step 3: Create Budget

```sql
-- Create a custom budget for the engineering team
CREATE BUDGET IF NOT EXISTS COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET;

-- Set a monthly spending limit (credits)
ALTER BUDGET COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET
    SET SPENDING_LIMIT = 5000;
```

## Step 4: Configure Budget Scope

```sql
-- Add AI Functions as tracked shared resource
CALL COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET!ADD_SHARED_RESOURCE('AI FUNCTION');

-- Optionally add other AI resources to the same budget
CALL COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET!ADD_SHARED_RESOURCE('CORTEX AGENT');

-- Link user tags to budget
CALL COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET!SET_USER_TAGS(
    [[(SELECT SYSTEM$REFERENCE('TAG', 'COST_MANAGEMENT.TAGS.TEAM', 'SESSION', 'APPLYBUDGET')),
      'ENGINEERING']],
    'UNION'
);
```

## Step 5: Verify

```sql
-- Verify budget scope
CALL COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET!GET_BUDGET_SCOPE();

-- Check available shared resource candidates
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES();

-- Confirm budget is tracking
SHOW BUDGETS IN SCHEMA COST_MANAGEMENT.BUDGETS;
```

---

## Notification Integration Setup (Optional)

```sql
-- Create email notification integration for budget alerts
CREATE OR REPLACE NOTIFICATION INTEGRATION ai_cost_alerts
    TYPE = EMAIL
    ENABLED = TRUE
    ALLOWED_RECIPIENTS = ('admin@company.com');

-- Note: Each recipient email must:
-- 1. Be listed in ALLOWED_RECIPIENTS
-- 2. Be set as EMAIL on a Snowflake user in the account
-- 3. Have completed email verification
```

---

## Teardown SQL (If Needed)

```sql
-- Drop budgets
DROP BUDGET IF EXISTS COST_MANAGEMENT.BUDGETS.ENGINEERING_AI_BUDGET;

-- Remove tags from users (must be done before dropping tags)
ALTER USER alice UNSET TAG COST_MANAGEMENT.TAGS.TEAM;
ALTER USER bob UNSET TAG COST_MANAGEMENT.TAGS.TEAM;
ALTER USER charlie UNSET TAG COST_MANAGEMENT.TAGS.TEAM;

-- Drop tags
DROP TAG IF EXISTS COST_MANAGEMENT.TAGS.COST_CENTER;
DROP TAG IF EXISTS COST_MANAGEMENT.TAGS.TEAM;

-- Drop schemas/database (optional)
DROP SCHEMA IF EXISTS COST_MANAGEMENT.BUDGETS;
DROP SCHEMA IF EXISTS COST_MANAGEMENT.TAGS;
DROP DATABASE IF EXISTS COST_MANAGEMENT;

-- Drop notification integration (optional)
DROP INTEGRATION IF EXISTS ai_cost_alerts;
```

---

## FrostGate App Configuration

The app's `snowflake.yml` will need these additional artifact entries:

```yaml
artifacts:
  # ... existing entries ...
  - app_pages/common_ai.py
  - app_pages/ai_dashboard.py
  - app_pages/ai_top_users.py
  - app_pages/ai_budgets.py
```

---

## Validation Queries

Use these to confirm everything is working before building the UI:

```sql
-- Confirm usage history view is accessible
SELECT COUNT(*) AS ROW_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP());

-- Confirm credits are being tracked
SELECT
    FUNCTION_NAME,
    ROUND(SUM(CREDITS), 4) AS TOTAL_CREDITS,
    COUNT(DISTINCT QUERY_ID) AS QUERY_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 2 DESC;

-- Confirm user join works
SELECT
    u.NAME,
    ROUND(SUM(h.CREDITS), 4) AS CREDITS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY h
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON h.USER_ID = u.USER_ID
WHERE h.START_TIME >= DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 2 DESC
LIMIT 5;
```
