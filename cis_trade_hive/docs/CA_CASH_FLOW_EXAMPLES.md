# Corporate Action Cash Flow Generation - Examples

## Overview

When a Corporate Action (CA) is validated, the system automatically generates cash flow entries based on the CA type and portfolio holdings.

**Key Concept**: Corporate Actions are created at the **security level**, not the portfolio level. When processing a CA, the system automatically finds **ALL portfolios** holding the security from `cis_trade_position` and creates cash flows for each portfolio-security combination.

---

## Example 1: Cash Dividend

### Scenario
- **Security**: AAPL (Apple Inc.)
- **CA Type**: DIVIDEND
- **Dividend Per Share**: $0.25 USD
- **Ex-Date**: 2026-03-15
- **Payment Date**: 2026-03-20

### Portfolio Holdings (as of Ex-Date)

| Portfolio | Security | Quantity Held |
|-----------|----------|---------------|
| EQUITY_FUND_A | AAPL | 10,000 shares |
| GROWTH_FUND_B | AAPL | 5,000 shares |
| BALANCED_FUND_C | AAPL | 2,500 shares |

### Corporate Action Record

**Note**: No portfolio is specified - CA applies to ALL portfolios holding the security.

```
CA Number:        CA-20260315-00001
CA Type:          DIVIDEND
Security:         AAPL
Ex Date:          2026-03-15
Record Date:      2026-03-16
Payment Date:     2026-03-20
Price:            0.25
Currency:         USD
Status:           VALIDATED
Created By:       john.maker
Validated By:     jane.checker
```

### Generated Cash Flows

When the CA is validated, the following cash flows are automatically created:

| CF Number | Portfolio | Security | Type | Direction | Quantity | Amount | Currency | Status |
|-----------|-----------|----------|------|-----------|----------|--------|----------|--------|
| CF-20260315-00001 | EQUITY_FUND_A | AAPL | DIVIDEND | RECEIVE | 10,000 | 2,500.00 | USD | PENDING |
| CF-20260315-00002 | GROWTH_FUND_B | AAPL | DIVIDEND | RECEIVE | 5,000 | 1,250.00 | USD | PENDING |
| CF-20260315-00003 | BALANCED_FUND_C | AAPL | DIVIDEND | RECEIVE | 2,500 | 625.00 | USD | PENDING |

### Calculation Formula

```
Cash Flow Amount = Quantity Held × Dividend Per Share

EQUITY_FUND_A:   10,000 × $0.25 = $2,500.00
GROWTH_FUND_B:    5,000 × $0.25 = $1,250.00
BALANCED_FUND_C:  2,500 × $0.25 =   $625.00
                                  -----------
Total Dividend Payout:            $4,375.00
```

---

## Example 2: Interest Payment (Bond)

### Scenario
- **Security**: US10Y_BOND (US Treasury 10-Year)
- **CA Type**: INTEREST
- **Interest Rate**: 2.5% per annum (semi-annual payment = 1.25%)
- **Face Value**: $1,000 per bond
- **Interest Per Bond**: $12.50 (1.25% × $1,000)
- **Ex-Date**: 2026-06-01
- **Payment Date**: 2026-06-15

### Portfolio Holdings

| Portfolio | Security | Quantity (Bonds) |
|-----------|----------|------------------|
| FIXED_INCOME_FUND | US10Y_BOND | 1,000 bonds |
| PENSION_FUND | US10Y_BOND | 500 bonds |

### Corporate Action Record

```
CA Number:        CA-20260601-00001
CA Type:          INTEREST
Security:         US10Y_BOND
Ex Date:          2026-06-01
Record Date:      2026-06-02
Payment Date:     2026-06-15
Price:            12.50
Currency:         USD
Status:           VALIDATED
```

### Generated Cash Flows

| CF Number | Portfolio | Security | Type | Direction | Quantity | Amount | Currency |
|-----------|-----------|----------|------|-----------|----------|--------|----------|
| CF-20260601-00001 | FIXED_INCOME_FUND | US10Y_BOND | INTEREST | RECEIVE | 1,000 | 12,500.00 | USD |
| CF-20260601-00002 | PENSION_FUND | US10Y_BOND | INTEREST | RECEIVE | 500 | 6,250.00 | USD |

---

## Example 3: Multi-Security Corporate Action

### Scenario
A company declares a dividend for multiple share classes.

- **Securities**: GOOG_A, GOOG_C (Alphabet Class A & C)
- **CA Type**: DIVIDEND
- **Dividend Per Share**: $0.50 USD
- **Ex-Date**: 2026-04-10

### Corporate Action Record

