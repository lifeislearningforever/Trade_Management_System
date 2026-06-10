# CIS Trade Hive — EOD Processing Guide

**Version:** 1.0  
**Updated:** 2026-06-10  
**Database:** `gmp_cis` (Apache Kudu via Impala)

---

## Overview

The EOD (End of Day) process runs in three sequential stages every business day:

```
Stage 1: Corporate Actions → generate cash flows from CA events
Stage 2: Cash Flow Application → apply approved cash flows to positions
Stage 3: Position Revaluation → refresh market values in cis_position (golden copy)
```

Each stage must complete successfully before the next begins. All stages support `--dry-run` for preview and `--portfolio` for targeted processing.

---

## Golden Copy — `cis_position`

`cis_position` is the **single source of truth** for all position data across all source systems.

| `src_system` | Origin |
|---|---|
| `CIS` | Internal trades entered via CIS Trade Hive |
| `GMP` | Global Markets Platform (external feed) |
| `AMSICEQ` | AMS equity positions (uploaded via `upload_amsiceq_positions`) |
| `USER_UPLOAD` | Manual position uploads via the Upload UI |

The `cis_trade_position` table is the **working ledger** used by `position_service.py` during trade processing. After settlement, positions are synced into `cis_position`. The EOD reval operates only on `cis_position`.

---

## Stage 1 — Corporate Actions (`process_corporate_actions`)

### What it does

Reads pending entries from `cis_ca_cash_flow_queue` and generates cash flow records in `cis_cash_flow` for each CA event (dividend, bonus, rights issue, etc.).

### Command

```bash
# Standard run — process all pending CAs
python manage.py process_corporate_actions

# Filter by payment date
python manage.py process_corporate_actions --date 2026-06-10

# Process a single CA by ID
python manage.py process_corporate_actions --ca-id 123456

# Process a single queue entry
python manage.py process_corporate_actions --queue-id 789

# Batch size control (default 100)
python manage.py process_corporate_actions --batch-size 200

# Preview without writing
python manage.py process_corporate_actions --dry-run

# Verbose output
python manage.py process_corporate_actions --verbose-output

# Check queue status only
python manage.py process_corporate_actions --status

# Reset entries stuck in PROCESSING state (> 10 min)
python manage.py process_corporate_actions --reset-stuck

# Retry failed entries (retry_count < 3)
python manage.py process_corporate_actions --retry-failed
```

### Queue status flow

```
PENDING → PROCESSING → COMPLETED
                    → FAILED (retry up to 3 times)
```

### Tables touched

| Table | Operation |
|---|---|
| `cis_ca_cash_flow_queue` | READ (pending entries), UPDATE status |
| `cis_cash_flow` | INSERT (generated cash flows) |

### Verify

```sql
-- Check queue health
SELECT status, COUNT(*) as cnt
FROM gmp_cis.cis_ca_cash_flow_queue
GROUP BY status;

-- Check cash flows generated today
SELECT ca_type, COUNT(*), SUM(local_ccy_amt)
FROM gmp_cis.cis_cash_flow
WHERE payment_date = CURRENT_DATE()
  AND src_system = 'CA'
GROUP BY ca_type;
```

---

## Stage 2 — Cash Flow Application (`process_approved_cashflows`)

### What it does

Reads APPROVED cash flows from `cis_cash_flow` (where `payment_date <= run_date` and `position_updated = false`) and applies them to the current open SETTLE_DATE position in `cis_trade_position` by writing a new version row.

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
# Standard run — process all approved cash flows up to today
python manage.py process_approved_cashflows

# Process cash flows up to a specific date (supports backdating)
python manage.py process_approved_cashflows --date 2026-06-10

# Limit to one portfolio
python manage.py process_approved_cashflows --portfolio UOB-SG-TRADING

# Preview without writing
python manage.py process_approved_cashflows --dry-run

# Re-process already-processed records (corrections)
python manage.py process_approved_cashflows --reprocess
```

### Idempotency

Each cash flow record has `position_updated` (BOOLEAN). Once applied, it is set to `true`. Re-runs on the same date skip already-processed records. Use `--reprocess` only for corrections.

### Tables touched

| Table | Operation |
|---|---|
| `cis_cash_flow` | READ (approved, unprocessed), UPDATE `position_updated = true` |
| `cis_trade_position` | UPDATE old version `is_latest = false`, UPSERT new version |

### Verify

```sql
-- Unprocessed cash flows (should be 0 after successful run)
SELECT COUNT(*)
FROM gmp_cis.cis_cash_flow
WHERE status = 'APPROVED'
  AND src_system = 'CIS'
  AND (position_updated = false OR position_updated IS NULL)
  AND payment_date <= CURRENT_DATE();

-- Check new position versions written today
SELECT portfolio_short_name, security_label, trade_type, version_id, updated_at
FROM gmp_cis.cis_trade_position
WHERE trade_type LIKE 'CF_%'
  AND updated_at >= CURRENT_DATE()
