# EOD Position Processing Flow — BA/SA Verification Guide

**System:** CIS Trade Hive  
**Last Updated:** 2026-06-11  
**Audience:** Business Analysts / System Analysts

---

## Overview

The EOD pipeline runs three management commands in sequence each evening:

```
Step 1  →  process_corporate_actions      (CA → cash flow records)
Step 2  →  process_approved_cashflows     (cash flows → position update)
Step 3  →  refresh_positions              (EOD revaluation → EOD position snapshot)
```

All position data lives in two tables:

| Table | Purpose | Write Pattern |
|---|---|---|
| `cis_trade_position` | CIS versioned ledger (BUY/SELL/cashflow history) | Mark old row `is_latest=false`, INSERT new row |
| `cis_position` | Golden copy — all sources (CIS, GMP, AMSICEQ, USER_UPLOAD) | Append-only INSERT; never overwrite |

---

## Step 1 — Process Corporate Actions

**Command:** `python manage.py process_corporate_actions`

**Input:** `cis_ca_cash_flow_queue` — validated CAs waiting to be processed  
**Output:** New records in `cis_cash_flow` table

### What it does

For each pending CA in the queue whose `payment_date <= today`:

1. Looks up all portfolios holding the security (from `cis_position` golden copy as of ex-date)
2. Calculates per-portfolio cash flow amount: `quantity × price_per_share`
3. Creates one `cis_cash_flow` record per portfolio/security holding
4. Marks the queue entry `COMPLETED`

### CA type → cash flow mapping

| CA Type | Cash Flow Type Created | Position Field Affected (Step 2) |
|---|---|---|
| `DIVIDEND` | `DIVIDEND` | `dividend_fc / dividend_lc` |
| `SPECIAL_DIVIDEND` | `DIVIDEND` | `dividend_fc / dividend_lc` |
| `INTEREST` | `INTEREST` | `dividend_fc / dividend_lc` |
| `COUPON` | `COUPON` | `dividend_fc / dividend_lc` |
| `INCOME_DISTRIBUTION` | `INCOME_DISTRIBUTION` | `realized_pnl_fc / realized_pnl_lc` |
| `ROC` | `RETURN_OF_CAPITAL` | AVP reduction (see Step 2) |
| `CAPITAL_DISTRIBUTION` | `CAPITAL_DISTRIBUTION` | AVP reduction (see Step 2) |
| `SPLIT` | — | Quantity adjustment only (no cash flow) |

**Idempotency:** A CA is skipped if a cash flow record already exists for the same `ca_id + portfolio + security`.

---

## Step 2 — Process Approved Cash Flows

**Command:** `python manage.py process_approved_cashflows [--date YYYY-MM-DD]`

**Input:** `cis_cash_flow` — records with `status=APPROVED` or `status=VALIDATED`, `payment_date <= run_date`  
**Output:** Updated rows in `cis_trade_position` (CIS) and `cis_position` (golden copy)

**Position basis affected:** `SETTLED` only

### Cash flow type processing rules

| Cash Flow Type | Field Updated | Accumulation Rule |
|---|---|---|
| `UNCALL_COMMITMENT` | `uncall_fc / uncall_lc` | Add amount (accumulate) |
| `PROVISION` | `provision_fc / provision_lc` | Add amount (accumulate) |
| `PIPELINE` | `pipeline_fc / pipeline_lc` | Add amount (accumulate) |
| `YTD_REALISE` | `realized_pnl_fc / realized_pnl_lc` | Add amount (accumulate) |
| `DIVIDEND` / `CASH_DIVIDEND` | `dividend_fc / dividend_lc` | Add amount (accumulate) |
| `INCOME_DISTRIBUTION` | `realized_pnl_fc / realized_pnl_lc` | Add amount (accumulate) |
| `RETURN_OF_CAPITAL` | `average_cost_fc` | AVP reduction: `avp_new = avp_old − (amount_fc ÷ qty)` |
| `CAPITAL_DISTRIBUTION` | `average_cost_fc` | AVP reduction: `avp_new = avp_old − (amount_fc ÷ qty)` |
| `OTHER` | — | Skipped (warning logged) |

### Send/Receive sign convention

| Type | SEND | RECEIVE | NULL |
|---|---|---|---|
| All types (except dividend) | + (increase) | − (decrease) | + (treated as SEND, warning logged) |
| `DIVIDEND` / `CASH_DIVIDEND` | − (fund paid out) | + (fund received) | + |

### New `cis_position` row written

After updating `cis_trade_position`, a new row is inserted into `cis_position` with:
- `position_type = 'INT'`
- `position_basis = 'SETTLED'`
- All accumulated CF fields carried forward
- `position_date` = the cash flow `payment_date`

