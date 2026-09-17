# CIS Trade Hive — Control-M EOD & CORR Job Schedule

**Version:** 1.0  
**Updated:** 2026-07-02  
**Audience:** System Analysts / Operations  
**Database:** `gmp_cis` (Apache Kudu via Impala)

---

## Overview

Two run-type schedules exist:

| Schedule | Trigger | position_date | position_type written |
|---|---|---|---|
| **EOD** | Every business day | `reporting_date` (T-1, from alldatesinfo) | `SOD`, `INT`, `EOD` |
| **CORR** | Month-end +1 … +5 business days | `last_month_end` (last calendar day of prior month) | `INT` (by cashflows), `CORR` (by reval) |

Date source: `gmp_cis_sta_dly_alldatesinfo`  
Filter: `src_system='gmp', sub_system='cis', data_frq='dly', record_type='D'`  
- `prev_day` → `reporting_date` (used for EOD)  
- `last_month_end` → computed in Python as `(first_of_ref_month − 1 day)`

---

## EOD Wave Structure

```
Wave 0   Pre-flight checks
Wave 1   Reference data sync        (GMP CA sync)
Wave 2   CA cash flow generation    (process_corporate_actions)
Wave 3   Cash flow application      (process_approved_cashflows)
Wave 4   EOD position revaluation   (refresh_positions)
Wave 5   SOD snapshot               (create_sod_snapshot)  — next business day prep
```

Each wave must complete (exit code 0) before the next starts.

---

## Job Definitions

### Wave 0 — Pre-flight

#### JOB: CIS_PREFLIGHT_CHECK

**Purpose:** Verify Impala connection is healthy before any data jobs run.

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py test_hive
```

**Dependencies:** None — first job in chain  
**On failure:** Abort entire EOD wave  
**Schedule:** Daily, before Wave 1

---

#### JOB: CIS_VERIFY_PRICES

**Purpose:** Check that equity prices and FX rates are loaded for today before reval runs.

```sql
-- Run via impala-shell; fail if count = 0
impala-shell -i ${IMPALA_HOST}:${IMPALA_PORT} -q \
  "SELECT COUNT(*) FROM gmp_cis.cis_equity_price WHERE is_active = true AND price_date = '${REPORTING_DATE}'" \
  --quiet

impala-shell -i ${IMPALA_HOST}:${IMPALA_PORT} -q \
  "SELECT COUNT(*) FROM gmp_cis.gmp_cis_sta_dly_fx_rates WHERE as_of_date = '${REPORTING_DATE}'" \
  --quiet
```

**Dependencies:** CIS_PREFLIGHT_CHECK  
**On failure:** Alert ops team; do not proceed to Wave 4  
**Schedule:** Daily, before refresh_positions

---

### Wave 1 — GMP CA Sync

#### JOB: CIS_SYNC_GMP_CA

**Purpose:** Pull new corporate actions from GMP source table into CIS and queue them for cash flow generation.

**Command:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py sync_gmp_corporate_actions
```

**Key arguments:**

| Argument | Description | Example |
|---|---|---|
| *(none)* | Standard run — sync all unprocessed for today | `sync_gmp_corporate_actions` |
| `--date YYYY-MM-DD` | Sync a specific processing date only | `--date 2026-06-30` |
| `--full-sync` | Re-sync all records ignoring duplicate check | `--full-sync` |
| `--batch-size N` | Records per Impala write batch (default: 500) | `--batch-size 1000` |
| `--verbose` | Per-record logging | `--verbose` |
| `--dry-run` | Preview without writing | `--dry-run` |

**Prerequisite:** GMP ETL job must have populated `gmp_cis_sfa_dly_corporate_action`

**Tables touched:**

