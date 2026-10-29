# Hive Integration Summary - Audit Log & UDF

## Overview
This document summarizes the complete Hive integration for **Audit Logging** and **User-Defined Fields (UDF)** in the CIS Trade Management System.

---

## ✅ What Has Been Completed

### 1. **Audit Log Hive Integration** ✅

#### Files Created/Modified:
- **`core/audit/audit_hive_repository.py`** - NEW
  - Complete Hive repository for audit log operations
  - Methods: `log_action()`, `get_all_logs()`, `get_entity_history()`, `get_statistics()`
  - Handles all CRUD operations with Hive `cis_audit_log` table

- **`core/old_views.py`** - MODIFIED
  - Updated `audit_log()` view (line 182-242)
  - Now fetches data from Hive instead of Django ORM
  - Supports search, filtering, pagination
  - Removed `@login_required` decorator for development

#### Hive Table:
- **`cis.cis_audit_log`** (30 columns)
  - Comprehensive audit logging with 29 fields
  - Includes: timestamp, user, action, entity, changes, request details, status, metadata
  - Partitioned by `audit_date` for performance

#### Features:
- ✅ Log actions to Hive
- ✅ Search and filter logs
- ✅ Get entity history
- ✅ Generate statistics
- ✅ Pagination support
- ✅ Web interface at `/core/audit-log/`

---

### 2. **UDF Hive Integration** ✅

#### Files Created/Modified:
- **`udf/repositories/udf_hive_repository.py`** - EXISTING
  - Already has UDF repository classes
  - `UDFDefinitionRepository`, `UDFOptionRepository`, `ReferenceDataRepository`
  - Methods for account_group, entity_group, currencies, countries

- **`udf/services/udf_service.py`** - EXISTING
  - Enhanced with Hive integration methods
  - `get_account_group_options()`, `get_entity_group_options()`, `get_currency_options()`
  - Dynamic dropdown routing with `get_udf_dropdown_options()`

- **`udf/urls.py`** - EXISTING
  - AJAX endpoint: `/udf/ajax/dropdown-options/<field_name>/`

- **`udf/views.py`** - EXISTING
  - All UDF CRUD views
  - Removed `@login_required` decorators for development

#### Hive Tables:
- **`cis.cis_udf_definition`** - UDF field definitions
- **`cis.cis_udf_value`** - UDF values for entities
- **`cis.cis_udf_option`** - Dropdown options
- **`cis.cis_udf_value_multi`** - Multi-select values

#### Features:
- ✅ Define custom fields for entities (Portfolio, Trade, etc.)
- ✅ 8 field types: TEXT, NUMBER, BOOLEAN, DROPDOWN, MULTI_SELECT, DATE, CURRENCY, PERCENTAGE
- ✅ Dynamic dropdown loading from Hive
- ✅ Field validation (required, unique, min/max, length)
- ✅ Web interface at `/udf/`
- ✅ AJAX integration

---

### 3. **Other Fixes** ✅

#### Horizontal Scrolling Fix:
- **`static/css/cistrade.css`** - Line 91
  - Commented out `overflow-x: hidden` on body
  - Counterparty table now shows horizontal scrollbar
  - All 20 columns visible with sticky first column

#### Files:
- ✅ Counterparty table: 20 columns with horizontal scroll
- ✅ Search pagination: Fixed for country and counterparty
- ✅ Audit log: Working with Hive backend

---

## 📁 Files Structure

```
cis_trade_hive/
├── core/
│   ├── audit/
│   │   ├── audit_hive_repository.py     ✅ NEW - Audit Hive integration
│   │   ├── audit_logger.py
│   │   └── audit_models.py
│   └── old_views.py                      ✅ MODIFIED - Uses Hive for audit logs
│
├── udf/
│   ├── repositories/
│   │   ├── __init__.py
│   │   └── udf_hive_repository.py        ✅ EXISTING - UDF Hive repository
│   ├── services/
│   │   └── udf_service.py                ✅ EXISTING - Enhanced with Hive
│   ├── urls.py                           ✅ EXISTING - AJAX endpoints
│   ├── views.py                          ✅ EXISTING - UDF CRUD views
│   └── SAMPLE_UDF_USAGE.md               ✅ NEW - Complete usage guide
│
├── scripts/
│   ├── init_udf_sample_data.sql          ✅ NEW - Sample UDF data
│   ├── init_audit_sample_data.sql        ✅ NEW - Sample audit data
│   └── demo_audit_udf.py                 ✅ NEW - Python demo script
│
├── static/css/
│   └── cistrade.css                      ✅ MODIFIED - Fixed overflow
│
└── templates/reference_data/
    ├── counterparty_list.html            ✅ MODIFIED - 20 columns + scroll
    └── country_list.html                 ✅ MODIFIED - Fixed search
```

