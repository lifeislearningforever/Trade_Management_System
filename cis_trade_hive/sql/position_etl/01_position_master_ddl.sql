-- ============================================================================
-- Position Master Table DDL
-- Target: Unified position master table combining all source systems
-- Format: Parquet with SNAPPY compression
-- Partitions: src_id, processing_date
-- ============================================================================

-- Drop table if exists (for development only)
-- DROP TABLE IF EXISTS gmp_cis.position_master;

CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.position_master (
    -- ========================================================================
    -- Core Position Identifiers
    -- ========================================================================
    portfolio                   STRING      COMMENT 'Portfolio code/name',
    security_full_name          STRING      COMMENT 'Full security name/description',
    security_short_name         STRING      COMMENT 'Short security name',
    isin                        STRING      COMMENT 'ISIN code',
    ticker                      STRING      COMMENT 'Ticker symbol',

    -- ========================================================================
    -- Quantity & Holdings
    -- ========================================================================
    quantity                    DECIMAL(18,4)   COMMENT 'Current quantity/units held',
    shares_outstanding          DECIMAL(18,4)   COMMENT 'Total shares outstanding',
    shares_issued               DECIMAL(18,4)   COMMENT 'Total shares issued',
    pct_holding                 DECIMAL(10,6)   COMMENT 'Percentage holding',

    -- ========================================================================
    -- Pricing Information
    -- ========================================================================
    market_price                DECIMAL(18,6)   COMMENT 'Current market price',
    average_cost                DECIMAL(18,6)   COMMENT 'Average cost per unit',

    -- ========================================================================
    -- Cost Values (Foreign Currency)
    -- ========================================================================
    cost_fc                     DECIMAL(18,4)   COMMENT 'Cost in foreign currency',
    market_value_fc             DECIMAL(18,4)   COMMENT 'Market value in foreign currency',
    net_book_value_fc           DECIMAL(18,4)   COMMENT 'Net book value in foreign currency',
    unrealized_pnl_fc           DECIMAL(18,4)   COMMENT 'Unrealized P&L in foreign currency',

    -- ========================================================================
    -- Cost Values (Local Currency)
    -- ========================================================================
    cost_lc                     DECIMAL(18,4)   COMMENT 'Cost in local currency',
    market_value_lc             DECIMAL(18,4)   COMMENT 'Market value in local currency',
    net_book_value_lc           DECIMAL(18,4)   COMMENT 'Net book value in local currency',
    unrealized_pnl_lc           DECIMAL(18,4)   COMMENT 'Unrealized P&L in local currency',
    provision_lc                DECIMAL(18,4)   COMMENT 'Provision in local currency',

    -- ========================================================================
    -- Security Classification
    -- ========================================================================
    product_type                STRING      COMMENT 'Product type (Equity, Bond, etc.)',
    security_type               STRING      COMMENT 'Security type classification',
    quoted_unquoted             STRING      COMMENT 'Quoted or Unquoted indicator',
    industry                    STRING      COMMENT 'Industry classification',
    fin_nonfin_co               STRING      COMMENT 'Financial/Non-Financial company indicator',
    issuer_type                 STRING      COMMENT 'Issuer type',
    reits_or_fund_y_n           STRING      COMMENT 'REITS or Fund indicator (Y/N)',

    -- ========================================================================
    -- Geographic Information
    -- ========================================================================
    exchange                    STRING      COMMENT 'Exchange code',
    country_code                STRING      COMMENT 'Country code',
    country_of_exchange         STRING      COMMENT 'Country of exchange',
    country_of_incorporation    STRING      COMMENT 'Country of incorporation',
    country_of_risk             STRING      COMMENT 'Country of risk',
    country_of_operation        STRING      COMMENT 'Country of operation',
    security_currency           STRING      COMMENT 'Security currency code',

    -- ========================================================================
    -- Corporate Information
    -- ========================================================================
    corp_code                   STRING      COMMENT 'Corporate code',
    branch_code                 STRING      COMMENT 'Branch code',
    cost_centre                 STRING      COMMENT 'Cost centre',
    cels                        STRING      COMMENT 'CELS code',

    -- ========================================================================
    -- BWCIF & MAS Codes
    -- ========================================================================
    bwcif_sg                    STRING      COMMENT 'BWCIF Singapore code',
    bwcif_ovs                   STRING      COMMENT 'BWCIF Overseas code',
    mas_6d_code_sg              STRING      COMMENT 'MAS 6D code Singapore',
    mas_6d_code_ovs             STRING      COMMENT 'MAS 6D code Overseas',

    -- ========================================================================
    -- Dates
    -- ========================================================================
    position_basis              STRING      COMMENT 'Position basis date (trade_date/settled_date)',
    reporting_date              STRING      COMMENT 'Reporting date',
    maturity_date               STRING      COMMENT 'Maturity date',

    -- ========================================================================
    -- Source System Metadata (Non-Partition)
    -- ========================================================================
    src_system                  STRING      COMMENT 'Source system (USER_UPLOAD, AMS_STREET)',
    sub_system                  STRING      COMMENT 'Sub-system identifier',
    data_cat                    STRING      COMMENT 'Data category',
    data_frq                    STRING      COMMENT 'Data frequency',
    source_table                STRING      COMMENT 'Original source table name',

    -- ========================================================================
    -- ETL Metadata
    -- ========================================================================
    etl_insert_ts               TIMESTAMP   COMMENT 'ETL insert timestamp',
    etl_batch_id                STRING      COMMENT 'ETL batch identifier'
)
COMMENT 'Unified Position Master table combining USER_UPLOAD and AMS_STREET sources'
PARTITIONED BY (
    src_id              STRING      COMMENT 'Source identifier',
    processing_date     STRING      COMMENT 'Processing date (DDMMYYYY format)'
)
STORED AS PARQUET
LOCATION '/data/gmp_cis/position_master'
TBLPROPERTIES (
    'parquet.compression' = 'SNAPPY',
    'transactional' = 'false'
);

-- ============================================================================
-- Add table statistics for query optimization
-- ============================================================================
-- ANALYZE TABLE gmp_cis.position_master COMPUTE STATISTICS;
-- ANALYZE TABLE gmp_cis.position_master COMPUTE STATISTICS FOR COLUMNS;
