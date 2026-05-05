-- ============================================================================
-- DDL: Standardise timestamp columns across gmp_cis
-- ============================================================================
-- Ticket : DATE_STD_001
-- Author : CIS Team
-- Date   : 2026-05-05
--
-- Standard adopted:
--   Audit timestamps  (created_at, updated_at, etc.)  → STRING 'YYYY-MM-DD HH:MM:SS'
--   Business dates    (trade_date, price_date, etc.)  → STRING 'YYYY-MM-DD'  (no change)
--   Partition dates   (processing_date, system_date)  → STRING 'YYYYMMDD'    (no change)
--   Millisecond PKs   (trade_id, event_id)            → BIGINT               (no change)
--
-- Kudu does NOT support ALTER COLUMN type.  Each affected table is migrated
-- using the pattern:
--   1. CREATE new table  (<table>_new)
--   2. INSERT INTO new SELECT ..., from_unixtime(col/1000)  or
--                                   from_timestamp(col)     as appropriate
--   3. Rename old → _bak, new → live
--   4. Drop backup after validation (commented out — run manually)
--
-- Tables affected:
--   BIGINT → STRING : cis_equity_price_kudu, cis_equity_price_history,
--                     cis_security_kudu, cis_udf_definition, cis_udf_value,
--                     cis_corporate_action, cis_system_date
--   TIMESTAMP → STRING : cis_party, cis_user, cis_user_group,
--                         cis_group_permissions, cis_cash_flow, cis_file_upload
-- ============================================================================

USE gmp_cis;

