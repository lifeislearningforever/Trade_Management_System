# Trade Management

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~15 minutes

---

## What Is a Trade?

A trade is a financial transaction — buying or selling a security (share, bond, etc.) for a portfolio, at a specific price, on a specific date.

In CIS, every trade follows a strict lifecycle with a mandatory approval step (the Four-Eyes rule) before it can affect positions or reporting.

---

## Trade Lifecycle (Plain English)

```
        ┌─────────────────────────────────────────────────────┐
        │                                                     │
  1.    │  Trader enters trade details, saves                 │
        │  Status: INITIAL                                    │
        │                                                     │
  2.    │  Trader reviews, optionally modifies               │
        │  Status: MODIFIED  (only if edited after creation) │
        │                                                     │
  3.    │  Trader clicks "Submit for Validation"             │
        │  Status: PENDING_VALIDATION                         │
        │                                                     │
  4a.   │  Checker reviews and APPROVES                      │
        │  Status: VALIDATED                                  │
        │                                                     │
  4b.   │  Checker reviews and REJECTS                       │
        │  Status: CANCELLED (trader can re-enter if needed) │
        │                                                     │
  5.    │  Settlement processing runs                         │
        │  Status: SETTLED                                    │
        │  → Position (AVP) updated automatically            │
        └─────────────────────────────────────────────────────┘
```

**Key rule:** The person who creates a trade cannot be the one to approve it.

---

## Trade Types

| Type | What it means |
|------|--------------|
| `BUY` | Purchase securities — increases holding |
| `SELL` | Sell securities — decreases holding |
| `ADD_LONG` | Add to an existing long position (similar to BUY but specific accounting treatment) |
| `DELIVER_LONG` | Deliver from an existing position (physical delivery) |
| `REDUCTION_BASIS` | Reduce the cost basis of a position (no quantity change) |
| `INCOME` | Income receipt — dividends, coupons |
| `SPLIT_TRANSACTION` | Stock split — adjusts quantity, recalculates average cost |

---

## What CIS Shows in the Trade List

When you open the Trade List, you see both CIS-created trades and GMP-sourced trades in one list:

| Column | CIS Trade | GMP Trade |
|--------|-----------|-----------|
| `src_system` | `CIS` | `GMP` |
| Edit button | Shown | Hidden |
| Status workflow | Full lifecycle | Pre-settled (view only) |
| Who can change | Trader + Checker | Nobody (ETL-controlled) |

CIS trades always sort first.

---

## Trade Fields Explained

### Core Fields

| Field | Description | Who sets it |
|-------|-------------|-------------|
| `trade_id` | Unique internal ID | System (auto) |
| `deal_number` | External reference number | Trader / GMP ETL |
| `trade_type` | BUY, SELL, etc. | Trader |
| `portfolio_short_name` | Which portfolio | Trader |
| `security_label` | Which security (e.g. AAPL) | Trader |
| `trade_date` | Date the trade was executed | Trader |
| `settle_date` | Date the trade settles (T+1, T+2, etc.) | Trader |
| `quantity` | Number of shares/units | Trader |
| `price` | Execution price | Trader |

### Financial Fields

| Field | Description |
|-------|-------------|
| `total_amount` | `quantity × price` |
| `total_amount_fc` | Total in the security's foreign currency |
| `total_amount_lc` | Total in the portfolio's local currency |
| `commission` | Broker commission |
| `sec_fee` | Securities transaction fee |
| `other_charges` | Any other charges |
| `accrued_interest` | For bonds — accrued interest on settlement |
| `portfolio_currency` | Portfolio's base currency |

### Workflow Fields

| Field | Description |
|-------|-------------|
| `status` | Current lifecycle status |
| `src_system` | `CIS` or `GMP` |
| `created_by` | User who created the trade |
| `submitted_by` | User who submitted for validation |
| `validated_by` | Checker who approved |
| `settled_by` | User/system that settled |
| `is_active` | `true` for live records |
| `is_deleted` | `true` if soft-deleted |

---

## Validation Rules

Before a trade is accepted, CIS checks:

