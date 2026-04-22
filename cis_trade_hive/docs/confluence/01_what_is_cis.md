# What Is CIS Trade Hive?

> **Audience:** Everyone — User, BA, SA, Developer, Support, New Joiner
> **Read time:** ~5 minutes

---

## In Plain English

**CIS Trade Hive** (CIS = Capital & Investment Services) is the system our team uses to manage investment trades end-to-end — from the moment a trader enters a deal, through compliance approval, all the way to settlement and reporting.

Think of it like this:

- A **trader** logs in, enters a trade (e.g. "Buy 1,000 shares of AAPL at $175")
- A **checker** reviews and approves it (nobody can approve their own trade — this is the Four-Eyes rule)
- The system automatically calculates the portfolio's **position** (how many shares we hold, at what average cost)
- **Market data** (FX rates, equity prices) flows in daily from an upstream system called GMP
- Every action — every click, every change — is written to an **audit log** that cannot be altered

It is a web application: you open it in a browser, no installation needed.

---

## Who Uses It?

| Role | What they do in CIS |
|------|---------------------|
| **Trader / Maker** | Enter trades, create portfolios, upload files |
| **Checker / Approver** | Review and approve/reject trades and portfolios |
| **Risk / Read-only** | View positions, reports, audit trail |
| **System Admin** | Manage users, roles, permissions |
| **Support / Ops** | Monitor, troubleshoot, run EOD jobs |
| **BA / SA** | Understand business rules, write requirements |

---

## What Can It Do?

| Module | What it manages |
|--------|----------------|
| **Portfolio** | Investment portfolios — create, approve, track |
| **Trade** | Buy/sell trades — enter, validate, settle |
| **Position (AVP)** | Automatic average cost position per portfolio/security |
| **Market Data** | Daily FX rates and equity prices from GMP |
| **Securities** | Security master data (ISIN, currency, type) |
| **Counterparties** | Brokers and counterparties used in trades |
| **Corporate Actions** | Dividends, splits, rights issues affecting positions |
| **Cash Flow** | Cash movements linked to trades and corporate actions |
| **UDF** | User-defined custom fields on trades and portfolios |
| **File Upload** | Upload CSV/Parquet files to ingest bulk data |
| **Audit Log** | Complete change history — who did what, when |
| **RBAC** | Role-based access — who can see/do what |

---

## The Big Picture (Non-Technical)

```
                        ┌─────────────────────┐
                        │   GMP (Upstream)     │
                        │  FX Rates, Prices,   │
                        │  Reference Data      │
                        └─────────┬───────────┘
                                  │ Daily feed (6 AM)
                                  ▼
┌──────────┐   enters   ┌─────────────────────┐   stores   ┌───────────────┐
│  Trader  │──────────▶│   CIS Trade Hive     │──────────▶│  Kudu / Hive  │
└──────────┘            │   (Django Web App)  │            │  (Database)   │
┌──────────┐   approves │                     │            └───────────────┘
│ Checker  │──────────▶│  • Portfolio Mgmt   │
└──────────┘            │  • Trade Lifecycle  │
┌──────────┐   views    │  • Positions / AVP  │
│   Risk   │──────────▶│  • Market Data      │
└──────────┘            │  • Corporate Actions│
                        │  • Audit Trail      │
                        └─────────────────────┘
```

---

## Technology at a Glance

| What | Technology | Why |
|------|-----------|-----|
| Web framework | Django 5.2 (Python) | Rapid development, clean architecture |
| Database | Apache Kudu (via Impala SQL) | Fast reads and writes on large datasets |
| Reference data store | Hive external tables (HDFS) | Read-only GMP feeds, no copy needed |
| Batch processing | Apache Spark | Large-scale data migration and backup |
| Frontend | Bootstrap 5 + jQuery | Browser-based, no install required |
| Server (production) | Cloudera CML (Hadoop cluster) | Enterprise platform |

---

## Environments

| Environment | Purpose | Who uses it |
|-------------|---------|-------------|
| **LOCAL** | Developer laptops with Docker | Developers only |
| **SIT** | System Integration Testing | Dev + QA |
| **UAT** | User Acceptance Testing | Business + QA |
| **PROD** | Live production | Everyone |

---

## Key Concepts to Know

**Four-Eyes (Maker-Checker):** No one can approve their own work. Every trade and portfolio goes through a second person's review before it becomes active.

**Kudu table:** CIS's own database tables — fully editable, full lifecycle. Think of these as "our data."

**Hive external table:** Read-only reference data fed by GMP (the upstream system). CIS reads it but never writes to it. Think of these as "their data, on loan."

**GMP (Global Market Platform):** The upstream source-of-truth system for market data and some reference data. CIS consumes GMP data daily.

**AVP (Average Price Position):** When you buy shares at different times/prices, the system calculates your running average cost automatically. This is the AVP.

**src_system:** A flag on each trade record. `src_system = 'CIS'` means CIS created it (fully editable). `src_system = 'GMP'` means it came from GMP via ETL (view-only).

**RBAC:** Role-Based Access Control. What you can see and do depends on what role(s) you have been assigned.

---

## Where to Go Next

| I want to... | Go to |
|-------------|-------|
| Understand the system architecture | [02 — System Architecture](02_architecture.md) |
| Understand how the database works | [03 — Kudu vs Hive External](03_kudu_vs_hive.md) |
| Understand how data gets in | [04 — ETL & Data Flows](04_etl_and_data_flows.md) |
| Learn about a specific module | [05a–05i Module Guides](00_INDEX.md) |
| Understand the approval workflow | [06 — Four-Eyes Workflow](06_four_eyes.md) |
| Set up a dev environment | [08 — Environments & Configuration](08_environments.md) |
| Look up a term | [10 — Glossary](10_glossary.md) |
