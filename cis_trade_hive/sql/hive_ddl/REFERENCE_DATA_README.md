# Reference Data Tables - Hive Implementation

## Overview
This document describes the Reference Data external tables implementation in the Hive database `cis`.

## Tables Created

All tables are **EXTERNAL TABLES** - the data files remain in their original location and are not moved into Hive's warehouse directory.

### 1. gmp_cis_sta_dly_calendar
- **Purpose**: Financial calendar and holiday data for various financial centers
- **Format**: External TEXT table (pipe-delimited)
- **Rows**: 100,000
- **Columns**:
  - calendar_label (STRING) - Calendar identifier (e.g., AAB, NYB, LNB, TGT)
  - calendar_description (STRING) - Description of the calendar (e.g., Amman, New York, London)
  - holiday_date (INT) - Holiday date in YYYYMMDD format
- **Location**: `file:///Users/prakashhosalli/.../reference_csv/gmp_cis_sta_dly_calendar/`
- **Sample Data**:
  ```
  AAB  | Amman      | 20130101
  NYB  | New York   | 20130101
  LNB  | London     | 20130101
  ```

### 2. gmp_cis_sta_dly_country
- **Purpose**: Country reference data
- **Format**: External TEXT table (pipe-delimited)
- **Rows**: 246
- **Columns**:
  - label (STRING) - Two-letter country code
  - full_name (STRING) - Full country name
- **Location**: `file:///Users/prakashhosalli/.../reference_csv/gmp_cis_sta_dly_country/`
- **Sample Data**:
  ```
  AR | Argentina
  AT | Austria
  AU | Australia
  BE | Belgium
  BR | Brazil
  ```

### 3. gmp_cis_sta_dly_currency
- **Purpose**: Currency reference data with trading information
- **Format**: External TEXT table (pipe-delimited)
- **Rows**: 178
- **Columns**:
  - name (STRING) - Currency short name
  - full_name (STRING) - Full currency name
  - symbol (STRING) - Currency symbol
  - iso_code (STRING) - ISO currency code
  - precision (STRING) - Currency precision (e.g., 1/100) - **Note: Backtick-escaped reserved keyword**
  - calendar (STRING) - Calendar code for this currency
  - spot_schedule (STRING) - Spot settlement schedule
  - rate_precision (STRING) - Exchange rate precision - **Note: Backtick-escaped**
- **Location**: `file:///Users/prakashhosalli/.../reference_csv/gmp_cis_sta_dly_currency/`
- **Sample Data**:
  ```
  USD | US DOLLAR        | USD | USD | 1/100 | NYB | +2 BUSINESS DAY | 7:2
  EUR | EURO             | EUR | EUR | 1/100 | TGT | +2 BUSINESS DAY | 7:2
  GBP | POUND STERLING   | GBP | GBP | 1/100 | LNB | +2 BUSINESS DAY | 7:2
  ```

**Important**: The columns `precision` and `rate_precision` are Hive reserved keywords and are escaped with backticks in the DDL.

### 4. gmp_cis_sta_dly_counterparty
- **Purpose**: Counterparty and entity information
- **Format**: External TEXT table (pipe-delimited)
- **Rows**: 6,385
- **Columns** (20 total):
  - counterparty_name (STRING) - Counterparty identifier/name
  - description (STRING) - Full description
  - salutation (STRING) - Salutation
  - address (STRING) - Street address
  - city (STRING) - City
  - country (STRING) - Country
  - postal_code (STRING) - Postal/ZIP code
  - fax (STRING) - Fax number
  - telex (STRING) - Telex number
  - industry (DOUBLE) - Industry code
  - is_counterparty_broker (STRING) - Is this a broker? (Y/N)
  - is_counterparty_custodian (STRING) - Is this a custodian? (Y/N)
  - is_counterparty_issuer (STRING) - Is this an issuer? (Y/N)
  - primary_contact (DOUBLE) - Primary contact ID
  - primary_number (DOUBLE) - Primary phone number
  - other_contact (DOUBLE) - Other contact ID
  - other_number (DOUBLE) - Other phone number
  - custodian_group (DOUBLE) - Custodian group ID
  - broker_group (DOUBLE) - Broker group ID
  - resident_y_n (DOUBLE) - Resident flag
