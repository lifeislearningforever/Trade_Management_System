# Business Rules

Core business rules and validation logic in CisTrade.

## Portfolio Management Rules

### Creation Rules

**PR-001: Unique Portfolio Code**
- Rule: Portfolio code must be unique across all portfolios
- Validation: Check against existing codes before creation
- Error: "Portfolio code already exists"

**PR-002: Required Fields**
- Rule: Code, Name, Currency, Manager are mandatory
- Validation: Frontend and backend validation
- Error: "Required field missing: {field}"

**PR-003: Valid Currency**
- Rule: Currency must exist in reference data
- Validation: Lookup in gmp_cis_sta_dly_currency
- Error: "Invalid currency: {currency}"

**PR-004: Initial Status**
- Rule: New portfolios start in DRAFT status
- Automatic: System sets status on creation
- Non-negotiable: Users cannot override

### Workflow Rules

**PR-101: Four-Eyes Principle**
- Rule: Maker cannot approve own work
- Validation: Compare creator_id with approver_id
- Error: "Cannot approve your own submission"

**PR-102: Status Transitions**
- Rule: Only valid state transitions allowed
  - DRAFT → PENDING_APPROVAL
  - PENDING_APPROVAL → ACTIVE (approve)
  - PENDING_APPROVAL → REJECTED (reject)
  - REJECTED → DRAFT (edit)
  - ACTIVE → CLOSED
  - CLOSED → ACTIVE (reactivate)
- Validation: Check current status before transition
- Error: "Invalid status transition from {from} to {to}"

**PR-103: Edit Restrictions**
- Rule: Only DRAFT and REJECTED portfolios can be edited
- Validation: Check status before allowing updates
- Error: "Cannot edit portfolio in {status} status"

**PR-104: Approval Comments**
- Rule: Approval/Rejection requires comments
- Validation: Comments cannot be empty
- Error: "Comments required for approval decision"

**PR-105: Reactivation Authorization**
- Rule: Only Checkers can reactivate closed portfolios
- Validation: Check user group membership
- Error: "Insufficient permissions to reactivate"

## UDF Rules

### Definition Rules

**UD-001: Unique UDF Code**
- Rule: UDF code must be unique within entity type
- Validation: Check existing UDFs before creation
- Error: "UDF code already exists for this entity type"

**UD-002: Valid Data Type**
- Rule: Data type must be TEXT, NUMBER, DATE, or BOOLEAN
- Validation: Enum check
- Error: "Invalid data type: {type}"

### Value Rules

**UD-101: Data Type Validation**
- Rule: Value must match UDF data type
  - NUMBER: Numeric only
  - DATE: Valid date format (YYYY-MM-DD)
  - BOOLEAN: true/false only
  - TEXT: Any string (max 500 chars)
- Validation: Type-specific validators
- Error: "Value does not match data type {type}"

**UD-102: Effective Date Logic**
- Rule: New value effective date cannot overlap existing
- Validation: Check date ranges before insert
- Error: "Effective date overlaps with existing value"

**UD-103: Historical Integrity**
- Rule: Cannot modify historical values (end_date < today)
- Validation: Check end_date before update
- Error: "Cannot modify historical UDF value"

## Market Data Rules

### FX Rate Rules

**MD-001: Rate Reasonableness**
- Rule: Rate must be within ±10% of previous rate
- Validation: Compare with last known rate
- Warning: "Rate change exceeds 10%, please verify"

**MD-002: Required Fields**
- Rule: Base currency, quote currency, rate, effective date required
- Validation: NULL check
- Error: "Missing required field: {field}"

**MD-003: Rate Precision**
- Rule: Rate must have appropriate decimal places
  - Major pairs: 4 decimals (e.g., 1.3450)
  - JPY pairs: 2 decimals (e.g., 135.45)
  - Others: 6 decimals
- Validation: Decimal place check
- Error: "Invalid precision for currency pair"

**MD-004: Future Dates**
- Rule: Cannot set rates for future dates (manual entry)
- Validation: Compare effective_date with today
- Error: "Cannot set future-dated rates manually"

## Reference Data Rules

### General Rules

**RD-001: Read-Only**
- Rule: Reference data cannot be modified via CisTrade
- Validation: UI controls disabled
- Error: "Reference data is read-only"

