# ETL & Data Flows

> **Audience:** Developer, SA, BA, Support
> **Read time:** ~12 minutes

---

## Plain English Summary

Data enters CIS in four ways:

1. **GMP daily feed** — The upstream GMP system pushes market/reference data every morning. CIS reads it directly (no copy, no transformation).
2. **GMP Trade ETL** — GMP trades are extracted from Hive, transformed to CIS schema, and loaded into `cis_trade` with `src_system='GMP'`. Runs daily at 6 AM via Control-M.
3. **User actions via UI** — Traders enter trades, portfolios, securities in real time. Written immediately to Kudu.
4. **File upload** — Users upload CSV/Parquet files via the Upload module, which creates Hive external tables on HDFS.

---

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                │
└────────────┬────────────────────────────────────┬───────────────────┘
             │                                    │
    ┌────────▼──────────┐              ┌──────────▼──────────┐
    │  GMP System       │              │  CIS Users (UI)     │
    │  (Upstream)       │              │                     │
    │  • Trades         │              │  • Portfolios       │
    │  • FX Rates       │              │  • Trades           │
    │  • Equity Prices  │              │  • Securities       │
    │  • Currencies     │              │  • Counterparties   │
    │  • Countries      │              │  • Corporate Actions│
    │  • Calendars      │              │  • File Uploads     │
    └────────┬──────────┘              └──────────┬──────────┘
             │                                    │
    ┌────────▼──────────┐              ┌──────────▼──────────┐
    │  Hive External    │              │  Kudu Tables         │
    │  Tables (HDFS)    │              │  (gmp_cis.*)         │
    │  (read-only)      │   GMP ETL    │                     │
    │  gmp_cis_sta_*    │─────────────▶│  cis_trade          │
    │                   │  (6 AM daily)│  (src_system='GMP') │
    └────────┬──────────┘              └──────────┬──────────┘
             │                                    │
             └──────────────┬─────────────────────┘
                            │ Impala SQL queries
                   ┌────────▼────────┐
                   │  CIS Django App │
                   │  (Services /    │
                   │   Repositories) │
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │  Browser / User │
                   └─────────────────┘
```

---

## Flow 1: GMP Reference Data (Daily Feed)

**What:** Currencies, countries, calendars, FX rates, equity prices
**When:** Daily, starting from ~2 AM SGT
**How:** GMP exports files to HDFS; Hive external tables point to those files; CIS reads via Impala

```
02:00 AM  GMP exports CSV files to HDFS
          /data/gmp_export/currency/
          /data/gmp_export/fx_rates/
          /data/gmp_export/equity_prices/
          /data/gmp_export/country/
          /data/gmp_export/calendar/

          (Files are pipe-delimited, partitioned by date)

No action needed from CIS — Hive external tables
automatically reflect new files when queried.

When user opens a form in CIS that needs a currency list:
  Django → ImpalaConnectionManager
         → SELECT * FROM gmp_cis.gmp_cis_sta_dly_currency
         → Results served as dropdown options
```

**What if GMP is late?** The external tables still return yesterday's data (or nothing if the partition doesn't exist). The application handles this gracefully — dropdowns still load with the last available data.

---

## Flow 2: GMP Trade ETL (Daily Batch)

**What:** GMP's settled trades loaded into CIS's `cis_trade` table as view-only records
**When:** Daily 6:00 AM SGT via Control-M job `CIS_ETL_GMP_TRADE`
**How:** PySpark job reads Hive partition, transforms to CIS schema, UPSERTs to Kudu

```
05:30 AM  GMP_FILE_WATCHER detects trade file arrived on HDFS
          Sets condition: GMP_TRADE_FILE_ARRIVED

06:00 AM  Control-M job CIS_ETL_GMP_TRADE starts

STEP 1 — VALIDATE
  • Check Hive partition exists for today's business_date
  • Validate record count > 0
  • Check required columns present

STEP 2 — EXTRACT
  SELECT * FROM gmp_cis_staging.gmp_trade_daily
  WHERE business_date = '2026-04-22'
  → ~1,500 records (example)

