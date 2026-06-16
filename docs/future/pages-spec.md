# Page Specifications: AI Functions Monitoring + Budgets

> **Note:** These are new pages to be added to the existing FrostGate navigation.
> All current pages (Home, Dashboard, Top Users, Account Limits, User Limits,
> Bulk Update, Interface Access, Logs, FAQs, SQL Reference) remain unchanged.

## Page 1: AI Usage Dashboard (`app_pages/ai_dashboard.py`)

### Purpose
Provide at-a-glance visibility into Cortex AI Functions credit consumption across
the account, broken down by function, model, user, and time.

### Data Source
`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY`

### UI Layout

```
┌─────────────────────────────────────────────────────────┐
│ AI Functions Usage Dashboard                            │
┌─────────────────────────────────────────────────────────┐
│ [Time Period v]  [Refresh]                              │
┌─────────────────────────────────────────────────────────┐
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐             │
│ │Total   │ │Active  │ │Avg/User│ │Funcs   │             │
│ │Credits │ │Users   │ │/Day    │ │Called   │             │
│ │ 127.4  │ │  12    │ │  3.2   │ │   6    │             │
│ └────────┘ └────────┘ └────────┘ └────────┘             │
┌─────────────────────────────────────────────────────────┐
│ [Daily Credits Line Chart - stacked by function]        │
┌─────────────────────────────────────────────────────────┐
│ Credits by Function    Credits by Model                 │
│ ┌──────────────────┐   ┌──────────────────┐             │
│ │ AI_COMPLETE  62% │   │ llama3.1-70b 45% │             │
│ │ AI_CLASSIFY  18% │   │ mistral-lrg  30% │             │
│ │ AI_SUMMARIZE 12% │   │ snowflake-.. 20% │             │
│ │ AI_EXTRACT    8% │   │ other         5% │             │
│ └──────────────────┘   └──────────────────┘             │
┌─────────────────────────────────────────────────────────┐
│ [Expandable: Daily detail table]                        │
└─────────────────────────────────────────────────────────┘
```
### Queries

```sql
-- Headline metrics
SELECT
    ROUND(SUM(CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(DISTINCT USER_ID) AS ACTIVE_USERS,
    COUNT(DISTINCT FUNCTION_NAME) AS FUNCTIONS_USED,
    COUNT(DISTINCT QUERY_ID) AS TOTAL_QUERIES
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP());

-- Daily trend
SELECT
    DATE_TRUNC('day', START_TIME) AS USAGE_DATE,
    FUNCTION_NAME,
    SUM(CREDITS) AS DAILY_CREDITS,
    COUNT(DISTINCT QUERY_ID) AS QUERY_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 1;

-- By function
SELECT FUNCTION_NAME, ROUND(SUM(CREDITS), 2) AS TOTAL_CREDITS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 2 DESC;

-- By model
SELECT MODEL_NAME, ROUND(SUM(CREDITS), 2) AS TOTAL_CREDITS
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY
WHERE START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 2 DESC;
```

---

## Page 2: AI Top Users (`app_pages/ai_top_users.py`)

### Purpose
Identify the highest AI Functions consumers. Show per-user breakdown with
function/model detail and token usage.

### UI Layout

```
┌─────────────────────────────────────────────────────────┐
│ AI Functions Top Users                                  │
┌─────────────────────────────────────────────────────────┐
│ [Time Period v]  [Top N: 10 v]                          │
┌─────────────────────────────────────────────────────────┐
│ User      │ Credits │ Queries │ Top Function            │
│───────────┼─────────┼─────────┼─────────────────────────│
│ ALICE     │  45.2   │   312   │ AI_COMPLETE             │
│ BOB       │  32.1   │   189   │ AI_CLASSIFY             │
│ CHARLIE   │  18.7   │    94   │ AI_COMPLETE             │
┌─────────────────────────────────────────────────────────┐
│ [Bar chart: Top N users by credits]                     │
┌─────────────────────────────────────────────────────────┐
│ [Expandable: User detail by function]                   │
└─────────────────────────────────────────────────────────┘
```

