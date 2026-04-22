# Portfolio Management

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~10 minutes

---

## What Is a Portfolio?

A portfolio in CIS represents an investment account or fund. Every trade, position, and cash flow belongs to a portfolio.

Think of a portfolio as a container: it has an owner, a base currency, and various classification codes (cost centre, account group, etc.). All the securities bought and sold within that portfolio are tracked together.

---

## Portfolio Lifecycle

```
  1. Maker creates portfolio with all details
     Status: DRAFT

  2. Maker reviews and submits for approval
     Status: PENDING_APPROVAL

  3a. Checker approves
      Status: APPROVED

  3b. Checker rejects (with comment)
      Status: REJECTED → Maker can edit and resubmit

  4. Portfolio becomes operational
     Status: ACTIVE
     → Trades can now be entered against this portfolio

  5. Portfolio closed or deactivated
     Status: INACTIVE / CLOSED
     → No new trades allowed
```

**Key rule:** The person who creates a portfolio cannot be the person who approves it.

---

## Portfolio Fields Explained

### Identity

| Field | Description |
|-------|-------------|
| `name` | Short code — unique identifier, used everywhere (e.g. `UOB-SG-EQ-001`) |
| `description` | Full descriptive name |
| `portfolio_type` | Type classification |
| `status` | Lifecycle status (see above) |

### Financial

| Field | Description |
|-------|-------------|
| `currency` | Base/reporting currency for the portfolio |
| `cash_balance` | Current cash balance |
| `revaluation_status` | Whether portfolio is being revalued |

### Classification (for reporting and GL)

| Field | Description |
|-------|-------------|
| `cost_centre_code` | GL cost centre |
| `corp_code` | Corporate entity code |
| `account_group` | Account grouping |
| `portfolio_group` | Portfolio grouping |
| `report_group` | Reporting group |
| `entity_group` | Legal entity group |

### Workflow

| Field | Description |
|-------|-------------|
| `submitted_by` | Who submitted for approval |
| `submitted_at` | When submitted |
| `submitted_for_approval_at` | Timestamp of submission |
| `reviewed_by` | Who reviewed (approved/rejected) |
| `reviewed_at` | When reviewed |
| `review_comments` | Checker's comments |
| `manager` | Portfolio manager name |

---

## Portfolio History

Every change to a portfolio is recorded in `cis_portfolio_history`. You can see the full audit trail from the portfolio detail page:
- What changed
- Who changed it
- When it changed
- Status at time of change

---

## How Portfolios Relate to Other Modules

```
Portfolio
    │
    ├── Trades belong to a portfolio
    │   (portfolio_short_name FK)
    │
    ├── Positions are per portfolio × security
    │   (cis_trade_position)
    │
    ├── Cash flows are per portfolio
    │   (cis_cash_flow)
    │
    └── UDF values can be attached to portfolios
        (entity_type = 'PORTFOLIO')
```

---

## For Users: Step-by-Step

### Creating a Portfolio

1. Click **Portfolio → Create Portfolio**
2. Fill in the **Name** (short code — must be unique)
3. Fill in **Description**, **Currency**, classification codes
4. Click **Save** → status is DRAFT
5. Review all details
6. Click **Submit for Approval** → status is PENDING_APPROVAL
7. A checker will be notified to review

### Approving a Portfolio (Checker)

1. Click **Portfolio → Pending Approval**
2. Select the portfolio to review
3. Review all details
4. Click **Approve** → portfolio becomes APPROVED/ACTIVE, ready for trading
   OR
5. Click **Reject** with a comment → portfolio goes back to REJECTED, maker can edit and resubmit

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `portfolio/repositories/portfolio_hive_repository.py` | All SQL on `cis_portfolio` |
| `portfolio/services/portfolio_service.py` | Business logic, status transitions |
| `portfolio/views.py` | HTTP handlers |
| `portfolio/models.py` | Portfolio Python model (wraps dict from Kudu) |
| `sql/ddl/02_portfolio_tables.sql` | Core portfolio DDL |
| `sql/ddl/01_create_portfolio_history_kudu.sql` | History table DDL |
| `sql/ddl/03_portfolio_maker_checker_workflow.sql` | Workflow status values |

### Status Check Pattern (in queries)
```python
# Only active portfolios available for trade entry
query = """
    SELECT name, description, currency, status
    FROM gmp_cis.cis_portfolio
    WHERE is_active = true
      AND status IN ('ACTIVE', 'VALIDATED', 'SETTLED')
    ORDER BY name
"""
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Portfolio not appearing in trade dropdown | Check status — must be ACTIVE. Check `is_active = true` |
| Cannot approve own portfolio | By design — Four-Eyes rule. A different user must approve |
| Portfolio stuck in PENDING_APPROVAL | Has a checker reviewed it? Do they have `portfolio-approve` permission? |
| Classification code fields missing | These are optional but needed for GL reporting — check with the business |
