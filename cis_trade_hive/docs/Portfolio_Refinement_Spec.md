# Portfolio UI and Workflow Refinement Specification

## Document Info
- **Version**: 1.0
- **Date**: 2026-01-21
- **Status**: Planning Phase

---

## Executive Summary

This document outlines the required changes to the Portfolio module based on user feedback. Changes are categorized into:
1. UI Refinements (List, Detail, Form screens)
2. Data Model Changes (New fields)
3. Workflow Simplification
4. Validation & Data Cleanup

---

## 1. UI Refinements

### 1.1 List View - Search & Filter Enhancements

**Current State:**
- Search by: name, description, manager
- Filter by: status, currency

**Required Changes:**
- Add filter dropdowns for:
  - Account Group
  - Portfolio Group
  - Report Group
  - Entity Group
- Enable sort functionality for all columns (click header to sort)

**Files to Modify:**
- `templates/portfolio/portfolio_list.html` - Add filter dropdowns
- `portfolio/views.py` - Add filter parameters to query
- `portfolio/repositories/portfolio_hive_repository.py` - Add filter support

**Implementation:**
```html
<!-- Add to filter section -->
<select id="accountGroupFilter" name="account_group">
    <option value="">All Account Groups</option>
    {% for group in account_groups %}
    <option value="{{ group }}">{{ group }}</option>
    {% endfor %}
</select>
<!-- Similar for portfolio_group, report_group, entity_group -->
```

---

### 1.2 List View - Column Layout Changes

**Current Column Order:**
Source, Name, Description, Currency, Manager, Client, Cash Balance, Status, Cost Centre, Corp Code, Account Group, Portfolio Group, Report Group, Entity Group, Revaluation, Created, Updated, Actions

**Required Column Order:**
| # | Column | Notes |
|---|--------|-------|
| 1 | Portfolio Name | Renamed from "Name" |
| 2 | Portfolio Description | Renamed from "Description" |
| 3 | Currency | Badge format |
| 4 | Revaluation | |
| 5 | Account Group | Sortable |
| 6 | Entity Group | Sortable |
| 7 | Report Group | Sortable |
| 8 | Portfolio Group | Sortable |
| 9 | Corp Code | |
| 10 | Cost Centre | |
| 11 | Manager | |
| 12 | Client | |
| 13 | Status | Badge format |
| 14 | Created | Date format |
| 15 | Updated | Date format |
| 16 | Actions | **STICKY column** |

**Action Column Requirements:**
- Must remain visible during horizontal scrolling
- Use CSS `position: sticky; right: 0;`
- Column header: "Actions"
- Background color to distinguish from scrolling content

**Files to Modify:**
- `templates/portfolio/portfolio_list.html`
- `static/css/cistrade.css` (add sticky column styles)

**CSS for Sticky Action Column:**
```css
/* Sticky Action Column */
.table-responsive table th:last-child,
.table-responsive table td:last-child {
    position: sticky;
    right: 0;
    background-color: var(--bg-primary);
    z-index: 1;
    box-shadow: -2px 0 5px rgba(0,0,0,0.1);
}
```

---

### 1.3 Detail Screen Updates

**Current Sections:**
1. Status Card (Source, Status, Active, Currency, Cash Balance)
2. Portfolio Information (Name, Description, Manager, Client)
3. Classification (Cost Centre, Corp Code, Account Group, etc.)
4. Workflow & Audit

**Required Changes:**

| Change | Current | New |
|--------|---------|-----|
| Cash Balance | Status Card | Portfolio Info section |
| Corp Code | Classification | Portfolio Info section |
| Cost Centre | Classification | Portfolio Info section |
| Section Name | "Classification" | "Grouping" |
| Accounting Section | N/A | NEW section |
| Revaluation | Classification | Accounting Section |
| EDIT Button | N/A | Add to top action bar |

**New Section Layout:**

