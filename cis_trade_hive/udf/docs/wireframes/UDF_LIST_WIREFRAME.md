# UDF List View Wireframe

## Page: `/udf/list/`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          UDF Fields                                          │
│  Manage user-defined fields                                                 │
│                                            [Add Field Value] [Dashboard]     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  FILTERS                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐  ┌─────────┐ │
│  │ Object Type    ▼ │  │ Field Name     ▼ │  │ Status     ▼ │  │[Search] │ │
│  │                  │  │                  │  │              │  │ [Clear] │ │
│  │ [PORTFOLIO    ]  │  │ [market       ]  │  │ [Active   ]  │  │         │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘  └─────────┘ │
│                                                                              │
│  Dropdown 1          → Dropdown 2 (Cascading)  Dropdown 3                   │
│  Object Type           Field Name              Status                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│  [5] fields found                                                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ Object Type │ Field Name     │ Field Value           │ Status  │ Actions    │
├─────────────┼────────────────┼───────────────────────┼─────────┼────────────┤
│ PORTFOLIO   │ market         │ US Market             │ Active  │ [✏️] [🗑️]  │
│ PORTFOLIO   │ market         │ European Market       │ Active  │ [✏️] [🗑️]  │
│ PORTFOLIO   │ market         │ Asian Market          │ Active  │ [✏️] [🗑️]  │
│ PORTFOLIO   │ market         │ Latin America Market  │ Active  │ [✏️] [🗑️]  │
│ PORTFOLIO   │ market         │ Africa Market         │ Inactive│ [✏️] [🔄]  │
└─────────────┴────────────────┴───────────────────────┴─────────┴────────────┘

Icons:
✏️  = Edit
🗑️  = Delete
🔄 = Restore
```

---

## Filter Behavior:

### **Dropdown 1: Object Type**
```
[All Object Types    ▼]
├── PORTFOLIO
├── EQUITY_PRICE
├── SECURITY
├── TRADE
├── MARKETDATA
├── REFERENCE
├── COMMENTS
└── POSITION
```

**When selected:**
- Triggers cascade to Dropdown 2
- AJAX call: `GET /udf/api/fields/{object_type}/`
- Populates Field Name dropdown with field names for selected object type

---

### **Dropdown 2: Field Name** (Cascading)
```
Initial State (no Object Type selected):
[All Field Names     ▼]  (disabled)

After Object Type = PORTFOLIO selected:
[All Field Names     ▼]
├── market
├── portfolio_type
├── fund_manager
├── account_group
└── region

Loading State:
[Loading...          ▼]  (disabled)
```

**Behavior:**
- Disabled until Object Type is selected
- Shows "Loading..." while fetching data
- Populates with unique field names for selected Object Type
- Allows "All Field Names" to show all fields for that Object Type

---

### **Dropdown 3: Status**
```
[Active              ▼]
├── Active
├── Inactive
└── All
```

**Independent filter** - does not cascade

---

## Cascading Flow Diagram:

```
User selects Object Type = "PORTFOLIO"
    ↓
JavaScript: objectTypeSelect.addEventListener('change')
    ↓
loadFieldNamesByObjectType('PORTFOLIO')
    ↓
AJAX: GET /udf/api/fields/PORTFOLIO/
    ↓
Response: {
  "success": true,
  "fields": [
    {"field_name": "market", "field_value": "US Market", ...},
    {"field_name": "portfolio_type", "field_value": "Equity", ...},
    ...
  ]
}
    ↓
Extract unique field_name values: ["market", "portfolio_type", ...]
    ↓
Populate Field Name dropdown
    ↓
Enable Field Name dropdown
```

---

## Search Button Flow:

```
User Configuration:
- Object Type: PORTFOLIO
- Field Name: market
- Status: Active
    ↓
User clicks [Search] button
    ↓
Form submits: GET /udf/list/?object_type=PORTFOLIO&field_name=market&status=active
    ↓
Backend filters:
- WHERE object_type = 'PORTFOLIO'
- AND field_name = 'market'
- AND is_active = true
    ↓
Results table updates with filtered data
```

---

## Add Field Value Button (Smart URL):

```
Current Filter State:
- Object Type: PORTFOLIO
- Field Name: market
- Status: Active
    ↓
JavaScript updates button URL dynamically:
    ↓
Button href = "/udf/create/?object_type=PORTFOLIO&field_name=market"
    ↓
User clicks [Add Field Value]
    ↓
Create form opens with pre-populated:
- Object Type = PORTFOLIO (locked)
- Field Name = market (locked)
- Field Value = [empty - user enters]
```

---

## Coming from Dashboard:

```
Dashboard: User clicks "View Fields" on Portfolio card
    ↓
URL: /udf/list/?object_type=PORTFOLIO&status=active
    ↓
List page loads with:
- object_type_filter = "PORTFOLIO"
- status_filter = "active"
    ↓
JavaScript DOMContentLoaded event:
    ↓
Detects preSelectedObjectType = "PORTFOLIO"
    ↓
Calls loadFieldNamesByObjectType("PORTFOLIO")
    ↓
Field Name dropdown populates with PORTFOLIO fields
    ↓
Filters are pre-selected:
- Object Type dropdown = PORTFOLIO
- Status dropdown = Active
    ↓
Results show all active PORTFOLIO field values
```

---

## Table Actions:

### **Edit (✏️)**
```
User clicks Edit icon
    ↓
Navigate to: /udf/{udf_id}/edit/
    ↓
Edit form opens (see UDF_FORM_WIREFRAME.md)
```

### **Delete (🗑️)**
```
User clicks Delete icon
    ↓
Confirmation modal appears:
┌────────────────────────────────────┐
│ Confirm Delete                  [X]│
├────────────────────────────────────┤
│ Are you sure you want to delete    │
│ the UDF field "US Market"?         │
│                                    │
│ This is a soft delete - the field  │
│ will be marked as inactive and can │
│ be restored later.                 │
├────────────────────────────────────┤
│          [Cancel]  [Delete]        │
└────────────────────────────────────┘
    ↓
User clicks [Delete]
    ↓
POST /udf/{udf_id}/delete/
    ↓
Backend: Sets is_active = false
    ↓
Redirect to list page
```

### **Restore (🔄)**
```
Similar flow to Delete, but sets is_active = true
```

---

## Empty State:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│                              📭                                              │
│                                                                              │
│                   No fields found.                                           │
│                   Try adjusting your filters or                              │
│                   add a new field value.                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Responsive Layout:

### Desktop (≥1200px)
- Filters in 4 columns (Object Type | Field Name | Status | Buttons)

### Tablet (768px - 1199px)
- Filters in 2 rows
- Row 1: Object Type | Field Name
- Row 2: Status | Buttons

### Mobile (<768px)
- Filters stacked vertically
- Full width dropdowns
- Buttons full width
