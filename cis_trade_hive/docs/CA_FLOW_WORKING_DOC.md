# Corporate Action (CA) — Full Working Document

**Last Updated:** 2026-04-21  
**Branch:** cis_trade_hive  
**Status:** Production-ready (post-fix commit 973e8d6)

---

## 1. Overview

Corporate Actions (CAs) in CIS Trade Hive follow a two-phase lifecycle:

1. **Maker-Checker Phase** — A user creates the CA; a second user validates it (Four-Eyes principle)
2. **EOD Processing Phase** — A background job picks up validated CAs, finds all portfolio holdings for the security, and generates cash flows / position adjustments

CAs are created at the **security level** — not tied to a specific portfolio. The EOD job discovers all portfolios holding the security from `cis_trade_position` and applies the CA to each one.

---

## 2. CA Types Reference

### 2A. Cash Flow CA Types
Generate a `cis_cash_flow` record per portfolio holding.

| CA Type | Cash Flow Type | AVP Change | Position Field Updated |
|---|---|---|---|
| `DIVIDEND` | DIVIDEND | No change | `dividend_fc` / `dividend_lc` accumulated |
| `SPECIAL_DIVIDEND` | SPECIAL_DIVIDEND | No change | `dividend_fc` / `dividend_lc` accumulated |
| `INTEREST` | INTEREST | No change | None |
| `COUPON` | COUPON | No change | None |
| `ROC` | ROC | `avp_new = avp_old - price_per_share` | `total_cost_fc/lc` recalculated |
| `CAPITAL_DISTRIBUTION` | CAPITAL_DISTRIBUTION | `avp_new = avp_old - price_per_share` | `total_cost_fc/lc` recalculated |
| `INCOME_DISTRIBUTION` | INCOME_DISTRIBUTION | No change | `realized_pnl_fc` / `realized_pnl_lc` accumulated |

**Cash flow amount formula:**
```
amount_fc = quantity × price
amount_lc = amount_fc × fx_rate (security_ccy → portfolio_ccy)
```

---

### 2B. Position Adjustment CA Types
No cash flow record. Modify quantity / AVP in `cis_trade_position`.

| CA Type | Qty Change | AVP Change |
|---|---|---|
| `BONUS_ISSUE` | `qty_new = qty_old × (1 + ratio)` | `total_cost / new_qty` |
| `SPLIT` / `STOCK_SPLIT` | `qty_new = qty_old × ratio` | `avp_old / ratio` |
| `REVERSE_SPLIT` / `CONSOLIDATION` | `qty_new = qty_old / ratio` | `avp_old × ratio` |
| `RIGHTS_ENTITLEMENT` / `RIGHTS_ISSUE` | Creates new position for `<security> RIGHTS` | AVP = 0 |
| `WARRANT_ENTITLEMENT` | Creates new position for `<security> WRNTS` | AVP = 0 |

**Bonus/Split note:** Total cost basis is always preserved. Only AVP recalculates.

**Rights/Warrants note:** The price field in the CA stores the entitlement ratio.  
`entitlement_qty = existing_qty × price`  
A brand-new `cis_trade_position` row is created for the rights/warrant security with AVP = 0.

---

### 2C. CF Position Overwrite Types
No cash flow record. Overwrites a specific field on the current SETTLE_DATE position version.

| CA Type | Field Overwritten |
|---|---|
| `CF-COMMITMENT` | `commit_fc` / `commit_lc` |
| `CF-UN CALL COMMITMENT` | `uncall_fc` / `uncall_lc` |
| `CF-PIPELINE` | `pipeline_fc` / `pipeline_lc` |
| `CF-YTD` | `realized_pnl_fc` / `realized_pnl_lc` |
| `CF-PROVISION` | `provision_fc` / `provision_lc` |

The `price` field in the CA stores the new FC value. LC is calculated via FX rate at ex_date.  
All other position fields are carried forward unchanged.

---

## 3. Database Tables

| Table | Purpose |
|---|---|
| `cis_corporate_actions` | CA master data — security, type, dates, price |
| `cis_corporate_actions_history` | Audit trail for CA lifecycle changes |
| `cis_ca_cash_flow_queue` | Processing queue (PENDING → PROCESSING → COMPLETED/FAILED) |
| `cis_ca_cash_flow_log` | Per-portfolio processing result log |
| `cis_cash_flow` | Generated cash flow records (`src_system = 'CA'`) |
| `cis_trade_position` | Position table — updated with new version after each CA |

