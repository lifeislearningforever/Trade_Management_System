# GMP Data Sync Guide — Security, Party, Party CIF, Equity Price

**Database:** `gmp_cis` (Apache Kudu via Impala)
**Updated:** 2026-07-16

---

## Overview

GMP sends daily reference data feeds into Hive staging tables (`gmp_cis_sta_dly_*`).
These must be synced into the live CIS Kudu tables before EOD processing runs.

```
GMP daily feed (Hive staging)
    ↓
gmp_cis_sta_dly_*              ← GMP source tables (Hive, read-only)
    ↓  PySpark / Impala SQL
cis_security_kudu              ← Security master (Kudu)
cis_party                      ← Party / counterparty master (Kudu)
cis_party_cif                  ← Party CIF (Kudu)
cis_equity_price               ← Equity price feed (Kudu)
```

**Run order before EOD:**
```
1. Security sync   (merge_gmp_security.py)
2. Party sync      (impala-shell: gmp_to_cis_party_sync.sql)
3. Party CIF sync  (impala-shell: gmp_to_cis_party_cif_sync.sql)
4. Equity price    (merge_gmp_equity_price.py)
5. → EOD pipeline  (see EOD_PROCESSING_GUIDE.md)
```

---

## Prerequisites

```bash
# Activate virtual environment
source .venv/bin/activate

# Confirm Impala is reachable
python manage.py test_hive

# Confirm GMP staging tables have today's data
impala-shell -i $IMPALA_HOST:21050 -q "
  SELECT 'security'    AS feed, MAX(processing_date) AS latest FROM gmp_cis.stg_gmp_security_kudu
  UNION ALL
  SELECT 'party_cif',          MAX(processing_date)            FROM gmp_cis.gmp_cis_sta_dly_party_cif
  UNION ALL
  SELECT 'equity_price',       MAX(processing_date)            FROM gmp_cis.stg_gmp_equity_price
"
```

---

## Step 1 — Security Sync (`merge_gmp_security.py`)

**Source:** `gmp_cis.stg_gmp_security_kudu` (Hive staging, daily feed)
**Target:** `gmp_cis.cis_security_kudu` (Kudu live table)
**Registry:** `gmp_cis.cis_security_id_registry` + `gmp_cis.cis_security_id_counter`

Uses registry-based stable IDs — existing securities are updated in place, new ones
get a permanent 12-digit ID. CIS-created securities (`src_system='CIS'`) are never touched.

```bash
# Verify staging has data
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.stg_gmp_security_kudu"

# Run on edge node (yarn cluster mode)
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-memory 4g \
  --executor-cores 2 \
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  sql/pyspark/merge_gmp_security.py \
  --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \
  --batch-id BATCH_$(date +%Y%m%d)_001

# Verify
impala-shell -i $IMPALA_HOST:21050 -q "
  SELECT src_system, COUNT(*) AS cnt, MAX(updated_at) AS last_update
  FROM gmp_cis.cis_security_kudu
  GROUP BY src_system
"
```

---

## Step 2 — Party Sync

**Source:** `gmp_cis.gmp_cis_sta_dly_counterparty` (Hive staging)
**Target:** `gmp_cis.cis_party` (Kudu live table)

Party sync uses an Impala SQL INSERT (no PySpark needed). Replace the
`processing_date` value with the target date in `YYYYMMDD` format.

