-- ================================================================
-- Kudu/Impala Tables for UDF Audit Trail
-- Database: gmp_cis
-- ================================================================

-- 1. UDF Audit Log Table
-- Tracks all UDF definition changes (CREATE, UPDATE, DELETE)
-- ================================================================
CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_audit_log (
    audit_id BIGINT,
    audit_timestamp TIMESTAMP,
    user_id STRING,
    username STRING,
    action_type STRING,  -- CREATE, UPDATE, DELETE
    udf_id BIGINT,
    field_name STRING,
    label STRING,
    entity_type STRING,
    changes STRING,  -- JSON string of changes
    action_description STRING,
    ip_address STRING,
    user_agent STRING,
    session_id STRING,
    status STRING,  -- SUCCESS, FAILURE
    error_message STRING,
    audit_date STRING,  -- Partition key YYYY-MM-DD
    PRIMARY KEY (audit_id, audit_timestamp)
)
PARTITION BY HASH(audit_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');


-- 2. UDF Value Audit Log Table
-- Tracks all UDF value changes for entities
-- ================================================================
CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_value_audit_log (
    audit_id BIGINT,
    audit_timestamp TIMESTAMP,
    user_id STRING,
    username STRING,
    action_type STRING,  -- CREATE, UPDATE, DELETE
    udf_id BIGINT,
    field_name STRING,
    entity_type STRING,
    entity_id BIGINT,
    old_value STRING,
    new_value STRING,
    value_type STRING,  -- TEXT, NUMBER, DATE, BOOLEAN, etc.
    action_description STRING,
    ip_address STRING,
    session_id STRING,
    status STRING,
    audit_date STRING,  -- Partition key YYYY-MM-DD
    PRIMARY KEY (audit_id, audit_timestamp)
)
PARTITION BY HASH(audit_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');


-- 3. General Audit Log Table (for all modules)
-- Migrated from Hive cis_audit_log
-- ================================================================
CREATE TABLE IF NOT EXISTS gmp_cis.cis_audit_log (
    audit_id BIGINT,
    audit_timestamp TIMESTAMP,
    user_id STRING,
    username STRING,
    user_email STRING,
    action_type STRING,  -- CREATE, UPDATE, DELETE, VIEW, LOGIN, LOGOUT
    action_category STRING,  -- DATA, SECURITY, SYSTEM, CONFIG
    action_description STRING,
    entity_type STRING,  -- PORTFOLIO, TRADE, UDF, ACL, USER, etc.
    entity_id STRING,
    entity_name STRING,
    field_name STRING,
    old_value STRING,
    new_value STRING,
    request_method STRING,  -- GET, POST, PUT, DELETE
    request_path STRING,
    request_params STRING,
    status STRING,  -- SUCCESS, FAILURE
    status_code INT,  -- HTTP status code
    error_message STRING,
    error_traceback STRING,
    session_id STRING,
    ip_address STRING,
    user_agent STRING,
    module_name STRING,
    function_name STRING,
    duration_ms INT,
    tags STRING,  -- JSON array of tags
    metadata STRING,  -- JSON object for additional data
    audit_date STRING,  -- Partition key YYYY-MM-DD
    PRIMARY KEY (audit_id, audit_timestamp)
)
PARTITION BY HASH(audit_id) PARTITIONS 16
STORED AS KUDU
TBLPROPERTIES ('kudu.num_tablet_replicas' = '1');


-- ================================================================
-- Indexes and Views (Impala doesn't support indexes, use partitioning)
-- ================================================================

-- View for recent UDF audit logs
CREATE VIEW IF NOT EXISTS gmp_cis.v_recent_udf_audits AS
SELECT
    audit_id,
    audit_timestamp,
    username,
    action_type,
    field_name,
    entity_type,
    changes,
    status,
    audit_date
FROM gmp_cis.cis_udf_audit_log
ORDER BY audit_timestamp DESC
LIMIT 1000;


-- View for recent UDF value changes
CREATE VIEW IF NOT EXISTS gmp_cis.v_recent_udf_value_changes AS
SELECT
    audit_id,
    audit_timestamp,
    username,
    action_type,
    field_name,
    entity_type,
    entity_id,
    old_value,
    new_value,
    status,
    audit_date
FROM gmp_cis.cis_udf_value_audit_log
ORDER BY audit_timestamp DESC
LIMIT 1000;


-- View for audit statistics by day
CREATE VIEW IF NOT EXISTS gmp_cis.v_audit_stats_by_day AS
SELECT
    audit_date,
    entity_type,
    action_type,
    COUNT(*) as action_count
FROM gmp_cis.cis_audit_log
GROUP BY audit_date, entity_type, action_type;
