# AVP Position Implementation Plan

## Document Info
| Field | Value |
|-------|-------|
| **Module** | Trade Position / AVP |
| **Created** | 2026-03-04 |
| **Based On** | SA Team Questionnaire Feedback |
| **Status** | Ready for Implementation |

---

## SA Feedback Summary

### Confirmed Requirements

| Requirement | Decision | Impact |
|-------------|----------|--------|
| Calculation Timing | **Async (Background)** | Decouple from trade save |
| Acceptable Delay | < 5 minutes | Queue-based processing |
| Position Status in UI | No (transparent) | No UI changes needed |
| Position Date | Trade Date AND Settle Date | Dual tracking |
| Future Settlement | Scheduled (wait until settle) | Background scheduler |
| Backdated Settlement | Allowed (prev month-end limit) | Recalculate chain |
| Trade Types | BUY, SELL only | Simple logic |
| Overselling | Reject | Validation required |
| Short Selling | Not allowed | Position >= 0 |
| AVP Method | Weighted Average | Standard formula |
| AVP Components | Price + Commission + Fees | All-in cost |
| AVP Precision | 8 decimals | DECIMAL(20,8) |
| Multi-Currency | Yes (floating FX) | Latest rate lookup |
| FX P&L | Combined (not separate) | Simpler calculation |
| Trade Amendments | All fields, recalculate | Full recalc trigger |
| Trade Cancellation | Full reversal | Reverse position |
| Settled Trade Cancel | Not allowed | Business rule |
| Manual Adjustments | Not allowed | Trades only |
| Position Recon | Yes (external import) | Future phase |
| History Retention | 7 years | Partitioning strategy |

---

## Implementation Phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AVP IMPLEMENTATION ROADMAP                            │
└─────────────────────────────────────────────────────────────────────────┘

  Phase 1                Phase 2               Phase 3              Phase 4
  ┌──────────┐          ┌──────────┐          ┌──────────┐         ┌──────────┐
  │  BASIC   │          │ SETTLE   │          │  ASYNC   │         │  MULTI-  │
  │   AVP    │    ──►   │  DATE    │    ──►   │ PROCESS  │   ──►   │ CURRENCY │
  │          │          │  LOGIC   │          │          │         │          │
  └──────────┘          └──────────┘          └──────────┘         └──────────┘

  - Weighted avg        - Future settle       - Queue system       - FX rate lookup
  - BUY/SELL only       - Backdated settle    - Background worker  - Local/Base amt
  - All-in cost         - Recalculation       - < 5 min SLA        - Combined P&L
  - 8 decimals          - Validation          - Error handling     - Latest rate
  - Position >= 0       - Month-end limit     - Retry logic
```

---

## Phase 1: Basic AVP Calculation (HIGH Priority)

### 1.1 Database Schema

```sql
-- Position table with AVP fields
CREATE TABLE gmp_cis.cis_trade_position (
    position_id STRING,
    portfolio_id STRING,
    security_id STRING,

    -- Position quantities
    quantity DECIMAL(20,8),

    -- AVP fields (8 decimal precision)
    avg_cost_local DECIMAL(20,8),      -- Average cost in security currency
    avg_cost_base DECIMAL(20,8),       -- Average cost in portfolio currency
    total_cost_local DECIMAL(20,8),    -- Total cost = quantity * avg_cost
    total_cost_base DECIMAL(20,8),

    -- Position dates
    position_date STRING,              -- YYYYMMDD format
    as_of_date STRING,                 -- When position was calculated

    -- Source tracking
    last_trade_id STRING,
    trade_count INT,

    -- Audit
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    created_by STRING,
    updated_by STRING,
    version INT,

    -- Partition
    processing_date STRING
)
PARTITIONED BY (processing_date)
STORED AS PARQUET;

-- Position history for audit (7 years retention)
CREATE TABLE gmp_cis.cis_trade_position_history (
    history_id STRING,
    position_id STRING,
    change_type STRING,  -- CREATE, UPDATE, DELETE

    -- Snapshot of position at this point
    quantity_before DECIMAL(20,8),
    quantity_after DECIMAL(20,8),
    avg_cost_before DECIMAL(20,8),
    avg_cost_after DECIMAL(20,8),

    -- Change details
    trade_id STRING,
    trade_type STRING,
    trade_quantity DECIMAL(20,8),
    trade_price DECIMAL(20,8),
    trade_charges DECIMAL(20,8),

    -- Audit
    changed_at TIMESTAMP,
    changed_by STRING,

    processing_date STRING
)
PARTITIONED BY (processing_date)
STORED AS PARQUET;
```

### 1.2 AVP Calculation Formula

```
Weighted Average Price (WAP) Formula:

