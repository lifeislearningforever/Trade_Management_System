# Kudu + Hive Backup/Restore — PROD → DR Drill

**Version:** 1.0
**Updated:** 2026-08-07
**Audience:** Ops / DBA / DR testing
**Database:** `gmp_cis` (Apache Kudu + Hive external Parquet tables, via Impala)

---

## Overview

This is a self-contained test plan for validating the Kudu/Hive backup and
restore tooling end-to-end — from PROD backup through DR restore — using a
small, dedicated drill dataset that is never confused with real business
data. It also documents fixes made to `scripts/kudu_full_restore.py` while
preparing this drill, and known limitations to be aware of before relying
on this tooling for a real disaster-recovery failover.

**Scripts involved:**

| Script | Scope | Notes |
|---|---|---|
| `scripts/kudu_full_backup.py` | Kudu **+** Hive/external (auto-discovers all tables in the DB) | |
| `scripts/kudu_full_restore.py` | Kudu **+** Hive/external (single table) | Fixed in this drill — see below |
| `scripts/kudu_incremental_backup.py` | Kudu only, fixed list of 21 `cis_*` tables | No Hive tables in scope |
| `scripts/kudu_incremental_restore.py` | Kudu only | Point-in-time path is manual two-step — see Known Limitations |

---

## Fixes made to `kudu_full_restore.py` for this drill

The script originally only restored Kudu tables, even though its backup
counterpart (`kudu_full_backup.py`) backs up both Kudu and Hive/external
tables. While extending it, three issues were found and fixed:

1. **Hive/external table restore was completely missing.** The script
   always wrote via the Kudu Spark connector regardless of the original
   table's type, so restoring a Hive-storage table would fail. Fixed by
   auto-detecting table type via `DESCRIBE FORMATTED` (same technique
   `kudu_full_backup.py` already uses) and routing Hive/external tables
   through `spark.sql`-based writes instead:
   - `truncate_insert` → `df.write.mode("overwrite").insertInto(table)`
   - `create_new` → `df.write.mode("errorifexists").saveAsTable(table)`
   - `upsert` / `insert_ignore` → **refused** with a clear error for
     non-Kudu tables. Kudu's upsert relies on native per-row primary-key
     semantics; a plain Hive/Parquet table has no equivalent without
     knowing it's an ACID transactional table, which can't be reliably
     detected — so rather than silently doing something that isn't really
     an upsert, these two modes now only work for Kudu tables.

2. **`_meta` / `_metadata` directory name mismatch.** `kudu_full_backup.py`
   writes per-table metadata to a `_meta` directory; the restore script was
   reading from `_metadata` — a name that never existed on disk. This made
   the "backup row count" sanity check silently fail (non-fatal, just
   printed "unknown") on every restore. Fixed the reader to match what the
   backup writer actually produces.

3. **`truncate_insert` never actually truncated anything (Kudu tables).**
   Despite the name and a 5-second "WARNING: this will DELETE all existing
   data!" countdown before running, the original implementation was
   byte-for-byte identical to `upsert` — it only ever upserted the backup
   data, with no delete step. Any row already in the target table that
   wasn't in the backup was silently left behind forever — exactly the
   kind of thing that quietly corrupts a DR mirror over time. Fixed with a
   real delete-then-upsert:
   - Resolves the table's actual internal Kudu name via the
     `kudu.table_name` table property (not guaranteed to equal the
     Hive-catalog `database.table` string, depending on how the table was
     originally created — same lookup the backup script already relies on).
   - Reads the table's real primary-key columns directly from the native
     Kudu client (bypasses fragile Impala DESCRIBE-FORMATTED text parsing).
   - Left-anti-joins existing keys against the backup's keys to find stale
     rows, deletes exactly those via `kudu.operation=delete`, then upserts
     the backup data.
   - The restore summary now reports `Rows Deleted` alongside `Rows
     Restored`.

All changes preserve the existing CLI/argument interface — no flags
changed. Verified with `python3 -m py_compile scripts/kudu_full_restore.py`.

