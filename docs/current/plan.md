# FrostGate: Current App Overview

## What It Is

FrostGate is a Streamlit-in-Snowflake app that manages **Cortex Code daily AI credit limits**
across three surfaces (CLI, Desktop, Snowsight) at both account and per-user levels.
It also provides usage dashboards, top-user analysis, bulk user management, and
interface access controls.

## Surfaces Managed

| Surface | Parameter | Usage View |
|---------|-----------|------------|
| CLI | `CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER` | `CORTEX_CODE_CLI_USAGE_HISTORY` |
| Desktop | `CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER` | `CORTEX_CODE_DESKTOP_USAGE_HISTORY` |
| Snowsight | `CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER` | `CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY` |

## How Limits Work

- **Account-level limits** set the default daily AI credit cap for all users on each surface
- **User-level limits** override the account default for specific users
- A value of `-1` means unlimited (no cap enforced)
- A value of `0` blocks usage entirely
- Snowflake enforces limits automatically via a rolling 24-hour window

## Pages

| Page | Purpose |
|------|---------|
| Home | Welcome page with feature overview |
| Usage Dashboard | Credit consumption charts by surface, daily trends, monthly totals |
| Top Users | Top 20 consumers, Pareto analysis, MoM growth, daily trends |
| Account Limits | View/set account-level defaults for all 3 surfaces |
| User Limits | View/set per-user overrides, usage comparison vs account average |
| Bulk User Update | Apply same limits to multiple users, override scanner |
| Interface Access | Manage ALLOWED_INTERFACES per user (single + bulk) |
| Logs | View app logs |
| FAQs | Help and documentation |
| SQL Reference | Reference SQL for manual administration |

## Key Capabilities

- Async query execution throughout (all queries use `collect_nowait()`)
- Parallel queries (up to 12 concurrent per page load)
- Caching: dashboard data (30 min TTL), user lists (24h TTL)
- Role/tag-based filtering for bulk operations
- Pareto (80/20) analysis to identify power users
- Month-over-month growth rate tracking
- User-vs-account average comparison metrics
- Self-protection (cannot modify own interface access)
- Confirmation dialogs for destructive operations

## Deployment

- Runs on Container Runtime (SPCS) via `SYSTEM_COMPUTE_POOL_CPU`
- Deployed as a Streamlit app object: `FROSTGATE.APP.FROST_GATE`
- Requires ACCOUNTADMIN role
- Query warehouse: `FROSTGATE_WH`
