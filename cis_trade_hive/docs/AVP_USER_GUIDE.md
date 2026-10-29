# AVP Position Calculation - User Guide

## Document Info
| Field | Value |
|-------|-------|
| **Module** | Trade Position / AVP |
| **Version** | 1.0 |
| **Created** | 2026-03-04 |
| **Status** | Implemented |

---

## Overview

The AVP (Average Price Position) system calculates portfolio positions using the **Weighted Average Price** method. When you create BUY or SELL trades in CIS Trade, the system automatically calculates and updates positions.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AVP POSITION FLOW                                   │
└─────────────────────────────────────────────────────────────────────────────┘

  Trade Entry          Background Processing          Position Update
  ┌──────────┐        ┌──────────────────┐           ┌──────────────┐
  │  User    │        │   Queue System   │           │  Position    │
  │  Creates │   ──►  │   (< 5 min SLA)  │    ──►    │  Master      │
  │  Trade   │        │                  │           │  src='CIS'   │
  └──────────┘        └──────────────────┘           └──────────────┘
```

---

## Four Phases

### Phase 1: Basic AVP Calculation

**What it does:** Calculates weighted average cost when you BUY or SELL securities.

**Formula:**
```
BUY Trade:
  new_avg_cost = (old_total_cost + trade_value + charges) / new_quantity

SELL Trade:
  avg_cost = unchanged (you sell at original average cost)
  realized_pnl = (sell_price - avg_cost) × quantity
```

**Precision:** 8 decimal places for all AVP calculations

**Service:** `trade/services/position_service.py`

---

### Phase 2: Settlement Date Handling

**What it does:** Determines when position is calculated based on settle_date.

**When is it triggered?** At **trade creation** (INITIAL status), NOT at workflow settlement.

| Settlement Type | Description | Action |
|-----------------|-------------|--------|
| **T+0** (Same Day) | Settle date = Today | Position calculated **immediately** on trade save |
| **T+1 / T+2** (Future) | Settle date > Today | Trade **queued** until settle date arrives |
| **Backdated** | Settle date < Today | Validated (up to prev month-end), then **recalculates chain** |

**Important:** The trade workflow (Submit → Validate → Settle) is for trade lifecycle management. The AVP calculation is independent and happens based on settle_date at trade creation time.

**Service:** `trade/services/settlement_service.py`

---

### Phase 3: Async Background Processing

**What it does:** Processes position calculations in background with retry logic.

```
┌─────────────┐     ┌────────────────┐     ┌─────────────────┐
│   Trade     │────▶│   Position     │────▶│   Background    │
│   Created   │     │   Queue        │     │   Worker        │
└─────────────┘     └────────────────┘     └─────────────────┘
                           │                       │
                           │                       ▼
                           │               ┌─────────────────┐
                           │               │  SLA: < 5 min   │
                           │               │  Max Retries: 3 │
                           │               └─────────────────┘
                           │                       │
                           ▼                       ▼
                    ┌────────────────┐     ┌─────────────────┐
                    │  Dead Letter   │◄────│  Position       │
                    │  (if failed)   │     │  Updated        │
                    └────────────────┘     └─────────────────┘
