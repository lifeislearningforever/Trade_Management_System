# AVP Position Logic Redesign Plan

## Executive Summary

This document outlines the redesign of the Average Price (AVP) position tracking system to:
1. **Decouple AVP from trade save/edit** - Improve trade performance
2. **Handle all settle date scenarios** - Current, future, backdated
3. **Cover all AVP corner cases** - Real-world trading scenarios

---

## Current State Analysis

### Current Flow (Synchronous)
```
Trade Create/Edit
    ↓
insert_trade() / update_trade()
    ↓
update_position_from_trade()  ← BLOCKING (slow)
    ↓
_insert_position_version()    ← Kudu UPSERT
    ↓
Response to User
```

### Performance Issues
| Operation | Current Time | Bottleneck |
|-----------|--------------|------------|
| Trade Save | ~2-5 seconds | Position calculation blocks |
| FX Rate Lookup | ~500ms | External query |
| Equity Price Lookup | ~500ms | External query |
| Position Insert | ~500ms | Kudu write |

### Current AVP Calculation
```python
# BUY/ADD_LONG
new_avg_cost = ((old_qty * old_avg_cost) + (trade_qty * trade_price)) / new_qty

# SELL/DELIVER_LONG
# AVP unchanged, calculate realized P&L
realized_pnl = trade_amount - (trade_qty * old_avg_cost)
```

### Current Settle Date Handling
- **Uses `trade_date` as position date** (not `settle_date`)
- **No support for future-dated settlements**
- **No support for backdated settlements**

---

## Proposed Architecture

### 1. Decoupled Position Processing

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TRADE MODULE                                 │
├─────────────────────────────────────────────────────────────────────┤
│  Trade Create/Edit                                                   │
│       ↓                                                              │
│  Save Trade to cis_trade                                            │
│       ↓                                                              │
│  Queue Position Update (Async)  ←── NEW: Non-blocking               │
│       ↓                                                              │
│  Response to User (Fast!)                                           │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              │ Message Queue / Background Task
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     POSITION PROCESSOR (Background)                  │
├─────────────────────────────────────────────────────────────────────┤
│  Position Queue Consumer                                             │
│       ↓                                                              │
│  Fetch Trade Details                                                 │
│       ↓                                                              │
│  Determine Position Date (based on settle_date logic)               │
│       ↓                                                              │
│  Calculate AVP (with all corner cases)                              │
│       ↓                                                              │
│  Insert Position Version                                             │
│       ↓                                                              │
│  Update Trade (position_processed = true)                           │
└─────────────────────────────────────────────────────────────────────┘
```

### 2. New Table: Position Queue

```sql
CREATE TABLE cis_position_queue (
    queue_id BIGINT NOT NULL,
    trade_id BIGINT NOT NULL,
    action STRING NOT NULL,           -- 'CREATE', 'UPDATE', 'CANCEL'
    priority INT DEFAULT 5,           -- 1=HIGH, 5=NORMAL, 10=LOW
    status STRING DEFAULT 'PENDING',  -- 'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    error_message STRING,
    created_at STRING,
    processed_at STRING,
    PRIMARY KEY (queue_id)
)
PARTITION BY HASH PARTITIONS 4
STORED AS KUDU;
```

### 3. Enhanced Position Table Fields

```sql
ALTER TABLE cis_trade_position ADD COLUMNS (
    settle_date STRING,              -- Settlement date
    position_type STRING,            -- 'T' (Trade Date), 'S' (Settle Date)
    effective_date STRING,           -- When position becomes effective
    is_future_dated BOOLEAN,         -- True if settle_date > today
    is_backdated BOOLEAN,            -- True if settle_date < today
    reprocessed_at STRING,           -- Last reprocessing timestamp
    reprocessed_by STRING            -- Who triggered reprocessing
);
```

---

## Settle Date Scenarios

### Scenario 1: Current Date Settlement (T+0)
```
Trade Date: 2026-03-03
Settle Date: 2026-03-03
Today: 2026-03-03

Action: Update position IMMEDIATELY
Position Date: 2026-03-03
is_future_dated: false
is_backdated: false
```

### Scenario 2: Future Settlement (T+2, T+3)
```
Trade Date: 2026-03-03
Settle Date: 2026-03-05 (T+2)
Today: 2026-03-03

Action:
  1. Create PENDING position record
  2. Scheduler processes on settle_date
Position Date: 2026-03-05 (when processed)
is_future_dated: true (until settle_date)
is_backdated: false
```

### Scenario 3: Backdated Settlement
```
Trade Date: 2026-03-01
Settle Date: 2026-02-28 (backdated)
Today: 2026-03-03