| Table | Operation |
|---|---|
| `gmp_cis_sfa_dly_corporate_action` | READ |
| `cis_corporate_actions` | UPSERT (new GMP CAs, `src_system='GMP'`, `status='VALIDATED'`) |
| `cis_ca_cash_flow_queue` | INSERT (PENDING entries for DIVIDEND, INTEREST, COUPON, ROC, BONUS_ISSUE, SPLIT, RIGHTS types) |

**Dependencies:** CIS_PREFLIGHT_CHECK, GMP_ETL_COMPLETE  
**On failure:** Alert ops; Wave 2 will find no pending queue entries  
**Idempotency:** Skips `ca_number` values already synced (`GMP-<ca_id>` prefix); `--full-sync` to override

---

### Wave 2 — CA Cash Flow Processing

#### JOB: CIS_PROCESS_CA

**Purpose:** Generate one `cis_cash_flow` record per portfolio holding a security for each pending CA in the queue.

**Command:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py process_corporate_actions
```

**Key arguments:**

| Argument | Description | Example |
|---|---|---|
| *(none)* | Standard run — process all PENDING queue entries | `process_corporate_actions` |
| `--status` | Show queue status counts without processing | `--status` |
| `--reset-stuck` | Reset PROCESSING entries stuck from a prior crashed run | `--reset-stuck` |
| `--retry-failed` | Retry FAILED entries (retry_count < 3) | `--retry-failed` |
| `--date YYYY-MM-DD` | Filter by CA payment date | `--date 2026-06-30` |
| `--ca-id ID` | Process a single CA by ID | `--ca-id 123456` |
| `--queue-id ID` | Process a single queue entry by ID | `--queue-id 789` |
| `--batch-size N` | Queue entries per batch (default: 100) | `--batch-size 200` |
| `--verbose-output` | Per-record logging | `--verbose-output` |
| `--dry-run` | Preview without writing | `--dry-run` |

**Queue status flow:** `PENDING → PROCESSING → COMPLETED` (or `FAILED`, retried up to 3×)

**Tables touched:**

| Table | Operation |
|---|---|
| `cis_ca_cash_flow_queue` | READ PENDING → UPDATE status PROCESSING → COMPLETED/FAILED |
| `cis_cash_flow` | INSERT (one per portfolio × security holding) |

**Dependencies:** CIS_SYNC_GMP_CA  
**On failure:** Re-run with `--retry-failed`; entries stuck in PROCESSING → re-run with `--reset-stuck` first  
**Idempotency:** Skips if cash flow already exists for same `ca_id + portfolio + security`

---

### Wave 3 — Cash Flow Application

#### JOB: CIS_PROCESS_CASHFLOWS

**Purpose:** Apply APPROVED cash flows to the current open SETTLED position in `cis_trade_position` and write `INT` rows to `cis_position`.

**Command — EOD:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py process_approved_cashflows --run-type EOD
```

**Command — CORR (month-end correction):**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py process_approved_cashflows --run-type CORR
```

**Key arguments:**

| Argument | Values / Default | Description |
|---|---|---|
| `--run-type` | `EOD` (default) \| `CORR` | EOD uses reporting_date; CORR uses last_month_end |
| `--position-date` | `YYYY-MM-DD` (optional) | Override inferred date; use for manual recovery runs |
| `--portfolio` | Short name string | Limit to one portfolio |
| `--reprocess` | flag | Re-apply already-processed CFs (corrections only — use with caution) |
| `--dry-run` | flag | Preview without writing |

**Date inference (when `--position-date` not set):**

| run-type | CF cutoff date | Position lookup date |
|---|---|---|
| `EOD` | `reporting_date` (T-1 from alldatesinfo) | `reporting_date` |
| `CORR` | `last_month_end` (Python: first_of_month − 1 day) | `last_month_end` |

**Always writes `position_type = 'INT'`** in both `cis_trade_position` and `cis_position` regardless of run type. The CORR label is applied by `refresh_positions`.

**Tables touched:**

| Table | Operation |
|---|---|
| `cis_cash_flow` | READ (APPROVED, `position_updated=false`, `payment_date <= run_date`), UPDATE `position_updated=true` |
| `cis_trade_position` | Mark old `is_latest=false`, UPSERT new version |
| `cis_position` | UPSERT (`position_type='INT'`) |

**Dependencies:** CIS_PROCESS_CA  
**On failure:** Re-run safely (idempotent — already-processed records skipped via `position_updated` flag)

---

### Wave 4 — EOD Position Revaluation

#### JOB: CIS_REFRESH_POSITIONS

**Purpose:** Fetch all open positions from `cis_position` (all sources), revalue with latest closing price and FX rates, write `EOD` (or `CORR`) rows back.

**Command — EOD:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py refresh_positions --run-type EOD
```