```

**SLA:** Position updated within 5 minutes of trade save
**Retries:** 3 attempts before moving to dead letter queue

**Service:** `trade/services/position_queue_service.py`

---

### Phase 4: Multi-Currency Support

**What it does:** Handles positions in multiple currencies with FX conversion.

| Currency Type | Description |
|---------------|-------------|
| **Local Currency** | Security's trading currency (e.g., USD for AAPL) |
| **Base Currency** | Portfolio's base currency (e.g., SGD for Singapore fund) |

**FX Rate:** Latest rate from `gmp_cis_sta_dly_fx_rates` table

**P&L Calculation:** Combined P&L (includes FX impact, not shown separately)

**Service:** `trade/services/multicurrency_service.py`

---

## Using AVP with Trade UI

### Key Concept: AVP Triggers at Trade Creation

**Important:** Position calculation is triggered when the trade is **created** (INITIAL status), NOT when the trade goes through the workflow (validate/settle).

The calculation timing depends on the **settle_date**:
- **settle_date = today (T+0):** Position calculated **immediately** on trade creation
- **settle_date > today (T+1, T+2):** Trade **queued** for future settlement
- **settle_date < today (backdated):** **Validated** and recalculated if within limits

### Step 1: Create a New Trade

1. Navigate to **Trade** → **Create Trade**
2. Fill in the trade form:

| Field | Description | Example |
|-------|-------------|---------|
| **Trade Type** | BUY or SELL | `BUY` |
| **Portfolio** | Select portfolio | `FUND-001` |
| **Security** | Select security | `AAPL` (Apple Inc) |
| **Quantity** | Number of shares | `100` |
| **Price** | Price per share | `175.50` |
| **Commission** | Broker commission | `10.00` |
| **Sec Fee** | SEC/exchange fee | `0.50` |
| **Other Charges** | Any other fees | `0.00` |
| **Trade Date** | When trade was executed | `2026-03-04` |
| **Settle Date** | When trade settles | `2026-03-04` (T+0 for immediate) |

3. Click **Save Trade**
4. **If settle_date = today:** Position is calculated **immediately**!

### Step 2: Position Calculation Flow

After saving the trade (at INITIAL status):

```
1. Trade saved to cis_trade table (status = INITIAL)
                │
                ▼
2. Settlement service checks settle_date
                │
   ┌────────────┼────────────┐
   │            │            │
   ▼            ▼            ▼
T+0 (Today)   T+1/T+2      Backdated
   │          (Future)         │
   │            │              │
   ▼            ▼              ▼
IMMEDIATE   QUEUED for     VALIDATE &
Position    settle_date    RECALCULATE
Calculated     │              │
   │            │              │
   ▼            ▼              ▼
Position    Background     Position
Updated     worker runs    Chain
NOW!        on date        Updated
```

### Step 3: View Position Results (Immediate for T+0)

For T+0 trades, position is available **immediately** after trade creation:

```sql
-- Check position right after creating trade
SELECT * FROM gmp_cis.cis_trade_position
WHERE portfolio_short_name = 'FUND-001'
  AND security_label = 'AAPL'
  AND status = 'OPEN';
