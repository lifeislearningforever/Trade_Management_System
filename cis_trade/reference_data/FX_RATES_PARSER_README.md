# FX Rates Parser Documentation

## Overview

This module provides comprehensive parsing capabilities for GMP daily FX rates files. The files contain pipe-delimited (`|`) records with header and detail information.

## File Format

### Header Records (H)
```
H|GMP|19800101|20251224111237
```

Fields:
- `record_type`: Always 'H' for header
- `source_system`: Source system identifier (e.g., 'GMP')
- `start_date`: Reference start date (YYYYMMDD)
- `system_timestamp`: System date and time (YYYYMMDDHHmmss)

### Detail Records (D)
```
D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET
```

Fields:
1. `record_type`: Always 'D' for detail
2. `ref_quot`: Reference quotation identifier
3. `spot_ff0`: Currency pair (e.g., USD-AED)
4. `base`: Base currency code
5. `trade_date`: Trading date (YYYYMMDD)
6. `spot_rf_a`: Spot rate reference A
7. `underlng`: Underlying currency code
8. `spot_rf_b`: Spot rate reference B
9. `alias`: Source/Alias identifier
10. **Calculated**: `mid_rate` = (spot_rf_a + spot_rf_b) / 2

## Hive External Table

### Table Definition

The Hive external table `gmp_cis_sta_dly_fx_rates` is defined in:
```
cis_trade/sql/ddl/06_market_data_fx_rates.sql
```

### Creating the Table

```sql
-- Create the external table
CREATE EXTERNAL TABLE gmp_cis_sta_dly_fx_rates (
    record_type     STRING      COMMENT 'Record type indicator (D=Detail, H=Header)',
    ref_quot        STRING      COMMENT 'Reference quotation identifier',
    spot_ff0        STRING      COMMENT 'Currency pair (e.g., USD-AED)',
    base            STRING      COMMENT 'Base currency code',
    trade_date      STRING      COMMENT 'Trade date in YYYYMMDD format',
    spot_rf_a       DECIMAL(18,6)   COMMENT 'Spot rate reference A',
    underlng        STRING      COMMENT 'Underlying currency code',
    spot_rf_b       DECIMAL(18,6)   COMMENT 'Spot rate reference B',
    alias           STRING      COMMENT 'Source/Alias identifier (e.g., BOSET)',
    mid_rate        DECIMAL(18,6)   COMMENT 'Mid rate calculated as (spot_rf_a + spot_rf_b)/2'
)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE
LOCATION '/user/hive/warehouse/gmp_cis_sta_dly_fx_rates';
```

### Querying the Table

```sql
-- Get all FX rates for a specific date
SELECT *
FROM gmp_cis_sta_dly_fx_rates
WHERE record_type = 'D'
  AND trade_date = '20251124';

-- Get rates for a specific currency pair
SELECT
    spot_ff0,
    trade_date,
    spot_rf_a,
    spot_rf_b,
    ROUND((spot_rf_a + spot_rf_b) / 2, 6) as mid_rate
FROM gmp_cis_sta_dly_fx_rates
WHERE record_type = 'D'
  AND spot_ff0 = 'USD-SGD';

-- Get latest rates for all currency pairs
SELECT
    spot_ff0,
    base,
    MAX(trade_date) as latest_date,
    AVG((spot_rf_a + spot_rf_b) / 2) as avg_mid_rate
FROM gmp_cis_sta_dly_fx_rates
WHERE record_type = 'D'
GROUP BY spot_ff0, base
ORDER BY spot_ff0;
```

## Python Parser Usage

### Installation

The parser is located at:
```
cis_trade/reference_data/services/fx_rates_parser.py
```

### Basic Usage

#### 1. Parse a File

```python
from reference_data.services.fx_rates_parser import FXRatesParser

# Create parser instance
parser = FXRatesParser()

# Parse file
result = parser.parse_file('fx_rates_20251124.txt')

print(f"Headers: {result['headers_count']}")
print(f"Details: {result['details_count']}")
print(f"Errors: {result['errors_count']}")

# Access parsed data
for detail in parser.details:
    print(f"{detail.spot_ff0}: {detail.mid_rate}")
```

#### 2. Parse Text Content

```python
from reference_data.services.fx_rates_parser import FXRatesParser

parser = FXRatesParser()

text_content = """
H|GMP|19800101|20251224111237
D|1|USD-SGD|SGD|20251124|1.3085|USD|1.3082|BOSET
D|1|USD-EUR|EUR|20251124|0.86865|USD|0.86855|BOSET
"""

result = parser.parse_text(text_content)

# Get details as dictionaries
details_dict = parser.get_details_as_dicts()
for detail in details_dict:
    print(detail)
```

#### 3. Using the Convenience Function

```python
from reference_data.services.fx_rates_parser import parse_fx_rates_file

# Quick one-liner to parse a file
result = parse_fx_rates_file('fx_rates_20251124.txt', skip_header=False)

print(f"Total records: {result['details_count']}")
```

### Advanced Usage

#### Filter by Currency Pair

```python
parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

# Get rates for USD-SGD
sgd_rates = parser.filter_by_currency_pair('USD-SGD')
for rate in sgd_rates:
    print(f"Date: {rate.trade_date}, Mid: {rate.mid_rate}")
```

#### Filter by Date

```python
parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

# Get all rates for a specific date
rates_on_date = parser.filter_by_date('20251124')
print(f"Found {len(rates_on_date)} rates for 2025-11-24")
```

#### Filter by Base Currency

