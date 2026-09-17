# CIS Trade Hive — Control-M PROD → DR Daily Sync Job

**Version:** 1.0
**Updated:** 2026-08-07
**Audience:** Ops / DBA / DR
**Database:** `gmp_cis` (Apache Kudu + Hive/external Parquet, via Impala)

---

## Overview

A daily job chain that keeps the DR `gmp_cis` database in sync with PROD:
full backup on PROD → transfer to DR-reachable storage → full restore on
DR, covering **both** Kudu and Hive/external tables via auto-discovery (no
hardcoded table list — same design as `kudu_full_backup.py`).

**This is a daily full sync, not continuous replication.** RPO (recovery
point objective) is up to 24 hours — if PROD fails between sync runs, DR
reflects yesterday's state. This was a deliberate scope choice (see
`docs/KUDU_DR_RESTORE_DRILL.md` for the incremental-backup alternative,
which is Kudu-only and currently has a broken `--auto-since` — see
Known Limitations below).

```
Wave DR1   Full backup on PROD           (kudu_full_backup.py)
Wave DR2   Transfer PROD → DR storage    (prod_dr_transfer.sh)
Wave DR3   Full restore on DR            (kudu_full_restore_from_manifest.py)
```

Each wave must complete (exit code 0) before the next starts.

---

## Job Definitions

### Wave DR1 — Full Backup on PROD

#### JOB: DR_SYNC_FULL_BACKUP_PROD

**Purpose:** Auto-discover and back up every Kudu + Hive/external table in
`gmp_cis` on PROD.

**Runs on:** PROD edge node (needs PROD's `spark-submit`, PROD's Kudu
master, PROD's Kerberos identity).

**Command:**

```bash
spark-submit --master yarn --deploy-mode client \
    --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \
    scripts/kudu_full_backup.py \
    --backup-path hdfs:///backups/gmp_cis \
    --kudu-master <PROD_KUDU_MASTER>:7051
```

**Key arguments:**

| Argument | Description |
|---|---|
| *(none)* | Auto-discover and back up every table (Kudu + Hive) |
| `--skip-tables` | Comma-separated tables to exclude (e.g. large staging/scratch tables not needed on DR) |
| `--kudu-only` / `--hive-only` | Restrict to one storage type |
| `--dry-run` | Discover + count rows, no write — use to sanity-check before wiring into Control-M |

**Output:** Per-table Parquet under
`hdfs:///backups/gmp_cis/gmp_cis/<table>/full/<TS>/`, plus a manifest at
`hdfs:///backups/gmp_cis/manifests/manifest_<TS>.json` listing every table's
backup status and row count — this manifest is what Wave DR3 reads to know
exactly what to restore, so no timestamp needs to be manually threaded
between Control-M jobs.

**Dependencies:** None (first job in chain)
**On failure:** Abort chain — do not proceed to transfer/restore with a
partial/failed backup
**Schedule:** Daily, off-peak (e.g. 02:00)

---

### Wave DR2 — Transfer PROD → DR

#### JOB: DR_SYNC_TRANSFER

**Purpose:** Copy the backup (data + manifest) from PROD's storage to
somewhere DR's restore job can read.

**⚠️ Status: connectivity between PROD and DR storage is UNTESTED as of
this writing.** PROD and DR are confirmed to be on different hostnames;
whether DR can read PROD's HDFS path directly (shared namespace, viewfs
federation, etc.) has not been verified. **Run
`scripts/prod_dr_transfer.sh test-connectivity` manually before scheduling
this job** — if it turns out DR can already read PROD's path directly,
this entire wave can be **removed** and Wave DR3 pointed straight at PROD's
backup path instead.

**Runs on:** Either edge node, as long as it can reach both PROD's and
DR's HDFS NameNodes (needed for `hadoop distcp`, which is itself a
YARN/MapReduce job requiring network access to both clusters).

**Command:**

```bash
PROD_NAMENODE=hdfs://<PROD_NAMENODE_HOST>:8020 \
DR_NAMENODE=hdfs://<DR_NAMENODE_HOST>:8020 \
scripts/prod_dr_transfer.sh transfer-latest
```

**What it does:**
1. Finds the most recent `manifest_<TS>.json` under PROD's `/manifests/`.
2. `hadoop distcp -update`s the manifest directory to DR's backup path.
3. Reads the manifest to get the list of successfully-backed-up tables.
4. `hadoop distcp -update`s each table's `full/<TS>/` directory to DR.

**Dependencies:** DR_SYNC_FULL_BACKUP_PROD
**On failure:** Abort chain — Wave DR3 must not run against a partial
transfer
**Schedule:** Daily, immediately after Wave DR1 completes

---

### Wave DR3 — Full Restore on DR

#### JOB: DR_SYNC_FULL_RESTORE_DR

**Purpose:** Restore every table from the transferred manifest into DR's
`gmp_cis`, in one job step (no per-table Control-M jobs needed).

