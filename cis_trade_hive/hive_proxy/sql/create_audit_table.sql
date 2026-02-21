-- =============================================================================
-- Hive Proxy Audit Table
-- Database: mrw_ima
-- =============================================================================

-- Create audit table for REST Proxy operations
CREATE TABLE IF NOT EXISTS mrw_ima.hive_proxy_audit (
    audit_id        STRING      COMMENT 'Unique audit record ID',
    operation       STRING      COMMENT 'Operation type: INSERT, UPDATE, DELETE, SOFT_DELETE, HARD_DELETE',
    database_name   STRING      COMMENT 'Target database name',
    table_name      STRING      COMMENT 'Target table name',
    record_id       STRING      COMMENT 'Primary key of affected record',
    old_values      STRING      COMMENT 'JSON of old values (for UPDATE/DELETE)',
    new_values      STRING      COMMENT 'JSON of new values (for INSERT/UPDATE)',
    performed_by    STRING      COMMENT 'Username who performed the operation',
    ip_address      STRING      COMMENT 'IP address of the client',
    performed_at    TIMESTAMP   COMMENT 'Timestamp of operation',
    success         BOOLEAN     COMMENT 'Whether operation succeeded',
    error_message   STRING      COMMENT 'Error message if failed',
    elapsed_ms      INT         COMMENT 'Operation duration in milliseconds'
)
COMMENT 'Audit log for Hive REST Proxy operations'
STORED AS ORC
TBLPROPERTIES (
    'transactional'='true',
    'orc.compress'='SNAPPY'
);

-- Verify table created
DESCRIBE FORMATTED mrw_ima.hive_proxy_audit;
