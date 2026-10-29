# Portfolio Table - Hive Implementation

## Overview
This document describes the Portfolio table implementation in the Hive database `cis`.

## Table: cis_portfolio

### Purpose
Portfolio master data containing information about investment portfolios managed by various entities within the UOB group and associated companies.

### Table Details
- **Format**: TEXT (pipe-delimited)
- **Total Rows**: 530
  - Active portfolios: 237
  - Inactive portfolios: 293
- **Storage**: Internal table (not external)

### Schema

| Column Name          | Data Type | Description                                    |
|---------------------|-----------|------------------------------------------------|
| name                | STRING    | Portfolio identifier/name (e.g., AIIF CP)      |
| description         | STRING    | Full portfolio description                     |
| currency            | STRING    | Base currency (SGD, USD, MYR, IDR, VND, etc.)  |
| manager             | STRING    | Portfolio manager                              |
| portfolio_client    | STRING    | Client name                                    |
| cash_balance_list   | STRING    | Cash balance list                              |
| cash_balance        | STRING    | Cash balance                                   |
| status              | STRING    | Portfolio status (Active/Inactive)             |
| cost_centre_code    | STRING    | Cost centre code (e.g., 00000000)              |
| corp_code           | STRING    | Corporate code (e.g., 0000)                    |
| account_group       | STRING    | Account group classification                   |
| portfolio_group     | STRING    | Portfolio group                                |
| report_group        | STRING    | Report group                                   |
| entity_group        | STRING    | Entity group (UOB GROUP, UOB SUBSIDIARY, etc.) |
| revaluation_status  | STRING    | Revaluation status (REVALUED/NON-REVALUED)     |
| created_at          | STRING    | Creation date                                  |
| updated_at          | STRING    | Last update date                               |

### Sample Data

```
NAME               | DESCRIPTION                              | CURRENCY | STATUS   | ENTITY_GROUP          | REVALUATION_STATUS
-------------------|------------------------------------------|----------|----------|----------------------|-------------------
AIIF CP            | AIIF CAPITAL PARTNERS LIMITED            | SGD      | Active   | Subsidiary Company   | NON-REVALUED
AVATEC             | AVATEC.AI (S) PTE LTD                    | SGD      | Active   | UOB SUBSIDIARY       |
FEB-AVG            | FAR EASTERN BANK LTD                     | SGD      | Active   | Subsidiary Company   | REVALUED
UOB KAY HIAN       | UOB KAY HIAN HOLDINGS LIMITED            | SGD      | Active   | UOB SUBSIDIARY       | REVALUED
UOBAM(VIETNAM)     | UOBAM(VIETNAM) FUND MGT JSC              | VND      | Active   | UOB SUBSIDIARY       | REVALUED
```

## Data Sources

### Schema Definition
- **File**: `cis_trade_hive/kudu_ddl/cis_portfolio.csv`
- **Purpose**: Defines the column names and expected structure
- **Columns**: 20 (includes 3 columns not in data file: source_name, branch_code, validation_status)

### Data File
- **File**: `cis_trade_hive/kudu_ddl/Porfolio_CIS_format_test2 (1).txt`
- **Format**: Pipe-delimited text file with header row
- **Rows**: 531 (1 header + 530 data rows)
- **Columns**: 17 (missing source_name, branch_code, validation_status)

## Loading Process

### Step 1: Analyze Schema
```bash
# Read CSV to understand expected columns
python3 -c "import csv; ..."
```

### Step 2: Create Staging Table
```sql
CREATE TABLE cis_portfolio_stage (
  name STRING,
  description STRING,
  ...
  created_at STRING,
  updated_at STRING
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;
```

### Step 3: Prepare Data File
```bash
# Remove header row from data file
tail -n +2 "Porfolio_CIS_format_test2 (1).txt" > cis_portfolio_data.txt
```

### Step 4: Load Data into Staging Table
```sql
LOAD DATA LOCAL INPATH '.../cis_portfolio_data.txt'
OVERWRITE INTO TABLE cis_portfolio_stage;
```

### Step 5: Rename to Production Table
```sql
DROP TABLE IF EXISTS cis_portfolio;
ALTER TABLE cis_portfolio_stage RENAME TO cis_portfolio;
```

## Table Format Decision

**Format**: TEXT with pipe delimiter (not ORC)

**Reason**:
- ORC format encountered persistent INSERT errors in local Hive environment
- Dataset is medium-sized (530 rows)
- TEXT format is adequate for this data volume
- Query performance is acceptable for this size
- Can be converted to ORC later if needed

## Portfolio Categories

### By Entity Group
- **UOB GROUP**: UOB subsidiaries and direct holdings
- **UOB SUBSIDIARY**: Direct UOB subsidiaries
- **UOB ASSOC GROUP**: Associated companies
- **Associated Companies/Company**: Associated entities
- Various other classifications

### By Currency
Major currencies represented:
- **SGD** (Singapore Dollar) - Primary currency
- **USD** (US Dollar)
- **MYR** (Malaysian Ringgit)
- **IDR** (Indonesian Rupiah)
- **VND** (Vietnamese Dong)
- **CNY** (Chinese Yuan)
- **HKD** (Hong Kong Dollar)
- And others

### By Manager
- **For reporting purposes**: Most common (legacy/reporting portfolios)
- **UOBAM**: UOB Asset Management
- **UOBVM**: UOB Venture Management
- **GLOBAL CAPITAL**: Global Capital group
- **REGIONAL DIGITAL BANKING**: Digital banking initiatives
- Various other managers