---

## 🚀 Quick Start Guide

### 1. Initialize Sample Data

```bash
# Navigate to project directory
cd /path/to/cis_trade_hive

# Load UDF sample data
beeline -u jdbc:hive2://localhost:10000/cis -f scripts/init_udf_sample_data.sql

# Load Audit Log sample data
beeline -u jdbc:hive2://localhost:10000/cis -f scripts/init_audit_sample_data.sql
```

### 2. Run Python Demo

```bash
# Activate virtual environment
source .venv/bin/activate

# Run demo script
python scripts/demo_audit_udf.py
```

### 3. Access Web Interfaces

- **Audit Log**: http://localhost:8000/core/audit-log/
- **UDF Management**: http://localhost:8000/udf/
- **Counterparty (20 cols)**: http://localhost:8000/reference-data/counterparty/
- **Country List**: http://localhost:8000/reference-data/country/

---

## 📊 Sample Usage

### Audit Log - Log an Action

```python
from core.audit.audit_hive_repository import audit_log_repository

# Log portfolio creation
audit_log_repository.log_action(
    user_id='user123',
    username='John Smith',
    action_type='CREATE',
    entity_type='PORTFOLIO',
    entity_id='1',
    entity_name='Trading Portfolio A',
    action_description='Created new trading portfolio',
    request_method='POST',
    request_path='/portfolio/create/',
    ip_address='192.168.1.100',
    user_agent='Mozilla/5.0',
    status='SUCCESS'
)
```

### Audit Log - Retrieve Logs

```python
# Get all logs with filters
logs = audit_log_repository.get_all_logs(
    limit=50,
    action_type='CREATE',
    entity_type='PORTFOLIO',
    date_from='2025-01-01',
    search='trading'
)

# Get entity history
history = audit_log_repository.get_entity_history('PORTFOLIO', '1')

# Get statistics
stats = audit_log_repository.get_statistics(days=30)
```

### UDF - Get Dropdown Options

```python
from udf.services.udf_service import UDFService

# Get account group options
options = UDFService.get_account_group_options()
# Returns: [{'value': 'TRADING', 'label': 'Trading'}, ...]

# Get entity group options
options = UDFService.get_entity_group_options()

# Dynamic routing
options = UDFService.get_udf_dropdown_options('account_group')
```

### UDF - Set/Get Values

```python
from udf.services.udf_service import UDFService

# Set UDF values for Portfolio
UDFService.set_entity_udf_values(
    entity_type='PORTFOLIO',
    entity_id=1,
    values={
        'account_group': 'TRADING',
        'entity_group': 'CORPORATE',
        'risk_rating': 7,
        'compliance_notes': 'Approved',
        'is_restricted': False
    },
    user=request.user
)

# Get UDF values
values = UDFService.get_entity_udf_values('PORTFOLIO', 1)
# Returns: {'account_group': 'TRADING', 'entity_group': 'CORPORATE', ...}
```

---

## 📝 SQL Queries

### Query Audit Logs

```sql
-- Recent audit logs
SELECT
    audit_timestamp,
    username,
    action_type,
    entity_type,
    action_description,
    status
FROM cis.cis_audit_log
ORDER BY audit_timestamp DESC
LIMIT 10;

-- Failed operations
SELECT *
FROM cis.cis_audit_log
WHERE status = 'FAILURE';

-- Portfolio operations
SELECT *
FROM cis.cis_audit_log
WHERE entity_type = 'PORTFOLIO'
AND audit_date >= '2025-01-01';
```