STEP 3 — TRANSFORM
  • Rename GMP columns to CIS column names:
      trade_ref     → deal_number
      portfolio_code → portfolio_short_name
      security_code  → security_label
      amount         → total_amount
      ... etc
  • Cast STRING columns to correct types (decimal, date)
  • Map GMP status to CIS status:
      GMP 'NEW'       → CIS 'SETTLED'
      GMP 'CONFIRMED' → CIS 'SETTLED'
      GMP 'CANCELLED' → CIS 'CANCELLED'
  • Set CIS-only defaults:
      src_system = 'GMP'
      created_by = 'ETL_GMP'
      is_active  = true

STEP 4 — LOAD
  • DELETE existing GMP records for this business_date (idempotency)
  • UPSERT transformed records into gmp_cis.cis_trade

STEP 5 — RECONCILE
  • Compare source count vs target count
  • Fail if variance > 0.01%
  • Alert on-call team if job fails

06:15 AM  Job completes — GMP trades visible in CIS Trade List
```

**GMP trades in UI:**
- Appear in Trade List alongside CIS trades
- Badge shows `GMP` source
- No Edit button — view only
- CIS trades sort first (by `src_system` ordering)

---

## Flow 3: CIS User Actions (Real-Time)

**What:** All user-initiated operations — creating/editing portfolios, trades, securities, etc.
**When:** Real-time, as users act
**How:** Django view → service → repository → Impala UPSERT → Kudu

### Create Trade (Example)
```
User submits form
  │
  ▼ permission_middleware: check 'trade-create' permission
  │
  ▼ trade/views.py create_trade()
  │   • Validate form fields
  │
  ▼ TradeService.create_trade(user, data)
  │   • Check portfolio exists and is ACTIVE
  │   • Check security exists and is APPROVED/ACTIVE
  │   • Check counterparty is active
  │   • Generate trade_id
  │
  ▼ TradeKuduRepository.insert_trade(data)
  │   UPSERT INTO gmp_cis.cis_trade (...) VALUES (...)
  │   Status = 'INITIAL', src_system = 'CIS'
  │
  ▼ audit_kudu_repository.log_action('CREATE', ...)
  │   (async — does not block the user)
  │
  ▼ HTTP 302 → trade detail page
```

### Trade Status Transitions
```
INITIAL
  │ Maker modifies
  ▼
MODIFIED
  │ Maker submits for validation
  ▼
PENDING_VALIDATION
  │                    │
  │ Checker approves   │ Checker rejects
  ▼                    ▼
VALIDATED           CANCELLED
  │
  │ Settlement processing (EOD or real-time T+0)
  ▼
SETTLED
```

---

## Flow 4: File Upload & Ingestion

**What:** Users upload CSV, Parquet, Excel, JSON, TSV files to bulk-import data
**When:** On demand by authorised users
**How:** Upload → validate → schema detect → HDFS → Hive external table

```
User selects file and uploads
  │
  ▼ FileValidationService
  │   • Check format (CSV, Parquet, Excel, JSON, TSV, Text)
  │   • Check size
  │   • Check encoding
  │
  ▼ Schema detection (first 100 rows)
  │   • Auto-detect delimiter
  │   • Detect header row
  │   • Detect column types
  │
  ▼ Preview shown to user (confirm or adjust)
  │
  ▼ File copied to HDFS
  │   /user/cis/uploads/<upload_id>/
  │
  ▼ Hive external table created
  │   CREATE EXTERNAL TABLE gmp_cis.upload_<id>
  │   LOCATION '/user/cis/uploads/<upload_id>/'
  │
  ▼ Metadata stored in cis_file_upload (Kudu)
  │   upload_id, file_name, row_count, column_count, status
  │
  ▼ Data available via Impala for downstream processing
