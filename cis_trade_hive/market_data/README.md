# Market Data Module - FX Rates

## Overview

The Market Data module provides comprehensive Foreign Exchange (FX) rate tracking and management capabilities. It integrates seamlessly with Apache Hive for data storage and retrieval, following the same patterns as the Portfolio module.

## Features

- **FX Rate Management**: Track exchange rates with bid/ask spreads
- **Multiple Data Sources**: Support for Bloomberg, Reuters, Manual, API, and Hive
- **Historical Tracking**: Maintain 30-day rate history for each currency pair
- **Real-time Dashboard**: Visual overview of latest rates and statistics
- **CSV Export**: Export filtered data to CSV format
- **Audit Logging**: Complete audit trail via Hive
- **Production-Ready**: Built with Django best practices

## Module Structure

```
market_data/
├── __init__.py
├── models.py                    # FXRate model with validation
├── views.py                     # List, dashboard, detail views
├── urls.py                      # URL routing
├── admin.py                     # Django admin configuration
├── repositories/
│   ├── __init__.py
│   └── fx_rate_hive_repository.py  # Hive data access layer
└── README.md                    # This file
```

## Database Schema

### FXRate Model Fields

- **Currency Information**:
  - `currency_pair`: Format "BASE/QUOTE" (e.g., "USD/EUR")
  - `base_currency`: 3-letter ISO code
  - `quote_currency`: 3-letter ISO code

- **Rate Information**:
  - `rate`: Main exchange rate (10 decimal places)
  - `bid_rate`: Buy price
  - `ask_rate`: Sell price
  - `mid_rate`: Average of bid/ask

- **Temporal Information**:
  - `rate_date`: Date of the rate
  - `rate_time`: Precise timestamp

- **Source and Status**:
  - `source`: Data source (BLOOMBERG, REUTERS, etc.)
  - `is_active`: Active status flag

## Hive Integration

### Table Structure

The module reads from Hive table `cis.fx_rates`:

```sql
CREATE TABLE fx_rates (
    currency_pair STRING,
    base_currency STRING,
    quote_currency STRING,
    rate DECIMAL(20,10),
    bid_rate DECIMAL(20,10),
    ask_rate DECIMAL(20,10),
    mid_rate DECIMAL(20,10),
    rate_date DATE,
    rate_time TIMESTAMP,
    source STRING,
    is_active BOOLEAN,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
) STORED AS ORC;
```

### Loading Sample Data

```bash
# Run the DDL script to create table and load sample data
beeline -u jdbc:hive2://localhost:10000/cis -f sql/ddl/market_data_tables.sql
```

## URL Configuration

Add to your main `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... other patterns
    path('market-data/', include('market_data.urls')),
]
```

## Available URLs

- `/market-data/fx-rates/` - List all FX rates with filters
- `/market-data/fx-rates/dashboard/` - Dashboard overview
- `/market-data/fx-rates/<currency_pair>/` - Rate detail and history

## Views

### FX Rate List (`fx_rate_list`)

Lists all FX rates with comprehensive filtering:
- Filter by currency pair
- Filter by date range (from/to)
- Filter by data source
- CSV export functionality
- Pagination (25 per page)

### FX Rate Dashboard (`fx_rate_dashboard`)

Overview dashboard featuring:
- Statistics cards (total rates, pairs, sources, latest update)
- Latest rates table
- Data source breakdown
- Currency coverage matrix

### FX Rate Detail (`fx_rate_detail`)

Detailed view for a specific currency pair:
- Current rate information
- Bid/ask spread analysis
- 30-day rate history
- Chart data (ready for Chart.js integration)

## Templates

All templates follow the ultra-premium UI design from `static/css/custom.css`:

- **fx_rate_list.html**: Responsive table with glassmorphism cards
- **fx_rate_dashboard.html**: Metric cards and statistics
- **fx_rate_detail.html**: Detail view with chart placeholder

## Rate Freshness Indicators

Rates are automatically classified based on age:

- **Fresh** (< 1 hour): Green badge
- **Normal** (1-24 hours): Blue badge
- **Stale** (> 24 hours): Yellow/warning badge

## Admin Interface

Access via Django admin at `/admin/market_data/fxrate/`:

- Comprehensive list view with formatting
- Filters by date, source, currency
- Search by currency pair
- Bulk actions (activate/deactivate)
- Color-coded freshness badges

## Repository Pattern

The `FXRateHiveRepository` provides clean data access:

```python
from market_data.repositories import fx_rate_hive_repository

# Get all rates with filters
rates = fx_rate_hive_repository.get_all_fx_rates(
    limit=100,
    currency_pair='USD/EUR',
    date_from='2025-12-01',
    date_to='2025-12-26'
)

# Get latest rates for each pair
latest = fx_rate_hive_repository.get_latest_rates()

# Get historical data
history = fx_rate_hive_repository.get_rate_history('USD/EUR', days=30)

# Get statistics
stats = fx_rate_hive_repository.get_statistics()
```

## CSV Export

Users can export filtered data:
- Click "Export CSV" button
- Maintains current filter selections
- Includes all rate details and calculated spreads
- Logs export action to audit log

## Model Validation

The FXRate model includes comprehensive validation:

- Currency pair format validation (BASE/QUOTE)
- Rate positivity checks
- Bid/ask relationship validation
- Auto-calculation of mid rate
- Future date prevention

## Helper Methods

```python
rate = FXRate.objects.first()

# Calculate spread
spread = rate.get_spread()

# Calculate spread percentage
spread_pct = rate.get_spread_percentage()

# Check freshness
if rate.is_fresh(hours=1):
    print("Rate is fresh!")

if rate.is_stale(hours=24):
    print("Rate is stale!")

# Get status
status = rate.get_freshness_status()  # 'fresh', 'normal', or 'stale'
color = rate.get_freshness_color()     # Bootstrap color class
```

## Production Deployment

### 1. Run Migrations

```bash
python manage.py makemigrations market_data
python manage.py migrate
```

### 2. Create Hive Table

```bash
beeline -u jdbc:hive2://localhost:10000/cis -f sql/ddl/market_data_tables.sql
```

### 3. Update Settings

Add to `INSTALLED_APPS`:
```python
INSTALLED_APPS = [
    # ...
    'market_data',
]
```

### 4. Configure URLs

Add to main `urls.py`:
```python
path('market-data/', include('market_data.urls')),
```

### 5. Collect Static Files

```bash
python manage.py collectstatic
```

## Dependencies

- Django >= 3.2
- Apache Hive 4.x
- Beeline CLI tool
- Custom CSS/JS from `static/`

## Future Enhancements

- Chart.js integration for visualizations
- Real-time rate updates via WebSocket
- Rate alerts and notifications
- Advanced analytics and trends
- Multiple currency pair comparison
- Rate prediction models

## Notes

- This is a **read-only** view of Hive data
- Audit logging writes to Hive `audit_logs` table
- Follows the same patterns as Portfolio module
- Uses ultra-premium UI design system
- Production-ready with comprehensive error handling

## Support

For questions or issues, refer to the main project documentation or contact the development team.

---

**Version**: 1.0
**Created**: December 26, 2025
**Author**: CisTrade Development Team
