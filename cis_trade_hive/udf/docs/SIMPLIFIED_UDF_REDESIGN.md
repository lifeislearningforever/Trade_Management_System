# UDF System Redesign - Simplified Free Text Approach

## Overview

The UDF (User-Defined Fields) system has been redesigned based on BA requirements for a simpler, free-text approach. This redesign eliminates complex field types, validations, and dropdown options in favor of a straightforward system where all UDF fields are simple text inputs.

## Key Changes

### Before (Complex System)
- Multiple field types (TEXT, NUMBER, DATE, DROPDOWN, etc.)
- Complex validation rules (min/max values, regex patterns)
- Separate dropdown options table
- Multiple default value columns
- Complex UI with many configuration options

### After (Simplified System)
- **Single field type:** All UDF fields are free text
- **Core fields only:** Field Name, Label, Entity Type, Required, Active
- **No validation rules:** Users can enter any text
- **No dropdown options:** Removed cis_udf_option table
- **Clean UI:** Simple form with essential fields only

## Architecture

### SOLID Principles Applied

1. **Single Responsibility Principle (SRP)**
   - Repository: Only handles data access
   - Service: Only handles business logic and validation
   - Views: Only handles HTTP request/response

2. **Open/Closed Principle (OCP)**
   - Extensible through composition
   - New entity types can be added without modifying existing code

3. **Liskov Substitution Principle (LSP)**
   - Repository implements clear interface
   - Can be swapped with different implementations

4. **Interface Segregation Principle (ISP)**
   - Focused interface for UDF field operations
   - No unnecessary methods

5. **Dependency Inversion Principle (DIP)**
   - Service depends on repository interface, not concrete implementation
   - Repository depends on impala_manager abstraction

## Database Schema

### New Simplified Table: `cis_udf_field`

```sql
CREATE TABLE gmp_cis.cis_udf_field_kudu (
    udf_id BIGINT NOT NULL,              -- Primary key
    field_name STRING NOT NULL,           -- Technical name (e.g., 'trade_date')
    label STRING NOT NULL,                -- Display label (e.g., 'Trade Date')
    entity_type STRING NOT NULL,          -- PORTFOLIO, TRADE, COMMENTS, etc.
    is_required BOOLEAN DEFAULT false,    -- Whether field is required
    is_active BOOLEAN DEFAULT true,       -- Soft delete flag
    created_by STRING NOT NULL,
    created_at BIGINT NOT NULL,           -- Unix timestamp (milliseconds)
    updated_by STRING NOT NULL,
    updated_at BIGINT NOT NULL,           -- Unix timestamp (milliseconds)
    PRIMARY KEY (udf_id)
) PARTITION BY HASH PARTITIONS 4 STORED AS KUDU;
```

### Removed Tables
- `cis_udf_definition` - Replaced by `cis_udf_field`
- `cis_udf_option` - No longer needed (no dropdowns)
- `cis_udf_value` - Simplified (values stored in entity tables)

## File Structure

### New Files Created

```
udf/
├── repositories/
│   └── udf_field_repository.py          # NEW - SOLID-compliant data access
├── services/
│   └── udf_field_service.py             # NEW - Business logic with audit logging
├── views_simplified.py                   # NEW - Clean, focused views
├── urls_simplified.py                    # NEW - Simplified URL routing
└── docs/
    └── SIMPLIFIED_UDF_REDESIGN.md       # This file

sql/ddl/
└── udf_simplified_schema.sql            # NEW - Simplified table DDL

templates/udf/
├── dashboard.html                        # NEW - Entity cards dashboard
├── list.html                            # NEW - List with search/filters
└── form.html                            # NEW - Create/Edit form
```

### Old Files (Keep for Reference, Not Used)

```
udf/
├── repositories/
│   └── udf_hive_repository.py           # OLD - Complex repository
├── services/
│   ├── udf_service.py                   # OLD - Complex service
│   └── portfolio_dropdown_service.py    # OLD - Dropdown service
├── views.py                              # OLD - Complex views
└── urls.py                               # OLD - Complex URL routing
```

## Implementation Steps

### Step 1: Create Kudu Table

