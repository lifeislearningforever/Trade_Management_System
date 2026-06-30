# Position Type Logic Audit

**Date:** 2026-06-30
**Scope:** INT, EOD, SOD, BACK, CORR position types
**Codebase:** CisTrade — Django 5.2.9 / Apache Kudu / Impala

---

## Context — Position Types

| Type | Meaning |
|------|---------|
| `INT` | Intraday — current day activity |
| `EOD` | End of Day — final state of a day |
| `SOD` | Start of Day — carry forward from previous EOD |
| `BACK` | Backdated entries (past adjustments) |
| `CORR` | Corrections on historical data |

---

## Expected Functional Behavior

### 1. Same-day processing
If `business_date == system_date`:
- Create `INT` position
- Generate `EOD` at end of day
- Generate next day's `SOD` from `EOD`

### 2. Backdated processing
If `business_date < system_date`:
- Create `BACK` position on the past business date
- Create `INT` position on current system date (to reflect impact)
- Continue EOD and next SOD generation for current date

### 3. Correction
If correction is triggered for a past date:
- Create `CORR` position on that date

### 4. Trade-specific logic
For trades:
- Logic applies primarily on Trade Date (TD)
- Settlement Date (SD) inherits positions via SOD/EOD flow
- Backdated trade:
  - `BACK` on TD
  - `INT` impact on current system date

---

## Current Implementation — What's in the Codebase

### Position Type Derivation
**File:** `trade/services/position_service.py` — `_derive_position_type()`

```python
if pos_dt == today:
    return True, '', 'INT'
elif pos_dt < today:
    return True, '', 'CORR'
else:
    return False, "Future position date not allowed", None
```

### EOD Generation
**File:** `trade/management/commands/refresh_positions.py`
- Nightly batch job
- Fetches latest position per portfolio/security/position_basis
- Revalues with latest market price
- Inserts new rows with `position_type='EOD'`
- Creates EOD for both `TRADE_DATE` and `SETTLE_DATE` basis

### SOD Generation
**File:** `trade/management/commands/create_sod_snapshot.py`
- Morning batch job
- Reads previous business day's EOD rows
- Copies all values forward to today's date
- Inserts with `position_type='SOD'`

### Backdated Trade Handling
**File:** `trade/services/settlement_service.py` — `_process_backdated_settlement()`
- Allowed for any past date
- Triggers `_recalculate_position_chain()` from past date to today
- Re-processes all trades in that date range
- Uses versioning: marks old rows `is_latest=false`, inserts new version

### Dual Position Logic
**File:** `trade/services/settlement_service.py`
- Every trade creates TWO positions:
  - `position_basis='TRADE_DATE'`, `position_date=trade_date`
  - `position_basis='SETTLE_DATE'`, `position_date=settle_date`
- Each basis chain is scoped independently (no cross-contamination of AVP)

---

## ✅ What is Correct

| Area | Detail |
|------|--------|
| **INT** on same-day trade | `_derive_position_type()` returns `INT` when `position_date == today` |
| **CORR** on backdated trade | Returns `CORR` when `position_date < today` |
| **EOD** nightly generation | `refresh_positions` command revalues and inserts EOD rows |
| **SOD** morning generation | `create_sod_snapshot` copies previous EOD to today as SOD |
| **Future date blocked** | Trade date > today rejected in `validate_settlement_date()` with UI popup |
| **Dual positions** | TRADE_DATE + SETTLE_DATE basis both created per trade |
| **Backdated chain recalc** | Re-processes all trades from backdated date to today via versioning |

---

## ❌ What is Missing / Incorrect

### 1. `BACK` type is never created
**Expected:** Backdated trade → `BACK` position on the past business date

**Actual:** Code only produces `CORR` for any past date. The `BACK` type is not defined or used anywhere in the codebase.

**Files affected:**
- `trade/services/position_service.py` — `_derive_position_type()` has no BACK branch
- `trade/services/settlement_service.py` — no BACK creation in backdated flow

---

### 2. No INT created on current system date for backdated trades
**Expected:** Backdated trade → BACK on TD + **INT on current system date** to reflect impact

**Actual:** `_process_backdated_settlement()` only creates a CORR on the past date and runs chain recalculation. No INT position is explicitly created on `contextual_today`.

**Files affected:**
- `trade/services/settlement_service.py` — `_process_backdated_settlement()`

---

### 3. Upload service fallback to `INT` for future dates
**Expected:** Future dated rows in upload should be blocked entirely

**Actual:** `upload_service.py` Step 7A CASE expression:
```sql
CASE
    WHEN reporting_date = today THEN 'INT'
    WHEN reporting_date < today THEN 'CORR'
    ELSE 'INT'   -- ← future rows fall through to INT instead of being excluded
END
```
Future rows are counted and warned but still inserted with `position_type='INT'`.

**Files affected:**
- `upload/services/upload_service.py` — Step 7A SQL

---

## ⚠️ Potential Edge Cases

### 1. EOD/SOD stale after backdated correction
If a `CORR` position is created for a past date **after** EOD already ran for that date, the historical EOD row is stale but not invalidated or re-run. Chain recalculation updates INT on today but does not re-generate EOD for the corrected historical date.

**Risk:** Historical EOD rows show wrong AVP/P&L even after a correction.

---

### 2. SETTLE_DATE position blocked for T+1/T+2 trades
`_derive_position_type()` blocks any `position_date > today`. For a trade with `settle_date = T+2`, the SETTLE_DATE basis position will fail silently because the settlement date is in the future.

**Risk:** T+1/T+2 settlement trades never get a SETTLE_DATE position created.

**Files affected:**
- `trade/services/position_service.py` — `_derive_position_type()` needs a separate code path for SETTLE_DATE basis (allow future settle dates, queue them)
- `trade/services/settlement_service.py` — `cis_settlement_queue` exists for this but may not be wired end-to-end

---

### 3. SOD copies from wrong day on holidays
`create_sod_snapshot` uses the reference date table (`gmp_cis_sta_dly_alldatesinfo`) to determine `prev_yyyymmdd`. If the table is stale or missing a holiday record, SOD copies from the wrong source EOD date.

**Risk:** SOD opening positions carry wrong balances after a holiday weekend.

---

## Summary Table

| Type | When Created | Position Date | Implemented | Notes |
|------|-------------|---------------|-------------|-------|
| `INT` | Trade on today's date | `trade_date` or `settle_date` | ✅ Yes | Via `_derive_position_type()` |
| `CORR` | Backdated trade entry | Past date | ✅ Yes | Any `position_date < today` |
| `EOD` | Nightly batch | Today | ✅ Yes | `refresh_positions` command |
| `SOD` | Morning batch | Today | ✅ Yes | `create_sod_snapshot` command |
| `BACK` | Backdated trade (separate from CORR) | Past business date | ❌ Never | Not implemented |
| `INT` on today (backdated impact) | After backdated trade | `contextual_today` | ❌ Missing | Expected per spec |

---

## Key Files Reference

| File | Role |
|------|------|
| `trade/services/position_service.py` | Position type derivation, AVP calculation |
| `trade/services/settlement_service.py` | Dual position logic, backdated handling |
| `trade/services/position_queue_service.py` | Async chain recalculation |
| `trade/management/commands/refresh_positions.py` | EOD batch generation |
| `trade/management/commands/create_sod_snapshot.py` | SOD batch generation |
| `upload/services/upload_service.py` | Bulk upload position type assignment |
| `core/services/system_date_service.py` | `contextual_today` from alldatesinfo |