**Idempotency:** `position_updated = true` is set on the cash flow record after processing; re-runs skip already-processed records.

---

## Step 3 — EOD Revaluation (refresh_positions)

**Command:** `python manage.py refresh_positions [--portfolio X] [--source CIS|GMP|AMSICEQ|USER_UPLOAD]`

**Input:** Latest row per `portfolio/security/position_basis` from `cis_position` (any `position_type`, `quantity > 0`)  
**Output:** New `EOD` rows in `cis_position`

### Processing matrix by portfolio and security type

#### Case A — REVALUED portfolio, normal security (not ASSOC/SUBSI)

| Step | Logic |
|---|---|
| Price | Latest `cis_equity_price.main_closing_price` |
| `market_value_fc` | `quantity × latest_price` |
| `market_value_lc` | `market_value_fc × fx_rate` |
| `average_cost_lc` | Recalculated: `average_cost_fc × fx_rate` |
| `cost_lc` | Recalculated: `cost_fc × fx_rate` |
| `unrealized_pnl_fc` | `market_value_fc − cost_fc` |
| `unrealized_pnl_lc` | `market_value_lc − cost_lc` |
| `net_book_value_fc` | `cost_fc + unrealized_pnl_fc − provision_fc` |
| `net_book_value_lc` | `cost_lc + unrealized_pnl_lc − provision_lc` |

#### Case B — NON-REVALUED portfolio, normal security

| Step | Logic |
|---|---|
| Price | Latest `cis_equity_price.main_closing_price` |
| `market_value_fc` | `quantity × latest_price` (price used for FC) |
| `market_value_lc` | `market_value_fc × fx_rate` (LC recalculated via FX) |
| `average_cost_lc` | **Carried forward** from source position (no MTM override) |
| `cost_lc` | **Carried forward** from source position (no MTM override) |
| `unrealized_pnl_fc` | `market_value_fc − cost_fc` |
| `unrealized_pnl_lc` | `market_value_lc − cost_lc` (uses carried-forward cost_lc) |
| `net_book_value_*` | Same formula as Case A |

#### Case C — Equity-method security (`security_investment = ASSOC` or `SUBSI`)

Applies regardless of portfolio revaluation status.

| Step | Logic |
|---|---|
| Price | Latest `cis_equity_price.main_closing_price` |
| `market_value_fc` | `quantity × latest_price` |
| `market_value_lc` | `market_value_fc × fx_rate` |
| `unrealized_pnl_fc` | **0** (equity-method — no mark-to-market P&L) |
| `unrealized_pnl_lc` | **0** |
| `net_book_value_fc` | `cost_fc + 0 − provision_fc` = `cost_fc − provision_fc` |
| `net_book_value_lc` | `cost_lc + 0 − provision_lc` = `cost_lc − provision_lc` |

#### Case D — No price available (any portfolio/security type)

| Step | Logic |
|---|---|
| Price | Not found in `cis_equity_price` |
| `market_value_fc` | **Carried forward** from source position |
| `market_value_lc` | `market_value_fc × latest_fx_rate` (FX refreshed) |
| All other fields | Same formulas as the applicable case above |

### FX Rate

- Source: `gmp_cis_sta_dly_fx_rates`
- Pair: `ref_quot_ccy = '{security_currency}-{portfolio_currency}'`
- Value: `spot_rate_d` — FC → LC multiplier
- If same currency, FX rate = 1 (no conversion)
- No fallback or inversion — if pair not found, rate = 1 and a warning is logged

### Currency Rounding

- Decimal places from `gmp_cis_sta_dly_currency.precision`  
  (e.g. `'0000000000.01'` → 2 dp)
- Default: 2 dp if currency not found

### Output rows written

For each source position processed:

- **DELETE** any existing `EOD` row for the same `(portfolio, security_label, position_basis, position_date)`
- **INSERT** new `cis_position` row with:
  - `position_type = 'EOD'`
  - `position_date` = source position's own `position_date`
  - `position_basis` = same as source (`TRADED` or `SETTLED`)
  - All accumulated CF fields (`dividend_fc`, `uncall_fc`, `provision_fc`, `pipeline_fc`, `realized_pnl_fc`) **carried forward unchanged** from the source row

---

## End-to-end Verification Checklist

### Pre-run checks

- [ ] `cis_equity_price` — prices loaded for today's date (`is_active = true`)
- [ ] `gmp_cis_sta_dly_fx_rates` — FX rates loaded for today's date
- [ ] `gmp_cis_sta_dly_currency` — currency precision table populated
- [ ] `cis_ca_cash_flow_queue` — pending CA queue entries for today

### Post Step 1 (CA → Cash Flows)

