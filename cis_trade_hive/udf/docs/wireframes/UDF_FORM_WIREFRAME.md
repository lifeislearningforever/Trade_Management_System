# UDF Create/Edit Form Wireframe

## Page: `/udf/create/` or `/udf/{udf_id}/edit/`

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Create UDF Field / Edit UDF Field                         │
│  Create a new user-defined field                                            │
│                                                            [Back to List]    │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐  ┌──────────────────────────────────┐
│  FORM                                │  │  TIPS & AUDIT INFO               │
│                                      │  │                                  │
│  ┌────────────────────────────────┐ │  │  💡 Tips                         │
│  │ Object Type *                  │ │  │                                  │
│  │ [PORTFOLIO                  ▼] │ │  │  Field Name                      │
│  │                                │ │  │  • Can use uppercase, lowercase  │
│  │ 📌 Module/Object this UDF      │ │  │  • Examples: AAF, AFFIN-UOB     │
│  │    belongs to.                 │ │  │  • Cannot be changed after      │
│  │ 🔒 Cannot be changed (edit)    │ │  │    creation                      │
│  └────────────────────────────────┘ │  │                                  │
│                                      │  │  Label                           │
│  ┌────────────────────────────────┐ │  │  • User-friendly display name    │
│  │ Field Name *                   │ │  │  • Can be updated anytime        │
│  │ [market                     ▼] │ │  │                                  │
│  │                                │ │  │  Object Type                     │
│  │ 📌 Technical field name.       │ │  │  • Cannot be changed after       │
│  │    Filtered by Object Type.    │ │  │    creation                      │
│  │ 🔒 Cannot be changed (edit)    │ │  │                                  │
│  └────────────────────────────────┘ │  │  Free Text Approach              │
│      ↑ Cascades from Object Type   │  │  All UDF fields are free-text    │
│                                      │  │  inputs.                         │
│  ┌────────────────────────────────┐ │  │                                  │
│  │ Field Value (Display Label) *  │ │  ├──────────────────────────────────┤
│  │ [US Market                   ] │ │  │  ℹ️ Audit Info (Edit only)       │
│  │                                │ │  │                                  │
│  │ 📌 User-friendly display label │ │  │  Created By: admin_user          │
│  │    shown in the UI.            │ │  │  Created At: 2024-01-05 10:30    │
│  └────────────────────────────────┘ │  │  Updated By: admin_user          │
│                                      │  │  Updated At: 2024-01-05 14:20    │
│  ┌────────────────────────────────┐ │  │                                  │
│  │ ☑ Active (Edit only)           │ │  └──────────────────────────────────┘
│  │                                │ │
│  │ Inactive fields are hidden     │ │
│  │ from users and cannot be used. │ │
│  └────────────────────────────────┘ │
│                                      │
│  ───────────────────────────────────│
│                                      │
│  [Create Field]  [Cancel]            │
│   or                                 │
│  [Save Changes]  [Cancel]            │
│                                      │
└──────────────────────────────────────┘
```

---

## Create Mode vs Edit Mode

### **Create Mode** (`/udf/create/`)

**Editable Fields:**
- ✅ Object Type (dropdown)
- ✅ Field Name (dropdown - cascades from Object Type)
- ✅ Field Value (text input)

**Hidden Fields:**
- ❌ Active checkbox (defaults to true)

**Button:**
- [Create Field]

---

### **Edit Mode** (`/udf/{udf_id}/edit/`)

**Editable Fields:**
- ✅ Field Value (text input)
- ✅ Active (checkbox toggle)

**Read-Only Fields:**
- 🔒 Object Type (locked with icon)
- 🔒 Field Name (locked with icon)

**Button:**
- [Save Changes]

**Additional Panel:**
- Audit information (Created By, Created At, Updated By, Updated At)

---

## Cascading Dropdown Flow (Create Mode):

```
Page Load (Create Mode)
    ↓
Check URL parameters:
- object_type = "PORTFOLIO" (from list page)
- field_name = "market" (from list page)
    ↓