**Command — CORR (month-end correction):**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py refresh_positions --run-type CORR
```

**Key arguments:**

| Argument | Values / Default | Description |
|---|---|---|
| `--run-type` | `EOD` (default) \| `CORR` | EOD → `position_type='EOD'`; CORR → `position_type='CORR'` |
| `--position-date` | `YYYY-MM-DD` (optional) | Override inferred date; use for manual recovery |
| `--portfolio` | Short name string | Limit to one portfolio |
| `--source` | `CIS` \| `GMP` \| `AMSICEQ` \| `USER_UPLOAD` | Limit to one source system |
| `--dry-run` | flag | Preview without writing |

**Date inference (when `--position-date` not set):**

| run-type | position_date used | position_type written |
|---|---|---|
| `EOD` | `reporting_date` (T-1 from alldatesinfo) | `EOD` |
| `CORR` | `last_month_end` (first_of_month − 1 day) | `CORR` |

**Price lookup order per position:**

```
1. cis_equity_price WHERE security_label = ? AND is_active = true
                    ORDER BY price_date DESC, price_timestamp DESC  LIMIT 1
2. Carry forward existing market_value_fc (no price found — logged as warning)
```

**Revaluation cases:**

| Case | Condition | LC cost treatment | unrealized_pnl |
|---|---|---|---|
| A — Revalued portfolio, normal security | `portfolio.revalued = true`, not ASSOC/SUBSI | Recalculated: `cost_fc × fx_rate` | `market_value_fc − cost_fc` |
| B — Non-revalued portfolio, normal security | `portfolio.revalued = false`, not ASSOC/SUBSI | Carried forward from source | `market_value_fc − cost_fc` |
| C — Equity-method security | `security_investment IN ('ASSOC','SUBSI')` | Per case A/B | **0** (no MTM P&L) |
| D — No price available | Price not in `cis_equity_price` | Per case A/B | Calculated using carried-forward `market_value_fc` |

**Tables touched:**

| Table | Operation |
|---|---|
| `cis_position` | READ (latest row per portfolio/security/basis/date), DELETE old EOD/CORR row, INSERT new EOD/CORR row |
| `cis_equity_price` | READ (latest closing price) |
| `cis_security_kudu` | READ (`security_investment` for equity-method check) |
| `gmp_cis_sta_dly_fx_rates` | READ (FC→LC spot rate) |
| `gmp_cis_sta_dly_currency` | READ (decimal precision per currency) |

**Dependencies:** CIS_PROCESS_CASHFLOWS, CIS_VERIFY_PRICES  
**On failure:** Re-run safely — DELETE + INSERT pattern means re-run overwrites previous EOD/CORR row

---

### Wave 5 — SOD Snapshot

#### JOB: CIS_CREATE_SOD_SNAPSHOT

**Purpose:** Create Start-of-Day position rows for the next business day by copying previous EOD rows and applying any settlement queue entries with `settle_date = today`.

**Command:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py create_sod_snapshot
```

**Key arguments:**

| Argument | Values / Default | Description |
|---|---|---|
| `--portfolio` | Short name string | Limit to one portfolio |
| `--source` | `CIS` \| `GMP` \| `AMSICEQ` \| `USER_UPLOAD` | Limit to one source system |
| `--dry-run` | flag | Preview without writing |

