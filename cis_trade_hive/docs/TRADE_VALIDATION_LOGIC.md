# Trade Validation Logic

## Overview

When creating or editing a trade, the system validates **Portfolio**, **Security**, and optionally **Counterparty** against master data in Kudu tables. This ensures data integrity and prevents trades against invalid or inactive entities.

## Validation Flow

```
User submits trade form
        ↓
trade_create() [views.py]
        ↓
trade_kudu_repository.validate_trade_data()
        ↓
trade_validation_repository.validate_trade_references()
        ↓
    ┌───────────────────┬────────────────────┬─────────────────────────┐
    ↓                   ↓                    ↓
validate_portfolio() validate_security() validate_counterparty()
    ↓                   ↓                    ↓
    └───────────────────┴────────────────────┴─────────────────────────┘
        ↓
    All Valid? → Yes → Insert Trade
        ↓
       No → Return Errors to User
```

## 1. Portfolio Validation

**Source File:** `trade/repositories/trade_validation_repository.py`
**Method:** `validate_portfolio()`
**Kudu Table:** `gmp_cis.cis_portfolio`

### Rules

| Check | Requirement | Error Message |
|-------|-------------|---------------|
| Required | Portfolio name cannot be empty | "Portfolio name is required" |
| Exists | Must exist in `cis_portfolio` table | "Portfolio '{name}' not found" |
| Status | Must be **SETTLED** | "Portfolio '{name}' has status '{status}'. Only SETTLED portfolios can be used for trading." |

### Valid Statuses

```python
PORTFOLIO_VALID_STATUSES = ['SETTLED']
```

### SQL Query

```sql
SELECT name, currency, manager, cash_balance, status, is_active
FROM gmp_cis.cis_portfolio
WHERE name = '{portfolio_name}'
LIMIT 1
```

### Why SETTLED Only?

Portfolios go through a maker-checker workflow:
- `DRAFT` → `PENDING_APPROVAL` → `APPROVED` → `ACTIVE` → `SETTLED`

Only **SETTLED** portfolios have completed all approvals and are ready for trading operations.

---

## 2. Security Validation

**Source File:** `trade/repositories/trade_validation_repository.py`
**Method:** `validate_security()`
**Kudu Table:** `gmp_cis.cis_security_kudu`

### Rules

| Check | Requirement | Error Message |
|-------|-------------|---------------|
| Required | Security name cannot be empty | "Security name is required" |
| Exists | Must exist in `cis_security_kudu` table | "Security '{name}' not found" |
| Status | Must be ACTIVE, APPROVED, SETTLED, or NULL | "Security '{name}' has status '{status}'. Only ACTIVE or APPROVED securities can be traded." |
| Active Flag | `is_active` must be **true** | "Security '{name}' is not active." |

### Valid Statuses

```python
SECURITY_VALID_STATUSES = ['ACTIVE', 'APPROVED', 'SETTLED', None, '']
```

> **Note:** NULL/empty status is allowed for legacy data that hasn't been migrated to the new status workflow.

### SQL Query

```sql
SELECT security_name, security_type, isin, ticker,
       currency_code, price, issuer, status, is_active
FROM gmp_cis.cis_security_kudu
WHERE security_name = '{security_name}'
LIMIT 1
```

---

## 3. Counterparty Validation

**Source File:** `trade/repositories/trade_validation_repository.py`
**Method:** `validate_counterparty()`
**Kudu Table:** `gmp_cis.cis_counterparty_kudu`

### Rules

| Check | Requirement | Error Message |
|-------|-------------|---------------|
| Optional | Counterparty is **not required** | (passes validation if empty) |
| Exists | If provided, must exist in table | "Counterparty '{name}' not found" |
| Not Deleted | `is_deleted` must be **false** or NULL | "Counterparty '{name}' has been deleted." |
| Active Flag | `is_active` must be **true** | "Counterparty '{name}' is not active." |

### SQL Query

```sql
SELECT counterparty_short_name, counterparty_full_name,
       country, is_broker, is_custodian, is_active, is_deleted
FROM gmp_cis.cis_counterparty_kudu
WHERE counterparty_short_name = '{counterparty_name}'
LIMIT 1
```

---

## 4. Trade-Type Specific Validations

**Source File:** `trade/repositories/trade_kudu_repository.py`
**Method:** `validate_trade_data()`

### Basic Required Fields

| Field | Requirement |
|-------|-------------|
| `portfolio_short_name` | Required for all trades |
| `security_label` | Required for all trades |
| `trade_type` | Required (BUY, SELL, etc.) |
| `trade_date` | Required for all trades |

### BUY Trade Validation

| Field | Requirement |
|-------|-------------|
| `quantity` | Required |
| `price` | Required |

### SELL Trade Validation

| Field | Requirement |
|-------|-------------|
| `quantity` | Required |
| `price` | Required |
| Position Check | Must have existing position with sufficient quantity |