| Rule | What is checked | Error if fails |
|------|-----------------|---------------|
| Portfolio exists | `portfolio_short_name` must exist in `cis_portfolio` | "Portfolio not found" |
| Portfolio is active | Portfolio status must be in `VALIDATED`, `SETTLED`, or `ACTIVE` | "Portfolio not active" |
| Security exists | `security_label` must exist in `cis_security` | "Security not found" |
| Security is approved | Security status must be `ACTIVE`, `APPROVED`, `INITIAL`, `VALIDATED`, or `SETTLED` | "Security not approved" |
| Counterparty exists | Must be in `cis_counterparty_kudu`, `is_active = true` | "Counterparty not found" |
| No short selling | SELL quantity must not exceed current holding | "Insufficient position" |
| Settle date valid | Must be ≥ trade date | "Invalid settle date" |

---

## Settlement Timing

| Settle Date | What happens |
|-------------|-------------|
| Same day (T+0) | Position calculated immediately after validation |
| T+1 / T+2 | Trade queued in `cis_settlement_queue`, processed on settle date by EOD job |
| Backdated | Allowed — triggers position recalculation for all subsequent trades in the chain |

---

## Position Update After Settlement

When a trade is SETTLED, it automatically triggers position recalculation:

- An event is written to `cis_position_queue`
- The background position worker picks it up (within 5 minutes)
- The AVP (average cost) for that portfolio/security is recalculated
- The result is written to `cis_trade_position`

See [05c — Position & AVP](05c_position_avp.md) for full details.

---

## Trade History

Every change to a trade creates a history record in `cis_trade_history`. You can see the complete change log from the trade detail page.

Each history record captures:
- What changed (old value → new value as JSON)
- Who made the change
- When the change happened
- What the status was at that point

---

## For Users: Step-by-Step

### Creating a Trade

1. Click **Trade → Create Trade**
2. Select a **Portfolio** (must be ACTIVE)
3. Select a **Security**
4. Choose **Trade Type** (BUY, SELL, etc.)
5. Enter **Trade Date** and **Settle Date**
6. Enter **Quantity** and **Price**
7. Enter any charges (Commission, SEC Fee)
8. Click **Save** → trade is INITIAL
9. Review the details
10. Click **Submit for Validation** → trade is PENDING_VALIDATION

### Approving a Trade (Checker)

1. Click **Trade → Pending Validation**
2. Select the trade to review
3. Review all details carefully
4. Click **Validate** to approve → trade becomes VALIDATED
   OR
5. Click **Reject** with a comment → trade becomes CANCELLED

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `trade/repositories/trade_kudu_repository.py` | All SQL queries on `cis_trade` |
| `trade/repositories/trade_validation_repository.py` | Checks portfolio, security, counterparty exist |
| `trade/services/trade_service.py` | Business logic, status transitions |
| `trade/views.py` | HTTP handlers for trade CRUD |
| `trade/views_position.py` | Position-related views |
| `trade/views_cash_flow.py` | Cash flow views |
| `trade/management/commands/process_settlements.py` | EOD settlement command |
| `sql/ddl/06_trade_tables_kudu.sql` | Core trade DDL |
| `sql/ddl/09_trade_validation_views.sql` | Validation SQL views |

### Key Query Pattern

```python
# Get all trades for a portfolio (trade_kudu_repository.py)
query = f"""
    SELECT trade_id, deal_number, trade_type, security_label,
           trade_date, settle_date, quantity, price, total_amount_fc,
           total_amount_lc, status, src_system, created_by, created_at
    FROM gmp_cis.cis_trade
    WHERE portfolio_short_name = '{portfolio_name}'
      AND is_active = true
      AND is_deleted = false
    ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END,
             created_at DESC
    LIMIT {limit}
"""
```

### UPSERT Pattern (all writes)
```python
query = """
    UPSERT INTO gmp_cis.cis_trade
    (trade_id, trade_type, portfolio_short_name, ..., status, updated_by, updated_at)
    VALUES (?, ?, ?, ..., ?, ?, ?)
"""
impala_manager.execute_write(query, params)
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Trade stuck in PENDING_VALIDATION | Has a checker reviewed it? Does the checker have `trade-approve` permission? |
| Trade shows "Portfolio not active" | Check portfolio status in cis_portfolio |
| GMP trade has wrong data | This comes from the ETL — check Control-M job log for that business_date |
| Position not updated after settlement | Check `cis_position_queue` for PENDING/FAILED entries for this trade |
| Trade cannot be edited | It may be SETTLED (no editing allowed) or it may be a GMP trade (src_system='GMP') |