**Date logic (from alldatesinfo):**

| Column | Value | Used for |
|---|---|---|
| `prev_day` | T-1 (reporting_date) | Source: find EOD rows with this `position_date` |
| `contextual_today` | Today's business date | Output: SOD rows get this as `position_date` |

**What is written:**

1. Load all `position_type = 'EOD'` rows where `position_date = prev_day`
2. Apply any `cis_settlement_queue` entries with `settle_date = contextual_today`
3. Write merged result as `position_type = 'SOD'` with `position_date = contextual_today`
4. Mark processed settlement queue entries as `COMPLETED`

**Tables touched:**

| Table | Operation |
|---|---|
| `cis_position` | READ (EOD rows for prev_day), INSERT (SOD rows for contextual_today) |
| `cis_settlement_queue` | READ (settle_date = today), UPDATE → `COMPLETED` |
| `gmp_cis_sta_dly_alldatesinfo` | READ (prev_day, contextual_today) |

**Dependencies:** CIS_REFRESH_POSITIONS  
**On failure:** Re-run safely (settlement queue entries idempotent via status flag)  
**Schedule:** Runs after Wave 4; must complete before trading opens next morning

---

### Additional EOD Jobs (Non-wave / Parallel)

#### JOB: CIS_PROCESS_SETTLEMENTS (parallel to Wave 3)

**Purpose:** Process T+1/T+2 trades from `cis_settlement_queue` that mature today (settle_date = today). Runs in parallel with cash flow application, before SOD snapshot.

**Command:**

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py process_settlements
```

**Key arguments:**

| Argument | Values / Default | Description |
|---|---|---|
| `-d` / `--date` | `YYYY-MM-DD` (default: today) | Settlement date to process |
| `-n` / `--dry-run` | flag | Preview without writing |
| `-v` / `--verbose` | flag | Verbose logging |
| `--user` | String (default: `SYSTEM`) | User label for audit log |
| `--batch-size` | Integer (default: 100) | Queue entries per batch |

**Tables touched:**

| Table | Operation |
|---|---|
| `cis_settlement_queue` | READ (settle_date = today, status PENDING), UPDATE → COMPLETED |
| `cis_trade_position` | UPSERT (settled position versions) |

**Dependencies:** CIS_PROCESS_CA (Wave 2)  
**Schedule:** Daily, parallel to Wave 3 (process_approved_cashflows)

---

## CORR Run Schedule

The CORR run replays cash flow application and position revaluation for `last_month_end`. Scheduled D+1 to D+5 after month-end to allow late GMP data to flow through.

### CORR Wave Structure

```
Wave C1   CORR Cash Flow Application   (process_approved_cashflows --run-type CORR)
Wave C2   CORR Position Revaluation    (refresh_positions --run-type CORR)
```

### CORR Job: CIS_CORR_PROCESS_CASHFLOWS

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py process_approved_cashflows --run-type CORR
```

**position_date:** Inferred as last calendar day of prior month (Python: `first_of_ref_month − 1 day`)  
**Override:** `--position-date 2026-05-31`  
**position_type written:** `INT`

---

### CORR Job: CIS_CORR_REFRESH_POSITIONS

```bash
cd /opt/cis_trade_hive
source .venv/bin/activate
python manage.py refresh_positions --run-type CORR
```

**position_date:** Same last_month_end as above  
**Override:** `--position-date 2026-05-31`  
**position_type written:** `CORR`

---

## Full EOD Dependency Chain

```
GMP_ETL_COMPLETE
        │
        ▼
CIS_PREFLIGHT_CHECK
        │
        ├──────────────────────────┐
        ▼                          ▼
CIS_SYNC_GMP_CA           CIS_VERIFY_PRICES
        │                          │
        ▼                          │
CIS_PROCESS_CA             ┌───────┘
        │                  │
        ├──────────────────┤
        ▼                  ▼
CIS_PROCESS_CASHFLOWS    CIS_PROCESS_SETTLEMENTS
        │                  │
        └──────────┬────────┘
                   ▼
        CIS_REFRESH_POSITIONS
                   │
                   ▼
        CIS_CREATE_SOD_SNAPSHOT
```

