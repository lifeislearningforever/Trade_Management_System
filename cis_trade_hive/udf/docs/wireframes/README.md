# UDF System - Wireframes & Documentation

This folder contains comprehensive wireframes and documentation for the UDF (User-Defined Fields) system.

---

## 📁 Files in this Directory

### 1. **JIRA_STORY.md**
Complete Jira story documentation including:
- User stories and acceptance criteria
- Technical implementation details
- Test scenarios
- API documentation
- Definition of Done

### 2. **UDF_DASHBOARD_WIREFRAME.md**
Dashboard view wireframe showing:
- Module cards layout
- Statistics display
- Navigation flows
- Color-coded icons

### 3. **UDF_LIST_WIREFRAME.md**
List view wireframe detailing:
- Cascading dropdown filters
- Search functionality
- Results table
- Smart "Add Field Value" button

### 4. **UDF_FORM_WIREFRAME.md**
Create/Edit form wireframe covering:
- Form fields and validation
- Pre-population logic
- Cascading dropdown behavior
- Create vs Edit mode differences

### 5. **UDF_COMPLETE_FLOW.md**
Complete system flow diagrams including:
- User journeys (4 main scenarios)
- Data flow diagrams
- Database schema
- URL routing map
- Security & audit trail

---

## 🎯 Quick Start Guide

### For Business Users:
1. Start with **JIRA_STORY.md** to understand the feature
2. Review **UDF_COMPLETE_FLOW.md** for user journeys
3. Check individual wireframes for specific page details

### For Developers:
1. Review **JIRA_STORY.md** for technical architecture
2. Study **UDF_COMPLETE_FLOW.md** for data flow and architecture
3. Check wireframes for frontend implementation details

### For QA/Testers:
1. Review test scenarios in **JIRA_STORY.md**
2. Follow user journeys in **UDF_COMPLETE_FLOW.md**
3. Use wireframes as visual reference for expected behavior

---

## 🔄 User Journeys

The system supports 4 main user journeys:

### Journey 1: Dashboard → List → Create
```
Dashboard → View Fields → Filtered List → Add Field Value → Create Form (Pre-populated)
```
**Use Case:** Administrator wants to add a new market type for portfolios

### Journey 2: Direct Create
```
Dashboard/List → Add Field Value → Create Form (Blank) → Select Object Type → Select Field Name
```
**Use Case:** Administrator wants to add a completely new field value

### Journey 3: Edit Existing
```
List → Edit Icon → Edit Form → Update Field Value
```
**Use Case:** Administrator wants to change a field label

### Journey 4: Delete/Restore
```
List → Delete Icon → Confirmation → Soft Delete
List (Inactive Filter) → Restore Icon → Confirmation → Restore
```
**Use Case:** Administrator wants to temporarily disable a field

---

## 🏗️ System Architecture

```
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

**Key Components:**
- **Templates:** Bootstrap 5 UI with cascading dropdowns
- **Views:** Django views handling HTTP requests
- **Services:** Business logic and validation
- **Repositories:** Data access layer (Impala/Kudu)
- **Database:** Kudu table for high-performance writes

---

## 📊 Database Schema

```sql
Table: cis_udf_field