---

## Known limitations (not changed in this drill)

- **Point-in-time restore is a manual two-step.**
  `kudu_incremental_restore.py --point-in-time` only *prints* an
  instruction to run `kudu_full_restore.py` first — it doesn't invoke it.
  Run the full restore, then the point-in-time incremental command,
  separately.
- **Hive tables have no incremental backup/restore path.** Only full
  backup/restore covers them (`kudu_incremental_backup.py`'s
  `TABLE_TIMESTAMP_COLUMNS` list is Kudu-only). A Hive table's DR copy is
  only ever as fresh as the last full backup.
- **Cross-cluster/Kerberos access is untested from this drill.** Whether
  the DR edge node's Kerberos identity can read the PROD backup path in
  HDFS was not verified here — check with a plain `hdfs dfs -ls
  <PROD_backup_path>` from the DR node before relying on the commands below
  for a real failover.

---

## Drill dataset

A small, dedicated pair of tables — deliberately **not** reusing any real
business table name, so this drill can never be confused with production
data: one Kudu table, one Hive/external table (matching this repo's
existing DDL conventions — see `kudu_ddl/04_udf_tables.sql` and
`sql/hive_ddl/create_hive_external_tables.sql`).

### Step 1 — Create in PROD

```bash
impala-shell -i <PROD_IMPALA_HOST>:21050 -d gmp_cis
```

```sql
-- Kudu test table
CREATE TABLE IF NOT EXISTS gmp_cis.dr_drill_test_kudu (
  drill_id      STRING    NOT NULL,
  label         STRING    NULL,
  amount        DECIMAL(20,8) NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
  PRIMARY KEY (drill_id)
)
PARTITION BY HASH (drill_id) PARTITIONS 4
STORED AS KUDU;

INSERT INTO gmp_cis.dr_drill_test_kudu (drill_id, label, amount) VALUES
  ('K001', 'drill-alpha',   100.50000000),
  ('K002', 'drill-bravo',   250.00000000),
  ('K003', 'drill-charlie', 999.99000000),
  ('K004', 'drill-delta',     0.00000000),
  ('K005', 'drill-echo',   1234.56780000);

-- Hive/external test table (Parquet), scratch location -- NOT under the
-- real /mrw/cis/hive/ landing-zone tree used by production ETL
CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.dr_drill_test_hive (
  drill_id      STRING,
  label         STRING,
  amount        DECIMAL(20,8)
)
PARTITIONED BY (processing_date STRING)
STORED AS PARQUET
LOCATION '/tmp/dr_drill/hive/dr_drill_test_hive'
TBLPROPERTIES ('parquet.compression'='SNAPPY');

ALTER TABLE gmp_cis.dr_drill_test_hive ADD IF NOT EXISTS
  PARTITION (processing_date='20260807');

INSERT INTO gmp_cis.dr_drill_test_hive PARTITION (processing_date='20260807')
  (drill_id, label, amount) VALUES
  ('H001', 'hive-drill-one',   10.00000000),
  ('H002', 'hive-drill-two',   20.50000000),
  ('H003', 'hive-drill-three', 30.75000000);
```

### Step 2 — Back up both on PROD

Scoped with `--table` so nothing else in `gmp_cis` is touched:

```bash
spark-submit --master yarn --deploy-mode client \
    --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \
    scripts/kudu_full_backup.py \
    --table dr_drill_test_kudu \
    --backup-path hdfs:///backups/gmp_cis \
    --kudu-master <PROD_KUDU_MASTER>:7051

spark-submit --master yarn --deploy-mode client \
    scripts/kudu_full_backup.py \
    --table dr_drill_test_hive \
    --backup-path hdfs:///backups/gmp_cis \
    --kudu-master <PROD_KUDU_MASTER>:7051
```

Backup output path convention (from `kudu_full_backup.py`):
`{backup_path}/{database}/{table}/full/{timestamp}` — note the printed
`out_path` / manifest at the end of each run for the exact `<TS>` to use in
Step 4.