```bash
# Connect to Impala
impala-shell -i <impala-host>:21050 -k --ssl

# Run DDL
source sql/ddl/udf_simplified_schema.sql

# Verify table created
DESCRIBE gmp_cis.cis_udf_field;

# Check sample data
SELECT * FROM gmp_cis.cis_udf_field LIMIT 10;
```

### Step 2: Update Django URLs

Replace the UDF URL configuration in `config/urls.py`:

**Before:**
```python
path('udf/', include('udf.urls')),  # OLD
```

**After:**
```python
path('udf/', include('udf.urls_simplified')),  # NEW
```

### Step 3: Update Navigation (Optional)

Update main navigation to point to new UDF dashboard:

**In `templates/components/sidebar.html` or navigation template:**
```html
<a href="{% url 'udf:dashboard' %}" class="nav-link">
    <i class="bi bi-sliders me-2"></i> UDF Management
</a>
```

### Step 4: Restart Django Server

```bash
# Django auto-reload should pick up changes
# If not, restart manually:
pkill -f "runserver"
python manage.py runserver 0.0.0.0:8000
```

### Step 5: Test Functionality

1. **Dashboard:** http://localhost:8000/udf/
2. **List View:** http://localhost:8000/udf/list/
3. **Create Field:** http://localhost:8000/udf/create/
4. **Edit Field:** http://localhost:8000/udf/{udf_id}/edit/
5. **Delete Field:** POST to http://localhost:8000/udf/{udf_id}/delete/
6. **Restore Field:** POST to http://localhost:8000/udf/{udf_id}/restore/

## Features

### 1. Dashboard View
- **URL:** `/udf/`
- **Features:**
  - Card view for each entity type
  - Shows total fields, active count, inactive count
  - Quick links to view fields by entity
  - "Add Field" button

### 2. List View
- **URL:** `/udf/list/`
- **Features:**
  - Search by field name or label
  - Filter by entity type
  - Filter by status (active/inactive/all)
  - Table with edit/delete/restore actions
  - Visual distinction for inactive fields

### 3. Create/Edit Form
- **URL:** `/udf/create/` or `/udf/{udf_id}/edit/`
- **Fields:**
  - Field Name (required, immutable after creation)
  - Label (required, can be updated)
  - Entity Type (required, immutable after creation)
  - Required checkbox
  - Active checkbox (edit only)
- **Validation:**
  - Field name uniqueness per entity type
  - Alphanumeric + underscores only for field name

### 4. Soft Delete
- **URL:** POST to `/udf/{udf_id}/delete/`
- **Behavior:** Sets `is_active = false`
- **Audit:** Logs DELETE action

### 5. Restore
- **URL:** POST to `/udf/{udf_id}/restore/`
- **Behavior:** Sets `is_active = true`
- **Audit:** Logs RESTORE action

## Audit Logging

All UDF operations are logged to `gmp_cis.cis_audit_log`:

| Action | entity_type | action_type | Description |
|--------|------------|-------------|-------------|
| Create | UDF | CREATE | Created UDF field '{label}' ({field_name}) for {entity_type} |
| Update | UDF | UPDATE | Updated UDF field '{label}' ({field_name}) for {entity_type} |
| Delete | UDF | DELETE | Deleted UDF field '{label}' ({field_name}) for {entity_type} |
| Restore | UDF | RESTORE | Restored UDF field '{label}' ({field_name}) for {entity_type} |

## Bootstrap 5 Components Used

All templates use **local Bootstrap 5** (not CDN):

- **Cards:** Entity cards on dashboard
- **Tables:** Responsive table with hover effects
- **Forms:** Form controls with validation
- **Modals:** Confirmation dialogs for delete/restore
- **Badges:** Status indicators (Active/Inactive, Required/Optional)
- **Buttons:** Action buttons with icons
- **Alerts:** Error/success messages

### Bootstrap Icons

Used icons (ensure Bootstrap Icons CSS is included):
- `bi-plus-circle` - Add
- `bi-pencil` - Edit
- `bi-trash` - Delete
- `bi-arrow-counterclockwise` - Restore
- `bi-search` - Search
- `bi-list-ul` - List view
- `bi-grid` - Dashboard view
- `bi-info-circle` - Info
- `bi-exclamation-triangle-fill` - Error

## API Endpoints

