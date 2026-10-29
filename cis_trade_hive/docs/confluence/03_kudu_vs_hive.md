# Data: Kudu Tables vs Hive External Tables

> **Audience:** Developer, SA, BA, Support, New Joiner
> **Read time:** ~8 minutes

---

## Plain English First

The CIS database (`gmp_cis`) contains two kinds of tables. From the application's perspective they look the same — you query both with SQL — but they are fundamentally different in terms of who owns the data, whether it can be edited, and where it physically lives.

**Think of it this way:**

- **Kudu tables** = CIS's own filing cabinet. We create records, update them, delete them. Full control.
- **Hive external tables** = A shared whiteboard owned by GMP (the upstream system). We can read what's on it, but we don't write to it. GMP updates it every morning.

Both are queried through **Impala** (the SQL engine on our Cloudera cluster), so they feel identical when writing a `SELECT` query. The difference only matters when you try to write.

---

## Side-by-Side Comparison

| | Kudu Tables | Hive External Tables |
|--|-------------|---------------------|
| **Owner** | CIS application | GMP (upstream system) |
| **Can CIS write?** | Yes — full INSERT / UPSERT / DELETE | No — read-only |
| **Data location** | Apache Kudu tablet servers | HDFS files (Parquet/ORC) |
| **Updated by** | Real-time via UI actions | Daily ETL (6 AM) |
| **Schema defined in** | `sql/ddl/` Kudu DDL files | GMP-side DDL (we reference it) |
| **Examples** | `cis_trade`, `cis_portfolio` | `gmp_cis_sta_dly_fx_rates` |
| **Backup method** | Spark Kudu connector | Spark spark.sql() |
| **What happens if data is wrong?** | CIS can correct it | Must wait for GMP to fix and re-feed |

---

## Which Tables Are Which?

### CIS-Owned Kudu Tables

These are fully managed by CIS. All trade, portfolio, position, and user data lives here.

| Table | What it holds |
|-------|--------------|
| `cis_trade` | All trades (both CIS-created and GMP-fed via ETL, using `src_system` flag) |
| `cis_trade_history` | Every change to every trade |
| `cis_portfolio` | Portfolios |
| `cis_portfolio_history` | Portfolio change history |
| `cis_security` | Security master (ISIN, currency, type) |
| `cis_security_history` | Security change history |
| `cis_counterparty_kudu` | Counterparty/broker records |
| `cis_trade_position` | Position history (versioned, by trade date) |
| `cis_position_queue` | Queue for async position calculations |
| `cis_settlement_queue` | Trades awaiting future settlement |
| `cis_trade_event_queue` | General async event queue |
| `cis_corporate_actions` | Corporate action records |
| `cis_corporate_actions_history` | CA change history |
| `cis_cash_flow` | Cash flow transactions |
| `cis_cash_flow_history` | Cash flow change history |
| `cis_ca_cash_flow_queue` | CA cash flows waiting for EOD processing |
| `cis_udf_definition` | Custom field definitions |
| `cis_udf_option` | Dropdown options for custom fields |
| `cis_udf_field` | Field metadata |
| `cis_udf_value` | Single-value custom field values |
| `cis_udf_value_multi` | Multi-select custom field values |
| `cis_file_upload` | Upload job metadata |
| `cis_audit_log` | System-wide audit trail |
| `cis_sequence` | ID sequence counter |
| `cis_system_date` | CIS business date |
| `cis_user` | User accounts (RBAC v1) |
| `cis_user_group` | User-group mapping (RBAC v1) |
| `cis_group` | Group definitions (RBAC v1) |
| `cis_group_permissions` | Group-permission mapping (RBAC v1) |
| `cis_user_info` | User accounts (RBAC v2) |
| `cis_user_group_info` | Group definitions (RBAC v2) |
| `cis_permission_info` | Permission definitions (RBAC v2) |
| `cis_user_group_mapping_info` | User-group mapping (RBAC v2) |
| `cis_group_permission_map` | Group-permission mapping (RBAC v2) |
| `cis_equity_price_kudu` | Equity prices stored in Kudu (CIS-managed copy) |
| `cis_equity_price_history` | Price change history |

### GMP-Fed Hive External Tables (Read-Only)

These are created and updated by GMP. CIS only reads them.

| Table | What it holds | Update frequency |
|-------|--------------|-----------------|
| `gmp_cis_sta_dly_fx_rates` | Daily FX rates for all currency pairs | Daily 6 AM |
| `gmp_cis_sta_dly_currency` | Currency reference data | Daily |
| `gmp_cis_sta_dly_country` | Country reference data | Daily |
| `gmp_cis_sta_dly_calendar` | Trading calendar / holidays | Daily |
| `gmp_cis_sta_dly_equity_price` | Daily equity prices | Daily |