### Step 3 — Create the empty table shells on DR

Run the **same** `CREATE TABLE` / `CREATE EXTERNAL TABLE` + `ALTER TABLE
... ADD PARTITION` statements from Step 1 against DR's `impala-shell`
(skip the `INSERT` statements — DR should start empty). `truncate_insert`
restores *data*; it doesn't create Kudu tables from nothing, and
`insertInto` for the Hive table needs the table/partition to already exist.

### Step 4 — Restore into DR

```bash
spark-submit --master yarn --deploy-mode client \
    --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \
    scripts/kudu_full_restore.py \
    --table dr_drill_test_kudu \
    --backup-path hdfs:///backups/gmp_cis/gmp_cis/dr_drill_test_kudu/full/<TS> \
    --kudu-master <DR_KUDU_MASTER>:7051 \
    --mode truncate_insert --validate

spark-submit --master yarn --deploy-mode client \
    scripts/kudu_full_restore.py \
    --table dr_drill_test_hive \
    --backup-path hdfs:///backups/gmp_cis/gmp_cis/dr_drill_test_hive/full/<TS> \
    --kudu-master <DR_KUDU_MASTER>:7051 \
    --mode truncate_insert --validate
```

Tip: run with `--dry-run` first to validate paths/types with zero writes
before the real restore.

### Step 5 — Verify on DR

```sql
SELECT * FROM gmp_cis.dr_drill_test_kudu ORDER BY drill_id;   -- expect 5 rows
SELECT * FROM gmp_cis.dr_drill_test_hive ORDER BY drill_id;   -- expect 3 rows
```

### Step 6 — Prove the truncate fix actually deletes stale rows

Insert an extra row directly into DR's Kudu table that PROD doesn't have:

```sql
-- on DR only
INSERT INTO gmp_cis.dr_drill_test_kudu (drill_id, label, amount)
  VALUES ('K999', 'stale-row', 1.0);
```

Re-run Step 4's Kudu restore command. `K999` should be gone afterward, and
the restore summary should print `Rows Deleted: 1`.

### Step 7 — Incremental backup/restore cycle (optional, Kudu only)

Only meaningful for tables in `kudu_incremental_backup.py`'s
`TABLE_TIMESTAMP_COLUMNS` list — `dr_drill_test_kudu` is **not** in that
list, so this step uses a real covered table (`cis_trade`) as an example
rather than the drill table itself:

```bash
# On PROD
spark-submit --jars /jars/kudu/*.jar scripts/kudu_incremental_backup.py \
    --table cis_trade --auto-since --kudu-master <PROD_KUDU_MASTER>:7051

# On DR
spark-submit --jars /jars/kudu/*.jar scripts/kudu_incremental_restore.py \
    --table cis_trade \
    --backup-path hdfs:///backups/kudu/gmp_cis/cis_trade/incremental/<TS> \
    --kudu-master <DR_KUDU_MASTER>:7051
```

### Step 8 — Cleanup

```sql
-- on both PROD and DR
DROP TABLE gmp_cis.dr_drill_test_kudu;
DROP TABLE gmp_cis.dr_drill_test_hive;
```

```bash
hdfs dfs -rm -r hdfs:///backups/gmp_cis/gmp_cis/dr_drill_test_kudu
hdfs dfs -rm -r hdfs:///backups/gmp_cis/gmp_cis/dr_drill_test_hive
hdfs dfs -rm -r /tmp/dr_drill/hive/dr_drill_test_hive
```

---

## Pass/fail checklist

- [ ] Step 2 backups complete with `SUCCESS` status for both tables
- [ ] Step 4 restores complete with `SUCCESS` status for both tables
- [ ] Step 5 row counts match PROD exactly (5 Kudu rows, 3 Hive rows)
- [ ] Step 6 confirms `K999` is deleted and `Rows Deleted: 1` is reported
- [ ] `--validate` passes for the Kudu restore (row count check against the live table)
- [ ] No errors in Spark driver output for any step
