# JIRA STORY: UDF (User-Defined Fields) System with Cascading Dropdowns

## Story Type: Feature Documentation / Epic

## Title:
UDF Management System with Cascading Dropdown Filters and Field Value Management

---

## User Story:
```
As a system administrator/business user,
I want to manage user-defined fields across different modules (Portfolio, Equity Price, Security, etc.)
So that I can dynamically configure custom data fields without code changes
```

---

## Description:

The UDF (User-Defined Fields) system allows business users to create and manage custom fields across various modules in the Trade Management System. The system uses a simplified free-text approach where administrators can define fields by selecting an **Object Type** (module), **Field Name** (technical identifier), and entering **Field Values** (display labels).

### **Key Concept:**
- **Object Type**: The module/entity where the field belongs (e.g., PORTFOLIO, EQUITY_PRICE, SECURITY)
- **Field Name**: Technical name/identifier (e.g., "market", "portfolio_type", "security_class")
- **Field Value**: User-friendly display label (e.g., "US Market", "Equity Fund", "Class A")

### **Database Structure:**
```
Table: cis_udf_field

Schema:
- object_type: PORTFOLIO, EQUITY_PRICE, SECURITY (Entity Type - stored as empty field_value)
- field_name: Technical identifier (e.g., "market", "portfolio_type")
- field_value: Display value (e.g., "US Market", "European Market")
- is_active: Soft delete flag
- Audit fields: created_by, created_at, updated_by, updated_at
```

---

## How It Works:

### **1. Dashboard View** (`/udf/`)
**Purpose:** Overview of all modules and their field statistics

**Features:**
- Card-based layout showing each module (Portfolio, Equity Price, Security, etc.)
- Each card displays:
  - User-friendly module name with color-coded icon
  - Technical object type code
  - Total fields count
  - Active fields count
  - Inactive fields count
  - "View Fields" button (navigates to filtered list)
- "Add Field Value" button (navigates to create form)

**User Journey:**
```
User → Dashboard → Clicks "View Fields" on Portfolio card
      ↓
List page opens pre-filtered with:
- Object Type = PORTFOLIO
- Status = Active
- Field Name dropdown populated with PORTFOLIO fields
```

---

### **2. List View** (`/udf/list/`)
**Purpose:** Search, filter, and manage UDF fields

**Filter System (Cascading Dropdowns):**

**Dropdown 1: Object Type**
- Options: PORTFOLIO, EQUITY_PRICE, SECURITY, TRADE, etc.
- When selected → triggers cascade

**Dropdown 2: Field Name** (Cascading)
- Dynamically populated based on selected Object Type
- Shows only field names belonging to selected Object Type
- Fetched via AJAX: `/udf/api/fields/{object_type}/`

**Dropdown 3: Status**
- Options: Active, Inactive, All
- Independent filter

**Search Button:**
- Triggers filtering based on all 3 dropdown selections
- Results update in table below

**Results Table:**
- Columns: Object Type | Field Name | Field Value | Status | Actions
- Actions: Edit (pencil icon) | Delete/Restore (trash/restore icon)

**Add Field Value Button:**
- Smart button that carries current filter context
- Example: If Object Type = PORTFOLIO and Field Name = "market" are selected
  - Button URL becomes: `/udf/create/?object_type=PORTFOLIO&field_name=market`
  - Create form pre-populates these dropdowns

---

### **3. Create Form** (`/udf/create/`)
**Purpose:** Add new field values

**Form Fields:**

**Object Type** (Dropdown 1 - Required)
- Cascading trigger
- Immutable after creation
- Pre-populated if coming from filtered list

**Field Name** (Dropdown 2 - Required, Cascading)
- Populated based on Object Type selection
- Shows existing field names for selected Object Type
- Immutable after creation
- Pre-populated if coming from filtered list

**Field Value** (Text Input - Required)
- User-friendly display label
- Free text input
- Can be updated anytime
- Example: "US Market", "European Fund", "Class A Securities"

**Validation:**
- Object Type + Field Name combination must be unique
- All fields required
- Field Name cannot be changed after creation

**User Journey Examples:**

**Scenario A: From Filtered List**
```
List: User selects Object Type = PORTFOLIO, Field Name = "market"
      ↓ Clicks "Add Field Value"
      ↓
Create Form opens with:
- Object Type = PORTFOLIO (pre-selected)
- Field Name = "market" (pre-selected)
- Field Value = [empty - user enters "Asian Market"]
      ↓
Submit → Creates new record
```

