# Party Migration Guide

## Overview

This guide documents the migration from `cis_counterparty_kudu` / `cis_counterparty_cif_kudu` tables to `cis_party` / `cis_party_cif` tables.

## New Files Created

### DDL
- `sql/ddl/cis_party_kudu.sql` - Creates new cis_party and cis_party_cif tables with data migration

### Repositories
- `reference_data/repositories/party_repository.py` - New PartyRepository class
- `reference_data/repositories/party_cif_repository.py` - New PartyCIFRepository class

### Services
- `reference_data/services/party_service.py` - PartyService and PartyCIFService classes

### Views
- `reference_data/views.py` - Added party_list, party_detail, party_create, party_edit, party_delete, party_restore views
- `reference_data/views.py` - Added party_cif_list, party_cif_create, party_cif_update, party_cif_delete AJAX views

### Templates
- `templates/reference_data/party_list.html` - Party list view with filtering, pagination, CIF modal
- `templates/reference_data/party_details.html` - Party detail view with CIFs and all fields
- `templates/reference_data/party_form.html` - Party create/edit form with CIF management

### URLs
- `reference_data/urls.py` - Added party URLs alongside existing counterparty URLs

## Column Mapping (Old → New)

### cis_counterparty_kudu → cis_party
| Old Column | New Column |
|------------|------------|
| counterparty_short_name | party_short_name |
| counterparty_full_name | party_full_name |
| counterparty_grandparent | party_grandparent |
| counterparty_parent | party_parent |
| cels_code | gics_code |
| (all other columns remain the same) | |

### cis_counterparty_cif_kudu → cis_party_cif
| Old Column | New Column |
|------------|------------|
| counterparty_short_name | party_name |
| (all other columns remain the same) | |

## Migration Steps

### Step 1: Create New Tables
Run the DDL to create new tables and migrate data:
```bash
impala-shell -i localhost:21050 -f sql/ddl/cis_party_kudu.sql
```

### Step 2: Update URLs (reference_data/urls.py)
Add new party URLs alongside existing counterparty URLs:
```python
# Party URLs (new naming)
path('party/', views.party_list, name='party_list'),
path('party/create/', views.party_create, name='party_create'),
path('party/<str:short_name>/', views.party_detail, name='party_detail'),
path('party/<str:short_name>/edit/', views.party_edit, name='party_edit'),
path('party/<str:short_name>/delete/', views.party_delete, name='party_delete'),
path('party/<str:short_name>/restore/', views.party_restore, name='party_restore'),

# Party CIF URLs (AJAX API)
path('party/<str:short_name>/cif/', views.party_cif_list, name='party_cif_list'),
path('party/<str:short_name>/cif/create/', views.party_cif_create, name='party_cif_create'),
path('party/<str:short_name>/cif/<str:m_label>/update/', views.party_cif_update, name='party_cif_update'),
path('party/<str:short_name>/cif/<str:m_label>/delete/', views.party_cif_delete, name='party_cif_delete'),
```

### Step 3: Create Party Views
Create new views in `reference_data/views.py` that use the new party services.

### Step 4: Create Party Templates
Copy and rename counterparty templates:
- `counterparty_list.html` → `party_list.html`
- `counterparty_details.html` → `party_details.html`
- `counterparty_form.html` → `party_form.html`

Update references in templates:
- Replace `counterparty` with `party`
- Replace `counterparty_short_name` with `party_short_name`
- Replace `counterparty_full_name` with `party_full_name`
- Update URLs from `counterparty_*` to `party_*`

### Step 5: Update Portfolio References
In portfolio module, update references:
- `counterparty` dropdown → `party` dropdown
- Update API endpoints to use party tables

### Step 6: Update Security References
In security module, update any counterparty references to party.

### Step 7: Update Trade References
In trade module:
- Update dropdown service to use party tables
- Update form to show party selection
- Update list/detail views

## Key API Endpoints (New)

| Endpoint | Purpose |
|----------|---------|
| `/reference-data/party/` | Party list view |
| `/reference-data/party/create/` | Create new party |
| `/reference-data/party/<short_name>/` | Party detail view |
| `/reference-data/party/<short_name>/edit/` | Edit party |
| `/reference-data/party/<short_name>/cif/` | Get CIFs for party (AJAX) |

## Field Additions for Party

The new `cis_party` table includes additional fields:
- `gics_code` - Global Industry Classification Standard code

## Backward Compatibility

The existing counterparty tables and code remain functional. The migration can be done gradually:
1. Create new party tables and migrate data
2. Add new party routes/views alongside existing ones
3. Update modules one at a time to use party
4. Deprecate counterparty routes when migration is complete

## Testing

After migration:
1. Verify party list loads with all migrated data
2. Create a new party and verify CIF creation
3. Edit an existing party
4. Verify party is available in portfolio, security, and trade dropdowns
5. Verify CIF data is saved correctly with auto-generated m_label
