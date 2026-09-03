# UDF System - Complete Flow Diagram

## Overview Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           UDF SYSTEM ARCHITECTURE                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌────────────────┐      ┌────────────────┐      ┌────────────────┐
│   Templates    │      │     Views      │      │    Services    │
│   (Frontend)   │◄────►│  (Controller)  │◄────►│ (Business Logic)│
└────────────────┘      └────────────────┘      └────────────────┘
                                                         │
                                                         ▼
                                                ┌────────────────┐
                                                │  Repositories  │
                                                │ (Data Access)  │
                                                └────────────────┘
                                                         │
                                                         ▼
                                                ┌────────────────┐
                                                │ Kudu Database  │
                                                │ cis_udf_field  │
                                                └────────────────┘
```

---

## Complete User Journey

### Journey 1: Dashboard → List → Create

```
START: User Dashboard
       │
       ▼
┌──────────────────────────────────────┐
│  UDF DASHBOARD (/udf/)               │
│                                      │
│  💼 Portfolio        📈 Equity Price │
│  [View Fields]      [View Fields]   │
└──────────────────────────────────────┘
       │
       │ User clicks "View Fields" on Portfolio card
       ▼
GET /udf/list/?object_type=PORTFOLIO&status=active
       │
       ▼
┌──────────────────────────────────────┐
│  UDF LIST (/udf/list/)               │
│                                      │
│  Filters (Pre-selected):             │
│  ┌─────────────────┐                 │
│  │ Object Type     │                 │
│  │ [PORTFOLIO   ▼] │ ← Pre-selected  │
│  └─────────────────┘                 │
│  ┌─────────────────┐                 │
│  │ Field Name      │                 │
│  │ [market      ▼] │ ← Populated     │
│  └─────────────────┘                 │
│  ┌─────────────────┐                 │
│  │ Status          │                 │
│  │ [Active      ▼] │ ← Pre-selected  │
│  └─────────────────┘                 │
│                                      │
│  Results:                            │
│  • US Market                         │
│  • European Market                   │
│  • Asian Market                      │
│                                      │
│  [Add Field Value]                   │
└──────────────────────────────────────┘
       │
       │ User selects Field Name = "market"
       │ User clicks "Add Field Value"
       ▼
GET /udf/create/?object_type=PORTFOLIO&field_name=market
       │
       ▼
┌──────────────────────────────────────┐
│  CREATE FORM (/udf/create/)          │
│                                      │
│  Object Type: [PORTFOLIO      ▼] 🔒 │
│  Field Name:  [market         ▼] 🔒 │
│  Field Value: [_____________]        │
│               👆 User types here     │
│                                      │
│  User enters: "African Market"       │
│                                      │
│  [Create Field]                      │
└──────────────────────────────────────┘
       │
       │ User clicks "Create Field"
       ▼
POST /udf/create/
{
  object_type: "PORTFOLIO",
  field_name: "market",
  field_value: "African Market"
}
       │
       ▼
┌──────────────────────────────────────┐
│  BACKEND PROCESSING                  │
│                                      │
│  1. views_simplified.udf_create()    │
│     - Extract form data              │
│     - Get user info                  │
│                                      │
│  2. udf_field_service.create_field() │
│     - Validate data                  │
│     - Check uniqueness               │
│     - Generate UDF ID                │
│                                      │
│  3. udf_field_repository.create()    │
│     - INSERT INTO cis_udf_field      │
│                                      │
│  4. audit_log_kudu_repository        │
│     - Log CREATE action              │
└──────────────────────────────────────┘
       │
       ▼
✅ SUCCESS
       │
       ▼
REDIRECT /udf/list/
       │
       ▼
┌──────────────────────────────────────┐
│  UDF LIST (Updated)                  │
│                                      │
│  Results now include:                │
│  • US Market                         │
│  • European Market                   │
│  • Asian Market                      │
│  • African Market  ← NEW             │
└──────────────────────────────────────┘
       │
       ▼
END
```

---

### Journey 2: Direct Create (No Pre-population)

```
START: User clicks "Add Field Value" from dashboard/list
       │
       ▼
GET /udf/create/
       │
       ▼