**Scenario B: Direct Access**
```
User clicks "Add Field Value" from dashboard/list without filters
      ↓
Create Form opens with:
- Object Type = [empty]
- Field Name = [empty - disabled until Object Type selected]
- Field Value = [empty]
      ↓
User selects Object Type = EQUITY_PRICE
      ↓ Triggers cascade
Field Name dropdown populates with EQUITY_PRICE field names
      ↓
User selects Field Name = "price_type"
User enters Field Value = "Closing Price"
      ↓
Submit → Creates new record
```

---

### **4. Edit Form** (`/udf/{udf_id}/edit/`)
**Purpose:** Update existing field values

**Editable Fields:**
- Field Value (can be updated)
- Active Status (toggle)

**Read-Only Fields:**
- Object Type (locked)
- Field Name (locked)

**Visual Indicators:**
- Lock icons next to immutable fields
- Audit information panel showing created/updated by and timestamps

---

### **5. Soft Delete/Restore**
**Delete:** POST `/udf/{udf_id}/delete/`
- Sets `is_active = false`
- Shows confirmation modal
- Audit log entry created

**Restore:** POST `/udf/{udf_id}/restore/`
- Sets `is_active = true`
- Shows confirmation modal
- Audit log entry created

---

## Technical Implementation:

### **Architecture (SOLID Principles):**

**Repository Layer:** `udf/repositories/udf_field_repository.py`
- Data access only
- Kudu/Impala queries
- Methods: get_all(), get_by_id(), create(), update(), soft_delete(), restore()

**Service Layer:** `udf/services/udf_field_service.py`
- Business logic
- Validation
- Audit logging integration
- Methods: create_field(), update_field(), delete_field(), restore_field()

**View Layer:** `udf/views_simplified.py`
- HTTP request/response handling
- User info extraction
- Template rendering

**Templates:**
- `templates/udf/dashboard.html` - Dashboard view
- `templates/udf/list.html` - List with filters
- `templates/udf/form.html` - Create/Edit form

---

## API Endpoints:

### **GET** `/udf/api/fields/{object_type}/`
**Purpose:** Fetch field names for cascading dropdown

**Request:**
```
GET /udf/api/fields/PORTFOLIO/
```

**Response:**
```json
{
  "success": true,
  "fields": [
    {
      "udf_id": 1704063600000,
      "object_type": "PORTFOLIO",
      "field_name": "market",
      "field_value": "US Market",
      "is_active": true
    },
    {
      "udf_id": 1704063600001,
      "object_type": "PORTFOLIO",
      "field_name": "portfolio_type",
      "field_value": "Equity Fund",
      "is_active": true
    }
  ]
}
```

---

## Acceptance Criteria:

### **Dashboard:**
- [ ] Display all module cards with icons and names
- [ ] Show accurate field counts (total, active, inactive)
- [ ] "View Fields" button navigates to filtered list
- [ ] "Add Field Value" button navigates to create form
- [ ] Module names are user-friendly (not raw codes)

### **List View:**
- [ ] Object Type dropdown shows all available modules
- [ ] Field Name dropdown cascades based on Object Type selection
- [ ] Status dropdown filters by Active/Inactive/All
- [ ] "Search" button triggers filtering
- [ ] Clear button resets all filters
- [ ] Results table updates based on filters
- [ ] "Add Field Value" button URL includes current filter context
- [ ] Coming from dashboard pre-selects filters correctly

### **Create Form:**
- [ ] Object Type dropdown populated from database
- [ ] Field Name dropdown cascades when Object Type selected
- [ ] Field Value accepts free text input
- [ ] URL parameters pre-populate dropdowns
- [ ] Validation prevents duplicate Object Type + Field Name
- [ ] Success redirects to list page
- [ ] Error messages display clearly

### **Edit Form:**
- [ ] Field Value can be updated
- [ ] Active status can be toggled
- [ ] Object Type and Field Name are locked
- [ ] Audit information displayed
- [ ] Success redirects to list page

### **Delete/Restore:**
- [ ] Confirmation modal appears before delete
- [ ] Confirmation modal appears before restore
- [ ] Soft delete sets is_active = false
- [ ] Restore sets is_active = true
- [ ] Audit logs created for both actions

### **Cascading Dropdown:**
- [ ] Field Name dropdown disabled until Object Type selected
- [ ] Loading state shows while fetching field names
- [ ] Error handling for API failures
- [ ] Pre-selected values restored on page load

---

## Data Flow Example:

### **Creating a New Field Value:**