- **Location**: `file:///Users/prakashhosalli/.../reference_csv/gmp_cis_sta_dly_counterparty/`
- **Sample Data**:
  ```
  JAPAN          | GOVERNMENT OF JAPAN                      | Japan         | N | N | Y
  GERMANY        | FEDERAL REPUBLIC OF GERMANY              | Germany       | N | N | Y
  AUSTRALIA      | COMMONWEALTH OF AUSTRALIA                | Australia     | N | N | Y
  UNITED KINGDOM | UNITED KINGDOM - UK TREASURY             | United Kingdom| N | N | Y
  UNITED STATES  | UNITED STATES OF AMERICA - US TREASURY   | United States | N | N | Y
  ```

**Data Quality Notes**:
- Many columns have significant null values (industry, contacts, groups columns are completely empty)
- Address-related fields (salutation, address, city) have many nulls
- Core fields (counterparty_name, country, is_* flags) are well-populated

## Data Source
- **Original File**: `cis_trade_hive/kudu_ddl/Reference_Data.xlsx`
- **Sheets**:
  1. gmp_cis_sta_dly_calendar
  2. gmp_cis_sta_dly_country
  3. gmp_cis_sta_dly_currency
  4. gmp_cis_sta_dly_counterparty
- **Total Rows**: 106,809 (100,000 + 246 + 178 + 6,385)

## Implementation Process

### Step 1: Export Excel to CSV
```bash
python3 export_reference_to_csv.py
```
This creates pipe-delimited CSV files in the `reference_csv/` directory.

**Export Details**:
- Delimiter: Pipe (|)
- Headers: Not included in CSV files
- NULL values: Represented as empty strings
- Boolean values: Converted to lowercase strings

### Step 2: Organize CSV Files into Directories
Each table gets its own directory for the EXTERNAL TABLE LOCATION:
```
reference_csv/
├── gmp_cis_sta_dly_calendar/
│   └── gmp_cis_sta_dly_calendar.csv
├── gmp_cis_sta_dly_country/
│   └── gmp_cis_sta_dly_country.csv
├── gmp_cis_sta_dly_currency/
│   └── gmp_cis_sta_dly_currency.csv
└── gmp_cis_sta_dly_counterparty/
    └── gmp_cis_sta_dly_counterparty.csv
```

### Step 3: Create External Tables
```bash
beeline -u jdbc:hive2://localhost:10000/cis \
  -f 03_reference_external_tables.sql
```

**External Table Benefits**:
- Data stays in original location (not moved to Hive warehouse)
- Easier to update data (just replace CSV files)
- No data duplication
- Faster table creation (no data copy)

### Step 4: Verify Data
```bash
beeline -u jdbc:hive2://localhost:10000/cis \
  -f 04_verify_reference_tables.sql
```

## Files Generated

### DDL Scripts
- `03_reference_external_tables.sql` - External table creation DDL
- `04_verify_reference_tables.sql` - Verification queries

### Python Scripts
- `export_reference_to_csv.py` - Excel to CSV converter

### CSV Data Files
- `reference_csv/gmp_cis_sta_dly_calendar/gmp_cis_sta_dly_calendar.csv` (3.3 MB)
- `reference_csv/gmp_cis_sta_dly_country/gmp_cis_sta_dly_country.csv` (3.6 KB)
- `reference_csv/gmp_cis_sta_dly_currency/gmp_cis_sta_dly_currency.csv` (13 KB)
- `reference_csv/gmp_cis_sta_dly_counterparty/gmp_cis_sta_dly_counterparty.csv` (655 KB)

## Usage Examples

### Query Calendar Holidays
```sql
-- Get all holidays for New York calendar in 2023
SELECT calendar_label, calendar_description, holiday_date
FROM gmp_cis_sta_dly_calendar
WHERE calendar_label = 'NYB'
  AND holiday_date >= 20230101
  AND holiday_date < 20240101;
```