```

1. Navigate to **Positions** (if available in UI)
2. Filter by portfolio to see updated positions:

| Field | Description |
|-------|-------------|
| **Quantity** | Total shares held |
| **Average Cost** | Weighted average price per share |
| **Total Cost** | Quantity × Average Cost |
| **Market Value** | Quantity × Current Price |
| **Unrealized P&L** | Market Value - Total Cost |
| **Realized P&L** | P&L from sold shares |

---

## Example Scenarios

### Scenario 1: First BUY Trade

**Trade Details:**
- Portfolio: FUND-001
- Security: AAPL
- Trade Type: BUY
- Quantity: 100
- Price: $175.00
- Commission: $10.00
- Sec Fee: $0.50

**Position Calculation:**
```
Trade Cost = (100 × $175.00) + $10.00 + $0.50 = $17,510.50
New Quantity = 0 + 100 = 100
New AVP = $17,510.50 / 100 = $175.1050
```

**Result:**
| Field | Value |
|-------|-------|
| Quantity | 100 |
| Average Cost | $175.10500000 |
| Total Cost | $17,510.50 |

---

### Scenario 2: Second BUY Trade (Adding to Position)

**Existing Position:**
- Quantity: 100
- Average Cost: $175.10500000
- Total Cost: $17,510.50

**New Trade:**
- Trade Type: BUY
- Quantity: 50
- Price: $180.00
- Commission: $5.00

**Position Calculation:**
```
Trade Cost = (50 × $180.00) + $5.00 = $9,005.00
New Quantity = 100 + 50 = 150
New Total Cost = $17,510.50 + $9,005.00 = $26,515.50
New AVP = $26,515.50 / 150 = $176.77000000
```

**Result:**
| Field | Value |
|-------|-------|
| Quantity | 150 |
| Average Cost | $176.77000000 |
| Total Cost | $26,515.50 |

---

### Scenario 3: SELL Trade (Partial Sale)

**Existing Position:**
- Quantity: 150
- Average Cost: $176.77000000
- Total Cost: $26,515.50

**Trade:**
- Trade Type: SELL
- Quantity: 30
- Price: $185.00 (Selling at profit)

**Position Calculation:**
```
Realized P&L = (185.00 - 176.77) × 30 = $246.90 (Profit)
New Quantity = 150 - 30 = 120
New AVP = $176.77000000 (unchanged on SELL)
New Total Cost = 120 × $176.77 = $21,212.40
```

**Result:**
| Field | Value |
|-------|-------|
| Quantity | 120 |
| Average Cost | $176.77000000 |
| Total Cost | $21,212.40 |
| Realized P&L | +$246.90 |

---

### Scenario 4: Full Position Close

**Existing Position:**
- Quantity: 120
- Average Cost: $176.77000000
- Realized P&L (prior): $246.90

**Trade:**
- Trade Type: SELL
- Quantity: 120 (all remaining)
- Price: $170.00 (Selling at loss)

**Position Calculation:**
```
Realized P&L This Trade = (170.00 - 176.77) × 120 = -$812.40 (Loss)
Total Realized P&L = $246.90 + (-$812.40) = -$565.50
New Quantity = 0
Position Status = CLOSED
```

**Result:**
| Field | Value |
|-------|-------|
| Quantity | 0 |
| Average Cost | 0 |
| Status | CLOSED |
| Realized P&L | -$565.50 |

---

### Scenario 5: Multi-Currency Position

**Trade Details:**
- Portfolio: FUND-SGD (Base currency: SGD)
- Security: AAPL (Security currency: USD)
- Trade Type: BUY
- Quantity: 100
- Price: $175.00 (USD)
- Charges: $10.50 (USD)

**FX Rate:** USD-SGD = 1.3500

**Position Calculation:**
```
Local (USD):
  Trade Cost = (100 × $175) + $10.50 = $17,510.50
  AVP = $17,510.50 / 100 = $175.105

Base (SGD):
  Trade Cost = $17,510.50 × 1.35 = S$23,639.18
  AVP = S$23,639.18 / 100 = S$236.39
```

**Result:**
| Field | USD (Local) | SGD (Base) |
|-------|-------------|------------|
| Quantity | 100 | 100 |
| Average Cost | $175.10500000 | S$236.39175000 |
| Total Cost | $17,510.50 | S$23,639.18 |
| FX Rate | 1.3500 | - |

---

## Business Rules Summary

| Rule | Description |
|------|-------------|
| **Trade Types** | Only BUY and SELL affect positions |
| **Short Selling** | ❌ Not allowed (cannot sell more than you hold) |
| **Overselling** | ❌ Rejected at validation |
| **AVP on SELL** | AVP stays unchanged when selling |
| **AVP on BUY** | AVP recalculated with new weighted average |
| **Precision** | 8 decimal places (0.00000001) |
| **Backdated Limit** | Up to previous month-end only |
| **Settled Trade Cancel** | ❌ Not allowed |
| **Manual Adjustments** | ❌ Not allowed (trades only) |
| **FX P&L** | Combined with trade P&L (not separate) |

---

## Troubleshooting

### Position Not Updating?

1. **Check SLA:** Wait up to 5 minutes for background processing
2. **Check Queue Status:**
   ```sql
   SELECT * FROM gmp_cis.cis_position_queue
   WHERE trade_id = <your_trade_id>
   ORDER BY queued_at DESC;
   ```
3. **Check for Errors:**
   ```sql
   SELECT * FROM gmp_cis.cis_position_queue
   WHERE status = 'FAILED' OR status = 'DEAD_LETTER'
   ORDER BY queued_at DESC LIMIT 10;
   ```

### Overselling Error?

- Check current position quantity before creating SELL trade
- Query current position:
  ```sql
  SELECT quantity, average_cost, status
  FROM gmp_cis.cis_trade_position
  WHERE portfolio_short_name = '<portfolio>'
    AND security_label = '<security>'
    AND status = 'OPEN'
  ORDER BY created_at DESC LIMIT 1;
  ```

### Backdated Trade Rejected?

- Backdated settlements only allowed up to previous month-end
- Example: If today is March 15, you can backdate to February 28, but not to January 31

---

## Database Tables

| Table | Purpose |
|-------|---------|
| `cis_trade` | Trade records |
| `cis_trade_position` | CIS internal position tracking |
| `cis_position_queue` | Async processing queue |
| `cis_settlement_queue` | Future settlement queue |
| `position_master` | Shared position table (src_system='CIS') |
| `gmp_cis_sta_dly_fx_rates` | FX rates for multi-currency |

---

## Running Tests

```bash
# All AVP tests
pytest trade/tests/test_position_service.py -v
pytest trade/tests/test_settlement_service.py -v
pytest trade/tests/test_position_queue_service.py -v
pytest trade/tests/test_multicurrency_service.py -v