---

## 4. CA Lifecycle — Step by Step

### Step 1: Create CA (Maker)

**UI:** `/reference-data/corporate-actions/create/`  
**Service:** `corporate_action_service.create()`  
**Status after:** `INITIAL`

Required fields:
- `security_name` — security label (comma-separated for multi-security)
- `ca_type` — see types above
- `ex_date` — ex-dividend / effective date (YYYY-MM-DD)
- `price` — per-share amount (cash flow types) or ratio (position adjustment types)
- `currency` — security currency

Optional: `record_date`, `payment_date`

---

### Step 2: Validate CA (Checker)

**UI:** `/reference-data/corporate-actions/<id>/validate/`  
**Service:** `corporate_action_service.validate()`  
**Status after:** `VALIDATED`

Rules:
- Checker must be a **different user** than the maker (Four-Eyes principle)
- Only `INITIAL` or `MODIFIED` records can be validated
- On validation, `ca_cash_flow_service.queue_ca_for_processing()` is called automatically
- Inserts a row into `cis_ca_cash_flow_queue` with status `PENDING`

If the CA type does not require processing (e.g. NAME_CHANGE), the queue step is silently skipped.

---

### Step 3: Reject CA (Checker)

**UI:** `/reference-data/corporate-actions/<id>/reject/`  
**Service:** `corporate_action_service.reject()`  
**Status after:** `REJECTED`

Same Four-Eyes rule applies.  
No queue entry is created. The CA can be edited and re-submitted.

---

### Step 4: Edit Validated CA (Maker)

**UI:** `/reference-data/corporate-actions/<id>/edit/`  
**Service:** `corporate_action_service.update()`  
**Status after:** `MODIFIED`

Only `CIS` source system CAs can be edited (not GMP-synced records).  
After edit, the CA returns to `MODIFIED` and must be re-validated before EOD processes it.

---

### Step 5: EOD Processing

**Command:**
```bash
python manage.py process_corporate_actions
```

**Processing flow per queue entry:**

```
cis_ca_cash_flow_queue (PENDING)
    ↓
Mark as PROCESSING
    ↓
Route by ca_type:
  ├── CASH_FLOW types  → get_holdings_for_ca()
  │                    → for each holding: create_cash_flow_from_ca()
  │                    →                   _update_position_with_ca_details()
  ├── POSITION_ADJUSTMENT types → get_holdings_for_ca()
  │                              → for each holding: _process_bonus_issue()
  │                              →                or _process_stock_split()
  │                              →                or _process_reverse_split()
  │                              →                or _create_rights_warrant_position()
  └── CF_POSITION_OVERWRITE types → get_holdings_for_ca()
                                  → for each holding: _overwrite_position_field()
    ↓
Mark as COMPLETED (or FAILED)
    ↓
Insert log row to cis_ca_cash_flow_log
```

---

## 5. Holdings Lookup

`get_holdings_for_ca(security_name, as_of_date)` queries `cis_trade_position`:

```sql
SELECT p.*
FROM cis_trade_position p
INNER JOIN (
    SELECT portfolio_short_name, security_label, MAX(position_date) as max_date
    FROM cis_trade_position
    WHERE security_label = '<security>'
      AND position_date <= '<ex_date>'
      AND status = 'OPEN'
      AND is_active = true
    GROUP BY portfolio_short_name, security_label
) latest ON p.portfolio_short_name = latest.portfolio_short_name
        AND p.security_label = latest.security_label
        AND p.position_date = latest.max_date
LEFT JOIN cis_portfolio pf ON p.portfolio_short_name = pf.name
WHERE p.quantity > 0
  AND p.status = 'OPEN'
  AND p.is_active = true
```

**Important:** The query does NOT filter by `position_basis`. It picks the latest version across both TRADE_DATE and SETTLE_DATE. However, `_get_current_position()` (used when writing the new position version) always targets `SETTLE_DATE`.

**If no holdings are found:** The queue entry is marked `COMPLETED` with `cash_flows_created = 0`. This is intentional — the CA is considered processed even if no portfolios held the security on the ex_date.

