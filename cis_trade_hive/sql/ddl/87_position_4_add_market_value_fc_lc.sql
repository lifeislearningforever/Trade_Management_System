-- ============================================================================
-- Format 4 (cis_user_sta_adhoc_position_4) raw upload source now sends
-- MARKET_VALUE_FC / MARKET_VALUE_LC instead of NET_BOOK_VALUE_FC / _LC.
-- Add the new columns; leave net_book_value_fc/lc in place (unused going
-- forward, but dropping a column from a live external Parquet table risks
-- breaking reads of already-landed partitions written with the old schema).
-- ============================================================================
ALTER TABLE gmp_cis.cis_user_sta_adhoc_position_4
ADD COLUMNS (
    market_value_fc     STRING,
    market_value_lc     STRING
);