IF URL parameters exist:
    ↓
    Pre-populate Object Type = "PORTFOLIO"
    ↓
    Trigger cascade: loadFieldNamesByObjectType("PORTFOLIO")
    ↓
    AJAX: GET /udf/api/fields/PORTFOLIO/
    ↓
    Field Name dropdown populates with PORTFOLIO fields
    ↓
    Pre-select Field Name = "market"
    ↓
    Focus on Field Value input (user just needs to type)
    ↓
ELSE:
    ↓
    Object Type = empty
    Field Name = empty (disabled)
    Field Value = empty
```

---

## User Scenarios:

### **Scenario A: From Filtered List (Pre-populated)**

```
┌─────────────────────────────────────┐
│ List Page                           │
│ Filters:                            │
│ - Object Type: PORTFOLIO            │
│ - Field Name: market                │
│ - Status: Active                    │
│                                     │
│ [Add Field Value] ← User clicks     │
└─────────────────────────────────────┘
            ↓
URL: /udf/create/?object_type=PORTFOLIO&field_name=market
            ↓
┌─────────────────────────────────────┐
│ Create Form                         │
│                                     │
│ Object Type: [PORTFOLIO      ▼] 🔒 │
│ Field Name:  [market         ▼] 🔒 │
│ Field Value: [_____________]  ← 👈  │  User enters here
│                                     │
│ User types: "African Market"        │
│ [Create Field]                      │
└─────────────────────────────────────┘
            ↓
POST /udf/create/
{
  object_type: "PORTFOLIO",
  field_name: "market",
  field_value: "African Market"
}
            ↓
✅ Created → Redirect to /udf/list/
```

---

### **Scenario B: Direct Access (Blank Form)**

```
User navigates directly to /udf/create/
            ↓
┌─────────────────────────────────────┐
│ Create Form                         │
│                                     │
│ Object Type: [Select...       ▼] ← │  User selects
│ Field Name:  [Disabled        ▼]   │
│ Field Value: [_____________]        │
│                                     │
└─────────────────────────────────────┘
            ↓
User selects Object Type = "EQUITY_PRICE"
            ↓
Field Name dropdown cascades:
            ↓
AJAX: GET /udf/api/fields/EQUITY_PRICE/
            ↓
┌─────────────────────────────────────┐
│ Create Form                         │
│                                     │
│ Object Type: [EQUITY_PRICE    ▼]   │
│ Field Name:  [price_type      ▼] ← │  User selects
│ Field Value: [_____________]        │
│                                     │
└─────────────────────────────────────┘
            ↓
User selects Field Name = "price_type"
User types Field Value = "Opening Price"
            ↓
[Create Field]
            ↓
✅ Created → Redirect to /udf/list/
```

---

### **Scenario C: Edit Existing Field**

```
List Page: User clicks Edit icon (✏️)
            ↓
URL: /udf/1704063600000/edit/
            ↓
┌─────────────────────────────────────┐
│ Edit Form                           │
│                                     │
│ Object Type: PORTFOLIO         🔒   │  Locked
│ Field Name:  market            🔒   │  Locked
│ Field Value: [US Market       ]  ← │  Editable
│                                     │
│ ☑ Active                            │  Editable
│                                     │
│ ─────────────────────────────────   │
│ ℹ️ Audit Info:                      │
│ Created By: admin_user              │
│ Created At: 2024-01-05 10:30:00     │
│ Updated By: john_doe                │
│ Updated At: 2024-01-07 14:20:00     │
│                                     │
│ [Save Changes]  [Cancel]            │
└─────────────────────────────────────┘
            ↓
User changes Field Value to "United States Market"
User clicks [Save Changes]
            ↓
POST /udf/1704063600000/edit/
{
  object_type: "PORTFOLIO",  # locked
  field_name: "market",      # locked
  field_value: "United States Market",  # updated
  is_active: true
}
            ↓