### Get Fields by Entity Type

**Endpoint:** `GET /udf/api/{entity_type}/fields/`

**Purpose:** Used by other modules (Portfolio, Trade, etc.) to fetch active UDF fields dynamically

**Example:**
```javascript
fetch('/udf/api/PORTFOLIO/fields/')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log('Fields:', data.fields);
      // Dynamically render UDF fields in form
    }
  });
```

**Response:**
```json
{
  "success": true,
  "fields": [
    {
      "udf_id": 1704063600000,
      "field_name": "account_group",
      "label": "Account Group",
      "entity_type": "PORTFOLIO",
      "is_required": true,
      "is_active": true
    }
  ]
}
```

## Migration from Old System

### Option 1: Fresh Start (Recommended)

1. Drop old tables (backup first!)
2. Create new `cis_udf_field` table
3. Manually recreate essential UDF fields
4. Update Django to use new URLs and views

### Option 2: Data Migration

If you need to preserve existing UDF data:

```sql
-- Insert existing UDF definitions into new table
INSERT INTO gmp_cis.cis_udf_field_kudu
SELECT
    udf_id,
    field_name,
    label,
    entity_type,
    is_required,
    is_active,
    created_by,
    created_at,
    updated_by,
    updated_at
FROM gmp_cis.cis_udf_definition
WHERE field_type != 'DROPDOWN';  -- Skip complex types

-- Manually handle DROPDOWN fields (convert to TEXT)
```

## Validation Rules

### Field Name
- Must be provided
- Alphanumeric + underscores only
- Must be unique per entity type
- Immutable after creation

### Label
- Must be provided
- Can contain any characters
- Can be updated anytime

### Entity Type
- Must be one of: PORTFOLIO, TRADE, COMMENTS, POSITION, MARKETDATA, REFERENCE
- Immutable after creation

## Error Handling

All operations return clear error messages:

- **Create duplicate field:** "Field Name '{field_name}' already exists for entity type '{entity_type}'"
- **Invalid field name:** "Field Name must contain only letters, numbers, and underscores"
- **Delete already deleted:** "UDF field is already deleted"
- **Restore active field:** "UDF field is already active"

## Testing Checklist

- [ ] Create new UDF field
- [ ] Edit existing UDF field
- [ ] Soft delete UDF field
- [ ] Restore deleted UDF field
- [ ] Search UDF fields
- [ ] Filter by entity type
- [ ] Filter by status (active/inactive)
- [ ] Verify audit logs created
- [ ] Test API endpoint for fetching fields
- [ ] Test validation (duplicate field name)
- [ ] Test validation (invalid field name format)

## Troubleshooting

### Issue: Templates not found

**Solution:** Ensure `templates/udf/` directory exists and contains:
- `dashboard.html`
- `list.html`
- `form.html`

### Issue: 404 on UDF URLs

**Solution:** Verify `config/urls.py` uses `udf.urls_simplified`:
```python
path('udf/', include('udf.urls_simplified')),
```

### Issue: Kudu table not found

**Solution:** Run the DDL script:
```bash
impala-shell -i <host>:21050 -k --ssl -f sql/ddl/udf_simplified_schema.sql
```

### Issue: Import errors

**Solution:** Ensure all new files are created:
- `udf/repositories/udf_field_repository.py`
- `udf/services/udf_field_service.py`
- `udf/views_simplified.py`
- `udf/urls_simplified.py`

## Future Enhancements

1. **Bulk Operations:** Select multiple fields for delete/restore
2. **Export/Import:** Export UDF definitions as JSON
3. **Field Groups:** Group related fields together
4. **Display Order:** Control the order fields appear in forms
5. **Field Help Text:** Add help text/tooltip for each field
6. **Validation Rules:** Optional regex validation per field
7. **Default Values:** Specify default values for fields

## Summary

This redesign delivers exactly what BA requested:
- ✅ Simple free text approach
- ✅ Essential fields only (Field Name, Label, Entity Type, Required, Active)
- ✅ Clean UI with cards and list views
- ✅ Edit and soft delete functionality
- ✅ SOLID principles throughout
- ✅ Complete audit logging
- ✅ Local Bootstrap 5

The system is now maintainable, testable, and easy to use for both business users and developers.
