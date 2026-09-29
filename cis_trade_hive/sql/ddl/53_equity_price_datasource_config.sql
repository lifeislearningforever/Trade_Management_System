-- ============================================================================
-- Datasource Config: Equity Price CSV Upload
-- ============================================================================
-- Registers cisEquPriceUpload.csv as a known datasource so the generic Upload
-- app can validate, preview, and ingest it into gmp_cis.cis_equity_price.
--
-- When a user uploads a file named exactly "cisEquPriceUpload.csv" through
-- the Upload app (/upload/create/), the system:
--   1. Detects this datasource config by source_name match
--   2. Validates the 5-column CSV structure (column count + names)
--   3. Shows a preview page before ingestion
--   4. On ingest: routes to _ingest_kudu_equity_price() which does Kudu UPSERT
--      (bypasses the standard INSERT OVERWRITE / partition path)
--
-- CSV format (from cisEquPriceUpload.csv):
--   Price Date, Security label, Closing Price, Shares outstanding, Market Value
--
-- Columns used for upsert into cis_equity_price:
--   price_date       <- "Price Date"
--   security_label   <- "Security label"
--   main_closing_price <- "Closing Price"
--   currency_code    <- looked up from cis_security by security_name
--   isin             <- looked up from cis_security by security_name
--
-- "Shares outstanding" and "Market Value" are carried through validation
-- (so column-count check passes) but ignored during ingest.
--
-- Run: impala-shell -i localhost:21050 -f sql/ddl/53_equity_price_datasource_config.sql
-- ============================================================================

USE gmp_cis;

UPSERT INTO gmp_cis.cis_datasource_mng (
    source_id,
    source_name,
    target_table,
    separator,
    header,
    no_of_skip_line,
    intake_columns,
    src_system,
    sub_system,
    data_cat,
    data_frq
) VALUES (
    'CIS_EQUITY_PRICE',                         -- source_id
    'cisEquPriceUpload.csv',                    -- source_name  (must match uploaded filename exactly)
    'cis_equity_price',                         -- target_table (Kudu — UPSERT path used)
    ',',                                        -- separator
    'true',                                     -- header (first row is header)
    '0',                                        -- no_of_skip_line
    'price_date,security_label,closing_price,shares_outstanding,market_value',
                                                -- intake_columns (all 5 CSV columns, cleaned names)
    'CIS',                                      -- src_system
    'user',                                     -- sub_system
    'sta',                                      -- data_cat
    'adhoc'                                     -- data_frq
);

-- Verify
SELECT source_id, source_name, target_table, separator, intake_columns
FROM gmp_cis.cis_datasource_mng
WHERE source_id = 'CIS_EQUITY_PRICE';
