# Data Migration & Backup/Restore

> **Audience:** Developer, Support, DevOps
> **Read time:** ~10 minutes

---

## When Would You Run This?

The most common scenario: **refreshing SIT with UAT data**.

After UAT completes user acceptance testing, you want SIT to have the same data so developers can test against realistic data. The environments are on separate Cloudera clusters with no direct connection, so you physically copy the data.

Other scenarios:
- Backup before a major deployment (safety net)
- Restore after a failed migration
- Copying a subset of tables to debug an issue

---

## The High-Level Flow

```
UAT cluster                    Internet/SFTP              SIT cluster
─────────────────────────────────────────────────────────────────────
                                                          
  Kudu + Hive tables                                       
       │                                                  
  Spark backup script                                      
  (auto-discovers all tables)                              
       │                                                  
  Parquet files on HDFS                                    
       │                                                  
  hdfs dfs -get                                            
       │                                                  
  Local disk (tar.gz)  ──────── SCP/SFTP ────────────▶  Local disk
                                                              │
                                                         hdfs dfs -put
                                                              │
                                                         HDFS on SIT
                                                              │
                                                         Spark restore
                                                         (UPSERT to Kudu)
```

---

## Scripts Reference

| Script | Purpose | Run on |
|--------|---------|--------|
| `scripts/backup_sit_to_local.py` | Backup ALL SIT tables (Kudu + Hive) to HDFS → auto-zips to local | SIT |
| `scripts/backup_uat_to_local.py` | Backup ALL UAT tables (Kudu + Hive) to HDFS → auto-zips to local | UAT |
| `scripts/restore_sit_from_local.py` | Restore Parquet (HDFS or local path) → target Kudu via UPSERT | SIT or any target |
| `scripts/migrate_uat_to_sit.py` | Direct cross-cluster migration (requires VPN/network between clusters) | Either |
| `sql/ddl/99_sit_clean_gmp_cis.sql` | DROP all tables in SIT `gmp_cis` database | SIT |
| `sql/ddl/00_all_kudu_tables_sit.sql` | Recreate SIT schema (fresh, empty tables) | SIT |

---

## Full Migration Runbook (UAT → SIT)

See also: `scripts/MIGRATION_RUNBOOK.md` for the definitive step-by-step.

### Phase 0 — Backup SIT (Rollback Safety Net)

Run this FIRST, before touching anything.

```bash
# On SIT
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,\
/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,\
/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/backup_sit_to_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --impala-host <sit-impala-host> \
  --output-dir /tmp/sit_backup \
  --local-dir /tmp
# → auto-creates: /tmp/gmp_cis_sit_YYYYMMDD_HHMMSS.tar.gz
```

### Phase 1 — Backup UAT (Source Data)

```bash
# On UAT
spark-submit \
  --master yarn --deploy-mode client \
  --jars <same jars> \
  scripts/backup_uat_to_local.py \
  --kudu-master <uat-kudu-master>:7051 \
  --impala-host <uat-impala-host> \
  --output-dir /tmp/uat_backup \
  --local-dir /tmp
# → auto-creates: /tmp/gmp_cis_YYYYMMDD_HHMMSS.tar.gz
# → Prints ready-to-use SCP command at end
```

### Phase 2 — Transfer to SIT

```bash
# On UAT server — SCP the tar.gz to SIT
scp /tmp/gmp_cis_20260422_110000.tar.gz \
    <your-user>@<sit-host>:/tmp/

# Verify on SIT
ls -lh /tmp/gmp_cis_20260422_110000.tar.gz
```

### Phase 3 — Extract on SIT

```bash
# On SIT
cd /tmp
tar -xzf gmp_cis_20260422_110000.tar.gz
ls -1 /tmp/gmp_cis_20260422_110000/  # should see table folders
```

### Phase 4 — Push to SIT HDFS

```bash
# On SIT
hdfs dfs -mkdir -p /tmp/uat_restore/
hdfs dfs -put /tmp/gmp_cis_20260422_110000/ /tmp/uat_restore/
hdfs dfs -ls /tmp/uat_restore/gmp_cis_20260422_110000/  # verify
```

