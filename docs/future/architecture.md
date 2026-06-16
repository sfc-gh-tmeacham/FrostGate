# Architecture: AI Functions Cost Controls (Monitoring + Native Budgets)

> **Note:** This describes additive pages being added to the existing FrostGate app.
> The current Cortex Code pages remain unchanged. See `docs/current/architecture.md`
> for the existing app architecture.

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│ FrostGate Streamlit App                                 │
│                                                         │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐   │
│ │ AI Functions  │ │  AI Budgets   │ │ AI Functions  │   │
│ │  Dashboard    │ │   Manager     │ │  Top Users    │   │
│ └───────┬───────┘ └───────┬───────┘ └───────┬───────┘   │
│         │                 │                 │           │
│ ┌───────┴─────────────────┴─────────────────┴───────┐   │
│ │          common_ai.py (shared utilities)          │   │
│ └───────────────────────────┬───────────────────────────┐   │
│                             │                           │
│ ┌───────────────────────────┴───────────────────────────┘   │
│ │          common.py (existing shared utils)          │   │
│ └───────────────────────────────────────────────────────┐   │
└─────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│ Snowflake Backend                                       │
│                                                         │
│ ┌───────────────────────────────────────────┐           │
│ │ ACCOUNT_USAGE Views (Read-only)           │           │
│ │                                           │           │
│ │ - CORTEX_AI_FUNCTIONS_USAGE_HISTORY       │           │
│ │ - USERS                                   │           │
│ │ - QUERY_HISTORY                           │           │
│ └───────────────────────────────────────────┘           │
│                                                         │
│ ┌───────────────────────────────────────────┐           │
│ │ Native Budget Objects                     │           │
│ │                                           │           │
│ │ - Custom budget instances                 │           │
│ │ - Tags on users (cost_center, team)       │           │
│ │ - Notification integrations               │           │
│ └───────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
```

## Data Flow

### Monitoring Flow (Read-Only)

```
CORTEX_AI_FUNCTIONS_USAGE_HISTORY
         │
         ├── GROUP BY FUNCTION_NAME, MODEL_NAME -> Function breakdown
         ├── GROUP BY USER_ID -> JOIN USERS -> Per-user consumption
         ├── GROUP BY DATE_TRUNC('day', START_TIME) -> Daily trends
         ├── GROUP BY WAREHOUSE_ID -> Warehouse attribution
         └── SUM(CREDITS) WHERE START_TIME >= month_start -> Monthly totals
```

### Budget Flow

```
┌──────────────┐     ┌──────────────────────────+     ┌──────────────────+
│ ALTER USER   │──▶| User tagged with         |──▶| Budget tracks    │
│ SET TAG      │     │ cost_center = 'TEAM_X'   │     │ usage by tagged  │
└──────────────┘     └──────────────────────────┘     │ users only       │
                                                      └──────────────────┘
                                                               │
                                                               ▼
                                                      ┌──────────────────┐
                                                      │ Budget alert when│
                                                      │ spending_limit   │
                                                      │ exceeded         │
                                                      └──────────────────┘
