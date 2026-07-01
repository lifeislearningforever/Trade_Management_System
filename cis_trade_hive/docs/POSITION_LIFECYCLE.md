# Position Lifecycle — Trade Capture, Upload & EOD Evolution

**Date:** 2026-07-01
**Codebase:** CisTrade — Django 5.2.9 / Apache Kudu / Impala

---

## 1. Date Reference — `gmp_cis_sta_dly_alldatesinfo`

All date comparisons use `contextual_today` from this table (via `system_date_service`):

| Field | Meaning | Example |
|-------|---------|---------|
| `contextual_today` | Business date (T) | 2026-07-01 |
| `prev_day` | T-1 (previous business day) | 2026-06-30 |
| `processing_date` | Batch run date | 2026-07-01 |
| `settlement_t1` | T+1 settlement date | 2026-07-02 |
| `settlement_t2` | T+2 settlement date (default) | 2026-07-03 |

---

## 2. Trade Capture — Date Scenarios

Every trade creates **two positions** simultaneously:
- `position_basis = TRADE_DATE` → `position_date = trade_date`
- `position_basis = SETTLE_DATE` → `position_date = settle_date`

### 2A. Same-day Trade (trade_date == settle_date == today)

```
trade_date = 2026-07-01  (T)
settle_date = 2026-07-01  (T+0)
contextual_today = 2026-07-01
```

| Basis | position_date | position_type | Processing |
|-------|--------------|---------------|------------|
| TRADE_DATE | 2026-07-01 | INT | Queued → async position worker |
| SETTLE_DATE | 2026-07-01 | INT | Queued → async position worker |

Both bases go to `cis_position_queue` immediately. Worker runs AVP calculation and writes to `cis_position`.

---

### 2B. Standard T+2 Trade (trade_date = today, settle_date = T+2)

```
trade_date = 2026-07-01  (T)
settle_date = 2026-07-03  (T+2)
contextual_today = 2026-07-01
```

| Basis | position_date | position_type | Processing |
|-------|--------------|---------------|------------|
| TRADE_DATE | 2026-07-01 | INT | Queued → async position worker (immediate) |
| SETTLE_DATE | 2026-07-03 | INT | Queued → `cis_settlement_queue` (processed on settle date) |

- TRADE_DATE position created today with full AVP
- SETTLE_DATE position **held in settlement queue** until 2026-07-03 becomes `contextual_today`

---

### 2C. Backdated Trade (trade_date < today)

```
trade_date = 2026-06-15  (past)
settle_date = 2026-06-17  (past)
contextual_today = 2026-07-01
```

| Basis | position_date | position_type | Processing |
|-------|--------------|---------------|------------|
| TRADE_DATE | 2026-06-15 | **INT** | Chain recalculation from 2026-06-15 → today |
| SETTLE_DATE | 2026-06-17 | **INT** | Chain recalculation from 2026-06-17 → today |

> **Rule:** Backdated trades always produce `INT` — not `BACK`, not `CORR`.

Chain recalculation (`_recalculate_position_chain`):
- Re-processes all trades from backdated date to today in chronological order
- Uses versioning: marks old rows `is_latest=false`, inserts new version with `is_latest=true`
- Result: corrected AVP/cost/P&L across all affected dates

---

### 2D. Future Trade Date (trade_date > today)

**Blocked at validation.** `validate_settlement_date()` rejects with UI error popup:
> "Trade date (2026-07-05) cannot be in the future. Today is 2026-07-01."

No position is created.

---

### Summary — Trade Capture Date Matrix

| trade_date | settle_date | TD position | SD position |
|-----------|------------|-------------|-------------|
| == today | == today (T+0) | INT, immediate | INT, immediate |
| == today | > today (T+1/T+2) | INT, immediate | INT, held in settlement queue |
| < today (backdated) | < today | INT, chain recalc | INT, chain recalc |
| < today (backdated) | == today | INT, chain recalc | INT, immediate |
| > today | any | **BLOCKED** | **BLOCKED** |

---

## 3. Position Upload — Date Scenarios

Upload sets `position_type = 'INT'` for all valid rows. Uses deterministic `position_id` hash (portfolio + security + basis + reporting_date + src_system) — re-running the same file **replaces** existing rows via UPSERT.

### 3A. Upload date == today

```
reporting_date = 2026-07-01 == contextual_today
```
→ `position_type = INT` — normal intraday upload, inserted immediately.

---

### 3B. Upload date < today (backdated upload)

```
reporting_date = 2026-06-15 < contextual_today
```
→ `position_type = INT` — backdated upload, still `INT`.

> Guard: If a position with `position_type='INT'` and `src_system='USER_UPLOAD'` already exists for that date, the UPSERT hash collision replaces it — **do not re-upload unless intentional**.

---

### 3C. Upload date > today (future date)

```
reporting_date = 2026-07-05 > contextual_today
```
→ **Step 6C blocks these rows.** They are counted and warned in logs but NOT inserted into `cis_position`.

---

### Summary — Upload Date Matrix

| reporting_date vs today | position_type | Action |
|------------------------|---------------|--------|
| == today | INT | Inserted / UPSERT |
| < today (backdated) | INT | Inserted / UPSERT |
| > today (future) | — | **Blocked, not inserted** |

---

## 4. Position Evolution — EOD Cycle

### 4A. During the Day (INT positions accumulate)

