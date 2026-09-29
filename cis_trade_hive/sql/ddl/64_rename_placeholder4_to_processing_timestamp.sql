-- DDL: Rename placeholder_4 → processing_timestamp in cis_position
-- Run this once on the live Kudu table via impala-shell

USE gmp_cis;

ALTER TABLE cis_position RENAME COLUMN placeholder_4 TO processing_timestamp;