```

### Budget Management Flow

```
┌──────────────────┐     ┌──────────────────────────────┐
│ FrostGate UI     │     │ Snowflake Budget API         │
│                  │     │                              │
│ Create Budget ───│──▶│ CREATE BUDGET                │
│ Set Limit     ───│──▶│ ALTER BUDGET SET             │
│                  │     │   SPENDING_LIMIT             │
│ Add Resource  ───│──▶| budget!ADD_SHARED_RESOURCE   │
│                  │     │   ('AI FUNCTION')            │
│ Tag Users     ───│──▶│ ALTER USER SET TAG           │
│ Link Tags     ───│──▶│ budget!SET_USER_TAGS         │
│ View Status   ───│──▶│ budget!GET_BUDGET_SCOPE      │
└──────────────────┘     ┌──────────────────────────────+
```

## CORTEX_AI_FUNCTIONS_USAGE_HISTORY View Schema

| Column | Type | Description |
|--------|------|-------------|
| START_TIME | TIMESTAMP_LTZ | Start of the one-hour usage window |
| END_TIME | TIMESTAMP_LTZ | End of the one-hour usage window |
| FUNCTION_NAME | VARCHAR | AI function name (AI_COMPLETE, AI_CLASSIFY, etc.) |
| MODEL_NAME | VARCHAR | LLM model used (llama3.1-70b, mistral-large2, etc.) |
| QUERY_ID | VARCHAR | Query that invoked the function |
| WAREHOUSE_ID | NUMBER | Warehouse that ran the query |
| ROLE_NAMES | ARRAY | Roles active during execution |
| QUERY_TAG | VARCHAR | Session query tag value |
| USER_ID | NUMBER | User who ran the query |
| METRICS | VARIANT (JSON array) | Token usage metrics, e.g. `[{"key":{"metric":"total","unit":"tokens"},"value":1594}]` |
| CREDITS | FLOAT | Credits consumed in this window |
| IS_COMPLETED | BOOLEAN | TRUE only on final row of a completed query |

**Key notes:**
- Long-running queries produce multiple rows (one per hour window)
- `IS_COMPLETED = FALSE` on all rows means query is still running
- ~10 minute latency (may be as few as 5 minutes)
- Credits are per-window, so SUM(CREDITS) GROUP BY QUERY_ID gives total cost

## Integration with Existing FrostGate Architecture

### Shared Patterns to Reuse

1. **Async queries** — all pages use `collect_nowait()` for parallel query execution
2. **Caching** — `@st.cache_data(ttl=1800)` for dashboard data, `ttl=86400` for user lists
3. **Common utilities** — centralized in `common.py` (extend with `common_ai.py`)
4. **Form-based actions** — `st.form()` with confirmation for state-changing operations
5. **Metric cards** — `st.metric()` with sparklines for at-a-glance stats
6. **Error handling** — partial results shown when one query fails; exceptions stored not raised

### New Module: `common_ai.py`

```python
AI_FUNCTIONS_USAGE_VIEW = "SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY"

AI_FUNCTION_NAMES = [
    "AI_CLASSIFY", "AI_COMPLETE", "AI_EXTRACT", "AI_FILTER",
    "AI_SENTIMENT", "AI_SUMMARIZE", "AI_TRANSLATE", "AI_EMBED",
    "AI_PARSE_DOCUMENT", "AI_REDACT", "AI_SIMILARITY",
    "AI_SUMMARIZE_AGG", "AI_AGG", "AI_TRANSCRIBE",
]

BUDGET_SHARED_RESOURCES = {
    "AI Functions": "AI FUNCTION",
    "Cortex Code": "CORTEX CODE",
    "Cortex Agents": "CORTEX AGENT",
    "Snowflake Intelligence": "SNOWFLAKE INTELLIGENCE",
}
```

### Navigation Update

```python
# Addition to streamlit_app.py navigation
":material/neurology: AI Functions": [
    st.Page("app_pages/ai_dashboard.py", title="AI Usage Dashboard", icon=":material/monitoring:"),
    st.Page("app_pages/ai_top_users.py", title="AI Top Users", icon=":material/leaderboard:"),
    st.Page("app_pages/ai_budgets.py", title="AI Budgets", icon=":material/account_balance:"),
],
```

### State Management

```python
def detect_budget_state(session):
    """Detect whether budget infrastructure exists."""
    state = {"has_budgets": False, "has_tags": False}

    try:
        rows = session.sql("SHOW BUDGETS").collect()
        state["has_budgets"] = len(rows) > 0
    except:
        pass

    try:
        rows = session.sql("SHOW TAGS IN ACCOUNT").collect()
        state["has_tags"] = len(rows) > 0
    except:
        pass

    return state
```