### Phase 5 — Clean SIT Schema

```bash
# Drop all SIT tables
impala-shell -i <sit-impala-host>:21050 \
  -f sql/ddl/99_sit_clean_gmp_cis.sql

# Recreate fresh empty tables
impala-shell -i <sit-impala-host>:21050 \
  -f sql/ddl/00_all_kudu_tables_sit.sql
```

### Phase 6 — Restore UAT Data into SIT

```bash
# Dry run first — validate files, no writes
spark-submit --master yarn --deploy-mode client \
  --jars <same jars> \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir hdfs:///tmp/uat_restore/gmp_cis_20260422_110000/ \
  --dry-run

# If dry run looks good — full restore
spark-submit --master yarn --deploy-mode client \
  --driver-memory 4g --executor-memory 4g \
  --jars <same jars> \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir hdfs:///tmp/uat_restore/gmp_cis_20260422_110000/
```

---

## Rollback (If Migration Fails)

```bash
# Step 1 — Drop and recreate SIT schema
impala-shell -i <sit-impala-host>:21050 -f sql/ddl/99_sit_clean_gmp_cis.sql
impala-shell -i <sit-impala-host>:21050 -f sql/ddl/00_all_kudu_tables_sit.sql

# Step 2 — Restore original SIT data (from Phase 0 backup)
spark-submit --master yarn --deploy-mode client \
  --jars <same jars> \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir /tmp/gmp_cis_sit_20260422_103000/
```

---

## How the Backup Scripts Work

Both backup scripts (`backup_sit_to_local.py`, `backup_uat_to_local.py`) are identical in design:

1. **Auto-discover tables** — `SHOW TABLES IN gmp_cis` via Impala JDBC (falls back to `spark.sql()`)
2. **Detect table type** — `DESCRIBE FORMATTED` per table → KUDU / HIVE / EXTERNAL
3. **Read data** — Kudu tables via Kudu Spark connector; Hive tables via `spark.sql()`
4. **Write Parquet** — one folder per table, `coalesce(1)` for single-file output
5. **Write manifest.json** — records timestamp, source env, table list, row counts
6. **Auto-copy HDFS → local** — `hdfs dfs -get`, then `tar -czf`
7. **Print SCP command** — ready-to-run command for the next step

### Script Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--kudu-master` | required | Kudu master host:port |
| `--impala-host` | required | Impala host for table discovery |
| `--impala-port` | 21050 | Impala port |
| `--output-dir` | `/tmp/uat_backup` | HDFS output directory |
| `--local-dir` | `/tmp` | Local dir for zip output |
| `--skip-tables` | none | Comma-separated tables to skip |
| `--no-zip` | false | Skip HDFS→local copy and zip |
| `--dry-run` | false | Discover + count rows, no write |

---

## Script Output Status Codes

| Status | Meaning |
|--------|---------|
| `SUCCESS` | Table backed up / restored with rows |
| `EMPTY` | Table exists but has 0 rows — empty Parquet written |
| `NOT_FOUND` | Table not found in Kudu or no backup folder found — **non-fatal, skipped** |
| `FAILED` | Unexpected error — **investigate before proceeding** |
| `DRY_RUN` | Dry run mode — no data written |

Scripts **never abort early** — all tables are attempted regardless of individual failures. A summary is printed at the end showing counts per status. Exit code is 1 if any FAILED tables exist.

---

## Cleanup After Successful Migration

```bash
# On UAT
rm -rf /tmp/gmp_cis_20260422_110000/
rm -f  /tmp/gmp_cis_20260422_110000.tar.gz
hdfs dfs -rm -r /tmp/uat_backup/gmp_cis_20260422_110000/

# On SIT
rm -rf /tmp/gmp_cis_20260422_110000/
rm -f  /tmp/gmp_cis_20260422_110000.tar.gz
hdfs dfs -rm -r /tmp/uat_restore/gmp_cis_20260422_110000/
# Keep Phase 0 SIT backup for 1 week, then:
hdfs dfs -rm -r /tmp/sit_backup/gmp_cis_sit_20260422_103000/
```