```
Step 1: Administrator navigates to dashboard
Step 2: Clicks "View Fields" on Portfolio card
        → URL: /udf/list/?object_type=PORTFOLIO&status=active

Step 3: List page loads with:
        - Object Type dropdown = PORTFOLIO
        - Field Name dropdown = [populated with PORTFOLIO fields]
        - Status dropdown = Active
        - Results = All active PORTFOLIO field values

Step 4: Administrator selects Field Name = "market"
Step 5: Clicks "Search" button
        → Results = All active "market" field values for PORTFOLIO

Step 6: Clicks "Add Field Value" button
        → URL: /udf/create/?object_type=PORTFOLIO&field_name=market

Step 7: Create form opens with:
        - Object Type = PORTFOLIO (pre-selected, locked)
        - Field Name = "market" (pre-selected, locked)
        - Field Value = [empty]

Step 8: Administrator enters Field Value = "Latin America Market"
Step 9: Clicks "Create Field"
        → Backend validation passes
        → Creates UDF record:
           {
             udf_id: 1704063600002,
             object_type: "PORTFOLIO",
             field_name: "market",
             field_value: "Latin America Market",
             is_active: true,
             created_by: "admin_user",
             created_at: 1704063600002
           }
        → Audit log entry created
        → Redirects to /udf/list/

Step 10: List page shows new field value in table
```

---

## Benefits:

✅ **No Code Changes Required** - Business users can add custom fields
✅ **Cascading Dropdowns** - Better UX, prevents invalid selections
✅ **Pre-population Support** - Faster data entry from filtered lists
✅ **Soft Delete** - Data recovery possible
✅ **Full Audit Trail** - Track all changes
✅ **SOLID Architecture** - Maintainable, testable code
✅ **User-Friendly Dashboard** - Visual overview with icons and colors
✅ **Flexible** - Supports multiple modules/entities

---

## Technical Stack:

- **Backend:** Django (Python)
- **Database:** Cloudera Kudu (via Impala)
- **Frontend:** Bootstrap 5, Vanilla JavaScript
- **Authentication:** Session-based
- **API:** RESTful JSON endpoints
- **Icons:** Bootstrap Icons

---

## Related Documentation:
- `/udf/docs/SIMPLIFIED_UDF_REDESIGN.md` - Technical redesign documentation
- `/udf/docs/wireframes/UDF_DASHBOARD_WIREFRAME.md` - Dashboard wireframe
- `/udf/docs/wireframes/UDF_LIST_WIREFRAME.md` - List view wireframe
- `/udf/docs/wireframes/UDF_FORM_WIREFRAME.md` - Form wireframe
- `/udf/docs/wireframes/UDF_COMPLETE_FLOW.md` - Complete flow diagrams

---

## Story Points: 13
## Priority: High
## Labels: UDF, Feature, Cascading-Dropdowns, Dashboard
## Components: UDF Module, Market Data
## Sprint: Sprint 1

---

## Definition of Done:

- [ ] All acceptance criteria met
- [ ] Code reviewed and approved
- [ ] Unit tests written and passing
- [ ] Integration tests passing
- [ ] User documentation updated
- [ ] Deployed to staging environment
- [ ] UAT (User Acceptance Testing) completed
- [ ] Deployed to production
- [ ] Stakeholders notified

---

## Test Scenarios:

### **Scenario 1: Create Field Value from Dashboard**
1. Navigate to UDF Dashboard
2. Click "View Fields" on Portfolio card
3. Verify list page loads with PORTFOLIO pre-selected
4. Select Field Name = "market"
5. Click "Add Field Value"
6. Verify form pre-populates PORTFOLIO and market
7. Enter Field Value = "Test Market"
8. Click "Create Field"
9. Verify success and redirect to list
10. Verify "Test Market" appears in results

### **Scenario 2: Cascading Dropdown**
1. Navigate to Create form directly
2. Select Object Type = "EQUITY_PRICE"
3. Verify Field Name dropdown populates
4. Verify Field Name options are EQUITY_PRICE specific
5. Select Field Name and complete form
6. Verify successful creation

### **Scenario 3: Edit and Soft Delete**
1. Navigate to List page
2. Click Edit on a field value
3. Change Field Value
4. Click "Save Changes"
5. Verify update successful
6. Click Delete on the same field
7. Confirm deletion
8. Change Status filter to "Inactive"
9. Verify field appears as inactive
10. Click Restore
11. Verify field is active again

---

## Known Limitations:

- Field Name and Object Type cannot be changed after creation
- No validation on Field Value format (free text)
- Single-level cascading only (Object Type → Field Name)
- No bulk operations (delete/restore multiple at once)

---

## Future Enhancements:

1. **Bulk Operations:** Select multiple fields for delete/restore
2. **Export/Import:** Export UDF definitions as JSON/CSV
3. **Field Groups:** Group related fields together
4. **Display Order:** Control the order fields appear in forms
5. **Field Help Text:** Add help text/tooltip for each field
6. **Validation Rules:** Optional regex validation per field
7. **Default Values:** Specify default values for fields
8. **Field Dependencies:** Make fields dependent on other field values

---

**Created By:** Development Team
**Last Updated:** 2025-01-07
**Version:** 1.0
