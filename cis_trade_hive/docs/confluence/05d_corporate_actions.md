# Corporate Actions & Cash Flow

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~10 minutes

---

## What Are Corporate Actions?

A **corporate action** is an event initiated by a company that affects its securities and therefore the holdings of investors. Common examples:

| Type | What happens |
|------|-------------|
| **Dividend** | Company pays cash to shareholders — increases portfolio cash balance |
| **Stock Split** | E.g. 2-for-1 split — quantity doubles, price halves, avg cost halves |
| **Rights Issue** | Company offers existing shareholders new shares at a discount |
| **Warrant** | Option to buy new shares at a set price |
| **Capital Distribution** | Return of capital to shareholders (reduces cost basis) |
| **Income Distribution** | Fund income distributed to holders |

CIS tracks these events and generates the corresponding cash flow and position adjustments automatically once the corporate action is processed.

---

## Cash Flow

A **cash flow** is any movement of money linked to the portfolio. CIS tracks:

| Cash Flow Type | Trigger |
|---------------|---------|
| `DIVIDEND` | Dividend corporate action |
| `COUPON` | Bond coupon payment |
| `CORPORATE_ACTION` | Other CA types |
| `SETTLEMENT` | Trade settlement (cash in/out) |
| `INCOME` | Income trade type |

Every cash flow record knows: which portfolio, which security, how much, in which currency, on which date.

---

## How Corporate Actions Flow Through CIS

```
1. Corporate action entered in CIS (manually or via GMP sync)
   INSERT INTO gmp_cis.cis_corporate_actions
   Status: PENDING

2. Cash flow entries queued for processing
   INSERT INTO gmp_cis.cis_ca_cash_flow_queue
   ca_id, security_id, payment_date, status='PENDING'

3. EOD job runs: python manage.py process_corporate_actions
   For each portfolio holding the affected security:
     • Calculate cash impact (e.g. dividend_per_share × holding_qty)
     • INSERT INTO gmp_cis.cis_cash_flow
         type='DIVIDEND', portfolio_id, security_id,
         amount, date, currency
   Mark queue entry as PROCESSED

4. For position-impacting CAs (splits, rights):
   Position service recalculates AVP
   (e.g. split 2:1 → quantity × 2, avg_cost / 2)

5. History recorded in cis_corporate_actions_history
   and cis_cash_flow_history
```

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `cis_corporate_actions` | Corporate action master records |
| `cis_corporate_actions_history` | CA change history |
| `cis_ca_cash_flow_queue` | Queue of CA cash flows awaiting EOD processing |
| `cis_ca_cash_flow_log` | Log of processed CA cash flows |
| `cis_cash_flow` | All cash flow transactions |
| `cis_cash_flow_history` | Cash flow change history |

### cis_ca_cash_flow_queue Queue Statuses

| Status | Meaning |
|--------|---------|
| `PENDING` | Waiting to be processed by EOD job |
| `PROCESSING` | Currently being processed |
| `PROCESSED` | Successfully completed |
| `FAILED` | Errored — needs investigation |

---

## For Users: Entering a Corporate Action

1. Go to **Reference Data → Corporate Actions**
2. Click **New Corporate Action**
3. Select the **Security** affected
4. Select the **CA Type** (Dividend, Split, Rights, etc.)
5. Enter the relevant details (ex-date, payment date, rate, ratio)
6. Save — the system queues the cash flow entries
7. After the EOD job runs on the payment date, cash flows appear in affected portfolios

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `reference_data/services/corporate_action_service.py` | CA business logic |
| `reference_data/services/ca_cash_flow_service.py` | Cash flow generation from CA |
| `reference_data/repositories/corporate_action_repository.py` | SQL on cis_corporate_actions |
| `reference_data/repositories/ca_cash_flow_queue_repository.py` | Queue management |
| `trade/repositories/cash_flow_repository.py` | SQL on cis_cash_flow |
| `trade/views_cash_flow.py` | Cash flow UI views |
| `trade/management/commands/process_corporate_actions.py` | EOD processing command |
| `sql/ddl/14_corporate_actions_kudu.sql` | CA table DDL |
| `sql/ddl/16_ca_cash_flow_queue.sql` | Queue table DDL |
| `sql/ddl/15_cash_flow_kudu.sql` | Cash flow table DDL |

### Running Corporate Actions Manually
```bash
# Process all pending CA cash flows
python manage.py process_corporate_actions

# Dry run (see what would be processed without writing)
python manage.py process_corporate_actions --dry-run

# Process specific corporate action ID
python manage.py process_corporate_actions --ca-id 12345

# Retry failed entries
python manage.py process_corporate_actions --retry-failed
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| CA cash flow not generated | Check `cis_ca_cash_flow_queue` for PENDING/FAILED entries for this CA |
| Wrong cash flow amount | Check dividend rate and holding quantity at ex-date |
| Position not adjusted after split | Check if the CA type triggered position recalculation — look in `cis_position_queue` |
| Duplicate cash flows | EOD job may have run twice — check `cis_cash_flow` for duplicate entries on same date/ca |

### Diagnostic queries
```sql
-- Check CA queue status
SELECT ca_id, status, COUNT(*) FROM gmp_cis.cis_ca_cash_flow_queue
GROUP BY ca_id, status ORDER BY 1;

-- View cash flows for a portfolio
SELECT type, security_label, amount, currency, flow_date
FROM gmp_cis.cis_cash_flow
WHERE portfolio_short_name = 'UOB-SG'
ORDER BY flow_date DESC
LIMIT 50;
```