---

## 6. Position Updates — Version Tracking

Every CA event writes a **new version** to `cis_trade_position` (append-only versioning):

1. `_mark_old_version_not_latest(old_version_id)` — sets `is_latest = false` on the current row
2. New row inserted with `is_latest = true`, same `position_id`, new `version_id` (epoch ms)

All new CA position rows:
- `position_basis = 'SETTLE_DATE'`
- `position_date = ex_date`
- `trade_type = 'CA_<ca_type>'` (e.g. `CA_DIVIDEND`)
- `last_ca_id`, `last_ca_number`, `last_ca_type`, `last_ca_date` populated

---

## 7. Duplicate Prevention

`_check_existing_cash_flow()` queries `cis_cash_flow`:

```sql
SELECT cash_flow_id, cash_flow_number
FROM cis_cash_flow
WHERE ca_number = '<ca_number>'
  AND portfolio_short_name = '<portfolio>'
  AND security_label = '<security>'
  AND ex_date = '<ex_date>'
  AND (is_deleted = false OR is_deleted IS NULL)
LIMIT 1
```

If a match is found **and** the result has a non-null `cash_flow_id`, the cash flow creation is skipped (returns the existing cash flow ID).

This prevents duplicate cash flows when the EOD job is re-run on the same CA.

---

## 8. CLI Commands

### Check queue status
```bash
python manage.py process_corporate_actions --status
```

### Process all pending (normal EOD run)
```bash
python manage.py process_corporate_actions
```

### Dry run (preview without writing)
```bash
python manage.py process_corporate_actions --dry-run
```

### Process specific CA
```bash
python manage.py process_corporate_actions --ca-id <ca_id>
```

### Process specific queue entry
```bash
python manage.py process_corporate_actions --queue-id <queue_id>
```

### Reset stuck PROCESSING entries
```bash
python manage.py process_corporate_actions --reset-stuck
```

### Retry failed entries (up to 3 attempts)
```bash
python manage.py process_corporate_actions --retry-failed
```

### Re-run completed queue (manual SQL reset required)
```sql
-- Reset all COMPLETED entries back to PENDING
UPDATE gmp_cis.cis_ca_cash_flow_queue
SET status = 'PENDING', error_message = NULL
WHERE status = 'COMPLETED';
```
Then run the normal EOD command.  
**Note:** This will skip cash flow creation for entries where the duplicate check finds an existing cash flow.

---

## 9. Verification Queries

### Check queue state
```sql
SELECT status, COUNT(*) as cnt, SUM(cash_flows_created) as cfs
FROM gmp_cis.cis_ca_cash_flow_queue
GROUP BY status;
```

### Check cash flows created by CA
```sql
SELECT ca_number, portfolio_short_name, security_label,
       cash_flow_type, foreign_ccy_amt, local_ccy_amt, status
FROM gmp_cis.cis_cash_flow
WHERE src_system = 'CA'
ORDER BY created_at DESC
LIMIT 50;
```

### Check per-CA processing log
```sql
SELECT l.*, q.ca_number, q.ca_type
FROM gmp_cis.cis_ca_cash_flow_log l
JOIN gmp_cis.cis_ca_cash_flow_queue q ON l.queue_id = q.queue_id
ORDER BY l.created_at DESC
LIMIT 50;
```

### Check position versions created by CA
```sql
SELECT version_id, position_date, position_basis, portfolio_short_name,
       security_label, quantity, average_cost_fc, dividend_fc,
       last_ca_number, last_ca_type, trade_type
FROM gmp_cis.cis_trade_position
WHERE trade_type LIKE 'CA_%'
ORDER BY updated_at DESC
LIMIT 50;
```

### Check holdings for a security (what the EOD job sees)
```sql
SELECT portfolio_short_name, security_label, quantity, position_date, position_basis
FROM gmp_cis.cis_trade_position
WHERE security_label = '<your_security>'
  AND status = 'OPEN'
  AND is_active = true
  AND is_latest = true
ORDER BY portfolio_short_name, position_basis;
```

---

## 10. Code Files

