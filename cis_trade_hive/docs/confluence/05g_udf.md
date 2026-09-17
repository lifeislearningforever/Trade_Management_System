# User-Defined Fields (UDF)

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~8 minutes

---

## What Are UDFs?

**User-Defined Fields (UDFs)** let the business add custom data fields to trades, portfolios, and securities — without needing a developer to change the database schema.

**Examples of UDFs in practice:**
- Add a "Strategy" dropdown to trades (Growth, Value, Momentum, etc.)
- Add a "Fund Manager Comment" text field to portfolios
- Add a "Credit Rating" field to securities
- Add a "Broker Instruction" free-text field to trades

UDFs are defined by admins/BAs and appear as additional fields in the UI forms.

---

## Field Types

| Type | What it looks like | Example |
|------|--------------------|---------|
| `TEXT` | Single-line text input | Notes, comments |
| `NUMBER` | Numeric input | Target price, risk score |
| `BOOLEAN` | Yes/No checkbox | Is ESG compliant? |
| `DROPDOWN` | Select from a list | Strategy, Region |
| `MULTI_SELECT` | Select multiple from a list | Asset classes, Themes |
| `DATE` | Date picker | Review date |
| `CURRENCY` | Decimal with currency symbol | NAV, hurdle rate |
| `PERCENTAGE` | Decimal 0–100 | Target return % |

---

## Which Entities Support UDFs?

| Entity | `entity_type` value |
|--------|-------------------|
| Trade | `TRADE` |
| Portfolio | `PORTFOLIO` |
| Security | `SECURITY` |

---

## How UDFs Work (Data Model)

```
cis_udf_definition                cis_udf_option
─────────────────────             ────────────────────
field_id (PK)                     option_id (PK)
entity_type (TRADE/PORTFOLIO/...)  field_id (FK → definition)
field_name                         option_value
field_type (TEXT/DROPDOWN/...)     display_label
is_required                        sort_order
display_order
group_name

cis_udf_value                     cis_udf_value_multi
─────────────────────             ────────────────────
value_id (PK)                     value_id (PK)
entity_type                        entity_type
entity_id (trade_id/portfolio name) entity_id
field_name                         field_name
value_string                       selected_option
```

- Single-value fields (TEXT, NUMBER, DROPDOWN, DATE, etc.) → stored in `cis_udf_value`
- Multi-select fields → stored in `cis_udf_value_multi` (one row per selected option)

---

## Adding a New UDF (Admin Steps)

1. Go to **UDF → Field Definitions**
2. Click **New Field Definition**
3. Choose:
   - **Entity type** (Trade / Portfolio / Security)
   - **Field name** (internal code, no spaces)
   - **Display label** (what user sees)
   - **Field type** (TEXT, DROPDOWN, etc.)
   - **Required?** (yes/no)
   - **Display order** (position in the form)
   - **Group name** (optional — groups related fields on the form)
4. If DROPDOWN or MULTI_SELECT — add options under the field
5. Save — the field appears immediately in the relevant form

---

## Validation Rules on UDFs

| Rule | Description |
|------|-------------|
| Required | Field must be filled in before saving |
| Unique | Value must be unique across all records of that entity type |
| Min value | Minimum number or date |
| Max value | Maximum number or date |
| Min length | Minimum text length |
| Max length | Maximum text length |
| Default value | Pre-filled default if user leaves blank |

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `udf/services/udf_service.py` | UDF value read/write, dropdown routing |
| `udf/services/udf_field_service.py` | Field definition management |
| `udf/repositories/udf_hive_repository.py` | SQL on all UDF tables |
| `udf/views.py` | UDF management views |
| `sql/ddl/04_udf_tables.sql` | Core UDF DDL |
| `sql/ddl/51_security_udf_fields.sql` | Seed UDF fields for securities |
| `sql/ddl/cis_udf_field.sql` | Extended field metadata DDL |

### Reading UDF Values for a Trade
```python
# udf/repositories/udf_hive_repository.py
query = """
    SELECT field_name, value_string
    FROM gmp_cis.cis_udf_value
    WHERE entity_type = 'TRADE'
      AND entity_id = '{trade_id}'
"""
```

### Writing a UDF Value
```python
query = """
    UPSERT INTO gmp_cis.cis_udf_value
    (value_id, entity_type, entity_id, field_name, value_string, updated_at)
    VALUES (?, 'TRADE', ?, ?, ?, ?)
"""
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| UDF field not appearing on form | Check `cis_udf_definition` — is `entity_type` correct? Is `is_active = true`? |
| Dropdown has no options | Check `cis_udf_option` for that `field_id` |
| Required UDF blocking save | User must fill in the field — it's marked `is_required = true` |
| Multi-select not saving | Check `cis_udf_value_multi` — may be a FK constraint issue |