**Runs on:** DR edge node (needs DR's `spark-submit`, DR's Kudu master, DR's
Kerberos identity).

**Command:**

```bash
spark-submit --master yarn --deploy-mode client \
    --jars /jars/kudu/kudu-spark3_2.12-1.17.0.jar \
    scripts/kudu_full_restore_from_manifest.py \
    --backup-path hdfs:///backups/gmp_cis \
    --latest \
    --kudu-master <DR_KUDU_MASTER>:7051 \
    --mode truncate_insert --validate
```

**Key arguments:**

| Argument | Description |
|---|---|
| `--latest` | Auto-discover the most recent manifest under `--backup-path/manifests/` — no manual timestamp needed |
| `--manifest <path>` | Restore from one specific manifest instead |
| `--mode` | `truncate_insert` (default, recommended for DR mirroring — see below), `upsert`, `insert_ignore` (Kudu only), `create_new` |
| `--skip-tables` | Comma-separated tables to exclude from this restore run |
| `--validate` | Row-count check against the live table after each restore |
| `--dry-run` | Validate paths/types with zero writes |

**Why `truncate_insert`:** for a true DR mirror, DR should end up with
**exactly** PROD's data, not PROD's data plus whatever was already there.
`kudu_full_restore.py`'s `truncate_insert` mode (fixed as part of this
work — see `docs/KUDU_DR_RESTORE_DRILL.md`) deletes any row not present in
the backup before upserting, for Kudu tables, and does a full overwrite for
Hive/external tables.

**Dependencies:** DR_SYNC_TRANSFER
**On failure:** Alert ops — DR may be in a partially-restored state; re-run
is safe (same manifest, same `truncate_insert` semantics — idempotent)
**Schedule:** Daily, immediately after Wave DR2 completes

---

## Full Dependency Chain

```
DR_SYNC_FULL_BACKUP_PROD  (PROD edge node)
        │
        ▼
DR_SYNC_TRANSFER          (either edge node — needs both clusters reachable)
        │
        ▼
DR_SYNC_FULL_RESTORE_DR   (DR edge node)
```

---

## Known Limitations

- **No incremental sync in this chain.** RPO is up to 24 hours. If a
  lower RPO is needed later, `kudu_incremental_backup.py` /
  `kudu_incremental_restore.py` cover it for Kudu tables only (fixed list
  of 21 `cis_*` tables in `TABLE_TIMESTAMP_COLUMNS`) — but
  `kudu_incremental_backup.py --auto-since` is currently a stub
  (`get_last_backup_timestamp()` always returns `None`) and would need
  real state tracking (e.g. a small local/Kudu-backed "last synced
  timestamp per table" store) before it could be trusted for automated
  scheduling. Not implemented as part of this daily-full-sync chain.
- **Hive tables never had an incremental path anyway** — full sync is
  already their only option, so this chain doesn't lose anything for them
  relative to what was possible before.
- **Wave DR2's necessity is unconfirmed.** See the ⚠️ callout above — test
  connectivity before scheduling.
- **Point-in-time recovery is out of scope for this chain** — it restores
  to "as of the last daily backup," not to an arbitrary timestamp. See
  `kudu_incremental_restore.py --point-in-time` (also has its own gap —
  documented in `docs/KUDU_DR_RESTORE_DRILL.md`) if that's ever needed.

---

## Pre-run Verification Checklist

```bash
# 1. Confirm PROD backup path connectivity from wherever DR_SYNC_TRANSFER runs
scripts/prod_dr_transfer.sh test-connectivity

# 2. Confirm DR's Kudu master and Impala are reachable from the DR edge node
impala-shell -i <DR_IMPALA_HOST>:21050 -q "SHOW DATABASES"
```

## Post-run Verification Checklist

```sql
-- Row counts should match between PROD and DR for spot-checked tables
-- (run on PROD)
SELECT COUNT(*) FROM gmp_cis.cis_trade;
-- (run on DR)
SELECT COUNT(*) FROM gmp_cis.cis_trade;
```

```bash
# Confirm the restore summary reported zero failures
# (check DR_SYNC_FULL_RESTORE_DR job output/log for "Failed   : 0")
```

Run the full drill in `docs/KUDU_DR_RESTORE_DRILL.md` (dedicated
`dr_drill_test_kudu` / `dr_drill_test_hive` tables) before trusting this
chain against real production tables for the first time.

---

## Indicative Schedule (Control-M Times)

| Time | Job | Wave |
|---|---|---|
| 02:00 | DR_SYNC_FULL_BACKUP_PROD | DR1 |
| 02:30 | DR_SYNC_TRANSFER | DR2 |
| 03:00 | DR_SYNC_FULL_RESTORE_DR | DR3 |

Times are indicative — size to your actual `gmp_cis` data volume and pick a
window that doesn't overlap the EOD chain in
`docs/CONTROL_M_EOD_JOBS.md` (17:30–19:00) or CORR runs.
