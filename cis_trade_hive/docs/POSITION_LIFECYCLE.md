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
- `position_basis = TRADED` → `position_date = trade_date`
- `position_basis = SETTLED` → `position_date = settle_date`

### 2A. Same-day Trade (trade_date == settle_date == today)

```
trade_date = 2026-07-01  (T)
settle_date = 2026-07-01  (T+0)
contextual_today = 2026-07-01
```

| Basis | position_date | position_type | Processing |
|-------|--------------|---------------|------------|
| TRADED | 2026-07-01 | INT | Queued → async position worker |
| SETTLED | 2026-07-01 | INT | Queued → async position worker |

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
| TRADED | 2026-07-01 | INT | Queued → async position worker (immediate) |
| SETTLED | 2026-07-03 | INT | Queued → `cis_settlement_queue` (processed on settle date) |

- TRADED position created today with full AVP
- SETTLED position **held in settlement queue** (status = PENDING) until 2026-07-03 becomes `contextual_today`, at which point the SOD job applies its AVP effect to the previous day's EOD row and writes it as SOD — no separate INT is created

---

### 2C. Backdated Trade (trade_date < today)

```
trade_date = 2026-06-15  (past)
settle_date = 2026-06-17  (past)
contextual_today = 2026-07-01
```

| Basis | position_date | position_type | Processing |
|-------|--------------|---------------|------------|
| TRADED | 2026-06-15 | **INT** | Chain recalculation from 2026-06-15 → today |
| SETTLED | 2026-06-17 | **INT** | Chain recalculation from 2026-06-17 → today |

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
| == today | > today (T+1/T+2) | INT, immediate | held in settlement queue (PENDING); applied by SOD job on settle_date |
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

**Output:** New row inserted with `position_type = 'EOD'` for each position (both TRADED and SETTLED basis). Never overwrites — always inserts a new versioned row.

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

Copies previous day's EOD rows to today's date as `SOD`, **and simultaneously folds in any pending settlement queue entries** whose `settle_date == today`. The resulting SOD already reflects those settled trades — no separate INT positions are created for them.

**Step-by-step:**

1. Fetch all EOD rows for `prev_day` from `cis_position`
2. Fetch PENDING entries from `cis_settlement_queue` where `settle_date == contextual_today`
3. Apply each queued trade's AVP effect to the matching EOD row in memory:
   - **BUY:** `new_cost_fc = old_cost_fc + (qty × price + charges)`; `new_avg_fc = new_cost_fc / new_qty`; LC via existing `avg_cost_lc / avg_cost_fc` ratio; all CA/CF fields carried unchanged
   - **SELL partial:** qty reduced; AVP unchanged; `realized_pnl` accumulated; market value and unrealized PnL prorated by `new_qty / old_qty`
   - **SELL full close:** qty → 0; all costs/market values → 0; `realized_pnl` accumulated; CA/CF obligations (uncall, pipeline, provision) carried
   - **New security (no prior EOD):** BUY creates a brand-new SOD row; SELL with no existing position → marked FAILED
4. Write the merged result as `position_type = 'SOD'`
5. Mark processed queue entries `COMPLETED` (skipped by the async settlement worker)

**What changes from EOD → SOD:**

| Field | From | To |
|-------|------|----|
| `position_date` | 2026-06-30 (EOD date) | 2026-07-01 (today) |
| `processing_date` | 2026-06-30 | 2026-07-01 |
| `position_type` | `EOD` | `SOD` |
| `quantity`, `cost_fc/lc`, `average_cost_fc/lc` | EOD values | Updated if a settlement trade applied |
| `realized_pnl_fc/lc` | EOD values | Accumulated if a SELL settled today |

**Everything else carried from EOD unchanged:**
- `market_value_fc/lc`, `unrealized_pnl_fc/lc`, `net_book_value_fc/lc` (re-priced by tonight's EOD job)
- `dividend_fc/lc`, `uncall_fc/lc`, `pipeline_fc/lc`, `provision_fc/lc`

> **Note:** `market_value` and `unrealized_pnl` are NOT recalculated during SOD — they are carried from the prior EOD and will be corrected by tonight's EOD revaluation run.

SOD represents the **opening position** for the new day — carrying all accumulated CA, CF, revaluation from the previous EOD, plus the quantity and cost effects of any trades that settled overnight.

---

## 5. Full Day Lifecycle — Timeline

```
06:00  SOD job runs
       └─ Fetches yesterday's EOD rows from cis_position
       └─ Fetches PENDING settlement queue entries where settle_date == today
       └─ Applies each queued trade's AVP effect to the matching EOD row:
            BUY  → recalculates qty, avg_cost, cost; carries CA/CF unchanged
            SELL → reduces qty, accumulates realized_pnl; zeros on full close
       └─ Writes merged result as SOD (position_type = SOD, position_date = today)
       └─ Marks processed queue entries COMPLETED
          (async settlement worker skips COMPLETED entries)

During day
       ├─ New trades create INT positions (TRADED + SETTLED basis)
       ├─ Backdated trades create INT positions + trigger chain recalc
       ├─ T+1/T+2 settle legs held in cis_settlement_queue (PENDING)
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
       └─ SOD job runs again:
            copies today's EOD + applies any new settlements due tomorrow
          (position_date = tomorrow, position_type = SOD)
```

---

## 6. Position Type Summary

| Type | When Created | Who Creates It |
|------|-------------|----------------|
| `INT` | Trade booked (any date ≤ today); position upload | `position_service`, `upload_service` |
| `EOD` | Nightly batch revaluation | `refresh_positions` management command |
| `SOD` | Morning batch: previous EOD + settled trades applied (settle_date == today) | `create_sod_snapshot` management command |
| `CORR` | Last-month-end correction (external trigger only) | External correction process via `alldatesinfo` |

> `BACK` type is **not used** in this system.