---

## Control-M Parameter Variables

Define these as global Control-M variables for all CIS jobs:

| Variable | Description | Example |
|---|---|---|
| `%%IMPALA_HOST` | Impala coordinator host | `localhost` / Cloudera CML host |
| `%%IMPALA_PORT` | Impala port | `21050` |
| `%%CIS_APP_DIR` | Application root directory | `/opt/cis_trade_hive` |
| `%%REPORTING_DATE` | T-1 business date (YYYY-MM-DD) | `2026-06-30` |
| `%%RUN_TYPE` | `EOD` or `CORR` | `EOD` |

These are **reference-only** — the management commands infer `REPORTING_DATE` automatically from `gmp_cis_sta_dly_alldatesinfo`. Pass `--position-date` only for manual override / recovery runs.

---

## Recovery / Manual Run Procedures

### Re-run a single stage for one portfolio

```bash
# Re-run cash flow application for one portfolio only
python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING

# Re-run reval for one portfolio only
python manage.py refresh_positions --portfolio UOB-SG-TRADING

# Re-run reval for one source only
python manage.py refresh_positions --source AMSICEQ
```

### Re-sync GMP CAs for a specific date

```bash
python manage.py sync_gmp_corporate_actions --date 2026-06-30
```

### Force full GMP re-sync (ignore duplicate check)

```bash
python manage.py sync_gmp_corporate_actions --full-sync
```

### Retry failed CA queue entries

```bash
python manage.py process_corporate_actions --retry-failed
```

### Reset stuck CA queue entries (previous crash)

```bash
python manage.py process_corporate_actions --reset-stuck
python manage.py process_corporate_actions
```

### Backdate cash flow processing

```bash
python manage.py process_approved_cashflows --position-date 2026-06-01
```

### Manual override of CORR position date

```bash
python manage.py process_approved_cashflows --run-type CORR --position-date 2026-05-31
python manage.py refresh_positions --run-type CORR --position-date 2026-05-31
```

### Re-apply already-processed cash flows (corrections)

```bash
python manage.py process_approved_cashflows --reprocess --portfolio UOB-SG-TRADING
```

---

## Pre-run Verification Checklist

Before each EOD run, verify:

```sql
-- 1. Alldatesinfo has today's row
SELECT prev_day, contextual_today
FROM gmp_cis.gmp_cis_sta_dly_alldatesinfo
WHERE src_system = 'gmp' AND sub_system = 'cis'
  AND data_frq = 'dly' AND record_type = 'D';

-- 2. Equity prices loaded for reporting date
SELECT COUNT(*), MAX(price_date)
FROM gmp_cis.cis_equity_price
WHERE is_active = true;

-- 3. FX rates loaded for reporting date
SELECT COUNT(*), MAX(as_of_date)
FROM gmp_cis.gmp_cis_sta_dly_fx_rates;

-- 4. GMP CA source table has today's data
SELECT COUNT(*), MAX(processing_date)
FROM gmp_cis.gmp_cis_sfa_dly_corporate_action;

-- 5. CA queue status (should have PENDING entries if CAs exist today)
SELECT status, COUNT(*) FROM gmp_cis.cis_ca_cash_flow_queue GROUP BY status;

-- 6. Unprocessed approved cash flows
SELECT COUNT(*) FROM gmp_cis.cis_cash_flow
WHERE status = 'APPROVED'
  AND (position_updated = false OR position_updated IS NULL);
```

---

## Post-run Verification Checklist

After EOD completes, verify:

```sql
-- EOD rows written today
SELECT src_system, COUNT(*) AS positions_revalued
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND processing_date = CURRENT_DATE()
GROUP BY src_system;

-- INT rows written by cashflow processing
SELECT COUNT(*) FROM gmp_cis.cis_position
WHERE position_type = 'INT'
  AND position_date = CURRENT_DATE();

-- All approved CFs processed (should be 0)
SELECT COUNT(*) FROM gmp_cis.cis_cash_flow
WHERE status = 'APPROVED'
  AND (position_updated = false OR position_updated IS NULL)
  AND payment_date <= CURRENT_DATE();

-- SOD rows for tomorrow
SELECT COUNT(*) FROM gmp_cis.cis_position
WHERE position_type = 'SOD';

-- Any CA queue failures
SELECT status, COUNT(*) FROM gmp_cis.cis_ca_cash_flow_queue
WHERE DATE(created_at) = CURRENT_DATE() GROUP BY status;
```

---

## Indicative Schedule (Control-M Times)

| Time | Job | Wave |
|---|---|---|
| 17:30 | GMP_ETL_COMPLETE (external dependency) | — |
| 17:45 | CIS_PREFLIGHT_CHECK | 0 |
| 17:50 | CIS_VERIFY_PRICES | 0 |
| 18:00 | CIS_SYNC_GMP_CA | 1 |
| 18:15 | CIS_PROCESS_CA | 2 |
| 18:30 | CIS_PROCESS_CASHFLOWS (EOD) | 3 |
| 18:30 | CIS_PROCESS_SETTLEMENTS (parallel) | 3 |
| 18:45 | CIS_REFRESH_POSITIONS (EOD) | 4 |
| 19:00 | CIS_CREATE_SOD_SNAPSHOT | 5 |

**CORR schedule (month-end +1 to +5, scheduled at same times as EOD):**

| Time | Job | Wave |
|---|---|---|
| 18:30 | CIS_CORR_PROCESS_CASHFLOWS | C1 |
| 18:45 | CIS_CORR_REFRESH_POSITIONS | C2 |

Times are indicative — adjust based on upstream GMP ETL completion SLA.

---

## Key Tables Reference

| Table | Role | Populated by |
|---|---|---|
| `gmp_cis_sta_dly_alldatesinfo` | Business date reference (prev_day, contextual_today) | GMP ETL (external) |
| `gmp_cis_sfa_dly_corporate_action` | GMP CA source feed | GMP ETL (external) |
| `gmp_cis_sta_dly_fx_rates` | FX spot rates | Market data ETL (external) |
| `gmp_cis_sta_dly_currency` | Currency decimal precision | Reference data load |
| `cis_equity_price` | Closing prices | Market data load jobs |
| `cis_corporate_actions` | CA master — all sources | `sync_gmp_corporate_actions`, CIS UI |
| `cis_ca_cash_flow_queue` | CA processing queue | `sync_gmp_corporate_actions`, `ca_cash_flow_service` |
| `cis_cash_flow` | Cash flow ledger | `process_corporate_actions`, UI |
| `cis_trade_position` | CIS versioned ledger (BUY/SELL/CF history) | `position_service`, `process_approved_cashflows` |
| `cis_settlement_queue` | T+1/T+2 settlement queue | `position_service` (on trade creation) |
| `cis_position` | **Golden copy — all sources** | `refresh_positions`, `create_sod_snapshot`, upload jobs |
| `cis_security_kudu` | Security master (incl. equity-method flag) | Security module |

---

## Position Type Reference

| `position_type` | Written by | Description |
|---|---|---|
| `SOD` | `create_sod_snapshot` | Start-of-day snapshot (prev EOD + today's settlements) |
| `INT` | `process_approved_cashflows`, trade processing | Intraday after cash flow application |
| `EOD` | `refresh_positions --run-type EOD` | End-of-day revalued snapshot |
| `CORR` | `refresh_positions --run-type CORR` | Month-end correction revaluation |