### Queries

```sql
-- Top users
-- Token counts are in the METRICS JSON column: [{"key":{"metric":"total","unit":"tokens"},"value":N}]
SELECT
    u.NAME AS USER_NAME,
    u.EMAIL,
    ROUND(SUM(h.CREDITS), 2) AS TOTAL_CREDITS,
    COUNT(DISTINCT h.QUERY_ID) AS QUERY_COUNT,
    SUM(m.VALUE:value::NUMBER) AS TOTAL_TOKENS,
    MODE(h.FUNCTION_NAME) AS TOP_FUNCTION,
    MODE(h.MODEL_NAME) AS TOP_MODEL
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY h
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON h.USER_ID = u.USER_ID,
    LATERAL FLATTEN(INPUT => h.METRICS) m
WHERE h.START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
  AND m.VALUE:key:unit::STRING = 'tokens'
GROUP BY u.NAME, u.EMAIL
ORDER BY TOTAL_CREDITS DESC
LIMIT :top_n;

-- Per-user function breakdown (for drill-down)
SELECT
    u.NAME AS USER_NAME,
    h.FUNCTION_NAME,
    h.MODEL_NAME,
    ROUND(SUM(h.CREDITS), 2) AS CREDITS,
    COUNT(DISTINCT h.QUERY_ID) AS QUERIES
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY h
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON h.USER_ID = u.USER_ID
WHERE h.START_TIME >= DATEADD('day', -:days, CURRENT_TIMESTAMP())
  AND u.NAME = :selected_user
GROUP BY u.NAME, h.FUNCTION_NAME, h.MODEL_NAME
ORDER BY CREDITS DESC;
```

---

## Page 3: AI Budgets (`app_pages/ai_budgets.py`)

### Purpose
Create and manage native Snowflake Shared Resource Budgets for AI Functions.
Provides a UI for budget lifecycle management, user tagging, and spending visibility.

### UI Layout

```
┌─────────────────────────────────────────────────────────────┐
│ AI Budgets (Shared Resources)                               │
┌─────────────────────────────────────────────────────────────┘
│ ℹ️ Budgets track spending by tagged user groups and alert    │
│    when limits are exceeded. They do not hard-block usage.  │
┌─────────────────────────────────────────────────────────────┐
│ Existing Budgets                                            │
│ Budget      │ Limit │ Spent │ % Used │ Resources           │
│─────────────┼───────┼───────┼────────┼─────────────────────│
│ eng_budget  │ 5000  │ 2340  │  47%   │ AI FUNCTION         │
│ finance_bgt │ 1000  │  450  │  45%   │ AI FUNCTION         │
│ ds_budget   │ 3000  │ 2890  │  96%   │ AI FUNC+AGENT       │
┌─────────────────────────────────────────────────────────────┐
│ 💡 Suggested Budgets (based on last 3 months)                │
│ Group        │ Peak Month │ Avg Month │ Suggested ×1.2      │
│──────────────┼────────────┼───────────┼─────────────────────│
│ ENGINEERING  │  4,120     │  3,540    │  4,944              │
│ DATA_SCIENCE │  2,680     │  2,210    │  3,216              │
│ FINANCE      │    890     │    720    │  1,068              │
│ (untagged)   │  1,450     │  1,100    │  1,740              │
│ Suggested = peak monthly spend × 1.2 (20% headroom)        │
┌─────────────────────────────────────────────────────────────┐
│ Create New Budget                                           │
│ Database.Schema: [COST_MANAGEMENT.BUDGETS v]                │
│ Budget Name: [_______________]                              │
│ Team/Group: [v ENGINEERING]                                 │
│ Monthly Limit (credits): [4944] ← suggested                │
│ Resources: ☑ AI Functions  ☐ Cortex Agents                  │
│ [Create Budget]                                             │
┌─────────────────────────────────────────────────────────────┐
│ Tag Users                                                   │
│ User: [v select user]  Tag: [v TEAM]  Value: [___]         │
│ [Apply Tag]                                                 │
┌─────────────────────────────────────────────────────────────┐
│ Link Tags to Budget                                         │
│ Budget: [v select budget]  Tag: [v tag]  Value: [___]       │
│ [Link Tag to Budget]                                        │
┌─────────────────────────────────────────────────────────────┐
│ Current User Tags                                           │
│ User    │ Tag          │ Value        │ Budget              │
│─────────┼──────────────┼──────────────┼─────────────────────│
│ ALICE   │ TEAM         │ ENGINEERING  │ eng_budget          │
│ BOB     │ TEAM         │ DATA_SCIENCE │ ds_budget           │
│ CHARLIE │ TEAM         │ FINANCE      │ finance_bgt         │
│ DAVE    │ (untagged)   │ —            │ (none)              │
└─────────────────────────────────────────────────────────────┘
```