┌──────────────────────────────────────┐
│  CREATE FORM (Blank)                 │
│                                      │
│  Object Type: [Select...      ▼]    │
│  Field Name:  [Disabled       ▼]    │
│  Field Value: [_____________]        │
└──────────────────────────────────────┘
       │
       │ User selects Object Type = "EQUITY_PRICE"
       ▼
JavaScript: objectTypeSelect.addEventListener('change')
       │
       ▼
AJAX GET /udf/api/fields/EQUITY_PRICE/
       │
       ▼
Response: ["price_type", "market", "exchange", ...]
       │
       ▼
┌──────────────────────────────────────┐
│  CREATE FORM (Cascaded)              │
│                                      │
│  Object Type: [EQUITY_PRICE   ▼]    │
│  Field Name:  [price_type     ▼] ✅ │ ← Enabled
│  Field Value: [_____________]        │
└──────────────────────────────────────┘
       │
       │ User selects Field Name = "price_type"
       │ User enters Field Value = "Closing Price"
       ▼
POST /udf/create/
       │
       ▼
[Same backend processing as Journey 1]
       │
       ▼
✅ SUCCESS → REDIRECT /udf/list/
       │
       ▼
END
```

---

### Journey 3: Edit Existing Field

```
START: User on List Page
       │
       ▼
┌──────────────────────────────────────┐
│  UDF LIST                            │
│                                      │
│  Results:                            │
│  ┌──────────────────────────────┐   │
│  │ PORTFOLIO | market           │   │
│  │ US Market  [✏️ Edit] [🗑️ Del] │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
       │
       │ User clicks Edit icon (✏️)
       ▼
GET /udf/1704063600000/edit/
       │
       ▼
┌──────────────────────────────────────┐
│  EDIT FORM                           │
│                                      │
│  Object Type: PORTFOLIO         🔒   │
│  Field Name:  market            🔒   │
│  Field Value: [US Market       ]  ✏️ │
│               👆 Editable            │
│                                      │
│  ☑ Active                            │
│                                      │
│  ───────────────────────────────     │
│  ℹ️ Audit Info:                      │
│  Created By: admin_user              │
│  Created At: 2024-01-05 10:30        │
│  Updated By: john_doe                │
│  Updated At: 2024-01-07 14:20        │
│                                      │
│  [Save Changes]                      │
└──────────────────────────────────────┘
       │
       │ User changes "US Market" to "United States Market"
       │ User clicks "Save Changes"
       ▼
POST /udf/1704063600000/edit/
{
  object_type: "PORTFOLIO",  # locked
  field_name: "market",      # locked
  field_value: "United States Market",  # updated
  is_active: true
}
       │
       ▼
┌──────────────────────────────────────┐
│  BACKEND PROCESSING                  │
│                                      │
│  1. udf_field_service.update_field() │
│     - Validate data                  │
│     - Preserve created_by/at         │
│                                      │
│  2. udf_field_repository.update()    │
│     - UPDATE cis_udf_field           │
│     - SET field_value = '...'        │
│     - SET updated_by = '...'         │
│     - SET updated_at = NOW()         │
│                                      │
│  3. audit_log_kudu_repository        │
│     - Log UPDATE action              │
└──────────────────────────────────────┘
       │
       ▼
✅ SUCCESS → REDIRECT /udf/list/
       │
       ▼
END
```

---

### Journey 4: Delete/Restore Field

```
START: User on List Page
       │
       ▼
┌──────────────────────────────────────┐
│  UDF LIST                            │
│                                      │
│  Results (Active):                   │
│  ┌──────────────────────────────┐   │
│  │ PORTFOLIO | market           │   │
│  │ US Market  [✏️] [🗑️ Delete]   │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
       │
       │ User clicks Delete icon (🗑️)
       ▼
┌──────────────────────────────────────┐
│  CONFIRMATION MODAL                  │
│                                      │
│  Are you sure you want to delete     │
│  the UDF field "US Market"?          │
│                                      │
│  This is a soft delete - the field   │
│  will be marked as inactive.         │
│                                      │
│  [Cancel]  [Delete]                  │
└──────────────────────────────────────┘
       │
       │ User clicks "Delete"
       ▼
POST /udf/1704063600000/delete/
       │
       ▼
Backend: Sets is_active = false
         Creates audit log entry
       │
       ▼
✅ SUCCESS → REDIRECT /udf/list/
       │
       ▼
