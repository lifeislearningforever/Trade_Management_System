-- Diagnose duplicate is_latest=true CORR rows in cis_position.
--
-- Root cause: trade/management/commands/refresh_positions.py generated a
-- timestamp-based position_id in _batch_upsert_eod before commit cb4b04f
-- (2026-07-20, "fix: use deterministic position_id + UPSERT in
-- _batch_upsert_eod to stop duplicate EOD rows"). Any environment that ran
-- refresh_positions --run-type CORR (or EOD) on the pre-fix code could have
-- left orphaned is_latest=true rows every time it re-ran for the same
-- natural key, instead of upserting the same row in place.
--
-- Confirmed live example: portfolio=UOBS_CIU_AC_TAEL, security_label=UQ-UOB-139 KY,
-- position_date=2026-02-27 had 2 pre-fix duplicate rows (position_id/version_id
-- differing by exactly 2,000,000 -- the old code's fixed offset -- and
-- processing_timestamp=NULL) still marked is_latest=true alongside the new,
-- correctly deterministic-hash rows.
--
-- Run Step 1 and Step 2 below and share the results before running any fix --
-- this only reads, it does not write.

-- =============================================================================
-- STEP 1: How many natural keys are affected, and how bad is it per key?
-- =============================================================================
SELECT portfolio, security_label, position_basis, position_date, COUNT(*) AS latest_count
FROM gmp_cis.cis_position
WHERE position_type = 'CORR'
  AND is_latest = true
GROUP BY portfolio, security_label, position_basis, position_date
HAVING COUNT(*) > 1
ORDER BY position_date, portfolio, security_label;

-- =============================================================================
-- STEP 2: The exact stale rows that need is_latest -> false.
--
-- Keeps the row with the highest version_id per natural key (the most
-- recently written one -- per the confirmed example, that's the correctly
-- deterministic-hash row) and lists everything else (rn > 1) as stale.
-- =============================================================================
SELECT position_id, portfolio, security_label, position_basis, position_date,
       version_id, processing_timestamp
FROM (
    SELECT p.*,
           ROW_NUMBER() OVER (
               PARTITION BY portfolio, security_label, position_basis, position_date
               ORDER BY version_id DESC
           ) AS rn
    FROM gmp_cis.cis_position p
    WHERE position_type = 'CORR'
      AND is_latest = true
) ranked
WHERE rn > 1
ORDER BY position_date, portfolio, security_label;