**RD-002: Data Source**
- Rule: All reference data sourced from GMP system
- Process: Daily ETL from GMP
- Frequency: Daily updates

## Audit & Compliance Rules

### Audit Log Rules

**AL-001: All Actions Logged**
- Rule: Every significant action must be logged
- Implementation: Audit middleware
- Actions: CREATE, UPDATE, DELETE, APPROVE, REJECT, EXPORT, etc.

**AL-002: Required Audit Fields**
- Rule: All audit logs must include:
  - User ID
  - Username
  - User email
  - Action type
  - Entity type
  - Entity ID
  - Timestamp
  - IP address
- Validation: NULL check before insert
- Error: "Missing required audit field: {field}"

**AL-003: Immutable Audit Logs**
- Rule: Audit logs cannot be modified or deleted
- Implementation: No UPDATE/DELETE permissions
- Protection: Kudu table insert-only

**AL-004: Retention Period**
- Rule: Audit logs retained for 7 years
- Process: Automated archival after 2 years
- Compliance: Regulatory requirement

### Access Control Rules

**AC-001: Permission Required**
- Rule: Every action requires appropriate permission
- Validation: Check user_permissions in session
- Error: "Access denied: Missing {permission} permission"

**AC-002: Permission Levels**
- Rule: Permission levels hierarchical:
  - READ: View only
  - WRITE: Create/Update
  - READ_WRITE: Full access
- Validation: Level check before action
- Error: "Insufficient permission level"

**AC-003: Session Timeout**
- Rule: Sessions expire after 8 hours of inactivity
- Implementation: Django session middleware
- User Action: Re-login required

## Data Validation Rules

### Common Validations

**DV-001: Date Format**
- Rule: All dates in YYYY-MM-DD format
- Validation: Regex or date parser
- Error: "Invalid date format: use YYYY-MM-DD"

**DV-002: Currency Code Format**
- Rule: Currency codes must be 3 uppercase letters
- Validation: Regex `^[A-Z]{3}$`
- Error: "Invalid currency code format"

**DV-003: Email Format**
- Rule: Valid email address format
- Validation: Django EmailValidator
- Error: "Invalid email address"

**DV-004: String Length**
- Rule: Enforce maximum lengths:
  - Code: 100 chars
  - Name: 200 chars
  - Description: 500 chars
  - Comments: 1000 chars
- Validation: Length check
- Error: "Exceeds maximum length: {max}"

## Business Logic Rules

### NAV Calculation**

**BL-001: Multi-Currency NAV**
- Rule: Convert all holdings to base currency for NAV
- Formula: `NAV = Σ(holding_value × fx_rate)`
- FX Rate: Use latest available rate

**BL-002: NAV Recalculation Triggers**
- Rule: Recalculate NAV when:
  - Holding value changes
  - FX rate updates
  - Manual trigger
- Frequency: Real-time or end-of-day

### Risk Management

**RM-001: Concentration Limits**
- Rule: Single holding cannot exceed 20% of NAV
- Validation: Check after trade execution
- Warning: "Concentration limit exceeded"

**RM-002: Currency Exposure**
- Rule: Non-base currency exposure cannot exceed 30%
- Validation: Calculate total FX exposure
- Warning: "FX exposure limit exceeded"

## Exception Handling

### Override Authority

**EX-001: Business Override**
- Rule: Certain rules can be overridden by managers
- Process: Manager approval required
- Audit: Override reason logged

**EX-002: Emergency Access**
- Rule: System admin can bypass four-eyes in emergencies
- Process: Requires VP+ approval
- Audit: Flagged for review

## Compliance Rules

**CM-001: Segregation of Duties**
- Rule: Maker and Checker must be different people
- Validation: User ID comparison
- Non-negotiable: Cannot be overridden

**CM-002: Data Privacy**
- Rule: Personal data access logged and restricted
- Implementation: Role-based access control
- Compliance: PDPA requirements

**CM-003: Change Traceability**
- Rule: All changes must have audit trail
- Implementation: Portfolio history table
- Fields: What changed, old value, new value, who, when

## Related Documentation

- [Business Processes](business-processes.md)
- [Four-Eyes Workflow](../business/four-eyes-workflow.md)
- [Database Schema](../technical/database-schema.md)