| File | Purpose |
|---|---|
| `reference_data/services/corporate_action_service.py` | Maker-checker CRUD + validation; triggers queue on validate |
| `reference_data/services/ca_cash_flow_service.py` | All EOD processing logic — routing, calculations, DB writes |
| `reference_data/repositories/ca_cash_flow_queue_repository.py` | Queue table CRUD (insert, mark_processing, mark_completed, mark_failed) |
| `reference_data/repositories/corporate_action_repository.py` | CA master table CRUD |
| `reference_data/management/commands/process_corporate_actions.py` | Django management command — CLI entry point for EOD job |
| `trade/repositories/cash_flow_repository.py` | `CashFlowRepository.insert()` — writes to `cis_cash_flow` |
| `trade/services/multicurrency_service.py` | `get_fx_rate()` — FX conversion for LC amounts |
| `sql/ddl/14_corporate_actions_kudu.sql` | DDL for `cis_corporate_actions` |
| `sql/ddl/16_ca_cash_flow_queue.sql` | DDL for `cis_ca_cash_flow_queue` + `cis_ca_cash_flow_log` |
| `sql/ddl/15_cash_flow_kudu.sql` | DDL for `cis_cash_flow` |
| `sql/ddl/13_avp_tables_kudu.sql` | DDL for `cis_trade_position` |
| `sql/ddl/24_position_add_commit_provision_columns.sql` | ALTER to add `commit_fc/lc`, `provision_fc/lc` to `cis_trade_position` |

---

## 11. Known Constraints / Edge Cases

| Situation | Behaviour |
|---|---|
| No holdings found on ex_date | Queue entry marked COMPLETED with 0 cash flows (not an error) |
| FX rate not found | Falls back to FX rate = 1 (amount_lc = amount_fc); warning logged |
| Duplicate cash flow (EOD re-run) | Skipped — returns existing cash_flow_id; no duplicate inserted |
| Rights/Warrants security name | Auto-generated as `<original_security> RIGHTS` or `<original_security> WRNTS` |
| CA edited after VALIDATED | Status reverts to MODIFIED; must be re-validated before EOD picks it up |
| GMP-sourced CA | Read-only in CIS UI; cannot be edited or deleted |
| Queue entry stuck in PROCESSING | Use `--reset-stuck` flag; or manually UPDATE status to PENDING |
| Max retries exceeded (3) | Entry stays FAILED; no longer returned by `get_pending()`; use `--retry-failed` to reset counter |
| position_basis on holdings query | `get_holdings_for_ca()` does not filter by basis — picks latest across both bases. Position writes always target SETTLE_DATE |
| CF-COMMITMENT / CF-PROVISION | Require DDL 24 to be run first (`commit_fc/lc`, `provision_fc/lc` columns) |

---

## 12. AVP Formula Reference

### DIVIDEND / SPECIAL_DIVIDEND / INTEREST / COUPON / INCOME_DISTRIBUTION
```
AVP unchanged
dividend_fc += qty × price       (DIVIDEND / SPECIAL_DIVIDEND only)
realized_pnl_fc += qty × price   (INCOME_DISTRIBUTION only)
```

### ROC / CAPITAL_DISTRIBUTION
```
price_per_share = price           (CA price field = per-share amount)
avp_new = avp_old - price_per_share   (floor at 0)
total_cost_new = avp_new × qty
```

### BONUS_ISSUE
```
qty_new = qty_old × (1 + ratio)   (ratio stored in price field, e.g. 0.1 for 1:10 bonus)
avp_new = total_cost / qty_new    (total cost unchanged)
```

### STOCK_SPLIT (Forward)
```
ratio = 1 / price                 (price field stores the fraction, e.g. 0.33 for 1:3 split → ratio=3)
qty_new = qty_old × ratio
avp_new = avp_old / ratio
total_cost unchanged
```

### REVERSE_SPLIT / CONSOLIDATION
```
ratio = price                     (price field stores the ratio directly, e.g. 3 for 3:1)
qty_new = qty_old / ratio
avp_new = avp_old × ratio
total_cost unchanged
```

### RIGHTS_ENTITLEMENT / RIGHTS_ISSUE / WARRANT_ENTITLEMENT
```
entitlement_qty = existing_qty × price   (price = entitlement ratio)
New position created: security = '<original> RIGHTS' or '<original> WRNTS'
AVP = 0
```

---

*Document auto-generated from code — reference_data/services/ca_cash_flow_service.py (commit 973e8d6)*