Action:
  1. Recalculate positions from settle_date to today
  2. Re-apply all subsequent trades
  3. Create corrected position versions
Position Date: 2026-02-28
is_future_dated: false
is_backdated: true
```

### Scenario 4: Trade Amendment After Settlement
```
Original Trade: BUY 100 @ 10.00 on 2026-02-28
Amendment: Change to BUY 150 @ 10.00 on 2026-03-03
Today: 2026-03-03

Action:
  1. Reverse original position impact
  2. Apply amended trade impact
  3. Recalculate all positions from 2026-02-28
```

---

## AVP Corner Cases

### Case 1: First Buy (New Position)
```
Before: No position
Trade: BUY 100 @ 50.00
After:
  quantity = 100
  average_cost = 50.00
  total_cost = 5000.00
```

### Case 2: Additional Buy (Increase Position)
```
Before: qty=100, avg_cost=50.00
Trade: BUY 50 @ 60.00
After:
  quantity = 150
  average_cost = (100*50 + 50*60) / 150 = 53.33
  total_cost = 8000.00
```

### Case 3: Partial Sell (Reduce Position)
```
Before: qty=150, avg_cost=53.33
Trade: SELL 50 @ 70.00
After:
  quantity = 100
  average_cost = 53.33 (UNCHANGED)
  total_cost = 5333.33
  realized_pnl = 50 * (70 - 53.33) = 833.33
```

### Case 4: Full Sell (Close Position)
```
Before: qty=100, avg_cost=53.33
Trade: SELL 100 @ 75.00
After:
  quantity = 0
  average_cost = 0
  total_cost = 0
  realized_pnl = 100 * (75 - 53.33) = 2166.67
  status = 'CLOSED'
```

### Case 5: Sell More Than Held (Short Selling)
```
Before: qty=100, avg_cost=53.33
Trade: SELL 150 @ 75.00

Option A - REJECT: Error - insufficient quantity
Option B - ALLOW SHORT:
  quantity = -50 (short position)
  average_cost = 75.00 (new short basis)
  realized_pnl = 100 * (75 - 53.33) = 2166.67
```

### Case 6: Buy to Cover Short
```
Before: qty=-50 (short), avg_cost=75.00
Trade: BUY 50 @ 70.00
After:
  quantity = 0
  average_cost = 0
  realized_pnl = 50 * (75 - 70) = 250 (profit on short)
  status = 'CLOSED'
```

### Case 7: Multiple Trades Same Day
```
Trade 1: BUY 100 @ 50.00 at 09:00
Trade 2: SELL 30 @ 55.00 at 10:00
Trade 3: BUY 50 @ 52.00 at 11:00

Processing Order: MUST be chronological by trade timestamp
Final:
  quantity = 120
  average_cost = weighted average of remaining
```

### Case 8: Trade Cancellation
```
Original: BUY 100 @ 50.00 → position created
Cancel: Trade cancelled

Action:
  1. Reverse the position impact
  2. If this was only trade → close position
  3. If subsequent trades exist → recalculate from cancellation point
```

### Case 9: Trade Amendment (Price Change)
```
Original: BUY 100 @ 50.00 → avg_cost = 50.00
Amendment: Change price to 55.00

Action:
  1. Reverse old impact: remove 100 @ 50.00
  2. Apply new impact: add 100 @ 55.00
  3. Recalculate avg_cost
```

### Case 10: Trade Amendment (Quantity Change)
```
Original: BUY 100 @ 50.00 → qty=100, avg=50.00
Amendment: Change qty to 150

Action:
  1. Calculate delta: +50 @ 50.00
  2. Adjust position: qty=150, recalculate avg
```

### Case 11: Corporate Action - Stock Split
```
Before: qty=100, avg_cost=100.00
Corporate Action: 2:1 split

After:
  quantity = 200
  average_cost = 50.00 (adjusted)
  total_cost = 10000.00 (unchanged)
```

### Case 12: Corporate Action - Dividend Reinvestment
```
Before: qty=100, avg_cost=50.00
Dividend: $1.00/share reinvested at $48.00

After:
  new_shares = 100 * 1.00 / 48.00 = 2.08
  quantity = 102.08
  total_cost = 5000 + 100 = 5100
  average_cost = 5100 / 102.08 = 49.96
```

### Case 13: Multi-Currency Position
```
Portfolio Currency: USD
Security Currency: SGD
FX Rate: 1 USD = 1.35 SGD

