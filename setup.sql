/*
 * FrostGate Environment Setup
 * Creates the database and schema required for the FrostGate Streamlit application.
 */

/* Create the top-level database for all FrostGate objects. */
CREATE DATABASE IF NOT EXISTS FROSTGATE
    COMMENT = 'Database for FrostGate — the Cortex Code credit usage limit manager.';

/* Create the schema where the Streamlit app and its supporting objects reside. */
CREATE OR ALTER SCHEMA FROSTGATE.APP
    COMMENT = 'Schema for the FrostGate Streamlit application.';