### Query UDF Data

```sql
-- Get all UDF definitions for Portfolio
SELECT *
FROM cis.cis_udf_definition
WHERE entity_type = 'PORTFOLIO'
AND is_active = true;

-- Get UDF values for Portfolio 1
SELECT
    field_name,
    value_string,
    value_int,
    value_bool,
    updated_at
FROM cis.cis_udf_value
WHERE entity_type = 'PORTFOLIO'
AND entity_id = 1
AND is_active = true;

-- Get dropdown options
SELECT *
FROM cis.cis_udf_option
WHERE field_name = 'account_group'
AND is_active = true
ORDER BY display_order;
```

---

## 🔧 Configuration

### Hive Connection Settings

Both repositories use the same connection:
- **Host**: localhost
- **Port**: 10000
- **Database**: cis
- **Auth**: NOSASL

### PyHive Limitations Handled

1. **No ORDER BY**: Results sorted in Python
2. **Qualified column names**: Auto-stripped (table.column → column)
3. **INSERT with timestamps**: Using `from_unixtime(unix_timestamp())`

---

## 📖 Documentation

### Complete Guides:
1. **`udf/SAMPLE_UDF_USAGE.md`**
   - Complete UDF usage guide
   - 5 detailed samples
   - Django, SQL, AJAX examples
   - Best practices

2. **`scripts/demo_audit_udf.py`**
   - Working Python demo
   - Shows audit + UDF integration
   - Combined workflow example

3. **SQL Init Scripts:**
   - `scripts/init_udf_sample_data.sql` - 8 UDF definitions, options, values
   - `scripts/init_audit_sample_data.sql` - 12 sample audit log entries

---

## ✨ Key Features

### Audit Log:
- ✅ **30-column comprehensive logging**
- ✅ **Action types**: CREATE, UPDATE, DELETE, VIEW, LOGIN, LOGOUT, EXPORT, IMPORT
- ✅ **Entity types**: PORTFOLIO, TRADE, UDF, USER, etc.
- ✅ **Track field changes**: old_value → new_value
- ✅ **Request details**: method, path, params, IP, user agent
- ✅ **Error tracking**: error_message, error_traceback
- ✅ **Performance**: duration_ms, metadata
- ✅ **Search & filter**: by action, entity, user, date, search term
- ✅ **Statistics**: action breakdown, entity breakdown

### UDF System:
- ✅ **8 field types** with validation
- ✅ **Dynamic dropdowns** from Hive
- ✅ **Required/unique** constraints
- ✅ **Min/max** validation for numbers
- ✅ **Max length** for text
- ✅ **Default values**
- ✅ **Display order** and grouping
- ✅ **Soft deletes** (is_active flag)
- ✅ **Audit trail** (created_by, updated_by)
- ✅ **Web interface** with AJAX

### Integration:
- ✅ **Full Hive backend** - no Django ORM dependency for Audit/UDF data
- ✅ **RESTful APIs** - AJAX endpoints
- ✅ **Search & pagination** - client and server side
- ✅ **Error handling** - comprehensive logging
- ✅ **Type safety** - correct Hive column types

---

## 🎯 Next Steps (Optional Enhancements)

1. **Authentication**: Uncomment `@login_required` decorators when user system ready
2. **Real-time Audit**: Add middleware to auto-log all requests
3. **UDF Templates**: Create predefined UDF sets for common scenarios
4. **Audit Dashboard**: Visual analytics with charts
5. **UDF Validation**: Add regex patterns for text fields
6. **Export**: CSV export for audit logs
7. **Notifications**: Email alerts for critical audit events

---

## 🐛 Known Issues

None currently. Both systems fully functional with Hive backend.

---

## 📞 Support

For issues or questions:
- Check `udf/SAMPLE_UDF_USAGE.md` for UDF documentation
- Run `scripts/demo_audit_udf.py` for working examples
- Review Hive tables: `beeline -u jdbc:hive2://localhost:10000/cis`

---

## 📅 Last Updated

2025-12-25 - Complete Hive integration for Audit Log and UDF systems
