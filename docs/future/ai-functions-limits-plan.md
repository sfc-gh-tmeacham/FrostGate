# FrostGate Expansion: Cortex AI Functions Cost Controls

> **Note:** These are additive features — new pages added to the existing FrostGate app
> alongside all current pages. Nothing in the current app is removed or replaced.
> See `docs/current/` for the existing app documentation.

## Overview

Add new pages to FrostGate for monitoring and controlling Cortex AI Functions
(AI_COMPLETE, AI_SUMMARIZE, AI_TRANSLATE, AI_SENTIMENT, AI_CLASSIFY, AI_EXTRACT, etc.)
credit consumption — complementing the existing Cortex Code limit management pages.

## Approach: Monitoring + Native Budgets

Uses Snowflake's native **Shared Resource Budgets** combined with the
`CORTEX_AI_FUNCTIONS_USAGE_HISTORY` view to track, visualize, and alert on
AI Function spending by tagged user groups. FrostGate provides the UI to:

1. View AI Functions usage dashboards (from `CORTEX_AI_FUNCTIONS_USAGE_HISTORY`)
2. Identify top consumers by user, function, and model
3. Create/manage budgets with spending limits for AI Functions
4. Tag users into cost-center groups
5. Configure budget notifications

## Key Differences from Cortex Code Limits

| Aspect | Cortex Code | Cortex AI Functions (this feature) |
|--------|-------------|-------------------------------------|
| Native parameter | Yes (`CORTEX_CODE_*_DAILY_EST_CREDIT_LIMIT_PER_USER`) | No native per-user parameter |
| Cost control mechanism | Snowflake enforces via rolling 24h window | Shared Resource Budgets (group-level alerts) |
| Granularity | Per-surface (CLI/Desktop/Snowsight) | Per-function, per-model, per-user-group |
| Usage view | `CORTEX_CODE_*_USAGE_HISTORY` | `CORTEX_AI_FUNCTIONS_USAGE_HISTORY` |
| Latency | ~45 min | ~10 min |

## Proposed New Pages

| Page | Purpose |
|------|---------|
| AI Functions Dashboard | Credit usage by function, model, user, warehouse |
| AI Top Users | Identify highest consumers with drill-down |
| AI Budgets | Native budget creation, user tagging, spending limits |

## Phased Delivery

### Phase 1: Monitoring (Read-Only)
- AI Functions Usage Dashboard (queries `CORTEX_AI_FUNCTIONS_USAGE_HISTORY`)
- Top AI Functions consumers by user
- Daily/monthly credit trends by function, model, user

### Phase 2: Budget Management
- Budget creation UI (wraps `CREATE BUDGET` + `ADD_SHARED_RESOURCE`)
- User tagging UI (wraps `ALTER USER SET TAG`)
- Budget status and spending-vs-limit display
- Notification configuration for budget alerts

## Dependencies

- `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_AI_FUNCTIONS_USAGE_HISTORY` (GA, ~10 min latency)
- Shared Resource Budgets (GA April 2026)
- ACCOUNTADMIN or equivalent privileges
- Tag-based user grouping (`ALTER USER SET TAG`)

## Advantages of This Approach

- **Native Snowflake feature** — no custom roles, tasks, or procedures to maintain
- **No account-wide breaking changes** — does not revoke `SNOWFLAKE.CORTEX_USER` from PUBLIC
- **Supported by Snowflake** — budgets are a GA feature with built-in alerting
- **Low operational risk** — read-only monitoring in Phase 1, budget management in Phase 2
- **Group-level flexibility** — budgets can cover teams, departments, or cost centers

## Limitations

| Limitation | Impact |
|------------|--------|
| Group-level only (not per-user hard caps) | Individual users can overspend within their group's budget |
| Alerts, not hard blocks | Budget exceeding triggers notifications but doesn't revoke access |
| Requires user tagging | Users must be tagged with cost-center/team tags for budget attribution |
| ~10 min usage view latency | Near-real-time but not instant |

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Usage view 10-min latency | Inform users via UI; budgets still track total spend accurately |
| Users not tagged = not tracked by budgets | Dashboard shows untagged user spending; tagging UI makes it easy to fix |
| Budget limit exceeded before alert fires | Set conservative limits; use notification integrations for fast alerts |