### Query Currency Information
```sql
-- Get major currencies with their settlement schedules
SELECT name, full_name, calendar, spot_schedule
FROM gmp_cis_sta_dly_currency
WHERE iso_code IN ('USD', 'EUR', 'GBP', 'JPY', 'CHF');
```

### Query Counterparties
```sql
-- Find all government issuers
SELECT counterparty_name, description, country
FROM gmp_cis_sta_dly_counterparty
WHERE is_counterparty_issuer = 'Y'
  AND is_counterparty_broker = 'N'
  AND is_counterparty_custodian = 'N'
LIMIT 20;
```

### Query Countries
```sql
-- Get all countries
SELECT label, full_name
FROM gmp_cis_sta_dly_country
ORDER BY full_name;
```

## Technical Notes

### Reserved Keywords
The currency table uses Hive reserved keywords as column names:
- `precision` - escaped as `` `precision` ``
- `rate_precision` - escaped as `` `rate_precision` ``

When querying these columns, use backticks:
```sql
SELECT name, `precision`, `rate_precision`
FROM gmp_cis_sta_dly_currency;
```

### Data Types
- **Dates**: Stored as INT in YYYYMMDD format (e.g., 20230101 for Jan 1, 2023)
- **Flags**: Stored as STRING ('Y', 'N')
- **Numeric IDs**: Stored as DOUBLE (allows NULL values)

### Performance Considerations
- **Calendar table (100K rows)**: Queries are fast due to small data size
- **Counterparty table (6.4K rows)**: Good performance for lookups
- No indexes needed for tables of this size
- Consider partitioning calendar table by year if dataset grows significantly

## Maintenance

### Updating Data
To update reference data:

1. **Update the Excel file**: `Reference_Data.xlsx`
2. **Re-export to CSV**:
   ```bash
   python3 export_reference_to_csv.py
   ```
3. **No Hive operations needed** - External tables automatically reflect updated CSV files
4. **Optional**: Refresh metadata if needed:
   ```sql
   REFRESH TABLE gmp_cis_sta_dly_calendar;
   ```

### Adding New Calendar Entries
```bash
# 1. Update Excel file with new holidays
# 2. Re-export
python3 export_reference_to_csv.py

# 3. Data is immediately available in Hive (no LOAD needed)
```

### Converting to ORC Format (Future)
If performance becomes an issue or the dataset grows significantly:

```sql
-- Create ORC table
CREATE TABLE gmp_cis_sta_dly_calendar_orc
STORED AS ORC
AS SELECT * FROM gmp_cis_sta_dly_calendar;

-- Drop external table and rename
DROP TABLE gmp_cis_sta_dly_calendar;
ALTER TABLE gmp_cis_sta_dly_calendar_orc
  RENAME TO gmp_cis_sta_dly_calendar;
```

## Integration with Django

### Using Reference Data in Views
```python
from cis_trade_hive.core.repositories.hive_connection import HiveConnectionManager

def get_currencies():
    """Get all currencies from reference data."""
    conn = HiveConnectionManager().get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name, full_name, iso_code, calendar
        FROM gmp_cis_sta_dly_currency
        ORDER BY name
    """)
    return cursor.fetchall()

def is_holiday(calendar_code, date_int):
    """Check if a date is a holiday for a given calendar."""
    conn = HiveConnectionManager().get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT COUNT(*) as is_holiday
        FROM gmp_cis_sta_dly_calendar
        WHERE calendar_label = %s
          AND holiday_date = %s
    """, (calendar_code, date_int))
    result = cursor.fetchone()
    return result[0] > 0
```

## Summary

**Status**: ✓ Complete
**Total Tables**: 4 external tables
**Total Rows**: 106,809
**Storage Format**: TEXT (pipe-delimited CSV)
**Table Type**: EXTERNAL (data remains in original location)

All reference data is now available in Hive and ready for use by the trading system.

---
**Created**: 2025-12-24
**Data Source**: Reference_Data.xlsx
**Database**: cis
