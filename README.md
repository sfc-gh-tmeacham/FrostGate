# FrostGate

[![Snowflake](https://img.shields.io/badge/Snowflake-29B5E8?logo=snowflake&logoColor=white)](https://www.snowflake.com)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Cortex Code AI Credit Usage Limit Manager**

> **This application is intended for exclusive use by Snowflake account administrators.** It requires the ACCOUNTADMIN role (or a custom role with equivalent privileges) to read usage history and modify account/user parameters.

A Streamlit-in-Snowflake application for monitoring and controlling daily AI credit consumption across Cortex Code surfaces (Snowsight, CLI, and Desktop).

## Overview

FrostGate provides Snowflake administrators with a unified interface to:

- **Monitor** daily AI credit usage with sparkline trends and configurable time periods
- **Set limits** at the account level (default for all users) or per-user level (overrides)
- **Identify power users** using Pareto analysis (80/20 rule)
- **Bulk update** limits for multiple users at once with role and tag filters
- **Track trends** including month-over-month growth and top consumer rankings

## How It Works

FrostGate does not enforce credit limits itself — it provides a UI layer on top of Snowflake's built-in credit control mechanism:

1. **Snowflake's native enforcement** — Snowflake exposes account-level and user-level parameters (e.g. `CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER`) that cap how many AI credits a user can consume per day. When the limit is reached, Snowflake blocks further Cortex Code requests until the 24-hour window resets.

2. **FrostGate reads usage data** — The app queries `SNOWFLAKE.ACCOUNT_USAGE` views to show how many credits each user has consumed across the three Cortex Code surfaces (Snowsight, CLI, Desktop).

3. **FrostGate writes limit parameters** — When an admin changes a limit through the UI, FrostGate executes `ALTER ACCOUNT SET ...` or `ALTER USER SET ...` SQL commands to update the Snowflake parameters that control enforcement.

4. **Two-tier model** — Account-level limits set the default cap for all users. Per-user overrides allow exceptions (higher or lower) for specific individuals. Unsetting a user override returns them to the account default.

```
┌─────────────────────────────────────────────────┐
│  FrostGate (UI Layer)                           │
│  ┌───────────────┐  ┌────────────────────────┐  │
│  │ Read usage    │  │ Write limits           │  │
│  │ (ACCOUNT_     │  │ (ALTER ACCOUNT/USER    │  │
│  │  USAGE views) │  │  SET parameter = N)    │  │
│  └───────┬───────┘  └───────────┬────────────┘  │
└──────────┼──────────────────────┼───────────────┘
           ▼                      ▼
┌─────────────────────────────────────────────────┐
│  Snowflake (Enforcement Layer)                  │
│  • Tracks per-user daily credit consumption     │
│  • Blocks requests when limit is exceeded       │
│  • Resets counters every 24 hours               │
└─────────────────────────────────────────────────┘
```

## Pages

| Page | Description |
|------|-------------|
| Home | Overview, system health, and key concepts |
| Usage Dashboard | Daily metrics with sparklines across all surfaces |
| Top Users | Top 20 consumers, trend charts, MoM growth, Pareto analysis |
| Account Limits | View and modify account-wide daily AI credit caps |
| User Limits | Per-user details, usage summary, and limit overrides |
| Bulk User Update | Apply changes to multiple users with role/tag filtering |
| Interface Access | Control which Snowflake interfaces (CoWork, Streamlit) users can access via ALLOWED_INTERFACES |
| Logs | View application logs from the account's event table with severity and time filtering |
| FAQs & Troubleshooting | Common questions, troubleshooting tips, and guidance for administrators |
| SQL Reference | SQL examples for manual operations |

## Quick Start

New to FrostGate? Follow these steps to set up credit controls for the first time:

1. **Check current usage** — Go to the **Usage Dashboard** to see how many AI credits are being consumed across surfaces.
2. **Set account-level limits** — Navigate to **Account Limits** and set a daily credit cap (e.g. 25 AI credits/day) for each surface. This becomes the default for all users.
3. **Identify power users** — Use the **Top Users** page to find who consumes the most credits.
4. **Grant overrides where needed** — On the **User Limits** page, set higher per-user limits for users who legitimately need more.
5. **Monitor ongoing usage** — Check the dashboard periodically to ensure limits are effective and adjust as needed.

## Requirements

- **Role**: ACCOUNTADMIN (or equivalent privileges)
- **Runtime**: Streamlit Container Runtime (Python 3.11)
- **Views Used**:
  - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_SNOWSIGHT_USAGE_HISTORY`
  - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`
  - `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_DESKTOP_USAGE_HISTORY`

## Deployment

### Option A: SQL + Snowflake CLI

Use this method if you prefer a scripted deployment or CI/CD pipeline.

1. **Clone this repository** locally:
   ```bash
   git clone <repo-url>
   cd frostgate
   ```

2. **Edit `setup.sql`** — update the configuration variables at the top:
   ```sql
   SET FROSTGATE_WAREHOUSE = 'YOUR_WAREHOUSE';
   SET FROSTGATE_COMPUTE_POOL = 'SYSTEM_COMPUTE_POOL_CPU';
   ```

3. **Run `setup.sql`** in a Snowflake worksheet (or via Snowflake CLI) as ACCOUNTADMIN. This creates the database, schema, warehouse, stage, and Streamlit object.

4. **Upload app files** to the stage using [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/index):
   ```bash
   snow stage copy frost-gate/ @FROSTGATE.APP.SOURCE/ --overwrite --no-auto-compress --recursive
   ```

5. **Access the app** — navigate to **Projects → Streamlit** in Snowsight and open `FROSTGATE`.

### Option B: Streamlit in Workspaces (Git-backed)

Use this method to develop, preview, and deploy directly from Snowsight with Git integration.

1. **Use this repository directly**, or fork/clone it to your own Git repository (GitHub, GitLab, Bitbucket, etc.).

2. **Open Snowsight** and navigate to **Workspaces**.

3. **Create a Git workspace** — click **+**, select **Git workspace**, and connect to the repository. For setup instructions, see [Setting up Snowflake to use Git](https://docs.snowflake.com/en/developer-guide/git/git-setting-up).

4. **Open `frost-gate/streamlit_app.py`** — the workspace automatically detects it as a Streamlit app and shows a **Run** button.

5. **Click Run** to preview the development app (private to you only).

6. **Create the target database and schema** where the deployed app will live:
   ```sql
   CREATE DATABASE IF NOT EXISTS FROSTGATE;
   CREATE SCHEMA IF NOT EXISTS FROSTGATE.APP;
   ```

7. **Click Deploy** in the project pane toolbar and configure:
   - **App title**: `FrostGate — Cortex Code AI Credit Limit Manager`
   - **Location**: `FROSTGATE.APP`
   - **Compute pool**: `SYSTEM_COMPUTE_POOL_CPU` (or your preferred pool)
   - **Query warehouse**: Your chosen warehouse

8. **Share the app** — add roles in the deploy dialog to grant access to other users.

For more details, see [Streamlit in Workspaces](https://docs.snowflake.com/en/developer-guide/streamlit/streamlit-in-workspaces/streamlit-in-workspaces-overview) and [Create and run a Streamlit app in a workspace](https://docs.snowflake.com/en/developer-guide/streamlit/streamlit-in-workspaces/streamlit-in-workspaces-create-run).

### Option C: Manual Workspace Upload

Use this method if you don't want to connect a Git repository to Snowflake.

1. **Clone this repository** locally:
   ```bash
   git clone <repo-url>
   ```

2. **Open Snowsight** and navigate to **Workspaces**.

3. **Create a new workspace** — click **+** and select **Workspace**.

4. **Upload the app files** — drag and drop the contents of the `frost-gate/` directory into the workspace (or use the upload button). Ensure the directory structure is preserved (`streamlit_app.py` at the root, `app_pages/` folder, etc.).

5. **Open `streamlit_app.py`** — the workspace detects it as a Streamlit app and shows a **Run** button.

6. **Click Run** to preview the development app (private to you only).

7. **Create the target database and schema** where the deployed app will live:
   ```sql
   CREATE DATABASE IF NOT EXISTS FROSTGATE;
   CREATE SCHEMA IF NOT EXISTS FROSTGATE.APP;
   ```

8. **Click Deploy** in the project pane toolbar and configure:
   - **App title**: `FrostGate — Cortex Code AI Credit Limit Manager`
   - **Location**: `FROSTGATE.APP`
   - **Compute pool**: `SYSTEM_COMPUTE_POOL_CPU` (or your preferred pool)
   - **Query warehouse**: Your chosen warehouse

9. **Share the app** — add roles in the deploy dialog to grant access to other users.

## Project Structure

```
frost-gate/
├── streamlit_app.py          # Main entry point and navigation
├── app_pages/
│   ├── common.py             # Shared constants and utility functions
│   ├── home.py               # Landing page with system health
│   ├── dashboard.py          # Usage dashboard with sparklines
│   ├── top_users.py          # Top users and Pareto analysis
│   ├── account_limits.py     # Account-level limit management
│   ├── user_limits.py        # Per-user limit management
│   ├── bulk_update.py        # Bulk user updates
│   ├── interface_access.py   # Interface access (ALLOWED_INTERFACES)
│   ├── logs.py               # Event table log viewer
│   ├── faq.py                # FAQs and troubleshooting
│   └── sql_reference.py      # SQL command reference
setup.sql                     # Database and schema creation
```

## Parameters Managed

| Parameter | Surface |
|-----------|---------|
| `CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER` | Snowsight |
| `CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER` | CLI |
| `CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER` | Desktop |

### Values

| Value | Behavior |
|-------|----------|
| `-1` | Unlimited (default) |
| `0` | Blocked |
| `> 0` | Daily AI credit cap |

### What Users See When Limited

When a user exceeds their daily credit cap, Cortex Code displays a message like this example:

> Daily credit usage limit reached (50.01 of 50.00 credits used). Your limit resets every 24 hours — please try again later or contact your Snowflake administrator to adjust the limit.

The exact values will vary based on the user's actual consumption and configured limit. This is the end-user experience that FrostGate helps administrators manage.

## Scope

FrostGate manages **Cortex Code** AI credit limits only. It does not cover Cortex AI Functions (such as `CORTEX.COMPLETE`, `CORTEX.SUMMARIZE`, etc.) which have separate billing and controls.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Disclaimer

THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

**This is not an official Snowflake product or offering.** This is an independent, community-built tool that interacts with Snowflake's documented parameters and views. It is not endorsed, supported, or maintained by Snowflake Inc. Use at your own risk.