ORDER BY updated_at DESC
LIMIT 20;
```

---

## Stage 3 — Position Revaluation (`refresh_positions`)

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

Since `cis_position` does not store the FX rate directly, the implied rate is derived from stored values:

```
implied_fx_rate  = cost_lc / cost_fc
market_value_lc  = market_value_fc × implied_fx_rate
unrealized_pnl_lc = market_value_lc - cost_lc
```

### Price lookup order

```
1. cis_equity_price  WHERE security_label = ?  ORDER BY price_date DESC  LIMIT 1
2. cis_security_kudu WHERE security_label = ?  (fallback — last known price)
3. SKIP if no price found (logged as warning)
```

### Command

```bash
# Standard run — all sources, all portfolios
python manage.py refresh_positions

# Preview without writing
python manage.py refresh_positions --dry-run

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
| `cis_position` | READ (all OPEN positions), UPSERT (same `position_id`, new `version_id`) |
| `cis_equity_price` | READ (latest closing price) |
| `cis_security_kudu` | READ (price fallback + `security_investment` for equity method check) |

### Verify

```sql
-- Count EOD versions written today
SELECT src_system, COUNT(*) as positions_revalued
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
  AND processing_date = CURRENT_DATE()
GROUP BY src_system;

-- Check for positions skipped (no price)
-- These will NOT have position_type = 'EOD' with today's processing_date
SELECT portfolio, security_label, src_system, position_type, processing_date
FROM gmp_cis.cis_position
WHERE position_type != 'EOD'
   OR processing_date < CURRENT_DATE();

-- Equity method positions (should have unrealized_pnl_fc = 0)
SELECT p.portfolio, p.security_label, s.security_investment,
       p.market_value_fc, p.unrealized_pnl_fc
FROM gmp_cis.cis_position p
JOIN gmp_cis.cis_security_kudu s ON s.security_label = p.security_label
WHERE s.security_investment IN ('ASSOC', 'SUBSI')
  AND p.processing_date = CURRENT_DATE();
```

---

## Full EOD Run — Step by Step

```bash
# Activate virtual environment
source .venv/bin/activate

# 0. Verify Impala connection
python manage.py test_hive

# --- STAGE 1: Corporate Actions ---

# 1a. Check queue status
python manage.py process_corporate_actions --status

# 1b. Reset any stuck entries from previous run
python manage.py process_corporate_actions --reset-stuck

# 1c. Preview
python manage.py process_corporate_actions --dry-run

# 1d. Run
python manage.py process_corporate_actions

# --- STAGE 2: Cash Flow Application ---

# 2a. Preview
python manage.py process_approved_cashflows --dry-run

# 2b. Run
python manage.py process_approved_cashflows

# --- STAGE 3: Position Revaluation ---

# 3a. Preview
python manage.py refresh_positions --dry-run

# 3b. Run
python manage.py refresh_positions
```

---

## Targeted / Recovery Runs

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
python manage.py process_approved_cashflows --date 2026-06-01
```

### Re-process already-applied cash flows (corrections)

```bash
python manage.py process_approved_cashflows --reprocess --portfolio UOB-SG-TRADING
```

### Retry failed CA queue entries

```bash
python manage.py process_corporate_actions --retry-failed
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Stage 1: `No pending corporate actions found` | No CAs due today or already processed | Check `cis_ca_cash_flow_queue` status with `--status` |
| Stage 1: entries stuck in `PROCESSING` | Previous run crashed mid-flight | Run `--reset-stuck` then re-run |
| Stage 2: `No open SETTLE_DATE position for X/Y` | Trade not yet settled or wrong basis | Verify position exists: `SELECT * FROM cis_trade_position WHERE portfolio_short_name='X' AND security_label='Y' AND position_basis='SETTLE_DATE' AND status='OPEN'` |
| Stage 2: cash flow applied twice | `--reprocess` used unintentionally | Check `position_updated` flag; do not run `--reprocess` in normal EOD |
| Stage 3: position skipped (no price) | Missing entry in `cis_equity_price` | Load price via market data feed; check `cis_security_kudu.price` as fallback |
| Stage 3: ASSOC/SUBSI showing non-zero P&L | `security_investment` not set on security master | Update `cis_security_kudu.security_investment` to `ASSOC` or `SUBSI` |
| Impala connection fails | Docker container stopped (local dev) | `docker start kudu-impala && python manage.py test_hive` |

---

## Key Tables Reference

| Table | Role | Owned by |
|---|---|---|
| `cis_ca_cash_flow_queue` | CA processing queue | `process_corporate_actions` |
| `cis_cash_flow` | Cash flow ledger (CA + manual) | `process_corporate_actions` (CA), UI (manual) |
| `cis_trade_position` | CIS trade working ledger (versioned) | `position_service`, `process_approved_cashflows` |
| `cis_position` | **Golden copy — all sources** | `refresh_positions` (EOD), upload jobs |
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
| `EOD` | `refresh_positions` | Position after EOD revaluation |

---

## Implementation Notes

- `unrealized_pnl_fc` is **always 0** for `security_investment IN ('ASSOC','SUBSI')` — equity method accounting, no mark-to-market.
- `cis_position` PK is `position_id` (single column). UPSERT on `position_id` **replaces** the current row. `version_id` is a non-PK audit column to track which EOD run last touched the row.
- `cis_trade_position` uses a **composite PK** (`version_id`) and supports true append-style versioning for audit history. This is separate from `cis_position`.
- The implied FX rate (`cost_lc / cost_fc`) is used in reval to avoid a separate FX rate lookup and preserve the original cost-basis FX rate.
- All three EOD commands support `--dry-run` — always run dry-run first on production.