For BUY:
  new_total_cost = old_total_cost + (buy_qty * buy_price) + charges
  new_quantity = old_quantity + buy_qty
  new_avg_cost = new_total_cost / new_quantity

For SELL:
  new_total_cost = old_total_cost - (sell_qty * old_avg_cost)
  new_quantity = old_quantity - sell_qty
  new_avg_cost = old_avg_cost  (unchanged on SELL)

Where charges = commission + sec_fee + other_charges
```

### 1.3 Service Layer

```python
# position_service.py

class PositionService:

    def calculate_position(
        self,
        portfolio_id: str,
        security_id: str,
        trade_type: str,      # BUY or SELL
        quantity: Decimal,
        price: Decimal,
        charges: Decimal,     # Total of all charges
        position_date: str,
        trade_id: str,
        updated_by: str
    ) -> Tuple[bool, str]:
        """
        Calculate position using weighted average method.

        Rules:
        - Only BUY and SELL affect position
        - Position quantity must be >= 0 (no short selling)
        - AVP precision: 8 decimal places
        - Charges included in average cost
        """

        # Get current position
        current = self.get_position(portfolio_id, security_id, position_date)

        if trade_type == 'BUY':
            return self._process_buy(current, quantity, price, charges, ...)
        elif trade_type == 'SELL':
            return self._process_sell(current, quantity, ...)
        else:
            return True, "Trade type does not affect position"

    def _process_buy(self, current, qty, price, charges, ...):
        """Process BUY trade - increase position, recalculate AVP."""

        old_qty = current.quantity if current else Decimal('0')
        old_cost = current.total_cost_local if current else Decimal('0')

        # Calculate all-in cost for this trade
        trade_cost = (qty * price) + charges

        # New position
        new_qty = old_qty + qty
        new_total_cost = old_cost + trade_cost
        new_avg_cost = (new_total_cost / new_qty).quantize(Decimal('0.00000001'))

        # Save position
        ...

    def _process_sell(self, current, qty, ...):
        """Process SELL trade - decrease position, AVP unchanged."""

        if not current or current.quantity < qty:
            return False, "Insufficient quantity for sale"

        old_qty = current.quantity
        old_avg = current.avg_cost_local

        # Reduce position at current average cost
        new_qty = old_qty - qty

        if new_qty == Decimal('0'):
            # Position fully closed
            new_total_cost = Decimal('0')
            new_avg_cost = Decimal('0')
        else:
            new_total_cost = new_qty * old_avg
            new_avg_cost = old_avg  # AVP unchanged on SELL

        # Save position
        ...
```

### 1.4 Validation Rules

```python
def validate_trade_for_position(trade, current_position):
    """
    Validation rules from SA feedback.
    """
    errors = []

    # Rule 1: Only BUY/SELL affect position
    if trade.trade_type not in ['BUY', 'SELL']:
        return True, []  # Skip position calculation

    # Rule 2: No short selling (SELL qty <= position qty)
    if trade.trade_type == 'SELL':
        available_qty = current_position.quantity if current_position else 0
        if trade.quantity > available_qty:
            errors.append(f"Insufficient quantity. Available: {available_qty}, Requested: {trade.quantity}")

    # Rule 3: Quantity must be positive
    if trade.quantity <= 0:
        errors.append("Trade quantity must be positive")

    # Rule 4: Price must be positive
    if trade.price <= 0:
        errors.append("Trade price must be positive")

    return len(errors) == 0, errors
```

---

## Phase 2: Settlement Date Logic (MEDIUM Priority)

### 2.1 Settlement Date Rules

| Scenario | Rule | Action |
|----------|------|--------|
| **Current Date Settle** | settle_date = today | Process immediately |
| **Future Settle (T+1, T+2)** | settle_date > today | Queue for settle_date |
| **Backdated Settle** | settle_date < today | Check month-end limit, recalculate chain |

### 2.2 Future Settlement Handling

```python
class SettlementScheduler:
    """
    Handle future-dated settlements.
    Position created only when settle_date arrives.
    """

    def process_trade(self, trade):
        today = datetime.now().strftime('%Y%m%d')
        settle_date = trade.settle_date

        if settle_date > today:
            # Future settlement - queue for later
            self.queue_for_settlement(trade)
            return "Trade queued for settlement on {settle_date}"
        elif settle_date == today:
            # Same-day settlement - process now
            return self.position_service.calculate_position(...)
        else:
            # Backdated - validate and recalculate
            return self.process_backdated(trade)

    def queue_for_settlement(self, trade):
        """Add to settlement queue table."""
        # Insert into cis_settlement_queue
        pass

    def run_daily_settlement(self):
        """
        Scheduled job - run daily at EOD.
        Process all trades with settle_date = today.
        """
        today = datetime.now().strftime('%Y%m%d')
        pending_trades = self.get_pending_settlements(today)

        for trade in pending_trades:
            self.position_service.calculate_position(...)