### Budget Suggestion Query

```sql
-- Calculate suggested budget per tagged group: peak monthly spend × 1.2
WITH monthly_spend AS (
    SELECT
        COALESCE(
            SYSTEM$GET_TAG('COST_MANAGEMENT.TAGS.TEAM', u.NAME, 'USER'),
            '(untagged)'
        ) AS GROUP_NAME,
        DATE_TRUNC('month', h.START_TIME) AS USAGE_MONTH,
        SUM(h.CREDITS) AS MONTHLY_CREDITS
    FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY h
    JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON h.USER_ID = u.USER_ID
    WHERE h.START_TIME >= DATEADD('month', -3, DATE_TRUNC('month', CURRENT_TIMESTAMP()))
      AND h.START_TIME < DATE_TRUNC('month', CURRENT_TIMESTAMP())
    GROUP BY 1, 2
)
SELECT
    GROUP_NAME,
    ROUND(MAX(MONTHLY_CREDITS), 0) AS PEAK_MONTH_CREDITS,
    ROUND(AVG(MONTHLY_CREDITS), 0) AS AVG_MONTH_CREDITS,
    ROUND(MAX(MONTHLY_CREDITS) * 1.2, 0) AS SUGGESTED_LIMIT
FROM monthly_spend
GROUP BY 1
ORDER BY SUGGESTED_LIMIT DESC;
```

The app pre-fills the "Monthly Limit" field with the suggested value when a
team/group is selected in the Create Budget form. The suggestion uses peak month
(not average) as the baseline — this avoids false alerts from normal usage spikes,
with the 20% buffer covering organic growth.

### Key Operations

```sql
-- List existing budgets
SHOW BUDGETS;

-- Get budget spending status
CALL db.schema.budget_name!GET_BUDGET_SCOPE();

-- Create budget
CREATE BUDGET IF NOT EXISTS db.schema.eng_budget;
ALTER BUDGET db.schema.eng_budget SET SPENDING_LIMIT = 5000;

-- Add AI Functions as shared resource
CALL db.schema.eng_budget!ADD_SHARED_RESOURCE('AI FUNCTION');

-- Tag users
ALTER USER alice SET TAG COST_MANAGEMENT.TAGS.TEAM = 'ENGINEERING';

-- Link user tags to budget
CALL db.schema.eng_budget!SET_USER_TAGS(
  [[(SELECT SYSTEM$REFERENCE('TAG', 'COST_MANAGEMENT.TAGS.TEAM', 'SESSION', 'APPLYBUDGET')),
    'ENGINEERING']],
  'UNION'
);

-- View budget scope
CALL db.schema.eng_budget!GET_BUDGET_SCOPE();

-- Check available shared resource candidates
SELECT SYSTEM$SHOW_BUDGET_SHARED_RESOURCE_CANDIDATES();

-- View tagged users
SELECT
    u.NAME AS USER_NAME,
    SYSTEM$GET_TAG('COST_MANAGEMENT.TAGS.TEAM', u.NAME, 'USER') AS TEAM_TAG
FROM SNOWFLAKE.ACCOUNT_USAGE.USERS u
WHERE u.DELETED_ON IS NULL
ORDER BY u.NAME;
```
