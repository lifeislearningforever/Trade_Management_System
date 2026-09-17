-- ================================================================
-- Hive DDL for Audit Log Table
-- Database: cis
-- Storage: TEXT format with pipe delimiter
-- Design: Follows SOLID principles for comprehensive audit trail
-- ================================================================

USE cis;

-- Drop existing table if exists
DROP TABLE IF EXISTS cis_audit_log;

-- ================================================================
-- Table: cis_audit_log
-- Comprehensive audit trail for all system actions
-- ================================================================

CREATE TABLE cis_audit_log (
  audit_id              BIGINT      COMMENT 'Unique audit entry ID (auto-increment simulation)',
  audit_timestamp       STRING      COMMENT 'Timestamp when action occurred (ISO 8601 format)',

  -- User Information
  user_id               STRING      COMMENT 'User ID who performed the action',
  username              STRING      COMMENT 'Username who performed the action',
  user_email            STRING      COMMENT 'User email address',

  -- Action Information
  action_type           STRING      COMMENT 'Type of action (CREATE, READ, UPDATE, DELETE, LOGIN, LOGOUT, EXPORT, IMPORT)',
  action_category       STRING      COMMENT 'Category (DATA, AUTH, ADMIN, REPORT, SYSTEM)',
  action_description    STRING      COMMENT 'Human-readable description of the action',

  -- Entity Information
  entity_type           STRING      COMMENT 'Type of entity affected (PORTFOLIO, TRADE, UDF, USER, etc.)',
  entity_id             STRING      COMMENT 'ID of the specific entity affected',
  entity_name           STRING      COMMENT 'Name/description of the entity',

  -- Change Tracking
  field_name            STRING      COMMENT 'Specific field that changed (for UPDATE actions)',
  old_value             STRING      COMMENT 'Previous value (before action)',
  new_value             STRING      COMMENT 'New value (after action)',

  -- Request Information
  request_method        STRING      COMMENT 'HTTP method (GET, POST, PUT, DELETE, PATCH)',
  request_path          STRING      COMMENT 'URL path of the request',
  request_params        STRING      COMMENT 'Request parameters (JSON format)',

  -- Result Information
  status                STRING      COMMENT 'Action status (SUCCESS, FAILURE, PARTIAL)',
  status_code           INT         COMMENT 'HTTP status code or custom code',
  error_message         STRING      COMMENT 'Error message if action failed',
  error_traceback       STRING      COMMENT 'Error traceback for debugging',

  -- Context Information
  session_id            STRING      COMMENT 'Session identifier',
  ip_address            STRING      COMMENT 'IP address of the request',
  user_agent            STRING      COMMENT 'Browser/client user agent string',

  -- Additional Metadata
  module_name           STRING      COMMENT 'Django app/module name',
  function_name         STRING      COMMENT 'Function/view name that triggered audit',
  duration_ms           BIGINT      COMMENT 'Action duration in milliseconds',
  tags                  STRING      COMMENT 'Additional tags (comma-separated)',
  metadata              STRING      COMMENT 'Additional metadata (JSON format)',

  -- Partitioning
  audit_date            STRING      COMMENT 'Date of audit (YYYY-MM-DD) for partitioning'
)
COMMENT 'Comprehensive audit log for all system actions - Follows SOLID principles'
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;

-- ================================================================
-- Create indexes (if supported by your Hive version)
-- Note: Hive doesn't support traditional indexes, but we can create
-- materialized views or use bucketing/partitioning for performance
-- ================================================================

-- Show table structure
DESCRIBE EXTENDED cis_audit_log;