```

### 2.3 Backdated Settlement Handling

```python
def process_backdated(self, trade):
    """
    Handle backdated settlements.

    Rules:
    - Allowed up to previous month-end
    - Triggers recalculation of all positions from settle_date to today
    """
    settle_date = trade.settle_date
    prev_month_end = self.get_previous_month_end()

    # Validate: not beyond previous month-end
    if settle_date < prev_month_end:
        return False, f"Backdated settlement not allowed before {prev_month_end}"

    # Recalculate all positions from settle_date to today
    affected_dates = self.get_dates_in_range(settle_date, today)

    for date in affected_dates:
        self.recalculate_position_for_date(
            portfolio_id=trade.portfolio_id,
            security_id=trade.security_id,
            position_date=date
        )

    return True, f"Position recalculated from {settle_date} to today"
```

---

## Phase 3: Async Background Processing (MEDIUM Priority)

### 3.1 Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Trade     │────▶│   Message    │────▶│   Background    │
│   Service   │     │   Queue      │     │   Worker        │
└─────────────┘     └──────────────┘     └─────────────────┘
      │                                          │
      │ (immediate)                              │ (< 5 min)
      ▼                                          ▼
┌─────────────┐                          ┌─────────────────┐
│   Trade     │                          │   Position      │
│   Saved     │                          │   Updated       │
└─────────────┘                          └─────────────────┘
```

### 3.2 Queue Table

```sql
CREATE TABLE gmp_cis.cis_position_queue (
    queue_id STRING,
    trade_id STRING,
    portfolio_id STRING,
    security_id STRING,
    trade_type STRING,
    quantity DECIMAL(20,8),
    price DECIMAL(20,8),
    charges DECIMAL(20,8),
    settle_date STRING,

    -- Queue status
    status STRING,  -- PENDING, PROCESSING, COMPLETED, FAILED
    retry_count INT,
    error_message STRING,

    -- Timing
    queued_at TIMESTAMP,
    processed_at TIMESTAMP,

    processing_date STRING
)
PARTITIONED BY (processing_date)
STORED AS PARQUET;
```

### 3.3 Background Worker

```python
class PositionWorker:
    """
    Background worker for async position calculation.
    SLA: < 5 minutes from trade save to position update.
    """

    def __init__(self):
        self.position_service = PositionService()
        self.max_retries = 3
        self.batch_size = 100

    def run(self):
        """Main worker loop."""
        while True:
            # Get pending items
            pending = self.get_pending_items(limit=self.batch_size)

            for item in pending:
                try:
                    self.process_item(item)
                except Exception as e:
                    self.handle_failure(item, str(e))

            # Sleep if no items
            if not pending:
                time.sleep(10)  # 10 seconds

    def process_item(self, item):
        """Process single queue item."""
        self.update_status(item.queue_id, 'PROCESSING')

        success, message = self.position_service.calculate_position(
            portfolio_id=item.portfolio_id,
            security_id=item.security_id,
            trade_type=item.trade_type,
            quantity=item.quantity,
            price=item.price,
            charges=item.charges,
            position_date=item.settle_date,
            trade_id=item.trade_id,
            updated_by='system'
        )

        if success:
            self.update_status(item.queue_id, 'COMPLETED')
        else:
            raise Exception(message)

    def handle_failure(self, item, error):
        """Handle failed processing with retry."""
        if item.retry_count < self.max_retries:
            self.update_for_retry(item.queue_id, error)
        else:
            self.update_status(item.queue_id, 'FAILED', error)
```

---

## Phase 4: Multi-Currency Support (MEDIUM Priority)

### 4.1 Currency Fields

```python
# Position with multi-currency
class Position:
    # Local currency (security currency)
    quantity: Decimal
    avg_cost_local: Decimal
    total_cost_local: Decimal
    currency_local: str

    # Base currency (portfolio currency)
    avg_cost_base: Decimal
    total_cost_base: Decimal
    currency_base: str

    # FX rate used
    fx_rate: Decimal
    fx_rate_date: str
```

### 4.2 FX Rate Lookup

