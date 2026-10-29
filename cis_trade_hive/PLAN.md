# Corporate Action Cash Flow Generation - Implementation Plan

## Overview

When a Corporate Action (CA) is created/validated, the system needs to automatically generate cash flow entries based on the CA type (e.g., cash dividend creates RECEIVE cash flows for portfolios holding the security).

## Current Architecture

### Existing Components
- **Corporate Action Repository**: `reference_data/repositories/corporate_action_repository.py`
- **Cash Flow Repository**: `trade/repositories/cash_flow_repository.py`
- **Cash Flow Service**: `trade/services/cash_flow_service.py`
- **Position Service**: `trade/services/position_service.py` (for getting holdings)
- **EOD Pattern**: `trade/management/commands/process_settlements.py`

### Key Tables
- `cis_corporate_actions` - CA master data
- `cis_cash_flow` - Cash flow entries
- `cis_trade_position` - Portfolio holdings/positions
- `cis_ca_cash_flow_queue` - New queue table for CA processing (to be created)

## Implementation Plan

### Phase 1: Database Schema

**1.1 Create CA Cash Flow Queue Table**

Create new DDL file: `sql/ddl/16_ca_cash_flow_queue.sql`

```sql
CREATE TABLE IF NOT EXISTS gmp_cis.cis_ca_cash_flow_queue (
    queue_id BIGINT PRIMARY KEY,
    ca_id BIGINT NOT NULL,
    ca_number STRING,
    ca_type STRING NOT NULL,
    security_name STRING NOT NULL,
    portfolio_name STRING,
    ex_date STRING,
    record_date STRING,
    payment_date STRING,
    price DECIMAL(20,8),
    currency STRING,
    status STRING DEFAULT 'PENDING',
    retry_count INT DEFAULT 0,
    error_message STRING,
    processed_at BIGINT,
    created_at BIGINT NOT NULL,
    created_by STRING,
    PRIMARY KEY (queue_id)
)
PARTITION BY HASH (queue_id) PARTITIONS 4
STORED AS KUDU;
```

**1.2 Add CA Reference to Cash Flow Table**

Add `ca_id` and `ca_number` fields to `cis_cash_flow` table for traceability.

### Phase 2: CA Cash Flow Service

**2.1 Create CA Cash Flow Service**

New file: `reference_data/services/ca_cash_flow_service.py`

**Responsibilities:**
- Queue CA for cash flow generation when validated
- Process queued CAs and generate cash flows
- Handle different CA types (DIVIDEND, INTEREST, etc.)
- Calculate amounts based on portfolio holdings

**Key Methods:**
```python
class CACashFlowService:
    def queue_ca_for_processing(ca_id, ca_data, username) -> bool
    def process_ca_cash_flows(ca_id) -> Tuple[bool, str]
    def get_affected_portfolios(security_name, ex_date) -> List[Dict]
    def calculate_dividend_amount(quantity, price) -> Decimal
    def create_cash_flow_from_ca(ca_data, portfolio, quantity) -> Tuple[bool, int]
```

**Processing Logic for DIVIDEND:**
1. Get all portfolios with positions in the security as of ex_date
2. For each portfolio:
   - Get quantity held (from `cis_trade_position`)
   - Calculate dividend: `quantity × dividend_price`
   - Create cash flow with type='DIVIDEND', send_receive='RECEIVE'
   - Link to CA via `ca_id` and `ca_number`

### Phase 3: CA Queue Repository

**3.1 Create CA Cash Flow Queue Repository**

New file: `reference_data/repositories/ca_cash_flow_queue_repository.py`

**Methods:**
```python
class CACashFlowQueueRepository:
    def insert(queue_data) -> Tuple[bool, int]
    def get_pending(limit=100) -> List[Dict]
    def update_status(queue_id, status, error_message=None) -> bool
    def mark_completed(queue_id) -> bool
    def mark_failed(queue_id, error_message) -> bool
    def get_by_ca_id(ca_id) -> List[Dict]
```

### Phase 4: Integration with CA Validation

**4.1 Update Corporate Action Service**

Modify: `reference_data/services/corporate_action_service.py`

When CA status changes to VALIDATED:
- Call `ca_cash_flow_service.queue_ca_for_processing()`
- Queue entry created with status='PENDING'

