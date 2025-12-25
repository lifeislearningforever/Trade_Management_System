# UDF (User Defined Fields) - Complete Usage Guide

## Overview
The UDF system allows you to add custom fields to entities like Portfolios, Trades, Orders, etc. All UDF data is stored in Hive tables for scalability.

## Hive Tables Structure

### 1. `cis_udf_definition` - Field Definitions
Defines the UDF fields available for each entity type.

**Columns:**
- `udf_id` - Unique ID
- `field_name` - Technical field name (e.g., `account_group`)
- `label` - Display label (e.g., `Account Group`)
- `description` - Field description
- `field_type` - Type: TEXT, NUMBER, BOOLEAN, DROPDOWN, MULTI_SELECT, DATE, CURRENCY, PERCENTAGE
- `entity_type` - Entity: PORTFOLIO, TRADE, ORDER, POSITION, etc.
- `is_required` - Whether field is mandatory
- `is_unique` - Whether value must be unique
- `max_length` - For TEXT fields
- `min_value_decimal` / `max_value_decimal` - For NUMBER fields
- `display_order` - Display order in forms
- `group_name` - Grouping for UI organization
- `is_active` - Soft delete flag

### 2. `cis_udf_value` - Field Values
Stores the actual UDF values for entities.

**Columns:**
- `entity_type` - Type of entity (PORTFOLIO, etc.)
- `entity_id` - ID of the specific entity
- `field_name` - UDF field name
- `udf_id` - Reference to definition
- `value_string` / `value_int` / `value_decimal` / `value_bool` / `value_datetime` - Type-specific values
- `is_active` - Soft delete
- `created_by` / `updated_by` - Audit fields

### 3. `cis_udf_option` - Dropdown Options
Stores dropdown/multi-select options.

**Columns:**
- `field_name` - UDF field name
- `option_value` - Internal value
- `option_label` - Display label
- `display_order` - Sort order

---

## Sample 1: Portfolio UDF Setup

### Step 1: Insert UDF Definitions

```sql
-- Account Group (Dropdown)
INSERT INTO cis.cis_udf_definition VALUES (
    1,                          -- udf_id
    'account_group',            -- field_name
    'Account Group',            -- label
    'Portfolio account classification',  -- description
    'DROPDOWN',                 -- field_type
    'PORTFOLIO',                -- entity_type
    true,                       -- is_required
    false,                      -- is_unique
    NULL,                       -- max_length
    NULL, NULL,                 -- min_value, max_value
    1,                          -- display_order
    'Portfolio Classification', -- group_name
    NULL, NULL, NULL, NULL, NULL,  -- default values
    true,                       -- is_active
    'admin', '2025-01-01 00:00:00',  -- created_by, created_at
    'admin', '2025-01-01 00:00:00'   -- updated_by, updated_at
);

-- Entity Group (Dropdown)
INSERT INTO cis.cis_udf_definition VALUES (
    2, 'entity_group', 'Entity Group',
    'Legal entity grouping', 'DROPDOWN', 'PORTFOLIO',
    true, false, NULL, NULL, NULL, 2,
    'Portfolio Classification',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);

-- Risk Rating (Number 1-10)
INSERT INTO cis.cis_udf_definition VALUES (
    3, 'risk_rating', 'Risk Rating',
    'Portfolio risk rating (1-10)', 'NUMBER', 'PORTFOLIO',
    false, false, NULL, 1, 10, 3,
    'Risk Management',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);

-- Compliance Notes (Text)
INSERT INTO cis.cis_udf_definition VALUES (
    4, 'compliance_notes', 'Compliance Notes',
    'Internal compliance notes', 'TEXT', 'PORTFOLIO',
    false, false, 500, NULL, NULL, 4,
    'Compliance',
    NULL, NULL, NULL, NULL, NULL,
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);

-- Is Restricted (Boolean)
INSERT INTO cis.cis_udf_definition VALUES (
    5, 'is_restricted', 'Restricted',
    'Is this portfolio restricted', 'BOOLEAN', 'PORTFOLIO',
    false, false, NULL, NULL, NULL, 5,
    'Compliance',
    NULL, NULL, NULL, false, NULL,
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);
```

### Step 2: Insert Dropdown Options