#### Position Check Logic

```python
position = self.get_position(portfolio_short_name, security_label)

if not position:
    error = "No position found for {security} in portfolio {portfolio}"

elif position.get('quantity', 0) < requested_quantity:
    error = "Insufficient quantity. Available: {available}, Requested: {requested}"
```

---

## 5. Combined Validation Method

**Method:** `validate_trade_references()`

Validates all three entities in one call:

```python
def validate_trade_references(
    self,
    portfolio_name: str,
    security_name: str,
    counterparty_name: Optional[str] = None
) -> Tuple[bool, List[ValidationResult]]:

    results = []

    # Portfolio (required)
    results.append(self.validate_portfolio(portfolio_name))

    # Security (required)
    results.append(self.validate_security(security_name))

    # Counterparty (optional)
    if counterparty_name:
        results.append(self.validate_counterparty(counterparty_name))

    all_valid = all(r.is_valid for r in results)
    return all_valid, results
```

---

## 6. ValidationResult Data Structure

```python
@dataclass
class ValidationResult:
    is_valid: bool              # True if validation passed
    entity_type: str            # 'PORTFOLIO', 'SECURITY', 'COUNTERPARTY'
    entity_name: str            # The name being validated
    message: str                # Human-readable message
    details: Optional[Dict]     # Full entity details (for auto-populate)
```

### Example Response

```python
# Valid portfolio
ValidationResult(
    is_valid=True,
    entity_type='PORTFOLIO',
    entity_name='PORT001',
    message="Portfolio 'PORT001' is valid for trading",
    details={
        'name': 'PORT001',
        'currency': 'USD',
        'manager': 'John Doe',
        'cash_balance': 1000000.00,
        'status': 'SETTLED',
        'is_active': True
    }
)

# Invalid security
ValidationResult(
    is_valid=False,
    entity_type='SECURITY',
    entity_name='SEC999',
    message="Security 'SEC999' not found",
    details=None
)
```

---

## 7. API Endpoints for Real-Time Validation

The UI can validate entities in real-time via AJAX calls:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/trade/api/validate-portfolio/` | GET | Validate portfolio |
| `/trade/api/validate-security/` | GET | Validate security |
| `/trade/api/validate-counterparty/` | GET | Validate counterparty |

### Request Parameters

```
GET /trade/api/validate-portfolio/?name=PORT001
```

### Response Format

```json
{
    "is_valid": true,
    "message": "Portfolio 'PORT001' is valid for trading",
    "details": {
        "name": "PORT001",
        "currency": "USD",
        "manager": "John Doe",
        "status": "SETTLED"
    }
}
```

---

## 8. Dropdown Data Endpoints

Get lists of valid entities for dropdowns:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/trade/api/portfolios/` | GET | List valid portfolios |
| `/trade/api/securities/` | GET | List valid securities |
| `/trade/api/counterparties/` | GET | List valid counterparties |
| `/trade/api/portfolios-detailed/` | GET | Portfolios with full details |
| `/trade/api/securities-detailed/` | GET | Securities with full details |

### Query Parameters

| Parameter | Description |
|-----------|-------------|
| `search` | Filter by name (optional) |
| `limit` | Max results (default: 100) |

### Example

```
GET /trade/api/securities/?search=AAPL&limit=50
```

---

## 9. Error Handling Flow

```
User submits invalid trade
        ↓
validate_trade_data() returns (False, [errors])
        ↓
Views loop through errors:
    for error in errors:
        messages.error(request, error)
        ↓
Re-render form with:
    - Error messages displayed
    - Previous form data preserved
    - User can correct and resubmit
```

---

## 10. Key Files Reference

| File | Purpose |
|------|---------|
| `trade/repositories/trade_validation_repository.py` | Entity validation logic |
| `trade/repositories/trade_kudu_repository.py` | Trade data validation & CRUD |
| `trade/views.py` | HTTP handlers, calls validation |
| `trade/urls.py` | API endpoint routing |

---

## 11. Validation Summary Table

| Entity | Required | Table | Key Checks |
|--------|----------|-------|------------|
| Portfolio | Yes | `cis_portfolio` | Exists + Status = SETTLED |
| Security | Yes | `cis_security_kudu` | Exists + Status valid + is_active = true |
| Counterparty | No | `cis_counterparty_kudu` | If provided: Exists + is_active = true + not deleted |

---

## 12. Future Enhancements

Potential improvements to validation logic:

1. **Currency Match Validation** - Ensure trade currency matches portfolio/security currency
2. **Trading Hours Check** - Validate trade date against market calendar
3. **Credit Limit Check** - Validate counterparty credit limits
4. **Duplicate Trade Detection** - Warn on potential duplicate entries
5. **Regulatory Checks** - Add compliance rule validations
