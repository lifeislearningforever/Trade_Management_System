# CIS Trade Hive — Migration Runbook
## UAT ↔ SIT Data Migration via SFTP (No distcp)

---

## Overview

```
SIT HDFS  →  SIT local  →  tar.gz  →  sftp/scp  →  UAT local  →  UAT HDFS  →  Spark restore → UAT Kudu
```

---

## Prerequisites

- Spark jars available at:
  - `/app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar`
  - `/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar`
  - `/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar`
- SSH/SFTP access between SIT and UAT servers
- Sufficient local disk space on both servers (check: `df -h /tmp`)
- Sufficient HDFS space (check: `hdfs dfs -df -h /tmp`)

---

## PHASE 0 — Backup SIT before migration (rollback safety net)

> Run this FIRST before making any changes to SIT.

```bash
# On SIT CML — backup all SIT tables to HDFS
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/backup_sit_to_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --output-dir /tmp/sit_backup

# Note the output path printed at end of script, e.g.:
#   /tmp/sit_backup/gmp_cis_sit_20260422_103000/
```

---

## PHASE 1 — Backup UAT (source data)

```bash
# On UAT CML — backup all UAT tables to HDFS
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/backup_uat_to_local.py \
  --kudu-master <uat-kudu-master>:7051 \
  --output-dir /tmp/uat_backup

# Note the output path, e.g.:
#   /tmp/uat_backup/gmp_cis_20260422_110000/
```

---

## PHASE 2 — Copy UAT backup from HDFS to UAT local disk

```bash
# On UAT server
hdfs dfs -ls /tmp/uat_backup/
# confirms e.g. gmp_cis_20260422_110000/

hdfs dfs -get /tmp/uat_backup/gmp_cis_20260422_110000/ /tmp/gmp_cis_20260422_110000/

# Verify all table folders present
ls -1 /tmp/gmp_cis_20260422_110000/

# Check disk usage
du -sh /tmp/gmp_cis_20260422_110000/
```

---

## PHASE 3 — Zip on UAT

```bash
# On UAT server
cd /tmp
tar -czf gmp_cis_20260422_110000.tar.gz gmp_cis_20260422_110000/

# Verify size
ls -lh /tmp/gmp_cis_20260422_110000.tar.gz
```

---

## PHASE 4 — SFTP / SCP to SIT

### Option A — SCP (simpler)
```bash
# On UAT server — push to SIT
scp /tmp/gmp_cis_20260422_110000.tar.gz \
    <your-username>@<sit-host>:/tmp/
```

### Option B — SFTP (interactive)
```bash
# On UAT server
sftp <your-username>@<sit-host>

sftp> cd /tmp
sftp> put gmp_cis_20260422_110000.tar.gz
sftp> ls -lh gmp_cis_20260422_110000.tar.gz
sftp> exit
```

### Verify transfer on SIT
```bash
# On SIT server
ls -lh /tmp/gmp_cis_20260422_110000.tar.gz
```

---

## PHASE 5 — Extract on SIT

```bash
# On SIT server
cd /tmp
tar -xzf gmp_cis_20260422_110000.tar.gz

# Verify all table folders are there
ls -1 /tmp/gmp_cis_20260422_110000/

# Check disk usage
du -sh /tmp/gmp_cis_20260422_110000/
```

---

## PHASE 6 — Push from SIT local disk → SIT HDFS

```bash
# On SIT server
hdfs dfs -mkdir -p /tmp/uat_restore/

hdfs dfs -put /tmp/gmp_cis_20260422_110000/ /tmp/uat_restore/

# Verify
hdfs dfs -ls /tmp/uat_restore/gmp_cis_20260422_110000/
hdfs dfs -du -h /tmp/uat_restore/gmp_cis_20260422_110000/
```

---

## PHASE 7 — Clean SIT schema

> This drops all existing SIT tables and data. Phase 0 backup must be done first.

```bash
# On SIT server
impala-shell -i <sit-impala-host>:21050 \
  -f sql/ddl/99_sit_clean_gmp_cis.sql

# Recreate fresh schema
impala-shell -i <sit-impala-host>:21050 \
  -f sql/ddl/00_all_kudu_tables_sit.sql
```

---

## PHASE 8 — Restore UAT data into SIT Kudu

### Dry run first (validate parquet files, no writes)
```bash
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir hdfs:///tmp/uat_restore/gmp_cis_20260422_110000/ \
  --dry-run
```

### Full restore from HDFS path
```bash
spark-submit \
  --master yarn --deploy-mode client \
  --driver-memory 4g \
  --executor-memory 4g \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir hdfs:///tmp/uat_restore/gmp_cis_20260422_110000/
```

### Alternative — restore directly from local disk (skip HDFS step)
```bash
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir /tmp/gmp_cis_20260422_110000/
```

---

## ROLLBACK — If migration fails

```bash
# Step 1 — Drop and recreate SIT schema
impala-shell -i <sit-impala-host>:21050 -f sql/ddl/99_sit_clean_gmp_cis.sql
impala-shell -i <sit-impala-host>:21050 -f sql/ddl/00_all_kudu_tables_sit.sql

# Step 2 — Copy SIT backup from HDFS to local (from Phase 0)
hdfs dfs -get /tmp/sit_backup/gmp_cis_sit_20260422_103000/ /tmp/gmp_cis_sit_20260422_103000/

# Step 3 — Restore original SIT data
spark-submit \
  --master yarn --deploy-mode client \
  --jars /app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar,/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar,/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar \
  scripts/restore_sit_from_local.py \
  --kudu-master <sit-kudu-master>:7051 \
  --backup-dir /tmp/gmp_cis_sit_20260422_103000/
```

---

## Cleanup (after successful migration)

```bash
# On UAT — remove local and HDFS temp files
rm -rf /tmp/gmp_cis_20260422_110000/
rm -f  /tmp/gmp_cis_20260422_110000.tar.gz
hdfs dfs -rm -r /tmp/uat_backup/gmp_cis_20260422_110000/

# On SIT — remove local and HDFS temp files
rm -rf /tmp/gmp_cis_20260422_110000/
rm -f  /tmp/gmp_cis_20260422_110000.tar.gz
hdfs dfs -rm -r /tmp/uat_restore/gmp_cis_20260422_110000/
# Keep Phase 0 SIT backup for 1 week as safety net, then:
hdfs dfs -rm -r /tmp/sit_backup/gmp_cis_sit_20260422_103000/
```

---

## Quick Reference — Script Summary

| Script | Purpose | Run on |
|--------|---------|--------|
| `backup_sit_to_local.py` | Backup SIT Kudu → HDFS (rollback safety net) | SIT |
| `backup_uat_to_local.py` | Backup UAT Kudu → HDFS (source data) | UAT |
| `restore_sit_from_local.py` | Restore Parquet (HDFS or local) → target Kudu | SIT or UAT |
| `sql/ddl/99_sit_clean_gmp_cis.sql` | Drop all SIT tables + database | SIT |
| `sql/ddl/00_all_kudu_tables_sit.sql` | Recreate SIT schema | SIT |

## Status codes in script output

| Status | Meaning |
|--------|---------|
| `SUCCESS` | Table backed up / restored with rows |
| `EMPTY` | Table exists but has 0 rows |
| `NOT_FOUND` | Table not in Kudu / no backup found — skipped, non-fatal |
| `FAILED` | Unexpected error — investigate before proceeding |
| `DRY_RUN` | Dry run mode — no data written |
