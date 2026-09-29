-- ============================================================================
-- Query Builder Report Template Table
-- ============================================================================
-- Stores saved report templates for the Query Builder module.
-- Database: gmp_cis
-- ============================================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_report_template (
    template_id    BIGINT NOT NULL,
    template_name  STRING NOT NULL,
    description    STRING,
    category       STRING,          -- TRADE, PORTFOLIO, POSITION, MARKET_DATA, SECURITY
    query_config   STRING,          -- JSON: full builder config {tables, joins, columns, filters, aggregations, sort, limit}
    allowed_groups STRING,          -- JSON array: ["TRADER", "RISK_MANAGER", "ADMIN"]
    is_public      BOOLEAN,         -- visible to all groups
    created_by     STRING,
    created_at     STRING,
    updated_by     STRING,
    updated_at     STRING,
    is_active      BOOLEAN,
    PRIMARY KEY (template_id)
)
PARTITION BY HASH (template_id) PARTITIONS 4
STORED AS KUDU
TBLPROPERTIES ('kudu.master_addresses' = 'kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251');