```sql
-- Account Group Options
INSERT INTO cis.cis_udf_option VALUES
('account_group', 'TRADING', 'Trading', 1, true, 'admin', '2025-01-01 00:00:00'),
('account_group', 'INVESTMENT', 'Investment', 2, true, 'admin', '2025-01-01 00:00:00'),
('account_group', 'HEDGING', 'Hedging', 3, true, 'admin', '2025-01-01 00:00:00'),
('account_group', 'TREASURY', 'Treasury', 4, true, 'admin', '2025-01-01 00:00:00'),
('account_group', 'OPERATIONS', 'Operations', 5, true, 'admin', '2025-01-01 00:00:00');

-- Entity Group Options
INSERT INTO cis.cis_udf_option VALUES
('entity_group', 'CORPORATE', 'Corporate', 1, true, 'admin', '2025-01-01 00:00:00'),
('entity_group', 'INSTITUTIONAL', 'Institutional', 2, true, 'admin', '2025-01-01 00:00:00'),
('entity_group', 'RETAIL', 'Retail', 3, true, 'admin', '2025-01-01 00:00:00'),
('entity_group', 'GOVERNMENT', 'Government', 4, true, 'admin', '2025-01-01 00:00:00'),
('entity_group', 'FUND', 'Fund', 5, true, 'admin', '2025-01-01 00:00:00');
```

### Step 3: Set UDF Values for Portfolio

```sql
-- Set UDF values for Portfolio ID 1
INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO',                -- entity_type
    1,                          -- entity_id
    'account_group',            -- field_name
    1,                          -- udf_id
    'TRADING',                  -- value_string
    NULL, NULL, NULL, NULL,     -- other value types
    true,                       -- is_active
    'admin', '2025-01-01 00:00:00',  -- created
    'admin', '2025-01-01 00:00:00'   -- updated
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'entity_group', 2, 'CORPORATE',
    NULL, NULL, NULL, NULL,
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'risk_rating', 3, NULL,
    8, NULL, NULL, NULL,        -- value_int = 8
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);

INSERT INTO cis.cis_udf_value VALUES (
    'PORTFOLIO', 1, 'is_restricted', 5, NULL,
    NULL, NULL, false, NULL,    -- value_bool = false
    true, 'admin', '2025-01-01 00:00:00', 'admin', '2025-01-01 00:00:00'
);
```

---

## Sample 2: Using UDF in Django

### Reading UDF Values

```python
from udf.services.udf_service import UDFService

# Get all UDF values for a portfolio
portfolio_id = 1
udf_values = UDFService.get_entity_udf_values('PORTFOLIO', portfolio_id)

# Result:
# {
#     'account_group': 'TRADING',
#     'entity_group': 'CORPORATE',
#     'risk_rating': 8,
#     'is_restricted': False,
#     'compliance_notes': None
# }

# Get specific UDF value
account_group = udf_values.get('account_group')
print(f"Account Group: {account_group}")
```

### Setting UDF Values

```python
from udf.services.udf_service import UDFService

# Set UDF values for a portfolio
portfolio_id = 2
values = {
    'account_group': 'INVESTMENT',
    'entity_group': 'INSTITUTIONAL',
    'risk_rating': 5,
    'compliance_notes': 'Requires monthly review',
    'is_restricted': True
}

UDFService.set_entity_udf_values(
    entity_type='PORTFOLIO',
    entity_id=portfolio_id,
    values=values,
    user=request.user  # For audit logging
)
```

### Validating UDF Values

```python
from udf.services.udf_service import UDFService
from django.core.exceptions import ValidationError

# Validate before saving
try:
    values = {
        'account_group': 'TRADING',
        'risk_rating': 15,  # Invalid: max is 10
    }

    UDFService.validate_udf_values('PORTFOLIO', values)
except ValidationError as e:
    print(f"Validation error: {e}")
    # ValidationError: risk_rating must be between 1 and 10
```

### Getting Dropdown Options

```python
from udf.services.udf_service import UDFService

# Get dropdown options for account_group
options = UDFService.get_account_group_options()

# Result:
# [
#     {'value': 'TRADING', 'label': 'Trading'},
#     {'value': 'INVESTMENT', 'label': 'Investment'},
#     {'value': 'HEDGING', 'label': 'Hedging'},
#     ...
# ]

# Get options for any UDF field
options = UDFService.get_udf_dropdown_options('entity_group')
```

---

## Sample 3: Using UDF in Templates

### Portfolio Detail View with UDFs

```django
{% extends 'base.html' %}

{% block content %}
<div class="card">
    <div class="card-header">
        <h3>Portfolio: {{ portfolio.name }}</h3>
    </div>

    <div class="card-body">
        <!-- Standard Portfolio Fields -->
        <div class="row">
            <div class="col-md-6">
                <p><strong>Code:</strong> {{ portfolio.code }}</p>
                <p><strong>Currency:</strong> {{ portfolio.currency }}</p>
            </div>
        </div>

        <!-- User Defined Fields -->
        <hr>
        <h4>User Defined Fields</h4>

        <div class="row">
            {% for udf_item in udf_data %}
            <div class="col-md-6 mb-3">
                <strong>{{ udf_item.udf.label }}:</strong>

                {% if udf_item.udf.field_type == 'BOOLEAN' %}
                    <span class="badge {% if udf_item.value %}badge-success{% else %}badge-secondary{% endif %}">
                        {% if udf_item.value %}Yes{% else %}No{% endif %}
                    </span>

                {% elif udf_item.udf.field_type == 'DROPDOWN' %}
                    <span class="badge badge-primary">{{ udf_item.value }}</span>

                {% elif udf_item.udf.field_type == 'NUMBER' %}
                    {{ udf_item.value|default:"-" }}

                {% else %}
                    {{ udf_item.value|default:"-" }}
                {% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
</div>
{% endblock %}
```