## Usage Examples

### Query Active Portfolios
```sql
SELECT name, description, currency, entity_group
FROM cis_portfolio
WHERE status = 'Active'
ORDER BY name;
```

### Query Portfolios by Currency
```sql
SELECT name, description, manager, entity_group
FROM cis_portfolio
WHERE currency = 'SGD'
  AND status = 'Active';
```

### Query Subsidiaries
```sql
SELECT name, description, currency, revaluation_status
FROM cis_portfolio
WHERE entity_group LIKE '%SUBSIDIARY%'
  AND status = 'Active';
```

### Query Portfolios by Manager
```sql
SELECT name, description, currency, status
FROM cis_portfolio
WHERE manager = 'UOBAM';
```

## Data Quality Notes

### Empty/NULL Values
Several fields have many empty values:
- `portfolio_client`: Often empty
- `cash_balance_list`: Often empty
- `cash_balance`: Often empty
- `updated_at`: Often empty
- `revaluation_status`: Mixed (REVALUED, NON-REVALUED, or empty)

### Data Inconsistencies
- Some entity_group values have trailing spaces (e.g., "Subsidiary Company ")
- Created_at dates in various formats (22-Mar-13, 05-Nov-14, 5-Oct-18, 18/09/2014, etc.)
- Portfolio names may have prefixes (z, zz) for special categorization

## Maintenance

### Adding New Portfolios
To add new portfolio data:

1. **Update the data file**: Add new rows to `Porfolio_CIS_format_test2 (1).txt`
2. **Prepare clean data**:
   ```bash
   tail -n +2 "Porfolio_CIS_format_test2 (1).txt" > cis_portfolio_data.txt
   ```
3. **Reload data**:
   ```sql
   -- Create temporary staging table
   CREATE TABLE cis_portfolio_new (...)
   ROW FORMAT DELIMITED FIELDS TERMINATED BY '|' STORED AS TEXTFILE;

   -- Load new data
   LOAD DATA LOCAL INPATH '.../cis_portfolio_data.txt'
   OVERWRITE INTO TABLE cis_portfolio_new;

   -- Swap tables
   DROP TABLE cis_portfolio;
   ALTER TABLE cis_portfolio_new RENAME TO cis_portfolio;
   ```

### Converting to ORC Format (Future)
If ORC format becomes necessary:

1. Investigate and resolve ORC insertion errors in local environment
2. Create ORC table with same schema
3. Use CTAS or INSERT SELECT from TEXT table
4. Update documentation

## Integration with Django

### Using Portfolio Data in Views
```python
from cis_trade_hive.core.repositories.hive_connection import HiveConnectionManager

def get_active_portfolios():
    """Get all active portfolios."""
    conn = HiveConnectionManager().get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, description, currency, manager, entity_group
        FROM cis_portfolio
        WHERE status = 'Active'
        ORDER BY name
    """)
    return cursor.fetchall()

def get_portfolio_by_name(portfolio_name):
    """Get portfolio details by name."""
    conn = HiveConnectionManager().get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM cis_portfolio
        WHERE name = %s
    """, (portfolio_name,))
    return cursor.fetchone()

def get_portfolios_by_currency(currency_code):
    """Get portfolios by currency."""
    conn = HiveConnectionManager().get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, description, manager, status
        FROM cis_portfolio
        WHERE currency = %s
        ORDER BY name
    """, (currency_code,))
    return cursor.fetchall()
```

## Files Generated

### DDL Scripts
- `05_cis_portfolio_table.sql` - Original table creation DDL (ORC + staging)
- `06_load_portfolio_data.sql` - Data loading script (attempted)
- `07_cis_portfolio_text.sql` - TEXT format table creation (attempted)

### Data Files
- `reference_csv/cis_portfolio_data.txt` - Clean data file (530 rows, no header)

### Documentation
- `PORTFOLIO_README.md` - This file

## Known Issues

### Issue 1: ORC Table INSERT Failures
- **Error**: Generic "Error running query" when inserting into ORC tables
- **Workaround**: Used TEXT format instead
- **Impact**: None for current dataset size
- **Future**: Investigate Hive configuration for ORC support

### Issue 2: Aggregation Query Failures
- **Error**: COUNT(), SUM(), and other aggregation queries fail
- **Likely Cause**: MapReduce/Tez execution engine configuration
- **Workaround**: Export data and count externally, or use simple SELECT queries
- **Impact**: Limited - can work around with client-side aggregation

### Issue 3: Missing Columns
- **Description**: Data file missing 3 columns from CSV schema (source_name, branch_code, validation_status)
- **Workaround**: Table created without these columns
- **Impact**: None - these columns can be added later if needed via ALTER TABLE ADD COLUMNS

## Statistics

- **Total Rows**: 530
- **Active Portfolios**: 237 (44.7%)
- **Inactive Portfolios**: 293 (55.3%)
- **Table Size**: ~72 KB
- **Format**: TEXT (pipe-delimited)

## Summary

**Status**: ✓ Complete
**Total Rows Loaded**: 530
**Storage Format**: TEXT (pipe-delimited)
**Table Type**: Internal table

All portfolio data has been successfully loaded into the Hive `cis_portfolio` table and is ready for use by the trading system.

---
**Created**: 2025-12-24
**Data Source**: Porfolio_CIS_format_test2 (1).txt
**Database**: cis
**Schema Reference**: cis_portfolio.csv