```
┌─────────────────────────────────────────────────────────────┐
│ Portfolio: UOB-SG-001                          [EDIT] [Back]│
├─────────────────────────────────────────────────────────────┤
│ STATUS CARD                                                 │
│ ┌─────────────┬─────────────┬─────────────┐                │
│ │ Status      │ Active      │ Currency    │                │
│ │ VALIDATED   │ Yes         │ SGD         │                │
│ └─────────────┴─────────────┴─────────────┘                │
├─────────────────────────────────────────────────────────────┤
│ PORTFOLIO INFORMATION                                       │
│ ┌─────────────────────┬─────────────────────┐              │
│ │ Portfolio Name      │ UOB-SG-001          │              │
│ │ Description         │ Singapore Trading    │              │
│ │ Manager             │ John Doe            │              │
│ │ Client              │ UOB Private         │              │
│ │ Cash Balance        │ SGD 1,000,000.00    │ ← MOVED     │
│ │ Corp Code           │ 1234                │ ← MOVED     │
│ │ Cost Centre         │ 5678                │ ← MOVED     │
│ │ Entity              │ UOB Singapore       │ ← NEW       │
│ │ Desk Head           │ Jane Smith          │ ← NEW       │
│ │ Portfolio Owner     │ Mike Johnson        │ ← NEW       │
│ │ Closure Date        │ -                   │ ← NEW       │
│ └─────────────────────┴─────────────────────┘              │
├─────────────────────────────────────────────────────────────┤
│ ACCOUNTING SECTION                              ← NEW      │
│ ┌─────────────────────┬─────────────────────┐              │
│ │ Accounting Section  │ Treasury            │ ← NEW       │
│ │ Revaluation Status  │ Mark-to-Market      │ ← MOVED     │
│ └─────────────────────┴─────────────────────┘              │
├─────────────────────────────────────────────────────────────┤
│ GROUPING (formerly Classification)              ← RENAMED  │
│ ┌─────────────────────┬─────────────────────┐              │
│ │ Account Group       │ UOB GROUP           │              │
│ │ Portfolio Group     │ TRADING             │              │
│ │ Report Group        │ DAILY               │              │
│ │ Entity Group        │ SINGAPORE           │              │
│ └─────────────────────┴─────────────────────┘              │
├─────────────────────────────────────────────────────────────┤
│ WORKFLOW & AUDIT                                            │
│ ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

**Files to Modify:**
- `templates/portfolio/portfolio_detail.html`

---

### 1.4 Create/Edit Form Updates

**Changes Required:**
1. Rename "Classification" section to "Grouping"
2. Add new fields (Entity, Desk Head, Portfolio Owner, Closure Date, Accounting Section)
3. Move Corp Code and Cost Centre to "Portfolio Information" section
4. Add 4-digit validation for Corp Code and Cost Centre
5. Reorder fields as specified

**New Form Layout:**

```
BASIC INFORMATION
├── Portfolio Name (required)
├── Description
└── Closure Date (NEW - date picker)

FINANCIAL INFORMATION
├── Currency (required, dropdown)
├── Cash Balance
├── Corp Code (4-digit validation)
└── Cost Centre (4-digit validation)

MANAGEMENT
├── Portfolio Manager (dropdown)
├── Portfolio Owner (NEW - dropdown/text)
├── Desk Head (NEW - dropdown/text)
├── Client
└── Entity (NEW - linked to Party table)

ACCOUNTING (NEW SECTION)
├── Accounting Section (NEW - dropdown)
└── Revaluation Status (dropdown)

GROUPING (renamed from Classification)
├── Account Group (dropdown - UOB GROUP, UOB ASSOC GROUP only)
├── Portfolio Group (dropdown)
├── Report Group (dropdown)
└── Entity Group (dropdown)
```

**Files to Modify:**
- `templates/portfolio/portfolio_form.html`

---

## 2. Data Model Changes

### 2.1 New Fields to Add

| Field Name | Data Type | Required | Source/Notes |
|------------|-----------|----------|--------------|
| entity | STRING | No | Linked to Party table |
| desk_head | STRING | No | Dropdown from UDF |
| portfolio_owner | STRING | No | Dropdown from UDF |
| closure_date | STRING | No | Date format YYYY-MM-DD |
| accounting_section | STRING | No | Dropdown from UDF |

### 2.2 DDL Changes

```sql
-- Add new columns to cis_portfolio table
ALTER TABLE gmp_cis.cis_portfolio ADD COLUMNS IF NOT EXISTS (
    entity STRING,
    desk_head STRING,
    portfolio_owner STRING,
    closure_date STRING,
    accounting_section STRING
);
```

### 2.3 Repository Changes

**Files to Modify:**
- `portfolio/repositories/portfolio_hive_repository.py`
  - Add new fields to INSERT/UPDATE/SELECT queries
  - Add new fields to column list

**Code Changes:**
```python
# Add to COLUMNS list
'entity',
'desk_head',
'portfolio_owner',
'closure_date',
'accounting_section',