### UDF Edit Form

```django
<form method="post" action="{% url 'udf:entity_values' 'portfolio' portfolio.id %}">
    {% csrf_token %}

    {% for udf_item in udf_data %}
    <div class="form-group">
        <label>{{ udf_item.udf.label }}
            {% if udf_item.udf.is_required %}<span class="text-danger">*</span>{% endif %}
        </label>

        {% if udf_item.udf.field_type == 'TEXT' %}
            <textarea name="{{ udf_item.udf.field_name }}" class="form-control"
                      maxlength="{{ udf_item.udf.max_length }}">{{ udf_item.value|default:"" }}</textarea>

        {% elif udf_item.udf.field_type == 'NUMBER' %}
            <input type="number" name="{{ udf_item.udf.field_name }}" class="form-control"
                   value="{{ udf_item.value|default:"" }}"
                   min="{{ udf_item.udf.min_value_decimal }}" max="{{ udf_item.udf.max_value_decimal }}">

        {% elif udf_item.udf.field_type == 'BOOLEAN' %}
            <input type="checkbox" name="{{ udf_item.udf.field_name }}"
                   {% if udf_item.value %}checked{% endif %}>

        {% elif udf_item.udf.field_type == 'DROPDOWN' %}
            <select name="{{ udf_item.udf.field_name }}" class="form-control">
                <option value="">-- Select --</option>
                {% for option in udf_item.options %}
                <option value="{{ option.value }}"
                        {% if udf_item.value == option.value %}selected{% endif %}>
                    {{ option.label }}
                </option>
                {% endfor %}
            </select>
        {% endif %}

        <small class="form-text text-muted">{{ udf_item.udf.description }}</small>
    </div>
    {% endfor %}

    <button type="submit" class="btn btn-primary">Save UDF Values</button>
</form>
```

---

## Sample 4: AJAX Integration

### Dynamic Dropdown Loading

```javascript
// Load dropdown options dynamically
function loadUDFOptions(fieldName) {
    $.ajax({
        url: `/udf/ajax/dropdown-options/${fieldName}/`,
        method: 'GET',
        success: function(response) {
            if (response.success) {
                const select = $(`select[name="${fieldName}"]`);
                select.empty();
                select.append('<option value="">-- Select --</option>');

                response.options.forEach(function(option) {
                    select.append(
                        `<option value="${option.value}">${option.label}</option>`
                    );
                });
            }
        }
    });
}

// Load on page ready
$(document).ready(function() {
    loadUDFOptions('account_group');
    loadUDFOptions('entity_group');
});
```

---

## Sample 5: Query UDFs from Hive

### Get All Portfolios with Specific UDF Value

```sql
-- Find all portfolios with Account Group = 'TRADING'
SELECT
    p.portfolio_id,
    p.portfolio_name,
    u.value_string as account_group
FROM cis.portfolio p
LEFT JOIN cis.cis_udf_value u
    ON u.entity_type = 'PORTFOLIO'
    AND u.entity_id = p.portfolio_id
    AND u.field_name = 'account_group'
WHERE u.value_string = 'TRADING'
AND p.is_active = true;
```

### Get Portfolio with All UDFs

```sql
-- Get all UDF values for Portfolio ID 1
SELECT
    field_name,
    value_string,
    value_int,
    value_decimal,
    value_bool,
    value_datetime,
    updated_by,
    updated_at
FROM cis.cis_udf_value
WHERE entity_type = 'PORTFOLIO'
AND entity_id = 1
AND is_active = true;
```

---

## Best Practices

1. **Field Naming**: Use snake_case for field names (e.g., `account_group`, not `AccountGroup`)

2. **Validation**: Always validate UDF values before saving

3. **Type Safety**: Store values in the correct column (value_string for TEXT, value_int for NUMBER, etc.)

4. **Soft Deletes**: Use `is_active = false` instead of DELETE

5. **Audit Trail**: Always populate `created_by`, `updated_by` fields

6. **Performance**: Index frequently queried UDF fields in Hive

7. **Documentation**: Add clear descriptions to all UDF definitions

---

## URLs Available

- `/udf/` - List all UDF definitions
- `/udf/create/` - Create new UDF definition
- `/udf/<id>/` - View UDF details
- `/udf/<id>/edit/` - Edit UDF definition
- `/udf/values/<entity_type>/<entity_id>/` - Manage entity UDF values
- `/udf/ajax/dropdown-options/<field_name>/` - Get dropdown options (AJAX)