┌──────────────────────────────────────┐
│  UDF LIST (Updated)                  │
│                                      │
│  Filter: Status = [All ▼]            │
│                                      │
│  Results:                            │
│  ┌──────────────────────────────┐   │
│  │ PORTFOLIO | market           │   │
│  │ US Market  Inactive [🔄]     │   │
│  │            👆 Can restore    │   │
│  └──────────────────────────────┘   │
└──────────────────────────────────────┘
       │
       │ User changes Status filter to "Inactive"
       │ User clicks Restore icon (🔄)
       ▼
POST /udf/1704063600000/restore/
       │
       ▼
Backend: Sets is_active = true
         Creates audit log entry
       │
       ▼
✅ SUCCESS → Field is active again
       │
       ▼
END
```

---

## Data Flow: Cascading Dropdown

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CASCADING DROPDOWN DATA FLOW                          │
└─────────────────────────────────────────────────────────────────────────────┘

Step 1: User selects Object Type = "PORTFOLIO"
        │
        ▼
┌────────────────────┐
│  Frontend (JS)     │
│  Event: onChange   │
└────────────────────┘
        │
        ▼
Step 2: AJAX Request
        │
        ▼
GET /udf/api/fields/PORTFOLIO/
        │
        ▼
┌────────────────────┐
│  Backend View      │
│  api_get_fields_   │
│  by_entity()       │
└────────────────────┘
        │
        ▼
┌────────────────────┐
│  Service Layer     │
│  get_fields_by_    │
│  entity()          │
└────────────────────┘
        │
        ▼
┌────────────────────┐
│  Repository Layer  │
│  get_fields_by_    │
│  entity()          │
└────────────────────┘
        │
        ▼
SQL Query:
SELECT DISTINCT
    udf_id,
    object_type,
    field_name,
    field_value,
    is_active
FROM cis_udf_field
WHERE object_type = 'PORTFOLIO'
  AND field_value IS NOT NULL
  AND field_value != ''
  AND is_active = true
ORDER BY field_name
        │
        ▼
Results:
[
  {udf_id: 1, object_type: "PORTFOLIO", field_name: "market", field_value: "US Market"},
  {udf_id: 2, object_type: "PORTFOLIO", field_name: "market", field_value: "EU Market"},
  {udf_id: 5, object_type: "PORTFOLIO", field_name: "portfolio_type", field_value: "Equity"},
  ...
]
        │
        ▼
Step 3: Response
        │
        ▼
JSON:
{
  "success": true,
  "fields": [
    {"field_name": "market", "field_value": "US Market", ...},
    {"field_name": "market", "field_value": "EU Market", ...},
    {"field_name": "portfolio_type", "field_value": "Equity", ...}
  ]
}
        │
        ▼
Step 4: Frontend processes response
        │
        ▼
Extract unique field_name values:
["market", "portfolio_type", "fund_manager", ...]
        │
        ▼
Step 5: Populate Field Name dropdown
        │
        ▼
<select id="field_name">
  <option value="">All Field Names</option>
  <option value="market">market</option>
  <option value="portfolio_type">portfolio_type</option>
  <option value="fund_manager">fund_manager</option>
</select>
        │
        ▼
Step 6: Enable Field Name dropdown
        │
        ▼
END
```

---

## Database Schema & Relationships

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      cis_udf_field (Kudu Table)                              │
├─────────────────────┬───────────────┬──────────────────────────────────────┤
│ Column              │ Type          │ Description                          │
├─────────────────────┼───────────────┼──────────────────────────────────────┤
│ udf_id              │ BIGINT (PK)   │ Unique ID (Unix timestamp in ms)    │
│ object_type         │ STRING        │ Module/Entity (PORTFOLIO, etc.)      │
│ field_name          │ STRING        │ Technical identifier (market, etc.)  │
│ field_value         │ STRING        │ Display label (US Market, etc.)      │
│ is_active           │ BOOLEAN       │ Soft delete flag                     │
│ created_by          │ STRING        │ Username who created                 │
│ created_at          │ BIGINT        │ Creation timestamp (Unix ms)         │
│ updated_by          │ STRING        │ Username who last updated            │
│ updated_at          │ BIGINT        │ Last update timestamp (Unix ms)      │
└─────────────────────┴───────────────┴──────────────────────────────────────┘

