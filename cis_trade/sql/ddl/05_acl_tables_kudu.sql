-- =====================================================
-- CisTrade - ACL Tables for Kudu/Impala
-- Role-Based Access Control
-- =====================================================

-- User Table (in Kudu)
CREATE TABLE IF NOT EXISTS cis_user (
    user_id BIGINT PRIMARY KEY,
    username STRING NOT NULL,
    login STRING NOT NULL,
    name STRING,
    email STRING,
    domain STRING,
    entity STRING,
    cis_user_group_id BIGINT,

    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,
    enabled BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
PARTITION BY HASH(user_id) PARTITIONS 16
STORED AS KUDU;

-- User Group Table
CREATE TABLE IF NOT EXISTS cis_user_group (
    group_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    group_name STRING,
    description STRING,

    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
PARTITION BY HASH(group_id) PARTITIONS 16
STORED AS KUDU;

-- Group Table
CREATE TABLE IF NOT EXISTS cis_group (
    group_id BIGINT PRIMARY KEY,
    group_name STRING NOT NULL,
    description STRING,

    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
PARTITION BY HASH(group_id) PARTITIONS 16
STORED AS KUDU;

-- Group Permissions Table
CREATE TABLE IF NOT EXISTS cis_group_permissions (
    permission_id BIGINT PRIMARY KEY,
    group_id BIGINT NOT NULL,
    permission_name STRING NOT NULL,

    can_view BOOLEAN DEFAULT FALSE,
    can_create BOOLEAN DEFAULT FALSE,
    can_edit BOOLEAN DEFAULT FALSE,
    can_delete BOOLEAN DEFAULT FALSE,
    can_approve BOOLEAN DEFAULT FALSE,

    object_id STRING,
    read_write STRING, -- 'READ', 'WRITE', 'READ_WRITE'

    is_active BOOLEAN DEFAULT TRUE,
    is_deleted BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
PARTITION BY HASH(permission_id) PARTITIONS 16
STORED AS KUDU;

-- =====================================================
-- Sample Permission Names
-- =====================================================
-- portfolio_view
-- portfolio_create
-- portfolio_edit
-- portfolio_delete
-- portfolio_approve
-- udf_view
-- udf_create
-- udf_edit
-- udf_delete
-- udf_approve
-- currency_view
-- currency_export
-- country_view
-- country_export
-- calendar_view
-- calendar_export
-- counterparty_view
-- counterparty_create
-- counterparty_edit
-- audit_log_view