Columns:
- udf_id (BIGINT, PK)           -- Unique ID
- object_type (STRING)          -- Module (PORTFOLIO, EQUITY_PRICE, etc.)
- field_name (STRING)           -- Technical name (market, price_type, etc.)
- field_value (STRING)          -- Display label (US Market, etc.)
- is_active (BOOLEAN)           -- Soft delete flag
- created_by (STRING)           -- Creator username
- created_at (BIGINT)           -- Creation timestamp
- updated_by (STRING)           -- Last updater username
- updated_at (BIGINT)           -- Last update timestamp
```

---

## 🔑 Key Features

### 1. **Cascading Dropdowns**
- Object Type dropdown triggers Field Name dropdown
- AJAX-based field loading
- Loading states and error handling

### 2. **Smart Pre-population**
- URL parameters carry filter context
- Create form pre-fills from list filters
- Faster data entry workflow

### 3. **User-Friendly Dashboard**
- Visual cards with icons and colors
- Statistics at a glance
- Direct navigation to filtered lists

### 4. **Soft Delete/Restore**
- Data never permanently deleted
- Easy restoration
- Full audit trail

### 5. **SOLID Architecture**
- Separation of concerns
- Maintainable and testable code
- Easy to extend

---

## 📋 Pages Overview

### Dashboard (`/udf/`)
**Purpose:** Overview of all modules and statistics

**Key Elements:**
- 💼 Portfolio card
- 📈 Equity Price card
- 🛡️ Security card
- etc.

### List (`/udf/list/`)
**Purpose:** Filter and manage field values

**Key Elements:**
- 3 cascading dropdowns (Object Type → Field Name → Status)
- Search button
- Results table
- Smart "Add Field Value" button

### Create/Edit (`/udf/create/` or `/udf/{id}/edit/`)
**Purpose:** Add or modify field values

**Key Elements:**
- Cascading form fields
- Pre-population support
- Validation and error handling
- Audit info (edit mode)

---

## 🔐 Security Features

- **Authentication:** @require_login on all views
- **CSRF Protection:** Django CSRF tokens
- **Audit Logging:** All CRUD operations logged
- **Soft Delete:** No permanent data loss
- **User Tracking:** Created by, Updated by fields

---

## 📚 API Endpoints

### GET `/udf/api/fields/{object_type}/`
Fetch field names for cascading dropdown

**Example Request:**
```bash
GET /udf/api/fields/PORTFOLIO/
```

**Example Response:**
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
    }
  ]
}
```

---

## ✅ Testing Checklist

### Dashboard
- [ ] All module cards display correctly
- [ ] Statistics are accurate
- [ ] "View Fields" navigates with filters
- [ ] Icons and colors render properly

### List View
- [ ] Cascading dropdown works
- [ ] Filtering works correctly
- [ ] Search button triggers filter
- [ ] Clear button resets filters
- [ ] "Add Field Value" carries context

### Create Form
- [ ] Pre-population from URL works
- [ ] Cascading dropdown populates
- [ ] Validation prevents duplicates
- [ ] Success creates record and redirects

### Edit Form
- [ ] Field Value is editable
- [ ] Object Type/Field Name locked
- [ ] Active toggle works
- [ ] Audit info displays

### Delete/Restore
- [ ] Confirmation modals appear
- [ ] Soft delete works
- [ ] Restore works
- [ ] Audit logs created

---

## 🎨 UI/UX Highlights

### Bootstrap 5 Components Used:
- **Cards:** Module cards on dashboard
- **Tables:** Results table with hover effects
- **Forms:** Form controls with validation
- **Modals:** Confirmation dialogs
- **Badges:** Status indicators (Active/Inactive)
- **Buttons:** Action buttons with icons
- **Alerts:** Error/success messages

### Bootstrap Icons:
- 💼 bi-briefcase (Portfolio)
- 📈 bi-graph-up (Equity Price)
- 🛡️ bi-shield-lock (Security)
- ↔️ bi-arrow-left-right (Trade)
- 📊 bi-bar-chart (Market Data)
- 📖 bi-book (Reference)
- ✏️ bi-pencil (Edit)
- 🗑️ bi-trash (Delete)
- 🔄 bi-arrow-counterclockwise (Restore)

---

## 📖 Related Documentation

- `/udf/docs/SIMPLIFIED_UDF_REDESIGN.md` - Technical redesign details
- `/udf/repositories/udf_field_repository.py` - Data access layer
- `/udf/services/udf_field_service.py` - Business logic layer
- `/udf/views_simplified.py` - View controllers

---

## 🚀 Deployment Notes

### Prerequisites:
- Django application running
- Kudu database access configured
- Bootstrap 5 CSS/JS included in templates
- Bootstrap Icons CSS included

### Configuration:
- Update `config/urls.py` to include `udf.urls_simplified`
- Ensure Impala connection configured in settings
- Run DDL script to create `cis_udf_field` table

### Verification:
1. Navigate to `/udf/` - Dashboard should load
2. Click "View Fields" - List should load with filters
3. Try creating a field value
4. Verify audit logs created

---

## 👥 Stakeholders

- **Business Users:** Create and manage field values
- **Administrators:** Configure UDF fields for modules
- **Developers:** Maintain and extend the system
- **QA Team:** Test functionality and edge cases

---

## 📞 Support

For questions or issues:
1. Check this documentation first
2. Review the complete flow diagram
3. Check the technical redesign document
4. Contact the development team

---

**Version:** 1.0
**Last Updated:** 2025-01-07
**Maintained By:** Development Team