Sample Data:
┌────────────────┬─────────────┬──────────────┬─────────────────┬───────────┐
│ udf_id         │ object_type │ field_name   │ field_value     │ is_active │
├────────────────┼─────────────┼──────────────┼─────────────────┼───────────┤
│ 1704063600000  │ PORTFOLIO   │              │                 │ true      │ ← Entity Type Record
│ 1704063600001  │ PORTFOLIO   │ market       │ US Market       │ true      │
│ 1704063600002  │ PORTFOLIO   │ market       │ European Market │ true      │
│ 1704063600003  │ PORTFOLIO   │ market       │ Asian Market    │ true      │
│ 1704063600004  │ EQUITY_PRICE│              │                 │ true      │ ← Entity Type Record
│ 1704063600005  │ EQUITY_PRICE│ price_type   │ Opening Price   │ true      │
│ 1704063600006  │ EQUITY_PRICE│ price_type   │ Closing Price   │ true      │
└────────────────┴─────────────┴──────────────┴─────────────────┴───────────┘

Notes:
- Entity Type records have empty field_value ('')
- Field records have non-empty field_value
- Same field_name can have multiple field_value entries
- (object_type + field_name + field_value) combination should be unique
```

---

## URL Routing Map

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              URL ROUTING                                     │
└─────────────────────────────────────────────────────────────────────────────┘

Dashboard:
GET  /udf/                              → udf_dashboard()

List:
GET  /udf/list/                         → udf_list()
     ?object_type=PORTFOLIO             (Filter by object type)
     &field_name=market                 (Filter by field name)
     &status=active                     (Filter by status)

Create:
GET  /udf/create/                       → udf_create() [GET]
     ?object_type=PORTFOLIO             (Pre-populate object type)
     &field_name=market                 (Pre-populate field name)
POST /udf/create/                       → udf_create() [POST]

Edit:
GET  /udf/{udf_id}/edit/                → udf_edit() [GET]
POST /udf/{udf_id}/edit/                → udf_edit() [POST]

Delete/Restore:
POST /udf/{udf_id}/delete/              → udf_delete()
POST /udf/{udf_id}/restore/             → udf_restore()

API Endpoints:
GET  /udf/api/object-types/             → api_get_object_types()
GET  /udf/api/fields/{object_type}/     → api_get_fields_by_entity()
```

---

## Security & Audit

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SECURITY & AUDIT TRAIL                               │
└─────────────────────────────────────────────────────────────────────────────┘

Authentication:
- @require_login decorator on all views
- Session-based authentication
- User info from session:
  - user_id
  - user_login (username)
  - user_email

CSRF Protection:
- {% csrf_token %} in all POST forms
- Django CSRF middleware validates tokens

Audit Logging (gmp_cis.cis_audit_log):
┌──────────────┬──────────────┬────────────────────────────────────────────┐
│ Action       │ Object Type  │ Description                                │
├──────────────┼──────────────┼────────────────────────────────────────────┤
│ CREATE       │ UDF          │ Created UDF field 'US Market' (market)     │
│ UPDATE       │ UDF          │ Updated UDF field 'US Market' (market)     │
│ DELETE       │ UDF          │ Deleted UDF field 'US Market' (market)     │
│ RESTORE      │ UDF          │ Restored UDF field 'US Market' (market)    │
└──────────────┴──────────────┴────────────────────────────────────────────┘

Audit Entry includes:
- user_id, username, user_email
- ip_address, user_agent
- request_method, request_path
- action_type, entity_name, entity_id
- timestamp
```

---

## Error Handling Flow

```
User Action
    │
    ▼
Frontend Validation
    │
    ├─ FAIL → Show inline error message
    │          User corrects → Retry
    ▼
    PASS
    │
    ▼
Backend Receives Request
    │
    ▼
Service Layer Validation
    │
    ├─ FAIL → Return error to view
    │          │
    │          ▼
    │        View renders form with error
    │          │
    │          ▼
    │        User sees error alert
    │          User corrects → Retry
    ▼
    PASS
    │
    ▼
Repository Layer Execution
    │
    ├─ FAIL (DB Error) → Exception caught
    │                     │
    │                     ▼
    │                   Log error
    │                     │
    │                     ▼
    │                   Show generic error page
    ▼
    SUCCESS
    │
    ▼
Audit Log Created
    │
    ▼
Redirect to Success Page
```