Each trade creates/updates INT positions. Multiple trades on the same security/portfolio/basis accumulate into a single AVP chain (versioned rows, latest `is_latest=true`).

Corporate actions and cash flows during the day update specific fields on the latest position row:
- `dividend_fc / dividend_lc` — from DIVIDEND, INTEREST, COUPON CAs
- `uncall_fc / uncall_lc` — from CF-UN CALL COMMITMENT
- `pipeline_fc / pipeline_lc` — from CF-PIPELINE

---

### 4B. EOD Job — `refresh_positions` (nightly)

**What it reads:** Latest position per portfolio/security/basis (MAX position_id — picks up all accumulated CA/CF values during the day).

**What it recalculates:**

| Field | How |
|-------|-----|
| `market_value_fc` | `quantity × latest_price` |
| `market_value_lc` | `market_value_fc × fx_rate` |
| `unrealized_pnl_fc` | `market_value_fc − cost_fc` (0 for equity ASSOC/SUBSI) |
| `unrealized_pnl_lc` | `market_value_lc − cost_lc` |
| `net_book_value_fc` | `cost_fc + unrealized_pnl_fc − provision_fc` |
| `net_book_value_lc` | `cost_lc + unrealized_pnl_lc − provision_lc` |
| `cost_lc` | If `revaluation_status=REVALUED`: `cost_fc × fx_rate`; if `NON-REVALUED`: unchanged |

**What is carried forward unchanged:**
- `quantity`, `average_cost_fc/lc`, `cost_fc`
- `realized_pnl_fc/lc`, `provision_fc/lc`
- `dividend_fc/lc`, `uncall_fc/lc`, `pipeline_fc/lc` (accumulated from CAs/CFs)

**Output:** New row inserted with `position_type = 'EOD'` for each position (both TRADE_DATE and SETTLE_DATE basis). Never overwrites — always inserts a new versioned row.

---

### 4C. Corporate Actions — Impact on Position

| CA Type | Effect on Position |
|---------|--------------------|
| `DIVIDEND`, `INTEREST`, `COUPON` | Updates `dividend_fc/lc`; AVP unchanged |
| `ROC`, `CAPITAL_DISTRIBUTION` | Reduces `average_cost_fc` by price_per_share |
| `BONUS_ISSUE`, `STOCK_SPLIT` | Increases `quantity`; adjusts AVP proportionally |
| `REVERSE_SPLIT`, `CONSOLIDATION` | Reduces `quantity`; adjusts AVP |
| `RIGHTS_ISSUE` | Creates new entitlement quantity |
| `CF-UN CALL COMMITMENT` | Updates `uncall_fc/lc` |
| `CF-PIPELINE` | Updates `pipeline_fc/lc` |
| `CF-PROVISION` | Updates `provision_fc/lc` |

These updates happen **before EOD runs**, so EOD picks up all CA/CF impacts via `MAX(position_id)`.

---

### 4D. SOD Job — `create_sod_snapshot` (next morning)

Copies previous day's EOD row to today's date as `SOD`.

**What changes:**

| Field | From | To |
|-------|------|----|
| `position_date` | 2026-06-30 (EOD date) | 2026-07-01 (today) |
| `processing_date` | 2026-06-30 | 2026-07-01 |
| `position_type` | `EOD` | `SOD` |

**Everything else copied exactly:**
- `quantity`, `average_cost_fc/lc`, `cost_fc/lc`
- `market_value_fc/lc`, `unrealized_pnl_fc/lc`, `net_book_value_fc/lc`
- `realized_pnl_fc/lc`, `provision_fc/lc`
- `dividend_fc/lc`, `uncall_fc/lc`, `pipeline_fc/lc`

SOD represents the **opening position** for the new day — carrying all accumulated CA, CF, and revaluation from the previous EOD.

---

## 5. Full Day Lifecycle — Timeline

```
06:00  SOD job runs
       └─ Copies yesterday's EOD → today's SOD for all positions
          (position_date = today, position_type = SOD)

During day
       ├─ New trades create INT positions (TRADE_DATE + SETTLE_DATE basis)
       ├─ Backdated trades create INT positions + trigger chain recalc
       ├─ T+2 settle legs held in settlement_queue
       ├─ Corporate actions update dividend_fc, quantity, avg_cost
       └─ Cash flows update uncall_fc, pipeline_fc, provision_fc

18:00  EOD job runs
       └─ Reads MAX(position_id) per portfolio/security/basis
          (picks up all day's INT + CA/CF updates)
       └─ Recalculates market_value, unrealized_pnl, net_book_value
          using latest price × FX rate
       └─ Inserts new EOD row for each position
          (position_type = EOD, position_date = today)

Next morning
       └─ SOD job copies today's EOD → tomorrow's SOD
          (position_date = tomorrow, position_type = SOD)

On settle_date (T+2)
       └─ Settlement queue processes SETTLE_DATE position
          (creates INT position on the settlement date)
```

---

## 6. Position Type Summary

| Type | When Created | Who Creates It |
|------|-------------|----------------|
| `INT` | Trade booked (any date ≤ today); position upload | `position_service`, `upload_service` |
| `EOD` | Nightly batch revaluation | `refresh_positions` management command |
| `SOD` | Morning batch copy of previous EOD | `create_sod_snapshot` management command |
| `CORR` | Last-month-end correction (external trigger only) | External correction process via `alldatesinfo` |

> `BACK` type is **not used** in this system.