```python
def validate(ca_id, validator_username, comments=None):
    # ... existing validation logic ...

    if success and ca_type in ['DIVIDEND', 'INTEREST', 'COUPON']:
        ca_cash_flow_service.queue_ca_for_processing(ca_id, ca_data, validator_username)

    return success, error_msg
```

### Phase 5: EOD Management Command

**5.1 Create EOD Processing Command**

New file: `reference_data/management/commands/process_corporate_actions.py`

**Usage:**
```bash
# Process all pending CAs
python manage.py process_corporate_actions

# Process specific date
python manage.py process_corporate_actions --date 2026-03-18

# Dry run
python manage.py process_corporate_actions --dry-run

# Specific CA
python manage.py process_corporate_actions --ca-id 123456
```

**Parameters:**
- `--date` (YYYY-MM-DD): Process CAs with payment_date = date
- `--dry-run`: Show what would be processed without changes
- `--ca-id`: Process specific CA
- `--batch-size`: Records per batch (default: 100)
- `--user`: User for audit trail (default: SYSTEM)
- `--verbose`: Detailed output

**Processing Flow:**
1. Query pending items from `cis_ca_cash_flow_queue`
2. For each CA:
   - Get portfolios holding the security
   - Calculate cash flow amounts
   - Create cash flow entries
   - Update queue status
3. Log results to `cis_audit_log`

### Phase 6: Cash Flow Repository Updates

**6.1 Update Cash Flow Repository**

Modify: `trade/repositories/cash_flow_repository.py`

Add fields to support CA linkage:
- `ca_id` - Reference to corporate action
- `ca_number` - CA number for display

Add method:
```python
def get_by_ca_id(ca_id) -> List[Dict]
```

### Phase 7: Position Query Enhancement

**7.1 Update Position Repository**

Modify: `trade/repositories/position_repository.py` (or create if needed)

Add method to get holdings as of a specific date:
```python
def get_holdings_as_of_date(security_name, as_of_date) -> List[Dict]
```

Returns: List of portfolios with their quantity held for the security.

## CA Type Processing Rules

| CA Type | Cash Flow Type | Direction | Amount Calculation |
|---------|---------------|-----------|-------------------|
| DIVIDEND | DIVIDEND | RECEIVE | quantity × price |
| INTEREST | INTEREST | RECEIVE | quantity × price |
| COUPON | COUPON | RECEIVE | quantity × price |
| STOCK_SPLIT | N/A | N/A | Position adjustment only |
| BONUS_ISSUE | N/A | N/A | Position adjustment only |
| RIGHTS_ISSUE | RIGHTS | RECEIVE | quantity × price (optional) |

## File Structure

```
reference_data/
├── management/
│   └── commands/
│       └── process_corporate_actions.py    # NEW: EOD command
├── repositories/
│   ├── corporate_action_repository.py      # Existing
│   └── ca_cash_flow_queue_repository.py    # NEW: Queue repository
├── services/
│   ├── corporate_action_service.py         # MODIFY: Add queue trigger
│   └── ca_cash_flow_service.py             # NEW: Cash flow generation
sql/
└── ddl/
    └── 16_ca_cash_flow_queue.sql           # NEW: Queue table DDL
trade/
└── repositories/
    └── cash_flow_repository.py             # MODIFY: Add CA fields
```

## Implementation Order

1. **DDL**: Create queue table schema
2. **Queue Repository**: CA cash flow queue data access
3. **CA Cash Flow Service**: Core business logic
4. **Position Query**: Get holdings as of date
5. **Cash Flow Repository**: Add CA linkage fields
6. **CA Service Integration**: Trigger on validation
7. **Management Command**: EOD processing script
8. **Testing**: Unit and integration tests

## Testing Strategy

1. **Unit Tests**: Service methods, repository methods
2. **Integration Tests**: Full flow from CA validation to cash flow creation
3. **Manual Testing**:
   - Create CA with DIVIDEND type
   - Validate CA
   - Run EOD command
   - Verify cash flows created

## Rollback Plan

- Queue table can be dropped without affecting core functionality
- CA validation continues to work without cash flow generation
- Cash flow `ca_id` field is optional (NULL allowed)