# All tests together (71 tests)
pytest trade/tests/test_position_service.py trade/tests/test_settlement_service.py trade/tests/test_position_queue_service.py trade/tests/test_multicurrency_service.py -v
```

---

## API Reference

### Position Service

```python
from trade.services import position_service

# Calculate position after trade
success, message, position = position_service.calculate_position(
    portfolio_id='FUND-001',
    security_id='AAPL',
    trade_type='BUY',
    quantity=Decimal('100'),
    price=Decimal('175.00'),
    charges=Decimal('10.50'),
    position_date='2026-03-04',
    trade_id=12345,
    updated_by='user1'
)

# Get current position
position = position_service.get_position('FUND-001', 'AAPL')

# Validate trade before position calc
is_valid, errors = position_service.validate_trade_for_position(
    trade_type='SELL',
    quantity=Decimal('50'),
    price=Decimal('180.00'),
    portfolio_id='FUND-001',
    security_id='AAPL'
)
```

### Settlement Service

```python
from trade.services import settlement_service

# Process trade settlement
success, message = settlement_service.process_trade_settlement(
    trade_id=12345,
    portfolio_id='FUND-001',
    security_id='AAPL',
    trade_type='BUY',
    quantity=Decimal('100'),
    price=Decimal('175.00'),
    charges=Decimal('10.50'),
    trade_date='2026-03-04',
    settle_date='2026-03-06',  # T+2
    updated_by='user1'
)
```

### Position Queue Service

```python
from trade.services import position_queue_service

# Enqueue for async processing
success, message, queue_id = position_queue_service.enqueue_position_calculation(
    trade_id=12345,
    portfolio_id='FUND-001',
    security_id='AAPL',
    trade_type='BUY',
    quantity=Decimal('100'),
    price=Decimal('175.00'),
    charges=Decimal('10.50'),
    settle_date='2026-03-04',
    queued_by='user1'
)

# Start background worker
position_queue_service.start_worker()

# Get queue statistics
stats = position_queue_service.get_queue_statistics()
```

### Multi-Currency Service

```python
from trade.services import multicurrency_service

# Get FX rate
rate, date_used = multicurrency_service.get_fx_rate('USD', 'SGD')

# Convert amount
converted, fx_rate = multicurrency_service.convert_amount(
    amount=Decimal('1000'),
    from_currency='USD',
    to_currency='SGD'
)

# Calculate position values in both currencies
values = multicurrency_service.calculate_position_values(
    quantity=Decimal('100'),
    avg_cost_local=Decimal('175.00'),
    current_price=Decimal('180.00'),
    security_currency='USD',
    portfolio_currency='SGD'
)
```

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-04 | System | Initial user guide for all 4 AVP phases |