```bash
# Verify staging has data
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.gmp_cis_sta_dly_counterparty"

# Run sync — replace 20260302 with target date
impala-shell -i $IMPALA_HOST:21050 -d gmp_cis -q "
INSERT INTO cis_party (
    party_name, short_name, party_type,
    is_broker, is_custodian, is_active, is_deleted,
    src_system, src_id, processing_date,
    created_by, created_at, updated_by, updated_at
)
SELECT
    counterparty_name                           AS party_name,
    counterparty_short_name                     AS short_name,
    counterparty_type                           AS party_type,
    CASE WHEN UPPER(counterparty_type) IN ('BROKER','BROK') THEN TRUE ELSE FALSE END AS is_broker,
    CASE WHEN UPPER(counterparty_type) IN ('CUST','CUSTODIAN') THEN TRUE ELSE FALSE END AS is_custodian,
    TRUE                                        AS is_active,
    FALSE                                       AS is_deleted,
    'GMP'                                       AS src_system,
    'gmp_cis_sta_dly_counterparty'              AS src_id,
    processing_date,
    'GMP LOAD'                                  AS created_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())             AS created_at,
    'GMP LOAD'                                  AS updated_by,
    FROM_UNIXTIME(UNIX_TIMESTAMP())             AS updated_at
FROM (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY counterparty_name
        ORDER BY processing_date DESC
    ) AS rn
    FROM gmp_cis_sta_dly_counterparty
    WHERE processing_date = '20260302'
      AND UPPER(src_system) = 'GMP'
) t
WHERE rn = 1
"

# Verify
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT src_system, COUNT(*) FROM gmp_cis.cis_party GROUP BY src_system"
```

---

## Step 3 — Party CIF Sync (`gmp_to_cis_party_cif_sync.sql`)

**Source:** `gmp_cis.gmp_cis_sta_dly_party_cif` (Hive staging)
**Target:** `gmp_cis.cis_party_cif` (Kudu live table)

> **Note:** The `PARTITION BY` must be `(counterparty_cif_name, cif, counterparty_cif_country)` —
> NOT just `cif`. Using only `cif` collapses multi-country parties (e.g. "3M CO\*" with
> both SG m_label=4343 and MY m_label=4349) into one row, losing the other country.

Edit `sql/ddl/gmp_to_cis_party_cif_sync.sql` — replace the `processing_date` value:

```sql
-- Change this line in gmp_to_cis_party_cif_sync.sql:
WHERE processing_date = '20260302'   -- use YYYYMMDD format
```

Then run:

```bash
# Verify staging has data for the target date
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.gmp_cis_sta_dly_party_cif WHERE processing_date = '20260302'"

# Run the sync
impala-shell -i $IMPALA_HOST:21050 -d gmp_cis \
  -f sql/ddl/gmp_to_cis_party_cif_sync.sql

# Verify
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT src_system, COUNT(*) FROM gmp_cis.cis_party_cif GROUP BY src_system"
```

---

## Step 4 — Equity Price Sync (`merge_gmp_equity_price.py`)

**Source:** `gmp_cis.stg_gmp_equity_price` (Hive staging)
**Target:** `gmp_cis.cis_equity_price` (Kudu live table)

Composite PK: `(currency_code, security_label, price_date)` — pure UPSERT, no ID registry needed.

```bash
# Verify staging has data
impala-shell -i $IMPALA_HOST:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.stg_gmp_equity_price"

# Run on edge node (yarn cluster mode)
spark-submit \
  --master yarn \
  --deploy-mode cluster \
  --num-executors 4 \
  --executor-memory 4g \
  --executor-cores 2 \
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  sql/pyspark/merge_gmp_equity_price.py \
  --kudu-master kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251 \
  --batch-id BATCH_$(date +%Y%m%d)_001

# Verify
impala-shell -i $IMPALA_HOST:21050 -q "
  SELECT src_system, COUNT(*) AS cnt, MAX(price_date) AS latest_price_date
  FROM gmp_cis.cis_equity_price
  GROUP BY src_system
"
```

---

## Full Run — Copy-Paste Sequence

