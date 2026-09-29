# CIS Trade Hive — EOD Processing Guide

**Version:** 1.2  
**Updated:** 2026-07-16  
**Database:** `gmp_cis` (Apache Kudu via Impala)

---

## Overview

The EOD (End of Day) process runs in six sequential stages every business day:

```
Stage 0: GMP CA Sync        → pull corporate actions from GMP source table into CIS
Stage 1: CA Processing      → generate cash flows from queued CA events
Stage 2: Cash Flow Apply    → apply approved cash flows to positions
Stage 3: Trade Settlement   → process T+1/T+2 trades settling today into cis_trade_position
Stage 4: Position Reval     → refresh market values in cis_position (golden copy)
Stage 5: SOD Snapshot       → copy today's EOD rows forward as tomorrow's start-of-day
```

Each stage must complete successfully before the next begins.  
All stages support `--dry-run` for safe preview before writing.

> **Date note:** Stages 2, 3, 4 and 5 infer the target date from `gmp_cis_sta_dly_alldatesinfo`
> when no date is supplied. For backdated / manual runs always pass the date flag explicitly
> (see [Manual / Backdated EOD Run](#manual--backdated-eod-run)).

### Full pipeline

```
GMP ETL job
    ↓
gmp_cis_sfa_dly_corporate_action          ← GMP source table
    ↓  sync_gmp_corporate_actions
cis_corporate_actions                     src_system='GMP', status='VALIDATED'
    ↓  (also: CA created via CIS UI)      src_system='CIS', status='APPROVED'
cis_ca_cash_flow_queue                    status='PENDING'
    ↓  process_corporate_actions
cis_cash_flow                             one entry per portfolio holding the security
    ↓  process_approved_cashflows
cis_trade_position                        new version row per cash flow applied
    ↓  process_settlements
cis_trade_position                        T+1/T+2 settled trades applied to CIS ledger
    ↓  refresh_positions
cis_position  (golden copy)               position_type='EOD', all sources revalued
    ↓  create_sod_snapshot
cis_position                              position_type='SOD', ready for next business day
```

---

## Golden Copy — `cis_position`

`cis_position` is the **single source of truth** for all position data across all source systems.

| `src_system` | Origin |
|---|---|
| `CIS` | Internal trades entered via CIS Trade Hive |
| `GMP` | Global Markets Platform (external feed) |
| `AMSICEQ` | AMS equity positions (uploaded via `upload_amsiceq_positions`) |
| `USER_UPLOAD` | Manual position uploads via the Upload UI |

`cis_trade_position` is the **working ledger** used by `position_service.py` during trade processing. After settlement, positions are synced into `cis_position`. The EOD reval operates only on `cis_position`.

---

## Stage 0 — GMP Corporate Action Sync (`sync_gmp_corporate_actions`)

### What it does

Reads new corporate action records from the GMP source table (`gmp_cis_sfa_dly_corporate_action`), maps GMP CA types to CIS CA types, inserts them into `cis_corporate_actions` with `status='VALIDATED'` (bypasses four-eyes — GMP records are pre-validated), and immediately queues them in `cis_ca_cash_flow_queue` for cash flow generation.

### Prerequisite

The GMP ETL job must have run and populated `gmp_cis_sfa_dly_corporate_action` before this step.

```sql
-- Verify GMP source table has data
SELECT COUNT(*), MAX(processing_date)
FROM gmp_cis.gmp_cis_sfa_dly_corporate_action;
```

### GMP CA type mapping

GMP uses free-text CA type codes. This command maps them to CIS standard types:

| GMP type (raw) | CIS `ca_type` |
|---|---|
| `cash dividend`, `dividend`, `div`, `d` | `DIVIDEND` |
| `special dividend`, `special div`, `clas sp` | `SPECIAL_DIVIDEND` |
| `interest`, `i` | `INTEREST` |
| `coupon`, `coupon payment`, `c` | `COUPON` |
| `roc`, `return of capital` | `ROC` |
| `capital distribution` | `CAPITAL_DISTRIBUTION` |
| `capital reduction`, `cap reduction`, `cap red` | `CAPITAL_REDUCTION` |
| `bonus issue`, `bonus`, `b` | `BONUS_ISSUE` |
| `stock split`, `split`, `s` | `SPLIT` |
| `reverse split`, `consolidation` | `REVERSE_SPLIT` / `CONSOLIDATION` |
| `rights issue`, `rights entitlement`, `rights`, `r` | `RIGHTS_ENTITLEMENT` |
| `warrant`, `warrant entitlement` | `WARRANT_ENTITLEMENT` |
| `merger`, `scheme of arrangement` | `MERGER` |
| `acquisition`, `takeover` | `ACQUISITION` |
| `redemption`, `maturity`, `full redemption`, `partial redemption` | `REDEMPTION` |

**Unknown type?** The record is skipped with a warning:
```
[INVALID] Skipping GMP-4521: unknown ca_type='NEW TYPE'. Add it to GMP_CA_TYPE_MAP.
```
Fix: add the mapping in `reference_data/management/commands/sync_gmp_corporate_actions.py`:
```python
GMP_CA_TYPE_MAP = {
    ...
    'new type': 'DIVIDEND',   # add here
}
```

### CA types that get queued for cash flow processing

| Category | Types |
|---|---|
| Cash flow generation | `DIVIDEND`, `SPECIAL_DIVIDEND`, `ROC`, `INTEREST`, `COUPON` |
| Position adjustment | `BONUS_ISSUE`, `SPLIT`, `RIGHTS_ENTITLEMENT`, `WARRANT_ENTITLEMENT` |
| All others | Inserted into `cis_corporate_actions` but NOT queued |

### Duplicate handling

`ca_number` is built as `GMP-<gmp_ca_id>` (e.g. `GMP-4521`). On each run, already-synced `ca_number` values (where `src_system='GMP'`) are loaded first and skipped. Use `--full-sync` to re-process all regardless.

### Command

```bash
# Verify GMP source has data first
impala-shell -i localhost:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.gmp_cis_sfa_dly_corporate_action"

# Preview — always run first
python manage.py sync_gmp_corporate_actions --dry-run --verbose

# Standard run — sync all unprocessed
python manage.py sync_gmp_corporate_actions

# Sync a specific processing date (YYYY-MM-DD or YYYYMMDD)
python manage.py sync_gmp_corporate_actions --date 2026-06-10

# Re-sync everything, ignoring already-synced check (corrections)
python manage.py sync_gmp_corporate_actions --full-sync

# Verbose per-record output
python manage.py sync_gmp_corporate_actions --verbose

# Specify batch size (default 500)
python manage.py sync_gmp_corporate_actions --batch-size 1000
```

### What is written per GMP record

| Column | Value |
|---|---|
| `ca_number` | `GMP-<gmp_ca_id>` |
| `ca_type` | Mapped CIS type (e.g. `DIVIDEND`) |
| `security_name` | From GMP `security` column |
| `src_system` | `'GMP'` |
| `status` | `'VALIDATED'` (skips four-eyes) |
| `currency` | `NULL` — GMP has no currency column; enrich manually if needed |
| `ex_date`, `record_date`, `payment_date` | Parsed from GMP (handles `DD/MM/YYYY`, `YYYY-MM-DD`, `YYYYMMDD`) |
| `price` | Parsed as Decimal; `NULL` if blank |

### Tables touched

| Table | Operation |
|---|---|
| `gmp_cis_sfa_dly_corporate_action` | READ |
| `cis_corporate_actions` | UPSERT (new GMP CAs) |
| `cis_ca_cash_flow_queue` | INSERT (PENDING entries for cash-flow CA types) |

### Verify

```sql
-- Records synced from GMP today
SELECT ca_type, status, COUNT(*) as cnt
FROM gmp_cis.cis_corporate_actions
WHERE src_system = 'GMP'
  AND DATE(created_at) = CURRENT_DATE()
GROUP BY ca_type, status;

-- Queue entries created from GMP today
SELECT ca_type, status, COUNT(*) as cnt
FROM gmp_cis.cis_ca_cash_flow_queue
WHERE DATE(created_at) = CURRENT_DATE()
GROUP BY ca_type, status;
```

---

## Stage 1 — CA Cash Flow Processing (`process_corporate_actions`)

### What it does

Reads `PENDING` entries from `cis_ca_cash_flow_queue` (from both GMP sync and CIS UI) and generates cash flow records in `cis_cash_flow` — one entry per portfolio that holds the security on the ex-date.

### Queue status flow

```
PENDING → PROCESSING → COMPLETED
                    → FAILED  (retried up to 3 times automatically)
```

### Command

```bash
# Check queue status before running
python manage.py process_corporate_actions --status

# Reset entries stuck in PROCESSING (previous run crashed)
python manage.py process_corporate_actions --reset-stuck

# Preview
python manage.py process_corporate_actions --dry-run

# Standard run — process all pending
python manage.py process_corporate_actions

# Filter by payment date
python manage.py process_corporate_actions --date 2026-06-10

# Process a single CA by ID
python manage.py process_corporate_actions --ca-id 123456

# Process a single queue entry by ID
python manage.py process_corporate_actions --queue-id 789

# Batch size control (default 100)
python manage.py process_corporate_actions --batch-size 200

# Verbose output
python manage.py process_corporate_actions --verbose-output

# Retry failed entries (retry_count < 3)
python manage.py process_corporate_actions --retry-failed
```

### Tables touched

| Table | Operation |
|---|---|
| `cis_ca_cash_flow_queue` | READ (pending), UPDATE status → `PROCESSING` → `COMPLETED` / `FAILED` |
| `cis_cash_flow` | INSERT (one per portfolio holding the security) |

### Verify

```sql
-- Queue health
SELECT status, COUNT(*) as cnt
FROM gmp_cis.cis_ca_cash_flow_queue
GROUP BY status;

-- Cash flows generated today (both GMP and CIS CAs)
SELECT ca_type, src_system, COUNT(*), SUM(local_ccy_amt)
FROM gmp_cis.cis_cash_flow
WHERE payment_date = CURRENT_DATE()
GROUP BY ca_type, src_system;
```

---

## Stage 2 — Cash Flow Application (`process_approved_cashflows`)

### What it does

Reads APPROVED cash flows from `cis_cash_flow` (where `payment_date <= run_date` and `position_updated = false`) and applies them to the current open SETTLED position in `cis_trade_position` by writing a new version row.

### Cash flow type → position field mapping

| `cash_flow_type` | Effect on position | Field(s) updated |
|---|---|---|
| `UNCALL_COMMITMENT` | Accumulate | `uncall_fc`, `uncall_lc` |
| `PROVISION` | Accumulate | `provision_fc`, `provision_lc` |
| `PIPELINE` | Accumulate | `pipeline_fc`, `pipeline_lc` |
| `YTD_REALISE` | Accumulate | `realized_pnl_fc`, `realized_pnl_lc` |
| `DIVIDEND` | Accumulate | `dividend_fc`, `dividend_lc` |
| `CASH_DIVIDEND` | Accumulate | `dividend_fc`, `dividend_lc` |
| `INCOME_DISTRIBUTION` | Accumulate | `realized_pnl_fc`, `realized_pnl_lc` |
| `CAPITAL_DISTRIBUTION` | AVP reduction | `average_cost_fc/lc`, `total_cost_fc/lc` |
| `RETURN_OF_CAPITAL` | AVP reduction | `average_cost_fc/lc`, `total_cost_fc/lc` |
| `OTHER` | Skip (logged) | — |

### Sign convention (`send_receive`)

| Value | Sign | Effect |
|---|---|---|
| `SEND` | +1 | Increases the field |
| `RECEIVE` | -1 | Decreases the field |
| `NULL` | +1 | Treated as SEND, logged as warning |

### AVP reduction formula

```
per_share_fc = amount_fc / quantity
new_avp_fc   = max(0, old_avp_fc - per_share_fc)
new_cost_fc  = new_avp_fc × quantity
```

### Command

```bash
# Preview
python manage.py process_approved_cashflows --dry-run

# Standard run — all approved cash flows up to today
python manage.py process_approved_cashflows

# Process cash flows up to a specific date (supports backdating)
python manage.py process_approved_cashflows --date 2026-06-10

# Limit to one portfolio
python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING

# Re-process already-processed records (corrections only)
python manage.py process_approved_cashflows --reprocess
```

### Idempotency

Each cash flow record has `position_updated` (BOOLEAN). Once applied it is set to `true`. Re-runs on the same date skip already-processed records. Use `--reprocess` only for corrections.

### Tables touched

| Table | Operation |
|---|---|
| `cis_cash_flow` | READ (approved, unprocessed), UPDATE `position_updated = true` |
| `cis_trade_position` | UPDATE old version `is_latest = false`, UPSERT new version |

### Verify

```sql
-- Unprocessed cash flows (should be 0 after a successful run)
SELECT COUNT(*)
FROM gmp_cis.cis_cash_flow
WHERE status = 'APPROVED'
  AND src_system = 'CIS'
  AND (position_updated = false OR position_updated IS NULL)
  AND payment_date <= CURRENT_DATE();

-- New position versions written today by cash flow type
SELECT trade_type, COUNT(*), MAX(updated_at)
FROM gmp_cis.cis_trade_position
WHERE trade_type LIKE 'CF_%'
  AND updated_at >= CURRENT_DATE()
GROUP BY trade_type;
```

---

## Stage 3 — Trade Settlement (`process_settlements`)

### What it does

Processes pending entries from `cis_settlement_queue` for trades that have reached their settlement date (T+1 / T+2 trades booked earlier). For each pending entry it calls `settlement_service.process_pending_settlements` which applies the trade's BUY/SELL effect to `cis_trade_position` (CIS working ledger) — the same AVP formula used at trade creation.

This is separate from the SOD settlement mechanism in `create_sod_snapshot`. `process_settlements` writes the CIS ledger (`cis_trade_position`); the SOD snapshot folds those results into the golden copy (`cis_position`) the next morning.

### Queue status flow

```
PENDING → COMPLETED
        → FAILED  (logged, queue entry stays for investigation)
```

### Command

```bash
# Preview — show pending settlements for today
python manage.py process_settlements --dry-run

# Standard run — process all pending settlements for today
python manage.py process_settlements

# Process settlements for a specific date (backdated run)
python manage.py process_settlements --date 2026-03-02

# Verbose output (shows each settlement as it is processed)
python manage.py process_settlements --verbose

# Backfill: repair missing queue entries from migrated trades
python manage.py process_settlements --backfill-queue

# Control batch size (default: 100)
python manage.py process_settlements --batch-size 200
```

> **Date flag:** uses `--date` (not `--position-date`). Default: today's date (`datetime.now()`).
> It does **not** read from `alldatesinfo` — always defaults to today unless you pass `--date`.

### Tables touched

| Table | Operation |
|---|---|
| `cis_settlement_queue` | READ (PENDING entries for settle_date), UPDATE status → `COMPLETED` / `FAILED` |
| `cis_trade` | READ (to get `total_amount_lc` for NON-REVAL portfolios) |
| `cis_trade_position` | UPSERT (new AVP position version per settled trade) |

### Verify

```sql
-- Pending settlements remaining after run (should be 0)
SELECT status, COUNT(*) AS cnt
FROM gmp_cis.cis_settlement_queue
WHERE settle_date = '2026-03-02'
GROUP BY status;

-- Positions written by settlement today
SELECT portfolio_short_name, security_label, quantity, average_cost_fc, position_date
FROM gmp_cis.cis_trade_position
WHERE updated_by = 'SYSTEM'
  AND position_date = '2026-03-02'
ORDER BY updated_at DESC
LIMIT 20;
```

---

## Stage 4 — Position Revaluation (`refresh_positions`)

### What it does

Fetches all positions from `cis_position` (golden copy, all sources) and refreshes market values using the latest closing price from `cis_equity_price`. Writes back to `cis_position` via UPSERT with `position_type = 'EOD'`.

### Equity method rule

Securities where `cis_security_kudu.security_investment IN ('ASSOC', 'SUBSI')` (associates and subsidiaries) are **carried at cost** under the equity method. For these:

```
unrealized_pnl_fc = 0
unrealized_pnl_lc = 0
market_value_fc   = qty × latest_price  (still calculated, for reporting)
```

### LC calculation

`cis_position` does not store the FX rate directly. The implied rate is derived from stored values:

```
implied_fx_rate   = cost_lc / cost_fc
market_value_lc   = market_value_fc × implied_fx_rate
unrealized_pnl_lc = market_value_lc - cost_lc
```

### Price lookup order

```
1. cis_equity_price  WHERE security_label = ?  AND is_active = true
                     ORDER BY price_date DESC, price_timestamp DESC  LIMIT 1
2. cis_security_kudu WHERE security_label = ?  (fallback — last known price)
3. SKIP position — logged as warning, position unchanged
```

### Command

```bash
# Preview
python manage.py refresh_positions --dry-run

# Standard run — all sources, all portfolios
python manage.py refresh_positions

# Filter by source system
python manage.py refresh_positions --source CIS
python manage.py refresh_positions --source GMP
python manage.py refresh_positions --source AMSICEQ
python manage.py refresh_positions --source USER_UPLOAD

# Filter by portfolio
python manage.py refresh_positions --portfolio UOB-SG-TRADING

# Combined
python manage.py refresh_positions --portfolio UOB-SG-TRADING --dry-run
```

### What is written per position

| Column | Value |
|---|---|
| `position_type` | `'EOD'` |
| `version_id` | New timestamp-based ID |
| `processing_date` | Today's date |
| `market_value_fc` | `qty × latest_price` |
| `market_value_lc` | `market_value_fc × implied_fx` |
| `net_book_value_fc/lc` | Same as `market_value_fc/lc` |
| `unrealized_pnl_fc` | `market_value_fc - cost_fc` (0 for ASSOC/SUBSI) |
| `unrealized_pnl_lc` | `market_value_lc - cost_lc` (0 for ASSOC/SUBSI) |
| All cost columns | Carried forward unchanged |
| All P&L, dividend, uncall, pipeline columns | Carried forward unchanged |

### Tables touched

| Table | Operation |
|---|---|
| `cis_position` | READ (all positions), UPSERT (same `position_id`, new `version_id`) |
| `cis_equity_price` | READ (latest closing price) |
| `cis_security_kudu` | READ (price fallback + `security_investment` equity method check) |

### Verify

```sql
-- Count EOD versions written today by source
SELECT src_system, COUNT(*) as positions_revalued
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND processing_date = CURRENT_DATE()
GROUP BY src_system;

-- Positions skipped (no price today)
SELECT portfolio, security_label, src_system, position_type, processing_date
FROM gmp_cis.cis_position
WHERE processing_date < CURRENT_DATE()
   OR position_type != 'EOD';

-- Equity method positions (unrealized_pnl_fc must be 0)
SELECT p.portfolio, p.security_label, s.security_investment,
       p.market_value_fc, p.unrealized_pnl_fc
FROM gmp_cis.cis_position p
JOIN gmp_cis.cis_security_kudu s ON s.security_label = p.security_label
WHERE s.security_investment IN ('ASSOC', 'SUBSI')
  AND p.processing_date = CURRENT_DATE();
```

---

## Stage 5 — SOD Snapshot (`create_sod_snapshot`)

### What it does

Creates Start-of-Day (SOD) position rows in `cis_position` for the **next business day** by:

1. Reading today's `EOD` rows from `cis_position` (the golden copy written by `refresh_positions`)
2. Applying any `PENDING` entries in `cis_settlement_queue` whose `settle_date = contextual_today` — so the SOD already reflects T+1/T+2 trades settling today (avoiding a separate INT position pass the next morning)
3. Writing the merged result as `position_type='SOD'` with the next business day as `position_date`
4. Marking the processed settlement queue entries as `COMPLETED`

> **Run order:** `create_sod_snapshot` must run **after** `refresh_positions`. It reads the EOD rows
> written by Stage 4. Running it before Stage 4 will snapshot stale INT/SOD rows instead.

### Date logic

Dates are read from `gmp_cis_sta_dly_alldatesinfo` (no date flag available):

| Field | Source column | Example | Meaning |
|---|---|---|---|
| `eod_date` (source) | `prev_day` | `20260226` | Previous business day — where EOD rows come from |
| `sod_date` (target) | `contextual_today` | `20260302` | Next business day — SOD rows written here |

There is **no `--date` flag** on this command. To run for a non-standard date you must update `alldatesinfo` or run it on the correct calendar day.

### Idempotency

The command deletes any existing SOD rows for `sod_date` before inserting, so it is safe to re-run.

### Command

```bash
# Preview — show what would be written (no DB changes)
python manage.py create_sod_snapshot --dry-run

# Standard run — copy EOD → SOD for next business day
python manage.py create_sod_snapshot

# Limit to one portfolio
python manage.py create_sod_snapshot --portfolio UOB-SG-TRADING

# Limit to one source system
python manage.py create_sod_snapshot --source CIS
python manage.py create_sod_snapshot --source GMP
```

### Tables touched

| Table | Operation |
|---|---|
| `gmp_cis_sta_dly_alldatesinfo` | READ (`contextual_today`, `prev_day`) |
| `cis_position` | READ (EOD rows for `prev_day`), DELETE (existing SOD for `sod_date`), UPSERT (new SOD rows) |
| `cis_settlement_queue` | READ (PENDING entries for `sod_date`), UPDATE → `COMPLETED` / `FAILED` |
| `cis_trade` | READ (join for `total_amount_lc` — NON-REVAL portfolios) |
| `cis_portfolio` | READ (`revaluation_status` — REVALUED vs NON-REVALUED) |

### Verify

```sql
-- SOD rows written for next business day
SELECT src_system, COUNT(*) AS rows, SUM(quantity) AS total_qty
FROM gmp_cis.cis_position
WHERE position_type = 'SOD'
  AND position_date = '2026-03-02'   -- replace with sod_date
GROUP BY src_system;

-- Settlement queue entries processed by SOD run
SELECT status, COUNT(*)
FROM gmp_cis.cis_settlement_queue
WHERE settle_date = '2026-03-02'
GROUP BY status;
```

---

## Full EOD Run — Step by Step

```bash
# Activate virtual environment
source .venv/bin/activate

# 0. Verify Impala connection
python manage.py test_hive

# ── STAGE 0: GMP CA Sync ────────────────────────────────────────────────────

# 0a. Verify GMP source table has today's data
impala-shell -i localhost:21050 -q \
  "SELECT COUNT(*), MAX(processing_date) FROM gmp_cis.gmp_cis_sfa_dly_corporate_action"

# 0b. Preview GMP sync
python manage.py sync_gmp_corporate_actions --dry-run --verbose

# 0c. Run GMP sync
python manage.py sync_gmp_corporate_actions

# ── STAGE 1: CA Cash Flow Processing ────────────────────────────────────────

# 1a. Check queue status (should show PENDING entries from Stage 0)
python manage.py process_corporate_actions --status

# 1b. Reset any stuck PROCESSING entries from a previous failed run
python manage.py process_corporate_actions --reset-stuck

# 1c. Preview
python manage.py process_corporate_actions --dry-run

# 1d. Run
python manage.py process_corporate_actions

# ── STAGE 2: Cash Flow Application ──────────────────────────────────────────

# 2a. Preview
python manage.py process_approved_cashflows --dry-run

# 2b. Run
python manage.py process_approved_cashflows

# ── STAGE 3: Trade Settlement ────────────────────────────────────────────────

# 3a. Preview — show pending T+1/T+2 settlements settling today
python manage.py process_settlements --dry-run

# 3b. Run
python manage.py process_settlements

# ── STAGE 4: Position Revaluation ───────────────────────────────────────────

# 4a. Preview
python manage.py refresh_positions --dry-run

# 4b. Run
python manage.py refresh_positions

# ── STAGE 5: SOD Snapshot ───────────────────────────────────────────────────

# 5a. Preview — show what EOD rows would be copied as SOD
python manage.py create_sod_snapshot --dry-run

# 5b. Run — copies today's EOD rows as tomorrow's SOD baseline
python manage.py create_sod_snapshot
```

---

## Manual / Backdated EOD Run

Use this when you need to run EOD for a past date (e.g. 2026-03-02) while `alldatesinfo` still
reflects a different date. Always pass the date explicitly on every stage.

> **Why explicit dates matter:** Stages 2, 4, and the CA commands read `alldatesinfo.reporting_date`
> when no date is supplied. If that table still shows 2026-02-27, every command will default to
> 27th Feb — wrong positions, wrong cutoffs.
> `process_settlements` defaults to today's calendar date (not alldatesinfo), so pass `--date` there too.
> `create_sod_snapshot` has **no date flag** — it always reads from `alldatesinfo`.

```bash
export TARGET=2026-03-02   # the date you are running for

# ── STAGE 0: GMP CA Sync ────────────────────────────────────────────────────
python manage.py sync_gmp_corporate_actions --date $TARGET

# ── STAGE 1: CA Cash Flow Processing ────────────────────────────────────────
python manage.py process_corporate_actions --date $TARGET

# ── STAGE 2: Cash Flow Application ──────────────────────────────────────────
python manage.py process_approved_cashflows --position-date $TARGET

# ── STAGE 3: Trade Settlement ────────────────────────────────────────────────
python manage.py process_settlements --date $TARGET

# ── STAGE 4: Position Revaluation ───────────────────────────────────────────
python manage.py refresh_positions --position-date $TARGET

# ── STAGE 5: SOD Snapshot ───────────────────────────────────────────────────
# No date flag — update alldatesinfo to have contextual_today=$TARGET first,
# or run create_sod_snapshot on the correct calendar day.
python manage.py create_sod_snapshot --dry-run   # verify before running live
python manage.py create_sod_snapshot
```

### Date flags quick reference

| Command | Date flag | Default when omitted |
|---|---|---|
| `sync_gmp_corporate_actions` | `--date YYYY-MM-DD` | Latest `processing_date` in GMP source |
| `process_corporate_actions` | `--date YYYY-MM-DD` | All PENDING entries (no date filter) |
| `process_approved_cashflows` | `--position-date YYYY-MM-DD` | `alldatesinfo.reporting_date` (T-1) |
| `process_settlements` | `--date YYYY-MM-DD` | Today's calendar date |
| `refresh_positions` | `--position-date YYYY-MM-DD` | `alldatesinfo.reporting_date` (T-1) |
| `create_sod_snapshot` | *(no flag)* | Always reads `alldatesinfo` |

---

## Targeted / Recovery Runs

### Re-sync GMP CAs for a specific date

```bash
python manage.py sync_gmp_corporate_actions --date 2026-06-10
```

### Re-sync all GMP CAs (ignore duplicates — full correction)

```bash
python manage.py sync_gmp_corporate_actions --full-sync
```

### Re-run for one portfolio

```bash
python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING
python manage.py refresh_positions --portfolio UOB-SG-TRADING
```

### Re-run reval for one source only

```bash
python manage.py refresh_positions --source AMSICEQ
```

### Backdate cash flow processing

```bash
python manage.py process_approved_cashflows --position-date 2026-06-01
```

### Re-process already-applied cash flows (corrections)

```bash
python manage.py process_approved_cashflows --reprocess --portfolio UOB-SG-TRADING
```

### Retry failed CA queue entries

```bash
python manage.py process_corporate_actions --retry-failed
```

### Re-process settlements for a specific date

```bash
python manage.py process_settlements --date 2026-03-02 --dry-run
python manage.py process_settlements --date 2026-03-02
```

### Backfill missing settlement queue entries (after bulk trade migration)

```bash
python manage.py process_settlements --backfill-queue --dry-run
python manage.py process_settlements --backfill-queue
```

### Re-run SOD snapshot for one portfolio

```bash
python manage.py create_sod_snapshot --portfolio UOB-SG-TRADING --dry-run
python manage.py create_sod_snapshot --portfolio UOB-SG-TRADING
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Stage 0: `No GMP records found` | GMP ETL hasn't run yet | Verify `gmp_cis_sfa_dly_corporate_action` has rows for today |
| Stage 0: `unknown ca_type='X'` | GMP type not in mapping table | Add `'x': 'CIS_TYPE'` to `GMP_CA_TYPE_MAP` in `sync_gmp_corporate_actions.py` |
| Stage 0: `currency = NULL` | GMP source has no currency column | Manually UPDATE `cis_corporate_actions` after sync, or enrich via a join to security master |
| Stage 1: `No pending corporate actions found` | Stage 0 not run, or all already processed | Run Stage 0 first; check queue with `--status` |
| Stage 1: entries stuck in `PROCESSING` | Previous run crashed mid-flight | Run `--reset-stuck` then re-run |
| Stage 1: CA inserted but not queued | CA type not in cash-flow or position-adjustment list | Check `ca_cash_flow_service.CASH_FLOW_CA_TYPES` — add the type if it should generate cash flows |
| Stage 2: `No open SETTLED position for X/Y` | Trade not yet settled or wrong position_basis | `SELECT * FROM cis_trade_position WHERE portfolio_short_name='X' AND security_label='Y' AND position_basis='SETTLED' AND status='OPEN'` |
| Stage 2: cash flow applied twice | `--reprocess` used unintentionally | Check `cf_processed` flag; do not use `--reprocess` in normal EOD |
| Stage 2/4 using wrong date (e.g. 27th Feb instead of 2nd Mar) | `alldatesinfo.reporting_date` not updated yet | Always pass `--position-date YYYY-MM-DD` explicitly for manual/backdated runs |
| Stage 3: `No pending settlements found` | No T+1/T+2 trades settling on that date | Expected — skip Stage 3 if settlement queue is empty for the target date |
| Stage 3: settlement queue entry stuck as PENDING | `process_settlements` didn't run or failed | Check logs; re-run `python manage.py process_settlements --date YYYY-MM-DD` |
| Stage 4: position skipped (no price) | Missing entry in `cis_equity_price` | Load price via market data feed; check `cis_security_kudu.price` as fallback |
| Stage 4: ASSOC/SUBSI showing non-zero P&L | `security_investment` not set on security master | `UPDATE cis_security_kudu SET security_investment='ASSOC' WHERE security_label='X'` |
| Stage 5: `No EOD rows found for position_date=X` | `refresh_positions` (Stage 4) not yet run | Run Stage 4 first; SOD reads `position_type='EOD'` rows |
| Stage 5: SOD date wrong (e.g. still 27th Feb) | `alldatesinfo.contextual_today` not updated | SOD has no date flag — update `alldatesinfo` or run on the correct calendar day |
| Impala connection fails | Docker container stopped (local dev) | `docker start kudu-impala && python manage.py test_hive` |

---

## Key Tables Reference

| Table | Role | Populated by |
|---|---|---|
| `gmp_cis_sfa_dly_corporate_action` | GMP CA source feed | GMP ETL job (external) |
| `cis_corporate_actions` | CA master — all sources | `sync_gmp_corporate_actions` (GMP), CIS UI (manual) |
| `cis_ca_cash_flow_queue` | CA processing queue | `sync_gmp_corporate_actions`, `ca_cash_flow_service` |
| `cis_cash_flow` | Cash flow ledger (CA + manual) | `process_corporate_actions` (CA), UI (manual) |
| `cis_trade_position` | CIS trade working ledger (versioned) | `position_service`, `process_approved_cashflows`, `process_settlements` |
| `cis_settlement_queue` | T+1/T+2 trade settlement queue | `position_service` (at trade booking), `process_settlements`, `create_sod_snapshot` |
| `cis_position` | **Golden copy — all sources** | `refresh_positions` (EOD), `create_sod_snapshot` (SOD), upload jobs |
| `cis_equity_price` | Market price feed | Market data load jobs |
| `cis_security_kudu` | Security master (incl. `security_investment`) | Security module |

---

## Position Type Values in `cis_position`

| `position_type` | Set by | Meaning |
|---|---|---|
| `LONG` | Trade processing (default) | Standard long position |
| `SHORT` | Trade processing | Short position |
| `COMMITTED` | Upload / manual | PE/VC committed capital |
| `PIPELINE` | Upload / manual | Pending / pipeline position |
| `HEDGE` | Upload / manual | Hedging position |
| `INT` | `process_approved_cashflows` | Intra-day position version after cash flow applied |
| `EOD` | `refresh_positions` | Position after EOD market revaluation |
| `SOD` | `create_sod_snapshot` | Start-of-day baseline for next business day |
| `CORR` | `refresh_positions --run-type CORR` | Month-end correction run position |

---

## `cis_corporate_actions` — `src_system` Values

| `src_system` | `status` on insert | Set by |
|---|---|---|
| `GMP` | `VALIDATED` | `sync_gmp_corporate_actions` — bypasses four-eyes |
| `CIS` | `INITIAL` → `APPROVED` | CIS UI — requires four-eyes approval before queuing |

---

## Implementation Notes

- **GMP CAs bypass four-eyes.** They are inserted with `status='VALIDATED'` directly — GMP data is considered pre-validated at source.
- **CIS CAs go through four-eyes.** Created via UI with `status='INITIAL'`, must be approved before `process_corporate_actions` picks them up.
- **`ca_number` uniqueness.** GMP CAs use the prefix `GMP-<ca_id>`. CIS CAs use an auto-generated sequential number (e.g. `CA-2026-00123`). Never duplicate across sources.
- **`unrealized_pnl_fc` is always 0** for `security_investment IN ('ASSOC','SUBSI')` — equity method accounting, no mark-to-market.
- **`cis_position` PK is `position_id`** (single column). UPSERT on `position_id` replaces the current row. `version_id` is a non-PK audit column tracking which EOD run last touched the row.
- **`cis_trade_position` uses composite PK** (`version_id`) and supports append-style versioning for full audit history. Separate from `cis_position`.
- **Implied FX rate** (`cost_lc / cost_fc`) is used in reval to avoid a separate FX lookup and preserve the original cost-basis rate.
- **Always `--dry-run` first** on production before any live EOD run.
