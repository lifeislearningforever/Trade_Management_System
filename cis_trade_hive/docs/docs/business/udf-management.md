# UDF Management Guide

User Defined Fields (UDFs) allow you to extend portfolio and trade data with custom attributes specific to your business needs.

## Overview

UDFs provide flexibility to:

- Add custom fields without changing database schema
- Store business-specific attributes
- Track dynamic values over time
- Support different data types (text, number, date, boolean)

## UDF Structure

### UDF Master

Defines the field metadata:

- **UDF Code**: Unique identifier (e.g., `RISK_RATING`)
- **UDF Name**: Display name (e.g., "Risk Rating")
- **Data Type**: TEXT, NUMBER, DATE, BOOLEAN
- **Description**: Purpose of the field
- **Entity Type**: PORTFOLIO or TRADE
- **Is Active**: Whether UDF is currently in use

### UDF Values

Stores actual values with history:

- **Entity Code**: Portfolio/Trade identifier
- **UDF Code**: Links to UDF Master
- **Value**: Actual value based on data type
- **Effective Date**: When value became active
- **End Date**: When value expired (NULL for current)
- **Created By**: User who set the value

## Common Use Cases

### 1. Risk Rating

Track portfolio risk levels:

```
UDF Code: RISK_RATING
Data Type: TEXT
Values: LOW, MEDIUM, HIGH
Entity Type: PORTFOLIO
```

### 2. Investment Strategy

Categorize investment approach:

```
UDF Code: STRATEGY
Data Type: TEXT
Values: GROWTH, VALUE, BALANCED, INCOME
Entity Type: PORTFOLIO
```

### 3. Compliance Flag

Mark portfolios requiring special attention:

```
UDF Code: REQUIRES_APPROVAL
Data Type: BOOLEAN
Values: true/false
Entity Type: PORTFOLIO
```

### 4. Review Date

Track when portfolio needs review:

```
UDF Code: NEXT_REVIEW_DATE
Data Type: DATE
Values: YYYY-MM-DD
Entity Type: PORTFOLIO
```

## Working with UDFs

### View UDF List

**Navigation**: UDF Management → User Defined Fields

**Features**:

- Search by code or name
- Filter by entity type (Portfolio/Trade)
- Filter by active status
- View value count for each UDF

### View UDF Details

Click on any UDF to see:

- Full definition and metadata
- Current values across all entities
- Value history timeline
- Usage statistics

### View Value History

**Navigation**: UDF Detail → Value History

Shows chronological changes:

```
2025-01-15: RISK_RATING changed from MEDIUM to HIGH (User: jsmith)
2024-12-01: RISK_RATING set to MEDIUM (User: alee)
2024-11-15: RISK_RATING created with value LOW (User: ptan)
```

### Search UDF Values

**Quick Search**: Enter entity code or value

**Advanced Filters**:

- Entity Type (Portfolio/Trade)
- Date Range (effective dates)
- Specific UDF Code
- Value pattern matching

### Export UDF Data

**CSV Export**: Download all UDF values

Format:
```csv
Entity Code,UDF Code,UDF Name,Value,Effective Date,End Date,Created By
PORT001,RISK_RATING,Risk Rating,HIGH,2025-01-15,,jsmith
PORT002,STRATEGY,Strategy,GROWTH,2025-01-10,,alee
```

## UDF Data Types

### TEXT

- Free-form text or predefined values
- Examples: Categories, descriptions, codes
- Max length: 500 characters

### NUMBER

- Numeric values (integer or decimal)
- Examples: Scores, percentages, amounts
- Precision: Up to 18 digits

### DATE

- Date values (no time component)
- Format: YYYY-MM-DD
- Examples: Review dates, deadlines

### BOOLEAN

- True/False flags
- Stored as: true/false
- Examples: Compliance flags, approvals

## Audit Trail

All UDF changes are tracked:

**Logged Actions**:

- VIEW: User accessed UDF list
- SEARCH: User searched UDFs
- EXPORT: User exported UDF data
- UPDATE: UDF value modified (tracked in value history)

**Audit Information**:

- Timestamp
- User who performed action
- What changed (old vs new values)
- IP address and user agent

## Best Practices

### Naming Conventions

✅ **Good**:
```
RISK_RATING
INVESTMENT_STRATEGY
COMPLIANCE_FLAG
REVIEW_DATE
```

❌ **Avoid**:
```
rr (too cryptic)
THE_RISK_RATING_FOR_PORTFOLIO (too long)
Risk Rating! (special characters)
```

### Data Type Selection

- Use **TEXT** for: Categories, codes, descriptions
- Use **NUMBER** for: Scores, ratings, amounts
- Use **DATE** for: Deadlines, review dates
- Use **BOOLEAN** for: Yes/No flags

### Value Management

1. **Set Effective Dates**: Always specify when value becomes active
2. **End Previous Values**: Close out old values when setting new ones
3. **Document Changes**: Add comments explaining why value changed
4. **Regular Reviews**: Periodically audit UDF values for accuracy

### Performance Tips

- Index frequently searched UDFs
- Archive historical values older than retention period
- Limit number of active UDFs (recommend < 50 per entity type)
- Use consistent value formats (e.g., always UPPERCASE for categories)

## Integration with Portfolios

UDFs enhance portfolio records:

```
Portfolio: TECH_GROWTH_FUND
  - Name: Technology Growth Fund
  - Currency: USD
  - Manager: Jane Smith

UDFs:
  - RISK_RATING: HIGH
  - STRATEGY: GROWTH
  - SECTOR_FOCUS: TECHNOLOGY
  - REVIEW_DATE: 2025-06-30
  - COMPLIANCE_FLAG: false
```

## Troubleshooting

### UDF Not Visible

**Check**:

1. Is UDF marked as Active?
2. Does user have permission to view UDFs?
3. Is entity type correct (Portfolio vs Trade)?

### Value Not Updating

**Possible Causes**:

1. Effective date in future
2. Previous value not end-dated
3. Validation error (wrong data type)
4. Permission denied

### Search Not Finding Values

**Try**:

1. Check date range filters
2. Verify exact entity code
3. Use wildcards for partial matches
4. Clear all filters and retry

## Related Documentation

- [Portfolio Management](portfolio-management.md) - How UDFs enhance portfolios
- [API Reference](../technical/api-reference.md) - UDF service methods
- [Database Schema](../technical/database-schema.md) - UDF table structure

## Need Help?

- **In-App**: Click ? icon (top right)
- **Support**: cistrade-support@yourcompany.com