-- ============================================================================
-- HELPER: conversion expressions used throughout
--   BIGINT ms  → STRING : from_unixtime(CAST(col AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
--   TIMESTAMP  → STRING : from_timestamp(col, 'yyyy-MM-dd HH:mm:ss')
-- ============================================================================


-- ============================================================================
-- GROUP 1: BIGINT → STRING
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1A. cis_equity_price_kudu
--     Columns: price_timestamp BIGINT, created_at BIGINT, updated_at BIGINT
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_equity_price_kudu_new
LIKE gmp_cis.cis_equity_price_kudu;

ALTER TABLE gmp_cis.cis_equity_price_kudu_new
    ALTER COLUMN price_timestamp STRING,
    ALTER COLUMN created_at      STRING,
    ALTER COLUMN updated_at      STRING;

INSERT INTO gmp_cis.cis_equity_price_kudu_new
SELECT
    currency_code,
    security_label,
    price_date,
    isin,
    main_closing_price,
    src_system,
    created_by,
    updated_by,
    from_unixtime(CAST(price_timestamp AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS price_timestamp,
    from_unixtime(CAST(created_at      AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END                                                             AS updated_at
FROM gmp_cis.cis_equity_price_kudu;

-- Rename (run after row-count validation):
-- ALTER TABLE gmp_cis.cis_equity_price_kudu     RENAME TO gmp_cis.cis_equity_price_kudu_bak;
-- ALTER TABLE gmp_cis.cis_equity_price_kudu_new RENAME TO gmp_cis.cis_equity_price_kudu;
-- DROP TABLE gmp_cis.cis_equity_price_kudu_bak;   -- run after smoke test


-- ----------------------------------------------------------------------------
-- 1B. cis_equity_price_history
--     Columns: changed_at BIGINT, price_timestamp BIGINT
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_equity_price_history_new
LIKE gmp_cis.cis_equity_price_history;

ALTER TABLE gmp_cis.cis_equity_price_history_new
    ALTER COLUMN changed_at      STRING,
    ALTER COLUMN price_timestamp STRING;

INSERT INTO gmp_cis.cis_equity_price_history_new
SELECT
    history_id,
    currency_code,
    security_label,
    price_date,
    isin,
    main_closing_price,
    src_system,
    changed_by,
    change_type,
    from_unixtime(CAST(changed_at      AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS changed_at,
    CASE WHEN price_timestamp IS NOT NULL
         THEN from_unixtime(CAST(price_timestamp AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END                                                              AS price_timestamp
FROM gmp_cis.cis_equity_price_history;

-- ALTER TABLE gmp_cis.cis_equity_price_history     RENAME TO gmp_cis.cis_equity_price_history_bak;
-- ALTER TABLE gmp_cis.cis_equity_price_history_new RENAME TO gmp_cis.cis_equity_price_history;
-- DROP TABLE gmp_cis.cis_equity_price_history_bak;


-- ----------------------------------------------------------------------------
-- 1C. cis_security_kudu
--     Columns: created_at BIGINT, updated_at BIGINT,
--              submitted_for_approval_at BIGINT, reviewed_at BIGINT
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_security_kudu_new
LIKE gmp_cis.cis_security_kudu;

ALTER TABLE gmp_cis.cis_security_kudu_new
    ALTER COLUMN created_at                 STRING,
    ALTER COLUMN updated_at                 STRING,
    ALTER COLUMN submitted_for_approval_at  STRING,
    ALTER COLUMN reviewed_at                STRING;

INSERT INTO gmp_cis.cis_security_kudu_new
SELECT
    security_id, security_name, security_short_name, isin, ticker,
    security_type, product_type, currency_code, country_code,
    exchange_code, industry, issuer_type, quoted_unquoted,
    reits_or_fund_y_n, fin_nonfin_co, status, maker_checker_status,
    created_by, updated_by, submitted_for_approval_by, reviewed_by,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at,
    CASE WHEN submitted_for_approval_at IS NOT NULL
         THEN from_unixtime(CAST(submitted_for_approval_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS submitted_for_approval_at,
    CASE WHEN reviewed_at IS NOT NULL
         THEN from_unixtime(CAST(reviewed_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS reviewed_at
FROM gmp_cis.cis_security_kudu;

-- ALTER TABLE gmp_cis.cis_security_kudu     RENAME TO gmp_cis.cis_security_kudu_bak;
-- ALTER TABLE gmp_cis.cis_security_kudu_new RENAME TO gmp_cis.cis_security_kudu;
-- DROP TABLE gmp_cis.cis_security_kudu_bak;


-- ----------------------------------------------------------------------------
-- 1D. cis_corporate_action
--     Columns: created_at BIGINT, updated_at BIGINT, performed_at BIGINT
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_corporate_action_new
LIKE gmp_cis.cis_corporate_action;

ALTER TABLE gmp_cis.cis_corporate_action_new
    ALTER COLUMN created_at   STRING,
    ALTER COLUMN updated_at   STRING,
    ALTER COLUMN performed_at STRING;

INSERT INTO gmp_cis.cis_corporate_action_new
SELECT
    ca_id, portfolio, security_id, ca_type, status,
    announcement_date, ex_date, record_date, payment_date,
    effective_date, subscription_start_date, subscription_end_date,
    cash_dividend, stock_dividend_ratio, rights_ratio, rights_price,
    created_by, updated_by,
    from_unixtime(CAST(created_at   AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at,
    CASE WHEN performed_at IS NOT NULL
         THEN from_unixtime(CAST(performed_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS performed_at
FROM gmp_cis.cis_corporate_action;

-- ALTER TABLE gmp_cis.cis_corporate_action     RENAME TO gmp_cis.cis_corporate_action_bak;
-- ALTER TABLE gmp_cis.cis_corporate_action_new RENAME TO gmp_cis.cis_corporate_action;
-- DROP TABLE gmp_cis.cis_corporate_action_bak;


-- ----------------------------------------------------------------------------
-- 1E. cis_system_date
--     Columns: loaded_at BIGINT, created_at BIGINT, updated_at BIGINT
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_system_date_new
LIKE gmp_cis.cis_system_date;

ALTER TABLE gmp_cis.cis_system_date_new
    ALTER COLUMN loaded_at  STRING,
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_system_date_new
SELECT
    system_date_id, system_date, report_date, processing_date,
    status, created_by, updated_by,
    from_unixtime(CAST(loaded_at  AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS loaded_at,
    from_unixtime(CAST(created_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_unixtime(CAST(updated_at AS BIGINT) / 1000, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_system_date;

-- ALTER TABLE gmp_cis.cis_system_date     RENAME TO gmp_cis.cis_system_date_bak;
-- ALTER TABLE gmp_cis.cis_system_date_new RENAME TO gmp_cis.cis_system_date;
-- DROP TABLE gmp_cis.cis_system_date_bak;


-- ============================================================================
-- GROUP 2: TIMESTAMP → STRING
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2A. cis_party
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_party_new
LIKE gmp_cis.cis_party;

ALTER TABLE gmp_cis.cis_party_new
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_party_new
SELECT
    party_id, party_name, party_short_name, party_type, status,
    country_code, currency_code, processing_date,
    created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_party;

-- ALTER TABLE gmp_cis.cis_party     RENAME TO gmp_cis.cis_party_bak;
-- ALTER TABLE gmp_cis.cis_party_new RENAME TO gmp_cis.cis_party;
-- DROP TABLE gmp_cis.cis_party_bak;


-- ----------------------------------------------------------------------------
-- 2B. cis_user
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_new
LIKE gmp_cis.cis_user;

ALTER TABLE gmp_cis.cis_user_new
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_user_new
SELECT
    cis_user_id, username, email, full_name, role, status,
    is_active, is_deleted, created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_user;

-- ALTER TABLE gmp_cis.cis_user     RENAME TO gmp_cis.cis_user_bak;
-- ALTER TABLE gmp_cis.cis_user_new RENAME TO gmp_cis.cis_user;
-- DROP TABLE gmp_cis.cis_user_bak;


-- ----------------------------------------------------------------------------
-- 2C. cis_user_group
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_user_group_new
LIKE gmp_cis.cis_user_group;

ALTER TABLE gmp_cis.cis_user_group_new
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_user_group_new
SELECT
    cis_user_group_id, username, group_name, created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_user_group;

-- ALTER TABLE gmp_cis.cis_user_group     RENAME TO gmp_cis.cis_user_group_bak;
-- ALTER TABLE gmp_cis.cis_user_group_new RENAME TO gmp_cis.cis_user_group;
-- DROP TABLE gmp_cis.cis_user_group_bak;


-- ----------------------------------------------------------------------------
-- 2D. cis_group_permissions
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_group_permissions_new
LIKE gmp_cis.cis_group_permissions;

ALTER TABLE gmp_cis.cis_group_permissions_new
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_group_permissions_new
SELECT
    cis_group_permissions_id, group_name, permission_name,
    can_create, can_read, can_update, can_delete,
    created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_group_permissions;

-- ALTER TABLE gmp_cis.cis_group_permissions     RENAME TO gmp_cis.cis_group_permissions_bak;
-- ALTER TABLE gmp_cis.cis_group_permissions_new RENAME TO gmp_cis.cis_group_permissions;
-- DROP TABLE gmp_cis.cis_group_permissions_bak;


-- ----------------------------------------------------------------------------
-- 2E. cis_cash_flow
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP,
--              validated_at TIMESTAMP, settled_at TIMESTAMP, cancelled_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_cash_flow_new
LIKE gmp_cis.cis_cash_flow;

ALTER TABLE gmp_cis.cis_cash_flow_new
    ALTER COLUMN created_at   STRING,
    ALTER COLUMN updated_at   STRING,
    ALTER COLUMN validated_at STRING,
    ALTER COLUMN settled_at   STRING,
    ALTER COLUMN cancelled_at STRING;

INSERT INTO gmp_cis.cis_cash_flow_new
SELECT
    cash_flow_id, trade_id, portfolio, security_id,
    cash_flow_type, status, currency_code,
    gross_amount, tax_amount, net_amount,
    trade_date, value_date, payment_date,
    dividend_date, ex_date, record_date,
    src_system, created_by, updated_by,
    from_timestamp(created_at,   'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at   IS NOT NULL THEN from_timestamp(updated_at,   'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS updated_at,
    CASE WHEN validated_at IS NOT NULL THEN from_timestamp(validated_at, 'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS validated_at,
    CASE WHEN settled_at   IS NOT NULL THEN from_timestamp(settled_at,   'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS settled_at,
    CASE WHEN cancelled_at IS NOT NULL THEN from_timestamp(cancelled_at, 'yyyy-MM-dd HH:mm:ss') ELSE NULL END AS cancelled_at,
    performed_at
FROM gmp_cis.cis_cash_flow;

-- ALTER TABLE gmp_cis.cis_cash_flow     RENAME TO gmp_cis.cis_cash_flow_bak;
-- ALTER TABLE gmp_cis.cis_cash_flow_new RENAME TO gmp_cis.cis_cash_flow;
-- DROP TABLE gmp_cis.cis_cash_flow_bak;


-- ----------------------------------------------------------------------------
-- 2F. cis_file_upload
--     Columns: created_at TIMESTAMP, updated_at TIMESTAMP
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS gmp_cis.cis_file_upload_new
LIKE gmp_cis.cis_file_upload;

ALTER TABLE gmp_cis.cis_file_upload_new
    ALTER COLUMN created_at STRING,
    ALTER COLUMN updated_at STRING;

INSERT INTO gmp_cis.cis_file_upload_new
SELECT
    upload_id, file_name, original_file_name, file_type, file_size,
    row_count, column_count, delimiter, has_header, encoding,
    status, description, hdfs_path, mime_type, target_table_name,
    target_database, validation_errors_json, schema_json,
    is_deleted, created_by, updated_by,
    from_timestamp(created_at, 'yyyy-MM-dd HH:mm:ss') AS created_at,
    CASE WHEN updated_at IS NOT NULL
         THEN from_timestamp(updated_at, 'yyyy-MM-dd HH:mm:ss')
         ELSE NULL END AS updated_at
FROM gmp_cis.cis_file_upload;

-- ALTER TABLE gmp_cis.cis_file_upload     RENAME TO gmp_cis.cis_file_upload_bak;
-- ALTER TABLE gmp_cis.cis_file_upload_new RENAME TO gmp_cis.cis_file_upload;
-- DROP TABLE gmp_cis.cis_file_upload_bak;


-- ============================================================================
-- VALIDATION QUERIES (run after each migration before rename)
-- ============================================================================
-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_kudu;
-- SELECT COUNT(*) FROM gmp_cis.cis_equity_price_kudu_new;
-- SELECT currency_code, security_label, price_date, price_timestamp, created_at
--   FROM gmp_cis.cis_equity_price_kudu_new LIMIT 5;
--
-- SELECT COUNT(*) FROM gmp_cis.cis_security_kudu;
-- SELECT COUNT(*) FROM gmp_cis.cis_security_kudu_new;
-- SELECT security_id, created_at, updated_at FROM gmp_cis.cis_security_kudu_new LIMIT 5;
--
-- SELECT COUNT(*) FROM gmp_cis.cis_user;
-- SELECT COUNT(*) FROM gmp_cis.cis_user_new;
-- SELECT cis_user_id, username, created_at FROM gmp_cis.cis_user_new LIMIT 5;
-- ============================================================================