```sql
-- Verify cash flows created today
SELECT ca_id, cash_flow_type, portfolio_short_name, security_label,
       amount_fc, amount_lc, payment_date, status
FROM gmp_cis.cis_cash_flow
WHERE payment_date = CURRENT_DATE()
  AND src_system = 'CA'
ORDER BY ca_id;
```

### Post Step 2 (Cash Flows → Positions)

```sql
-- Verify INT rows created today (SETTLED basis)
SELECT portfolio, security_label, position_basis, position_date,
       position_type, dividend_fc, uncall_fc, provision_fc, pipeline_fc, realized_pnl_fc
FROM gmp_cis.cis_position
WHERE position_type = 'INT'
  AND position_date = CURRENT_DATE()
ORDER BY portfolio, security_label;
```

```sql
-- Verify cash flows marked as processed
SELECT COUNT(*) AS total,
       SUM(CASE WHEN position_updated = true THEN 1 ELSE 0 END) AS processed
FROM gmp_cis.cis_cash_flow
WHERE payment_date = CURRENT_DATE();
```

### Post Step 3 (EOD Revaluation)

```sql
-- Verify EOD rows for today
SELECT portfolio, security_label, position_basis, position_date,
       position_type, quantity,
       market_value_fc, market_value_lc,
       unrealized_pnl_fc, unrealized_pnl_lc,
       net_book_value_fc, net_book_value_lc
FROM gmp_cis.cis_position
WHERE position_type = 'EOD'
ORDER BY portfolio, security_label, position_basis;
```

```sql
-- Spot-check: REVALUED portfolio — cost_lc should differ from INT row
SELECT p1.portfolio, p1.security_label, p1.position_basis,
       p1.cost_lc AS int_cost_lc,
       p2.cost_lc AS eod_cost_lc,
       p2.market_value_fc, p2.unrealized_pnl_fc
FROM gmp_cis.cis_position p1
JOIN gmp_cis.cis_position p2
  ON p1.portfolio = p2.portfolio
 AND p1.security_label = p2.security_label
 AND p1.position_basis = p2.position_basis
WHERE p1.position_type = 'INT'
  AND p2.position_type = 'EOD'
  AND p2.position_date = CURRENT_DATE()
ORDER BY p1.portfolio, p1.security_label;
```

```sql
-- Spot-check: Equity-method securities — unrealized_pnl_fc must be 0
SELECT portfolio, security_label, position_type,
       unrealized_pnl_fc, unrealized_pnl_lc, market_value_fc
FROM gmp_cis.cis_position cp
JOIN gmp_cis.cis_security cs ON cp.security_label = cs.security_name
WHERE cp.position_type = 'EOD'
  AND cp.position_date = CURRENT_DATE()
  AND cs.security_investment IN ('ASSOC', 'SUBSI');
-- Expected: unrealized_pnl_fc = 0 for all rows
```

---

## Common Issues / Edge Cases

| Scenario | Expected Behaviour | How to Verify |
|---|---|---|
| No price in `cis_equity_price` | `market_value_fc` carried forward from source; `market_value_lc` recalculated via FX | `market_value_fc` unchanged vs INT row |
| Security not in `cis_security` | `sec_ccy` not found → FX rate = 1, `fc_dp` = 2 (default) | Warning in logs; LC = FC amount |
| Portfolio not in `cis_portfolio` | `port_ccy` not found → FX rate = 1, `lc_dp` = 2 (default) | Warning in logs |
| FX pair not in `gmp_cis_sta_dly_fx_rates` | Rate defaults to 1 (no conversion) | LC values = FC values |
| CA already processed (duplicate run) | Step 1 skipped (idempotent by `ca_id + portfolio`) | Queue entry stays `COMPLETED` |
| Cash flow already processed | Step 2 skipped (`position_updated = true`) | `cis_cash_flow.position_updated = true` |
| EOD run twice on same date | Previous EOD row deleted, new row inserted | Only one EOD row per `portfolio/security/basis/date` |
| `quantity = 0` | Position skipped in EOD revaluation | No EOD row written |
| Backdated cash flow | Processed normally; `position_date` = payment_date of CF | INT row date = CF payment_date |

---

## EOD Run Schedule (Reference)

```
18:00  process_corporate_actions        # CA queue → cis_cash_flow
18:15  process_approved_cashflows       # cis_cash_flow → INT rows in cis_position
18:30  refresh_positions                # INT rows → EOD rows in cis_position
```

---

## Position Type Reference

| `position_type` | Written By | Basis | Description |
|---|---|---|---|
| `INT` | Trade creation, cashflow processing, CA processing | TRADED + SETTLED | Intraday working position |
| `EOD` | `refresh_positions` command | TRADED + SETTLED | End-of-day revalued snapshot |
| `SOD` | SOD snapshot job (future) | TRADED + SETTLED | Start-of-day snapshot |