# Add to insert_portfolio() and update_portfolio()
entity = portfolio_data.get('entity', '').replace("'", "\\'")
desk_head = portfolio_data.get('desk_head', '').replace("'", "\\'")
portfolio_owner = portfolio_data.get('portfolio_owner', '').replace("'", "\\'")
closure_date = portfolio_data.get('closure_date', '')
accounting_section = portfolio_data.get('accounting_section', '').replace("'", "\\'")
```

### 2.4 UDF Field Additions

**New UDF Fields Required:**
| Field Name | Object Type | Sample Values |
|------------|-------------|---------------|
| Desk Head | PORTFOLIO | (user list or manual entry) |
| Portfolio Owner | PORTFOLIO | (user list or manual entry) |
| Accounting Section | PORTFOLIO | Treasury, Investments, Trading, etc. |

**Files to Modify:**
- `portfolio/services/portfolio_dropdown_service.py` - Add methods for new dropdowns

---

## 3. Workflow Simplification

### 3.1 Status Changes

**Current Workflow:**
```
INITIAL → MODIFIED → PENDING_VALIDATION → VALIDATED → SETTLED
                                       ↘ CANCELLED
```

**New Simplified Workflow:**
```
INITIAL → MODIFIED → PENDING_VALIDATION → VALIDATED
                                       ↘ CANCELLED → REACTIVATE → INITIAL
```

**Statuses to REMOVE:**
- ~~SETTLED~~ (merge into VALIDATED as final active state)
- ~~PENDING_VALIDATION~~ status stays but rename display

**Changes:**
| Current Status | New Status | Meaning |
|----------------|------------|---------|
| INITIAL | INITIAL | New portfolio, not submitted |
| MODIFIED | MODIFIED | Edited, not submitted |
| PENDING_VALIDATION | PENDING_APPROVAL | Awaiting checker |
| VALIDATED | ACTIVE | Approved and active |
| SETTLED | REMOVE | N/A |
| CANCELLED | CANCELLED | Rejected/Cancelled |

### 3.2 Remove Pending Settlement

**Files to Modify:**
- `templates/components/sidebar.html` - Remove "Pending Settlement" link
- `portfolio/urls.py` - Remove or deprecate pending_settlement URL
- `portfolio/views.py` - Remove pending_settlement view (or redirect)

### 3.3 Allow Updates During Pending Validation

**Current Behavior:** Cannot edit when status = PENDING_VALIDATION

**New Behavior:** Allow edits during PENDING_VALIDATION (Maker can modify while awaiting approval)

**Files to Modify:**
- `portfolio/repositories/portfolio_hive_repository.py`
  - Change MAKER_EDITABLE_STATUSES to include PENDING_VALIDATION

```python
# Current
MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED]

# New
MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_PENDING_VALIDATION]
```

- `portfolio/views.py` - Update portfolio_edit() validation
- `templates/portfolio/portfolio_detail.html` - Show Edit button for PENDING_VALIDATION

---

## 4. Validation & Data Cleanup

### 4.1 Remove GMP Source

**Current:** Portfolio can have src_system = 'CIS' or 'GMP'

**New:** Only src_system = 'CIS' allowed

**Changes:**
- Remove GMP badge from list view
- Remove source filter (if exists)
- Set default src_system = 'CIS' (already done)
- Hide src_system display in detail view

**Files to Modify:**
- `templates/portfolio/portfolio_list.html` - Remove Source column
- `templates/portfolio/portfolio_detail.html` - Remove Source display

### 4.2 Corp Code and Cost Centre Validation

**Requirement:** Accept only 4-digit values

**Implementation:**

**Frontend (HTML):**
```html
<input type="text"
       id="corp_code"
       name="corp_code"
       pattern="\d{4}"
       maxlength="4"
       title="Must be exactly 4 digits">