```bash
export TARGET_DATE=20260302   # YYYYMMDD
export KUDU_MASTER=kudu-master-1:7051,kudu-master-2:7151,kudu-master-3:7251
export IMPALA_HOST=your-impala-host

# ── Step 1: Security ─────────────────────────────────────────────────────────
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  sql/pyspark/merge_gmp_security.py \
  --kudu-master $KUDU_MASTER \
  --batch-id BATCH_${TARGET_DATE}_001

# ── Step 2: Party ─────────────────────────────────────────────────────────────
impala-shell -i $IMPALA_HOST:21050 -d gmp_cis -q "
INSERT INTO cis_party (party_name, short_name, party_type, is_broker, is_custodian,
    is_active, is_deleted, src_system, src_id, processing_date,
    created_by, created_at, updated_by, updated_at)
SELECT counterparty_name, counterparty_short_name, counterparty_type,
    CASE WHEN UPPER(counterparty_type) IN ('BROKER','BROK') THEN TRUE ELSE FALSE END,
    CASE WHEN UPPER(counterparty_type) IN ('CUST','CUSTODIAN') THEN TRUE ELSE FALSE END,
    TRUE, FALSE, 'GMP', 'gmp_cis_sta_dly_counterparty', processing_date,
    'GMP LOAD', FROM_UNIXTIME(UNIX_TIMESTAMP()), 'GMP LOAD', FROM_UNIXTIME(UNIX_TIMESTAMP())
FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY counterparty_name ORDER BY processing_date DESC) AS rn
      FROM gmp_cis_sta_dly_counterparty
      WHERE processing_date = '$TARGET_DATE' AND UPPER(src_system) = 'GMP') t
WHERE rn = 1
"

# ── Step 3: Party CIF ─────────────────────────────────────────────────────────
# Edit sql/ddl/gmp_to_cis_party_cif_sync.sql → set processing_date = '$TARGET_DATE'
impala-shell -i $IMPALA_HOST:21050 -d gmp_cis \
  -f sql/ddl/gmp_to_cis_party_cif_sync.sql

# ── Step 4: Equity Price ──────────────────────────────────────────────────────
spark-submit \
  --master yarn --deploy-mode cluster \
  --archives hdfs:///cis/spark/venvs/cis_etl_env.tar.gz#cis_etl_env \
  --conf spark.yarn.appMasterEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  --conf spark.executorEnv.PYSPARK_PYTHON=./cis_etl_env/bin/python3.10 \
  sql/pyspark/merge_gmp_equity_price.py \
  --kudu-master $KUDU_MASTER \
  --batch-id BATCH_${TARGET_DATE}_002

# ── Then run EOD pipeline (see EOD_PROCESSING_GUIDE.md) ──────────────────────
python manage.py sync_gmp_corporate_actions --date 2026-03-02
python manage.py process_corporate_actions  --date 2026-03-02
python manage.py process_approved_cashflows --date 2026-03-02
python manage.py refresh_positions
```

---

## GMP Source Tables Reference

| CIS Target Table      | GMP Source Table                        | Sync Method       |
|-----------------------|-----------------------------------------|-------------------|
| `cis_security_kudu`   | `stg_gmp_security_kudu`                 | PySpark           |
| `cis_party`           | `gmp_cis_sta_dly_counterparty`          | Impala SQL INSERT |
| `cis_party_cif`       | `gmp_cis_sta_dly_party_cif`             | Impala SQL INSERT |
| `cis_equity_price`    | `stg_gmp_equity_price`                  | PySpark           |
| `cis_corporate_actions` | `gmp_cis_sfa_dly_corporate_action`    | `sync_gmp_corporate_actions` management command |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `stg_gmp_security_kudu` empty | GMP ETL hasn't run yet | Wait for GMP ETL or check HDFS staging path |
| Security gets a new ID each run | Old truncate-reload approach | Use `merge_gmp_security.py` (registry-based) — never truncate `cis_security_kudu` |
| Party CIF missing country variants | Wrong `PARTITION BY cif` in sync SQL | Must use `PARTITION BY counterparty_cif_name, cif, counterparty_cif_country` |
| `libpython3.10.so.1.0: No such file` | Missing `.so` on YARN workers | See `SPARK_PYTHON_VENV_CLUSTER_MODE.md` → Troubleshooting |
| Equity price not reflecting in EOD reval | `stg_gmp_equity_price` synced after `refresh_positions` ran | Always run equity price sync **before** `refresh_positions` |
| Party not appearing in trade dropdown | `cis_party.is_broker` or `is_custodian` not set | Check `counterparty_type` mapping in the Party sync INSERT |
