/*
 * FrostGate Environment Setup
 * Creates the database, schema, and Streamlit app required for FrostGate.
 *
 * INSTRUCTIONS:
 * 1. Set the variables below to match your environment.
 * 2. Run this script as ACCOUNTADMIN (or a role with CREATE DATABASE, CREATE WAREHOUSE, etc.).
 * 3. Upload app source files to the stage, then the CREATE STREAMLIT will reference them.
 */

/* ============================================================
 * CONFIGURATION — Update these to match your environment
 * ============================================================ */
USE ROLE ACCOUNTADMIN;

SET FROSTGATE_WAREHOUSE = 'FROSTGATE_WH'; -- Create a new warehouse or replace with an existing one (e.g., 'MY_WH')
SET FROSTGATE_COMPUTE_POOL = 'SYSTEM_COMPUTE_POOL_CPU'; -- Default system compute pool provisioned by Snowflake in all accounts

/* ============================================================
 * DATABASE & SCHEMA
 * ============================================================ */

/* Create the top-level database for all FrostGate objects. */
CREATE DATABASE IF NOT EXISTS FROSTGATE
    COMMENT = 'Database for FrostGate — the Cortex Code AI credit usage limit manager.';

/* Create the schema where the Streamlit app and its supporting objects reside. */
CREATE OR ALTER SCHEMA FROSTGATE.APP
    COMMENT = 'Schema for the FrostGate Streamlit application.';

/* ============================================================
 * WAREHOUSE
 * ============================================================ */

CREATE WAREHOUSE IF NOT EXISTS IDENTIFIER($FROSTGATE_WAREHOUSE)
    WAREHOUSE_SIZE = 'SMALL'
    GENERATION = '2'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    MIN_CLUSTER_COUNT = 1
    MAX_CLUSTER_COUNT = 3
    SCALING_POLICY = 'STANDARD'
    ENABLE_QUERY_ACCELERATION = TRUE
    QUERY_ACCELERATION_MAX_SCALE_FACTOR = 2
    COMMENT = 'Gen2 multi-cluster query warehouse for FrostGate Streamlit app.';

/* ============================================================
 * COMPUTE POOL (Container Runtime)
 * The default is SYSTEM_COMPUTE_POOL_CPU, provided by Snowflake
 * for all accounts. Create your own only if you need custom sizing.
 * ============================================================ */

-- Uncomment below to create a dedicated compute pool instead:
-- CREATE COMPUTE POOL IF NOT EXISTS IDENTIFIER($FROSTGATE_COMPUTE_POOL)
--     MIN_NODES = 1
--     MAX_NODES = 1
--     INSTANCE_FAMILY = CPU_X64_XS;

/* ============================================================
 * STAGE (App Source Files)
 * ============================================================ */

CREATE STAGE IF NOT EXISTS FROSTGATE.APP.SOURCE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Internal stage for FrostGate app source files.';

/*
 * Upload app files to the stage using Snowflake CLI:
 *
 *   snow stage copy frost-gate/ @FROSTGATE.APP.SOURCE/ --overwrite --no-auto-compress --recursive
 */

/* ============================================================
 * STREAMLIT APP
 * ============================================================ */

CREATE STREAMLIT IF NOT EXISTS FROSTGATE.APP.FROSTGATE
    FROM '@FROSTGATE.APP.SOURCE'
    MAIN_FILE = 'streamlit_app.py'
    TITLE = 'FrostGate — Cortex Code AI Credit Limit Manager'
    QUERY_WAREHOUSE = $FROSTGATE_WAREHOUSE
    COMPUTE_POOL = $FROSTGATE_COMPUTE_POOL
    RUNTIME_NAME = 'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'
    COMMENT = 'FrostGate — Cortex Code AI Credit Usage Limit Manager';