✅ Updated → Redirect to /udf/list/
```

---

## Validation Rules:

### **Create Mode:**

| Field        | Validation                                           | Error Message                                    |
|--------------|------------------------------------------------------|--------------------------------------------------|
| Object Type  | Required                                             | "Object Type is required"                        |
| Field Name   | Required                                             | "Field Name is required"                         |
| Field Value  | Required                                             | "Field Value (Label) is required"                |
| Field Value  | Max 200 characters                                   | "Field Value must be 200 characters or less"     |
| Uniqueness   | (object_type + field_name) must be unique            | "Field Name 'market' already exists for entity type 'PORTFOLIO'" |

### **Edit Mode:**

| Field        | Validation                                           | Error Message                                    |
|--------------|------------------------------------------------------|--------------------------------------------------|
| Field Value  | Required                                             | "Field Value (Label) is required"                |
| Field Value  | Max 200 characters                                   | "Field Value must be 200 characters or less"     |

---

## Error Display:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ⚠️ Error: Field Name 'market' already exists for entity type 'PORTFOLIO'   │
│                                                                           [X]│
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────┐
│  FORM                                │
│  (Form fields with error styling)   │
└──────────────────────────────────────┘
```

---

## JavaScript Behavior:

### **Cascading Dropdown (Create Mode)**

```javascript
// When Object Type changes
objectTypeSelect.addEventListener('change', function() {
    const selectedObjectType = this.value;

    if (!selectedObjectType) {
        // Reset Field Name dropdown
        fieldNameSelect.innerHTML = '<option value="">-- Select Object Type First --</option>';
        fieldNameSelect.disabled = true;
        return;
    }

    // Show loading state
    fieldNameSelect.innerHTML = '<option value="">Loading fields...</option>';
    fieldNameSelect.disabled = true;

    // Fetch fields via AJAX
    fetch(`/udf/api/fields/${selectedObjectType}/`)
        .then(response => response.json())
        .then(data => {
            if (data.success && data.fields) {
                // Populate dropdown
                fieldNameSelect.innerHTML = '<option value="">-- Select Field Name --</option>';

                data.fields.forEach(field => {
                    const option = document.createElement('option');
                    option.value = field.field_name;
                    option.textContent = `${field.field_name} - ${field.field_value}`;
                    fieldNameSelect.appendChild(option);
                });

                fieldNameSelect.disabled = false;
            }
        });
});
```

### **Pre-population from URL Parameters**

```javascript
// On page load
document.addEventListener('DOMContentLoaded', function() {
    const urlParams = new URLSearchParams(window.location.search);
    const preSelectedObjectType = urlParams.get('object_type');
    const preSelectedFieldName = urlParams.get('field_name');

    if (preSelectedObjectType) {
        // Set Object Type
        objectTypeSelect.value = preSelectedObjectType;

        // Trigger cascade
        loadFieldNamesByObjectType(preSelectedObjectType, function() {
            // After fields loaded, set Field Name
            if (preSelectedFieldName) {
                fieldNameSelect.value = preSelectedFieldName;
            }

            // Focus on Field Value input
            document.getElementById('field_value').focus();
        });
    }
});
```

---

## Success Flow:

```
User submits form
    ↓
Frontend validation passes
    ↓
POST request to backend
    ↓
Backend validation (Service Layer)
    ↓
IF valid:
    ↓
    Create/Update in database (Repository Layer)
    ↓
    Audit log entry created
    ↓
    Redirect to /udf/list/
    ↓
    Success message (flash message or toast)
    ↓
ELSE:
    ↓
    Return to form with error message
    ↓
    Display error alert
    ↓
    Form fields retain user input
```

---

## Responsive Behavior:

### Desktop (≥992px)
```
┌─────────────────────┬─────────────────┐
│  Form (70%)         │  Tips (30%)     │
│                     │                 │
└─────────────────────┴─────────────────┘
```

### Tablet/Mobile (<992px)
```
┌──────────────────────────────────────┐
│  Form (100%)                         │
└──────────────────────────────────────┘
┌──────────────────────────────────────┐
│  Tips (100%)                         │
└──────────────────────────────────────┘
```