```
CA Number:        CA-20260410-00001
CA Type:          DIVIDEND
Security:         GOOG_A,GOOG_C    (comma-separated)
Ex Date:          2026-04-10
Payment Date:     2026-04-20
Price:            0.50
Currency:         USD
Status:           VALIDATED
```

### Portfolio Holdings

| Portfolio | Security | Quantity |
|-----------|----------|----------|
| TECH_FUND | GOOG_A | 500 |
| TECH_FUND | GOOG_C | 300 |
| INDEX_FUND | GOOG_A | 1,000 |

### Generated Cash Flows

| CF Number | Portfolio | Security | Amount |
|-----------|-----------|----------|--------|
| CF-20260410-00001 | TECH_FUND | GOOG_A | $250.00 |
| CF-20260410-00002 | TECH_FUND | GOOG_C | $150.00 |
| CF-20260410-00003 | INDEX_FUND | GOOG_A | $500.00 |

---

## Processing Flow

### Step 1: Create Corporate Action (Maker)
```
User: john.maker creates CA
Status: INITIAL
```

### Step 2: Validate Corporate Action (Checker)
```
User: jane.checker validates CA
Status: VALIDATED
→ System automatically queues CA for cash flow generation
```

### Step 3: EOD Processing
```
EOD Job: python manage.py process_corporate_actions

1. Reads pending CAs from cis_ca_cash_flow_queue
2. For each CA:
   a. Queries cis_trade_position to find ALL portfolios holding the security as of ex_date
   b. For each portfolio with positive holdings:
      - Calculates dividend amount: quantity × price
      - Creates cash flow entry linked to the CA
   c. Logs results to cis_ca_cash_flow_log
3. Marks queue entry as COMPLETED
```

### Step 4: Cash Flow Approval
```
Cash flows created with status: PENDING
→ Require separate approval workflow
```

---

## Database Tables Involved

| Table | Purpose |
|-------|---------|
| `cis_corporate_actions` | CA master data |
| `cis_ca_cash_flow_queue` | Processing queue |
| `cis_ca_cash_flow_log` | Detailed processing log |
| `cis_trade_position` | Portfolio holdings |
| `cis_cash_flow` | Generated cash flows |

---

## CA Types That Generate Cash Flows

| CA Type | Cash Flow Type | Direction |
|---------|---------------|-----------|
| DIVIDEND | DIVIDEND | RECEIVE |
| INTEREST | INTEREST | RECEIVE |
| COUPON | COUPON | RECEIVE |
| CAPITAL_DISTRIBUTION | CAPITAL_DISTRIBUTION | RECEIVE |

### CA Types That Do NOT Generate Cash Flows

| CA Type | Action |
|---------|--------|
| STOCK_SPLIT | Position quantity adjustment |
| BONUS_ISSUE | Position quantity adjustment |
| REVERSE_SPLIT | Position quantity adjustment |
| MERGER | Security replacement |
| NAME_CHANGE | Security update |

---

## CLI Commands

### Process All Pending CAs
```bash
python manage.py process_corporate_actions
```

### Process Specific Date
```bash
python manage.py process_corporate_actions --date 2026-03-18
```

### Dry Run (Preview)
```bash
python manage.py process_corporate_actions --dry-run
```

### Process Specific CA
```bash
python manage.py process_corporate_actions --ca-id 1710758400000
```

---

## Key Business Rules

1. **Security-Level CA**: Corporate Actions are created at the security level, NOT portfolio level
2. **Automatic Portfolio Discovery**: System queries `cis_trade_position` to find ALL portfolios holding the security
3. **Four-Eyes Principle**: CA must be validated by a different user than the creator
4. **Holdings as of Ex-Date**: Only portfolios holding the security on the ex-date receive cash flows
5. **Positive Quantity Only**: Portfolios with zero or negative positions are skipped
6. **Amount Precision**: 8 decimal places (DECIMAL(20,8))
7. **Cash Flow Status**: Created with status INITIAL, requires separate approval
8. **CA Reference**: Each cash flow links back to the source CA via `ca_id` and `ca_number`

## Data Flow

```
┌─────────────────────┐     ┌─────────────────────────┐     ┌──────────────────┐
│  Create CA          │     │  cis_ca_cash_flow_queue │     │  cis_cash_flow   │
│  (Security: AAPL)   │ ──▶ │  (Queued for EOD)       │ ──▶ │  (Cash flows)    │
│  No portfolio!      │     │                         │     │                  │
└─────────────────────┘     └─────────────────────────┘     └──────────────────┘
                                      │
                                      ▼
                            ┌─────────────────────────┐
                            │  cis_trade_position     │
                            │  (Find ALL portfolios   │
                            │   holding AAPL)         │
                            └─────────────────────────┘
```