```

---

## EOD (End-of-Day) Jobs

These run after market close. They are Django management commands or shell scripts triggered by a scheduler (Control-M or cron).

| Job | Command | What it does |
|-----|---------|--------------|
| **Settlement processing** | `python manage.py process_settlements` | Settles VALIDATED trades whose settle date has arrived |
| **Position refresh** | `python manage.py refresh_positions` | Recalculates AVP positions for a date range |
| **Trade event worker** | `python manage.py run_trade_event_worker` | Processes `cis_trade_event_queue` (async events) |
| **Corporate actions** | `python manage.py process_corporate_actions` | Processes `cis_ca_cash_flow_queue` → `cis_cash_flow` |
| **GMP Trade ETL** | `spark-submit gmp_trade_etl.py` | Loads today's GMP trades (Control-M) |
| **Position worker daemon** | `scripts/position_worker_daemon.sh` | Long-running process, constantly drains `cis_position_queue` |

### EOD Sequence
```
Market close
  │
  ▼ process_settlements       → VALIDATED trades → SETTLED
  │                            Position events queued
  │
  ▼ position_worker_daemon     → Drains cis_position_queue
  │                            AVP recalculated per portfolio/security
  │
  ▼ process_corporate_actions  → CA cash flows generated
  │
  ▼ GMP Trade ETL (6 AM next day)
  │
  ▼ GMP reference data refresh (2 AM)
```

---

## Position Calculation Flow (AVP)

This is triggered by trade settlement and runs asynchronously.

```
Trade settled (status → SETTLED)
  │
  ▼ TradeEventQueueService.enqueue_position_event(trade)
  │   INSERT INTO gmp_cis.cis_position_queue
  │   event_type='SETTLEMENT', trade_id=..., status='PENDING'
  │
  ▼ position_worker_daemon (background process, polls every 10s)
  │   SELECT * FROM cis_position_queue WHERE status='PENDING' LIMIT 100
  │
  ▼ PositionService.calculate_position(trade)
  │
  │   If BUY:
  │     new_avg_cost = (old_total_cost + trade_cost + charges) / new_qty
  │     new_qty = old_qty + trade_qty
  │
  │   If SELL:
  │     avg_cost = unchanged
  │     realized_pnl = (sell_price - avg_cost) × qty
  │     new_qty = old_qty - trade_qty
  │
  │   Precision: 8 decimal places (DECIMAL(20,8))
  │
  ▼ INSERT INTO gmp_cis.cis_trade_position (versioned record)
  │
  ▼ Mark cis_position_queue entry as PROCESSED
  │
  SLA: < 5 minutes from queue to completion
```

---

## Cash Flow Generation (Corporate Actions)

```
Corporate action created (e.g. dividend)
  │
  ▼ INSERT INTO gmp_cis.cis_ca_cash_flow_queue
  │   ca_id, security_id, payment_date, status='PENDING'
  │
  ▼ process_corporate_actions (EOD job)
  │
  ▼ For each portfolio holding the security:
  │   Calculate cash impact (dividend amount × holding qty)
  │   INSERT INTO gmp_cis.cis_cash_flow
  │     type='DIVIDEND', portfolio_id, security_id, amount, date
  │
  ▼ Mark queue entry as PROCESSED
```

---

## Data Retention

| Data | Retention | Notes |
|------|-----------|-------|
| Trades | 7 years | Regulatory requirement |
| Audit log | 7 years | All changes, all users |
| Positions | Forever | Needed for P&L history |
| Cash flows | 7 years | Regulatory |
| Market data | 10 years | Historical rates/prices |
| GMP trade ETL logs | 90 days | Operational logs |

---

## Common Troubleshooting

| Symptom | Likely Cause | Action |
|---------|-------------|--------|
| FX rate dropdown empty | GMP feed late or HDFS unavailable | Check `gmp_cis_sta_dly_fx_rates` last partition date |
| GMP trades not appearing | ETL job failed or partition missing | Check Control-M job log |
| Position not updated after trade | Position queue backed up or worker stopped | Check `cis_position_queue` for stuck PENDING entries |
| CA cash flow not generated | EOD job failed or CA status wrong | Check `cis_ca_cash_flow_queue` for FAILED entries |
| File upload stuck | HDFS write permission issue | Check upload log and HDFS quota |