```

**Backend (Python):**
```python
def validate_portfolio_data(data):
    errors = []

    corp_code = data.get('corp_code', '')
    if corp_code and (len(corp_code) != 4 or not corp_code.isdigit()):
        errors.append("Corp Code must be exactly 4 digits")

    cost_centre = data.get('cost_centre_code', '')
    if cost_centre and (len(cost_centre) != 4 or not cost_centre.isdigit()):
        errors.append("Cost Centre must be exactly 4 digits")

    return errors
```

**Files to Modify:**
- `templates/portfolio/portfolio_form.html`
- `portfolio/views.py` - Add validation in create/edit

### 4.3 Currency Display Fix

**Issue:** Currency shows "SGD - SGD" redundantly

**Fix:** Show only currency code or name, not both

**Current:**
```html
{{ portfolio.currency }} - {{ portfolio.currency }}
```

**Fixed:**
```html
{{ portfolio.currency }}
```

**Files to Modify:**
- `templates/portfolio/portfolio_detail.html`
- `templates/portfolio/portfolio_list.html`

### 4.4 Account Group UDF Cleanup

**Requirement:** Only show these values:
- UOB GROUP
- UOB ASSOC GROUP

**Options:**
1. **Database Cleanup:** Deactivate other values in cis_udf_field
2. **Code Filter:** Filter in dropdown service

**Recommended: Code Filter (non-destructive)**
```python
# In portfolio_dropdown_service.py
def get_account_groups(self):
    all_groups = self.repository.get_account_groups()
    # Filter to only allowed values
    allowed = ['UOB GROUP', 'UOB ASSOC GROUP']
    return [g for g in all_groups if g.get('field_value') in allowed]
```

**Files to Modify:**
- `portfolio/services/portfolio_dropdown_service.py`

---

## 5. Implementation Priority

### Phase 1: Quick Wins (Low Risk)
1. Rename "Name" to "Portfolio Name"
2. Rename "Classification" to "Grouping"
3. Fix Currency display (SGD - SGD issue)
4. Remove Source column (GMP)
5. Add EDIT button to detail screen

### Phase 2: UI Layout Changes
1. Reorder columns in list view
2. Make Action column sticky
3. Move Cash Balance, Corp Code, Cost Centre to Portfolio Info
4. Add Accounting Section to detail view

### Phase 3: Data Model & Validation
1. Add new fields (entity, desk_head, portfolio_owner, closure_date, accounting_section)
2. Add 4-digit validation for Corp Code/Cost Centre
3. Filter Account Group UDF values
4. Add search/filter for all group columns

### Phase 4: Workflow Changes
1. Remove Pending Settlement tab
2. Allow edits during Pending Validation
3. Simplify status names (if approved)

---

## 6. Files Summary

| File | Changes |
|------|---------|
| `templates/portfolio/portfolio_list.html` | Column order, sticky actions, remove Source, rename headers, add filters |
| `templates/portfolio/portfolio_detail.html` | Section reorganization, add EDIT button, rename Classification |
| `templates/portfolio/portfolio_form.html` | Section reorganization, add new fields, validation |
| `templates/components/sidebar.html` | Remove Pending Settlement link |
| `portfolio/views.py` | Add filters, validation, allow PENDING_VALIDATION edits |
| `portfolio/repositories/portfolio_hive_repository.py` | Add new fields, update editable statuses |
| `portfolio/services/portfolio_dropdown_service.py` | Filter Account Groups, add new dropdown methods |
| `portfolio/urls.py` | Remove/deprecate pending_settlement |
| `static/css/cistrade.css` | Sticky column styles |
| `sql/ddl/` | ALTER TABLE for new columns |

---

## 7. Testing Checklist

- [ ] List view displays correct column order
- [ ] Action column stays visible during horizontal scroll
- [ ] All filters work (Account/Portfolio/Report/Entity Groups)
- [ ] Detail screen shows correct section layout
- [ ] EDIT button appears on detail screen (for editable statuses)
- [ ] New fields save and display correctly
- [ ] Corp Code/Cost Centre reject non-4-digit values
- [ ] Account Group dropdown shows only UOB GROUP and UOB ASSOC GROUP
- [ ] Currency displays correctly (no duplication)
- [ ] Can edit portfolio during Pending Validation status
- [ ] Pending Settlement link removed from sidebar
- [ ] No GMP source references visible

---

**Document Version**: 1.0
**Last Updated**: 2026-01-21
**Author**: CIS Development Team
