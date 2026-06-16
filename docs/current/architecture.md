# Architecture: FrostGate Current State

## System Architecture

```
┌───────────────────────────────────────────────────────────────┐
│ FrostGate Streamlit App (SPCS)                                │
│ FROSTGATE.APP.FROST_GATE                                      │
│                                                               │
│ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐     │
│ │   Home    │ │ Dashboard │ │ Top Users │ │ Account   │     │
│ │           │ │           │ │           │ │ Limits    │     │
│ └───────────┘ └───────────┘ └───────────┘ └───────────┘     │
│ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐     │
│ │   User    │ │   Bulk    │ │ Interface │ │   Logs    │     │
│ │  Limits   │ │  Update   │ │  Access   │ │           │     │
│ └───────────┘ └───────────┘ └───────────┘ └───────────┘     │
│ ┌───────────┐ ┌───────────┐                                  │
│ │   FAQs    │ │    SQL    │                                  │
│ │           │ │ Reference │                                  │
│ └───────────┘ └───────────┘                                  │
│        │                                                      │
│ ┌──────┴──────────────────────────────────────────────────┐   │
│ │ common.py (shared utilities)                            │   │
│ │ • PARAMS dict (3 surface parameters)                    │   │
│ │ • USAGE_VIEWS dict (3 ACCOUNT_USAGE views)              │   │
│ │ • TIME_PERIODS dict (7/14/30/60/90/365 days)            │   │
│ │ • fetch_params_async() — parallel param fetching        │   │
│ │ • apply_limit_action() — ALTER ACCOUNT/USER SET/UNSET   │   │
│ │ • get_user_list() — cached 24h user list                │   │
│ │ • get_users_df() — user details DataFrame               │   │
│ │ • display_limit_value() — human-readable formatting     │   │
│ └─────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────────┐
│ Snowflake Backend                                             │
│                                                               │
│ ┌─────────────────────────────────────────────────────┐       │
│ │ ACCOUNT_USAGE Views (Read-only)                     │       │
│ │                                                     │       │
│ │ • CORTEX_CODE_CLI_USAGE_HISTORY                     │       │
│ │ • CORTEX_CODE_DESKTOP_USAGE_HISTORY                 │       │
│ │ • CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY               │       │
│ │ • USERS                                             │       │
│ │ • GRANTS_TO_USERS                                   │       │
│ │ • TAG_REFERENCES                                    │       │
│ └─────────────────────────────────────────────────────┘       │
│                                                               │
│ ┌─────────────────────────────────────────────────────┐       │
│ │ Account Parameters (Read/Write)                     │       │
│ │                                                     │       │
│ │ • ALTER ACCOUNT SET/UNSET <param>                   │       │
│ │ • ALTER USER SET/UNSET <param>                      │       │
│ │ • ALTER USER SET ALLOWED_INTERFACES                 │       │
│ │ • SHOW PARAMETERS LIKE ... IN ACCOUNT               │       │
│ │ • SHOW PARAMETERS LIKE ... IN USER                  │       │
│ │ • SHOW USERS / DESCRIBE USER                        │       │
│ │ • SHOW ROLES                                        │       │
│ └─────────────────────────────────────────────────────┘       │
└───────────────────────────────────────────────────────────────┘
```

## Data Flow

### Reading Limits (SHOW PARAMETERS)

```
SHOW PARAMETERS LIKE 'CORTEX_CODE_%' IN ACCOUNT
SHOW PARAMETERS LIKE 'CORTEX_CODE_%' IN USER "username"
         │
         ├── value: the credit limit (-1=unlimited, 0=blocked, N=credits/day)
         ├── level: ACCOUNT, USER, or DEFAULT
         └── key: the parameter name
```

### Writing Limits (ALTER)

```
User selects action in form
         │
         ├── "Set limit"      → ALTER <target> SET <param> = N
         ├── "Set unlimited"  → ALTER <target> SET <param> = -1
         ├── "Block usage"    → ALTER <target> SET <param> = 0
         └── "Unset"          → ALTER <target> UNSET <param>

Where <target> = ACCOUNT | USER "username"
```

### Usage Monitoring (ACCOUNT_USAGE)

```
CORTEX_CODE_{CLI|DESKTOP|SNOWSIGHT}_USAGE_HISTORY
         │
         ├── USER_NAME — who consumed credits
         ├── TOKEN_CREDITS — estimated AI credits consumed
         ├── USAGE_TIME — when the usage occurred
         │
         ├── GROUP BY USER_NAME → Top users ranking
         ├── GROUP BY DATE(USAGE_TIME) → Daily trends
         ├── GROUP BY DATE_TRUNC('month') → MoM growth
         └── Pareto analysis (cumulative % of total)
```

### Interface Access (DESCRIBE USER + ALTER USER)

```
DESCRIBE USER "username"
         │
         └── property = ALLOWED_INTERFACES → current setting

ALTER USER "username" SET ALLOWED_INTERFACES = ('value1', 'value2')
ALTER USER "username" UNSET ALLOWED_INTERFACES  (reverts to ALL)
```

## Async Execution Pattern

All pages follow this pattern for non-blocking queries:

```python
# Submit multiple queries in parallel
job1 = session.sql("...").collect_nowait()
job2 = session.sql("...").collect_nowait()
job3 = session.sql("...").collect_nowait()

# Collect results (blocks until each completes)
result1 = job1.result()
result2 = job2.result()
result3 = job3.result()
```

The Top Users page submits **12 parallel queries** (4 per surface x 3 surfaces):
- Top 20 users by credits
- Daily credit trends for top 10
- Pareto analysis (cumulative %)
- Month-over-month growth rates

## Caching Strategy

| Cache Target | TTL | Purpose |
|-------------|-----|---------|
| `get_user_list()` | 24 hours | User dropdown options |
| `fetch_top_users()` | 30 min | Top users + trends + growth data |
| `get_user_details()` | 24 hours | User profile info |
| `fetch_user_usage()` | 30 min | Per-user usage stats |

## File Structure

```
frost-gate/
├── streamlit_app.py          # Entry point: session, auth check, navigation
├── snowflake.yml             # Deployment config (SPCS, compute pool, warehouse)
├── pyproject.toml            # Python dependencies
├── .streamlit/config.toml    # Streamlit theme config
└── app_pages/
    ├── common.py             # Shared constants, utilities, caching functions
    ├── home.py               # Welcome/feature overview
    ├── dashboard.py          # Usage charts and metrics
    ├── top_users.py          # Top consumers + Pareto + MoM growth
    ├── account_limits.py     # Account-level limit management
    ├── user_limits.py        # Per-user limit overrides
    ├── bulk_update.py        # Multi-user batch updates
    ├── interface_access.py   # ALLOWED_INTERFACES management
    ├── logs.py               # App log viewer
    ├── faq.py                # FAQs
    └── sql_reference.py      # SQL reference documentation
```

## Deployment Config

```yaml
definition_version: 2
entities:
  streamlit_app:
    type: streamlit
    identifier:
      database: FROSTGATE
      schema: APP
      name: FROST_GATE
    query_warehouse: FROSTGATE_WH
    compute_pool: SYSTEM_COMPUTE_POOL_CPU
    run_mode: SpcsOnly
    execute_as: OWNER
```