```python
def get_latest_fx_rate(from_currency: str, to_currency: str) -> Decimal:
    """
    Get latest FX rate for position valuation.
    Uses floating rate (not locked trade rate).
    """
    query = f"""
    SELECT rate
    FROM gmp_cis.cis_fx_rate
    WHERE from_currency = '{from_currency}'
      AND to_currency = '{to_currency}'
    ORDER BY rate_date DESC
    LIMIT 1
    """
    result = execute_query(query)
    return Decimal(str(result[0]['rate'])) if result else Decimal('1')
```

### 4.3 Position Calculation with FX

```python
def calculate_position_multicurrency(
    self,
    quantity: Decimal,
    price_local: Decimal,
    charges_local: Decimal,
    currency_local: str,
    currency_base: str
) -> dict:
    """
    Calculate position in both local and base currency.
    """
    # Local currency calculation
    total_cost_local = (quantity * price_local) + charges_local
    avg_cost_local = total_cost_local / quantity

    # Get latest FX rate
    fx_rate = self.get_latest_fx_rate(currency_local, currency_base)

    # Base currency calculation
    total_cost_base = total_cost_local * fx_rate
    avg_cost_base = avg_cost_local * fx_rate

    return {
        'avg_cost_local': avg_cost_local.quantize(Decimal('0.00000001')),
        'avg_cost_base': avg_cost_base.quantize(Decimal('0.00000001')),
        'total_cost_local': total_cost_local,
        'total_cost_base': total_cost_base,
        'fx_rate': fx_rate,
        'currency_local': currency_local,
        'currency_base': currency_base,
    }
```

---

## Trade Amendment & Cancellation

### Amendment Handling

```python
def handle_trade_amendment(self, trade_id: str, changes: dict):
    """
    Handle trade amendment - recalculate affected positions.

    All fields are amendable (per SA feedback):
    - Quantity, Price, Trade Date, Settle Date, Security, Portfolio

    Each change triggers full position recalculation.
    """
    original_trade = self.get_trade(trade_id)

    # Check if settled (not allowed to amend)
    if original_trade.status == 'SETTLED':
        return False, "Cannot amend settled trades"

    # Reverse original trade impact
    self.reverse_position_impact(original_trade)

    # Apply new trade values
    updated_trade = self.apply_changes(original_trade, changes)

    # Recalculate position with new values
    self.calculate_position(updated_trade)

    return True, "Trade amended and position recalculated"
```

### Cancellation Handling

```python
def handle_trade_cancellation(self, trade_id: str):
    """
    Handle trade cancellation - full reversal.

    Rules:
    - Settled trades cannot be cancelled
    - Full reversal of position impact
    """
    trade = self.get_trade(trade_id)

    # Check if settled
    if trade.status == 'SETTLED':
        return False, "Cannot cancel settled trades"

    # Reverse position impact
    if trade.trade_type == 'BUY':
        # Reverse BUY = reduce position
        self.process_sell(
            portfolio_id=trade.portfolio_id,
            security_id=trade.security_id,
            quantity=trade.quantity,
            ...
        )
    elif trade.trade_type == 'SELL':
        # Reverse SELL = increase position
        self.process_buy(
            portfolio_id=trade.portfolio_id,
            security_id=trade.security_id,
            quantity=trade.quantity,
            price=trade.price,
            charges=trade.charges,
            ...
        )

    return True, "Trade cancelled and position reversed"
```

---

## Implementation Checklist

### Phase 1: Basic AVP
- [ ] Create position table DDL
- [ ] Create position history table DDL
- [ ] Implement PositionService
- [ ] Implement weighted average calculation
- [ ] Implement BUY processing
- [ ] Implement SELL processing with validation
- [ ] Add 8 decimal precision handling
- [ ] Include charges in AVP calculation
- [ ] Unit tests for AVP calculation
- [ ] Integration tests

### Phase 2: Settlement Date
- [ ] Create settlement queue table
- [ ] Implement future settlement queuing
- [ ] Implement backdated validation (month-end limit)
- [ ] Implement position recalculation chain
- [ ] Create daily settlement scheduler
- [ ] Tests for settlement scenarios

### Phase 3: Async Processing
- [ ] Create position queue table
- [ ] Implement queue producer (in trade service)
- [ ] Implement background worker
- [ ] Add retry logic
- [ ] Add error handling
- [ ] Monitor SLA (< 5 min)
- [ ] Tests for async processing

### Phase 4: Multi-Currency
- [ ] Add currency fields to position
- [ ] Implement FX rate lookup
- [ ] Calculate local and base amounts
- [ ] Combined P&L calculation
- [ ] Tests for multi-currency

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-04 | Claude | Initial implementation plan based on SA feedback |