```python
parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

# Get all rates with EUR as base
eur_rates = parser.filter_by_base_currency('EUR')
for rate in eur_rates:
    print(f"{rate.spot_ff0}: {rate.mid_rate}")
```

#### Get Summary Statistics

```python
parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

summary = parser.get_summary()
print(f"Total records: {summary['total_records']}")
print(f"Unique currencies: {summary['unique_currencies']}")
print(f"Currency pairs: {summary['unique_currency_pairs']}")
print(f"Date range: {summary['date_range']}")
print(f"Currencies: {summary['currencies']}")
```

### Data Classes

#### FXRateHeader

```python
from reference_data.services.fx_rates_parser import FXRateHeader

header = FXRateHeader(
    record_type='H',
    source_system='GMP',
    start_date='19800101',
    system_timestamp='20251224111237'
)

# Get parsed timestamp
timestamp = header.parsed_timestamp  # Returns datetime object
```

#### FXRateDetail

```python
from reference_data.services.fx_rates_parser import FXRateDetail
from decimal import Decimal

detail = FXRateDetail(
    record_type='D',
    ref_quot='1',
    spot_ff0='USD-SGD',
    base='SGD',
    trade_date='20251124',
    spot_rf_a=Decimal('1.3085'),
    underlng='USD',
    spot_rf_b=Decimal('1.3082'),
    alias='BOSET'
)

# Get mid rate
print(detail.mid_rate)  # 1.30835

# Get parsed date
print(detail.parsed_date)  # datetime object

# Convert to dictionary
detail_dict = detail.to_dict()
```

## Sample Data

Sample FX rates data is available at:
```
cis_trade/sql/sample_data/07_fx_rates_sample.txt
```

This file contains realistic FX rates data for testing and development.

## Testing

### Running Tests

```bash
# Run all FX rates parser tests
cd cis_trade
pytest reference_data/tests/test_fx_rates_parser.py -v

# Run with coverage
pytest reference_data/tests/test_fx_rates_parser.py --cov=reference_data.services.fx_rates_parser

# Run specific test class
pytest reference_data/tests/test_fx_rates_parser.py::TestFXRatesParser -v
```

### Test Coverage

The test suite covers:
- Header parsing and validation
- Detail parsing and validation
- Mid rate calculations
- Date parsing
- File parsing
- Text parsing
- Filtering operations
- Summary statistics
- Error handling
- Edge cases (empty lines, invalid data, etc.)

## Error Handling

The parser collects errors during parsing:

```python
parser = FXRatesParser()
result = parser.parse_file('fx_rates.txt')

# Check for errors
if parser.errors:
    print(f"Found {len(parser.errors)} errors:")
    for error in parser.errors:
        print(f"  Line: {error['line']}")
        print(f"  Type: {error['type']}")
        print(f"  Error: {error['error']}")
```

## Integration with Django

### Loading Data into Django Models

```python
from reference_data.services.fx_rates_parser import FXRatesParser
# Assuming you create a Django model for FX rates

parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

# Bulk create in Django (if model exists)
# FXRate.objects.bulk_create([
#     FXRate(**detail.to_dict())
#     for detail in parser.details
# ])
```

### Using with Impala/Kudu

```python
from reference_data.services.fx_rates_parser import FXRatesParser
from core.repositories.impala_connection import ImpalaConnectionManager

parser = FXRatesParser()
parser.parse_file('fx_rates_20251124.txt')

# Get connection
conn_manager = ImpalaConnectionManager()
cursor = conn_manager.get_cursor()

# Insert into Kudu via Impala
for detail in parser.details:
    cursor.execute("""
        INSERT INTO gmp_cis_sta_dly_fx_rates VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """, (
        detail.record_type,
        detail.ref_quot,
        detail.spot_ff0,
        detail.base,
        detail.trade_date,
        float(detail.spot_rf_a),
        detail.underlng,
        float(detail.spot_rf_b),
        detail.alias,
        float(detail.mid_rate)
    ))
```

## Best Practices

1. **Always validate data**: Check `errors_count` after parsing
2. **Use skip_header**: Set `skip_header=True` if you only need detail records
3. **Handle exceptions**: Wrap file operations in try-except blocks
4. **Log errors**: Use Python logging to track parsing issues
5. **Batch processing**: For large files, process in batches
6. **Data validation**: Validate currency codes and dates before database insertion

## Troubleshooting

### Common Issues

1. **File not found**
   ```python
   # Solution: Use absolute paths
   import os
   file_path = os.path.abspath('fx_rates.txt')
   ```

2. **Invalid decimal format**
   ```python
   # Check errors
   if parser.errors:
       for err in parser.errors:
           if 'Invalid' in err['error']:
               print(f"Invalid data: {err['line']}")
   ```

3. **Date parsing failures**
   ```python
   # Validate date format before parsing
   import re
   date_pattern = r'^\d{8}$'
   if not re.match(date_pattern, trade_date):
       print("Invalid date format")
   ```

## Performance Considerations

- **Large files**: For files > 100MB, consider streaming or chunked processing
- **Memory usage**: The parser loads all records into memory
- **Batch inserts**: Use bulk operations for database inserts
- **Indexing**: Ensure database indexes on `trade_date` and `spot_ff0`

## Future Enhancements

- [ ] Streaming parser for very large files
- [ ] Async file processing
- [ ] Data validation against currency reference tables
- [ ] Automatic database synchronization
- [ ] REST API endpoints for FX rates queries
- [ ] WebSocket support for real-time rate updates

## Support

For questions or issues:
- Check test files for examples
- Review sample data file
- Consult the main CisTrade documentation

---

**CisTrade FX Rates Parser** © 2025