Trade: BUY 100 @ SGD 67.50
After:
  cost_value_local = 6750 SGD
  cost_value_base = 6750 / 1.35 = 5000 USD

Market Price: SGD 70.00
  market_value_local = 7000 SGD
  market_value_base = 7000 / 1.35 = 5185.19 USD
  unrealized_pnl_local = 250 SGD
  unrealized_pnl_base = 185.19 USD
```

### Case 14: FX Rate Change Impact
```
Day 1: Buy at SGD 67.50, FX = 1.35
  cost_value_base = 5000 USD

Day 2: FX = 1.40 (USD strengthened)
  cost_value_base = 6750 / 1.40 = 4821.43 USD
  FX P&L = -178.57 USD (currency loss)
```

### Case 15: Zero Price Trade (Transfer)
```
Trade: DELIVER_LONG 100 @ 0.00 (internal transfer)

Action:
  - Remove from source portfolio at avg_cost
  - Realized P&L = 0 (no sale)
  - Destination portfolio receives at avg_cost
```

---

## Implementation Plan

### Phase 1: Database Changes (Week 1)
- [ ] Create `cis_position_queue` table
- [ ] Add new columns to `cis_trade_position`
- [ ] Add `position_processed` flag to `cis_trade`
- [ ] Create indexes for queue processing

### Phase 2: Position Processor Service (Week 2)
- [ ] Create `PositionProcessorService` class
- [ ] Implement queue consumer
- [ ] Implement all AVP corner cases
- [ ] Add settle date logic

### Phase 3: Trade Integration (Week 3)
- [ ] Remove sync position call from `insert_trade()`
- [ ] Add queue insertion instead
- [ ] Update `update_trade()` for amendments
- [ ] Handle trade cancellation

### Phase 4: Background Worker (Week 4)
- [ ] Create Django management command for processor
- [ ] Add cron/scheduler integration
- [ ] Implement retry logic
- [ ] Add monitoring/alerting

### Phase 5: Backdated Processing (Week 5)
- [ ] Implement position recalculation
- [ ] Handle trade chain reprocessing
- [ ] Add audit trail for corrections

### Phase 6: Testing & Validation (Week 6)
- [ ] Unit tests for all corner cases
- [ ] Integration tests
- [ ] Performance benchmarking
- [ ] UAT with SA team

---

## New Files to Create

```
trade/
├── services/
│   └── position_processor_service.py    # Core AVP logic
├── repositories/
│   └── position_queue_repository.py     # Queue operations
├── management/
│   └── commands/
│       └── process_positions.py         # Background worker
└── tests/
    └── test_avp_corner_cases.py         # Comprehensive tests
```

---

## Configuration Options

```python
# settings.py
POSITION_PROCESSING = {
    'MODE': 'ASYNC',  # 'SYNC' for immediate, 'ASYNC' for queued
    'BATCH_SIZE': 100,
    'RETRY_MAX': 3,
    'RETRY_DELAY_SECONDS': 60,
    'FUTURE_DATE_ENABLED': True,
    'BACKDATE_ENABLED': True,
    'BACKDATE_MAX_DAYS': 30,  # How far back we allow
    'SHORT_SELLING_ENABLED': False,
}
```

---

## API Changes

### New Endpoints
```
POST /trade/api/reprocess-position/     # Manual reprocessing
GET  /trade/api/position-queue-status/  # Queue monitoring
POST /trade/api/position-queue/retry/   # Retry failed items
```

### Trade Response Enhancement
```json
{
  "trade_id": 12345,
  "status": "INITIAL",
  "position_status": "QUEUED",  // NEW: 'QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED'
  "position_queue_id": 67890    // NEW: Reference to queue
}
```

---

## Monitoring & Alerts

### Metrics to Track
- Queue depth (pending items)
- Processing time per position
- Failure rate
- Retry count distribution
- Backdate frequency

### Alert Conditions
- Queue depth > 1000
- Processing time > 5 seconds
- Failure rate > 5%
- Any item with retry_count = max_retries

---

## Questions for SA Team

1. **Short Selling**: Should we allow selling more than held quantity?
2. **Backdate Limit**: How far back should we allow backdated settlements?
3. **Amendment Impact**: Should quantity/price amendments trigger full recalculation?
4. **Corporate Actions**: Do we need to handle splits, dividends, mergers?
5. **Multi-Portfolio**: Can the same security exist in multiple portfolios?
6. **Position Correction**: Manual position adjustment allowed?

---

## Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Business Analyst | | | |
| Solution Architect | | | |
| Tech Lead | | | |
| Product Owner | | | |