---

## How They Look the Same in Code

From the repository layer, you query both identically:

```python
# Querying a CIS Kudu table
query = "SELECT * FROM gmp_cis.cis_trade WHERE portfolio_short_name = 'UOB-SG'"

# Querying a GMP Hive external table
query = "SELECT * FROM gmp_cis.gmp_cis_sta_dly_fx_rates WHERE processing_date = '2026-04-22'"

# Both go through exactly the same connection manager:
results = impala_manager.execute_query(query)
```

The same `ImpalaConnectionManager` handles both. Impala presents them in the same `gmp_cis` database namespace.

---

## How They Differ in the UI

In the **Trade List**, both CIS-created trades and GMP-sourced trades appear. The `src_system` column tells them apart:

```
Deal#    Portfolio  Security  Qty   src_system  Actions
──────────────────────────────────────────────────────────
CIS-001  UOB-SG     AAPL      100   CIS         Edit | View
GMP-001  UOB-SG     AAPL      100   GMP         View only
CIS-002  UOB-HK     MSFT      50    CIS         Edit | View
```

- `src_system = 'CIS'` → Full Edit/View buttons shown
- `src_system = 'GMP'` → View Only (Edit button hidden in template)

The template check:
```html
{% if trade.src_system == 'CIS' %}
    <a href="{% url 'trade:edit' trade.trade_id %}">Edit</a>
{% endif %}
```

---

## How FX Rates Merge With Trades in the UI

When displaying a trade's value in local currency (LC), the system JOINs the Kudu trade table with the Hive external FX rate table — both in a single Impala SQL query:

```sql
SELECT
    t.trade_id,
    t.total_amount_fc,                              -- Trade amount in foreign currency
    fx.spot_rate_d,                                  -- Today's FX rate (from Hive external)
    t.total_amount_fc * fx.spot_rate_d AS total_lc   -- Calculated LC amount
FROM gmp_cis.cis_trade t                            -- Kudu table
LEFT JOIN gmp_cis.gmp_cis_sta_dly_fx_rates fx       -- Hive external table
    ON t.security_currency = fx.underlying_cur
    AND t.portfolio_currency = fx.base_cur
    AND fx.processing_date = (
        SELECT MAX(processing_date) FROM gmp_cis.gmp_cis_sta_dly_fx_rates
    )
WHERE t.trade_id = ?
```

Impala handles the JOIN seamlessly — it reads Kudu data from tablet servers and HDFS data from Parquet files in the same query plan.

---

## How Reference Data Works (Currency, Country, Calendar)

GMP pushes fresh reference data files to HDFS every morning. The Hive external tables point to those files. CIS reads them directly:

```
GMP Database
    │ SQL Extract → pipe-delimited CSV (daily 2 AM)
    │
HDFS: /data/gmp_export/currency/
    │ Hive external table points here
    │
Impala query: SELECT * FROM gmp_cis.gmp_cis_sta_dly_currency
    │
Django reference_data app → currency dropdown in forms
```

CIS never copies these into its own Kudu tables. They are always served fresh from the Hive external pointer.

**Exception:** Equity prices and counterparties — CIS has its own Kudu copies (`cis_equity_price_kudu`, `cis_counterparty_kudu`) that are maintained separately with full lifecycle management.

---

## Backup Implications

Because the two table types read differently, the backup scripts treat them differently:

| Table Type | How Backed Up | Script |
|------------|--------------|--------|
| Kudu | `spark.read.format("org.apache.kudu.spark.kudu")` | `backup_uat_to_local.py` |
| Hive external | `spark.sql("SELECT * FROM gmp_cis.table")` | Same script — auto-detected |
| Hive internal | `spark.sql("SELECT * FROM gmp_cis.table")` | Same script — auto-detected |

The backup scripts auto-discover all tables using `SHOW TABLES IN gmp_cis` + `DESCRIBE FORMATTED`, then pick the right read method per table type.

---

## For Developers: How to Know Which Type a Table Is

Run this in impala-shell:

```sql
DESCRIBE FORMATTED gmp_cis.cis_trade;
```

Look for:
- **Storage Handler:** `com.cloudera.kudu.hive.KuduStorageHandler` → **Kudu**
- **Table Type:** `EXTERNAL_TABLE` → **Hive External**
- **Table Type:** `MANAGED_TABLE` (no Kudu handler) → **Hive Internal (managed)**

Or in Python (`detect_table_type()` in the backup scripts):
```python
if "kudu" in storage_handler:       → TYPE_KUDU
elif "external" in table_type_raw:  → TYPE_EXTERNAL
else:                                → TYPE_HIVE
```
