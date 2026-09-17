# AVP (Average Valuation Price) Logic - Implementation Examples

## Overview

This document provides detailed examples of the AVP (Average Valuation Price) logic implemented in the CIS Trade Hive system. The AVP method is used to calculate the average cost of securities positions and track realized/unrealized P&L.

---

## Core AVP Formulas

### BUY Trade
```
New Quantity     = Old Quantity + Buy Quantity
New Total Cost   = Old Total Cost + (Buy Quantity × Buy Price) + Charges
New Average Cost = New Total Cost / New Quantity
Realized P&L     = No change (unchanged on BUY)
```

### SELL Trade
```
New Quantity     = Old Quantity - Sell Quantity
New Average Cost = Old Average Cost (unchanged on SELL)
New Total Cost   = Old Total Cost × (New Quantity / Old Quantity)
Realized P&L     = Old Realized P&L + [Sell Quantity × (Sell Price - Average Cost)]
```

### Position Status
```
Status = 'OPEN'   if New Quantity > 0
Status = 'CLOSED' if New Quantity <= 0
```

---

## Use Case 1: Simple BUY Trade (Opening Position)

### Scenario
Portfolio A purchases 100 shares of Security XYZ at $50.00 per share.

### Input
| Field | Value |
|-------|-------|
| Portfolio | Portfolio A |
| Security | XYZ |
| Trade Type | BUY |
| Quantity | 100 |
| Price | $50.00 |
| Charges | $0.00 |
| Settlement Date | 2026-03-05 |

### Calculation
```
Previous Position: None (new position)

New Quantity     = 0 + 100 = 100
New Total Cost   = 0 + (100 × 50.00) + 0 = $5,000.00
New Average Cost = 5,000.00 / 100 = $50.00
Realized P&L     = $0.00
Status           = OPEN
```

### Result
| Field | Value |
|-------|-------|
| Quantity | 100 |
| Average Cost | $50.00 |
| Total Cost | $5,000.00 |
| Realized P&L | $0.00 |
| Status | OPEN |

---

## Use Case 2: Additional BUY Trade (Averaging Up)

### Scenario
Portfolio A already holds 100 shares of XYZ at $50.00 average cost.
Now purchases additional 50 shares at $60.00 per share.

### Input
| Field | Value |
|-------|-------|
| Previous Quantity | 100 |
| Previous Avg Cost | $50.00 |
| Previous Total Cost | $5,000.00 |
| New Trade | BUY 50 @ $60.00 |
| Charges | $10.00 |

### Calculation
```
New Quantity     = 100 + 50 = 150
Buy Value        = 50 × 60.00 = $3,000.00
New Total Cost   = 5,000.00 + 3,000.00 + 10.00 = $8,010.00
New Average Cost = 8,010.00 / 150 = $53.40
Realized P&L     = $0.00 (no change on BUY)
```

### Result
| Field | Before | After |
|-------|--------|-------|
| Quantity | 100 | 150 |
| Average Cost | $50.00 | $53.40 |
| Total Cost | $5,000.00 | $8,010.00 |
| Realized P&L | $0.00 | $0.00 |
| Status | OPEN | OPEN |

---

## Use Case 3: Additional BUY Trade (Averaging Down)

### Scenario
Portfolio A holds 100 shares of XYZ at $50.00 average cost.
Now purchases additional 100 shares at $40.00 per share (price dropped).

### Input
| Field | Value |
|-------|-------|
| Previous Quantity | 100 |
| Previous Avg Cost | $50.00 |
| Previous Total Cost | $5,000.00 |
| New Trade | BUY 100 @ $40.00 |
| Charges | $0.00 |

### Calculation
```
New Quantity     = 100 + 100 = 200
Buy Value        = 100 × 40.00 = $4,000.00
New Total Cost   = 5,000.00 + 4,000.00 + 0 = $9,000.00
New Average Cost = 9,000.00 / 200 = $45.00
Realized P&L     = $0.00
```

### Result
| Field | Before | After |
|-------|--------|-------|
| Quantity | 100 | 200 |
| Average Cost | $50.00 | $45.00 |
| Total Cost | $5,000.00 | $9,000.00 |
| Realized P&L | $0.00 | $0.00 |

**Note:** Average cost decreased from $50.00 to $45.00 (averaging down).

---

## Use Case 4: Partial SELL Trade (Profit)

### Scenario
Portfolio A holds 150 shares of XYZ at $53.40 average cost.
Now sells 50 shares at $70.00 per share (profit scenario).

### Input
| Field | Value |
|-------|-------|
| Previous Quantity | 150 |
| Previous Avg Cost | $53.40 |
| Previous Total Cost | $8,010.00 |
| Previous Realized P&L | $0.00 |
| New Trade | SELL 50 @ $70.00 |

### Calculation
```
New Quantity     = 150 - 50 = 100
New Average Cost = $53.40 (unchanged on SELL)
New Total Cost   = 8,010.00 × (100 / 150) = $5,340.00

Profit per Share = 70.00 - 53.40 = $16.60
Realized P&L     = 0 + (50 × 16.60) = $830.00
Status           = OPEN (quantity > 0)
```

### Result
| Field | Before | After |
|-------|--------|-------|
| Quantity | 150 | 100 |
| Average Cost | $53.40 | $53.40 |
| Total Cost | $8,010.00 | $5,340.00 |
| Realized P&L | $0.00 | **$830.00** |
| Status | OPEN | OPEN |

---

## Use Case 5: Partial SELL Trade (Loss)

### Scenario
Portfolio A holds 100 shares of XYZ at $53.40 average cost.
Now sells 30 shares at $45.00 per share (loss scenario).

### Input
| Field | Value |
|-------|-------|
| Previous Quantity | 100 |
| Previous Avg Cost | $53.40 |
| Previous Total Cost | $5,340.00 |
| Previous Realized P&L | $830.00 |
| New Trade | SELL 30 @ $45.00 |

### Calculation
```
New Quantity     = 100 - 30 = 70
New Average Cost = $53.40 (unchanged)
New Total Cost   = 5,340.00 × (70 / 100) = $3,738.00

Loss per Share   = 45.00 - 53.40 = -$8.40
Realized P&L     = 830.00 + (30 × -8.40) = 830.00 - 252.00 = $578.00
Status           = OPEN
```

### Result
| Field | Before | After |
|-------|--------|-------|
| Quantity | 100 | 70 |
| Average Cost | $53.40 | $53.40 |
| Total Cost | $5,340.00 | $3,738.00 |
| Realized P&L | $830.00 | **$578.00** |
| Status | OPEN | OPEN |

---

## Use Case 6: Full SELL Trade (Closing Position)

### Scenario
Portfolio A holds 70 shares of XYZ at $53.40 average cost.
Now sells ALL 70 shares at $60.00 per share.

### Input
| Field | Value |
|-------|-------|
| Previous Quantity | 70 |
| Previous Avg Cost | $53.40 |
| Previous Total Cost | $3,738.00 |
| Previous Realized P&L | $578.00 |
| New Trade | SELL 70 @ $60.00 |

### Calculation
```
New Quantity     = 70 - 70 = 0
New Average Cost = $53.40 (preserved for records)
New Total Cost   = 3,738.00 × (0 / 70) = $0.00

Profit per Share = 60.00 - 53.40 = $6.60
Realized P&L     = 578.00 + (70 × 6.60) = 578.00 + 462.00 = $1,040.00
Status           = CLOSED (quantity = 0)
```

### Result
| Field | Before | After |
|-------|--------|-------|
| Quantity | 70 | **0** |
| Average Cost | $53.40 | $53.40 |
| Total Cost | $3,738.00 | $0.00 |
| Realized P&L | $578.00 | **$1,040.00** |
| Status | OPEN | **CLOSED** |

---

## Use Case 7: Complete Trading Cycle Example

### Scenario
Track a complete trading cycle for Portfolio A, Security FLT SP.

### Trade Sequence
| Date | Trade | Qty | Price | Charges |
|------|-------|-----|-------|---------|
| 2026-03-13 | BUY | 50 | $50.00 | $0 |
| 2026-03-15 | BUY | 100 | $0.935 | $0 |
| 2026-03-17 | BUY | 150 | $10.00 | $0 |
| 2026-03-18 | SELL | 300 | $20.00 | $0 |

### Step-by-Step Calculation

#### Trade 1: BUY 50 @ $50.00 (Opening)
```
Quantity     = 0 + 50 = 50
Total Cost   = 0 + (50 × 50.00) = $2,500.00
Average Cost = 2,500.00 / 50 = $50.00
Realized P&L = $0.00
Status       = OPEN
```

#### Trade 2: BUY 100 @ $0.935 (Averaging Down)
```
Quantity     = 50 + 100 = 150
Total Cost   = 2,500.00 + (100 × 0.935) = 2,500.00 + 93.50 = $2,593.50
Average Cost = 2,593.50 / 150 = $17.29
Realized P&L = $0.00
Status       = OPEN
```

#### Trade 3: BUY 150 @ $10.00 (Further Averaging)
```
Quantity     = 150 + 150 = 300
Total Cost   = 2,593.50 + (150 × 10.00) = 2,593.50 + 1,500.00 = $4,093.50
Average Cost = 4,093.50 / 300 = $13.645 (rounded)
Realized P&L = $0.00
Status       = OPEN
```

#### Trade 4: SELL 300 @ $20.00 (Closing with Profit)
```
Quantity     = 300 - 300 = 0
Average Cost = $13.645 (unchanged)
Total Cost   = 4,093.50 × (0 / 300) = $0.00

Profit/Share = 20.00 - 13.645 = $6.355
Realized P&L = 0 + (300 × 6.355) = $1,906.50
Status       = CLOSED
```

### Summary Table
| Date | Trade | Qty After | Avg Cost | Total Cost | Realized P&L | Status |
|------|-------|-----------|----------|------------|--------------|--------|
| 2026-03-13 | BUY 50 @ 50.00 | 50 | $50.00 | $2,500.00 | $0.00 | OPEN |
| 2026-03-15 | BUY 100 @ 0.935 | 150 | $17.29 | $2,593.50 | $0.00 | OPEN |
| 2026-03-17 | BUY 150 @ 10.00 | 300 | $13.645 | $4,093.50 | $0.00 | OPEN |
| 2026-03-18 | SELL 300 @ 20.00 | 0 | $13.645 | $0.00 | **$1,906.50** | CLOSED |

---

## Use Case 8: Multiple Trades Same Day

### Scenario
Portfolio A executes multiple trades on the same day.

### Trade Sequence (All on 2026-03-10)
| Time | Trade | Qty | Price |
|------|-------|-----|-------|
| 09:30 | BUY | 100 | $65.00 |
| 11:00 | BUY | 50 | $68.00 |
| 14:00 | SELL | 30 | $70.00 |
| 15:30 | BUY | 20 | $67.00 |

### Step-by-Step (Intraday)

#### 09:30 - BUY 100 @ $65.00
```
Quantity = 100, Avg Cost = $65.00, Total = $6,500.00
```

#### 11:00 - BUY 50 @ $68.00
```
Quantity = 100 + 50 = 150
Total Cost = 6,500 + 3,400 = $9,900.00
Avg Cost = 9,900 / 150 = $66.00
```

#### 14:00 - SELL 30 @ $70.00
```
Quantity = 150 - 30 = 120
Avg Cost = $66.00 (unchanged)
Total Cost = 9,900 × (120/150) = $7,920.00
Realized P&L = 30 × (70 - 66) = $120.00
```

#### 15:30 - BUY 20 @ $67.00
```
Quantity = 120 + 20 = 140
Total Cost = 7,920 + 1,340 = $9,260.00
Avg Cost = 9,260 / 140 = $66.14
Realized P&L = $120.00 (unchanged)
```

### End of Day Position
| Field | Value |
|-------|-------|
| Quantity | 140 |
| Average Cost | $66.14 |
| Total Cost | $9,260.00 |
| Realized P&L | $120.00 |
| Status | OPEN |

---

## Use Case 9: SELL Validation (Insufficient Quantity)

### Scenario
Portfolio A holds 50 shares but attempts to sell 100 shares.

### Input
| Field | Value |
|-------|-------|
| Current Quantity | 50 |
| Attempted SELL | 100 shares |

### Validation
```
Available Quantity: 50
Requested Sell:     100
Result:             FAILED - Insufficient quantity
```

### System Response
- Trade is marked as **FAILED** in settlement log
- Error message: "Insufficient quantity. Available: 50, Requested: 100"
- Position remains unchanged

---

## Use Case 10: SELL Without Position (No Holdings)

### Scenario
Portfolio A has no position in Security ABC but attempts to sell.

### Input
| Field | Value |
|-------|-------|
| Portfolio | Portfolio A |
| Security | ABC |
| Current Position | None |
| Attempted SELL | 50 shares |

### Validation
```
Current Position: NULL (no holdings)
Requested Sell:   50 shares
Result:           FAILED - No position found
```

### System Response
- Trade is marked as **FAILED** in settlement log
- Error message: "No position found for ABC in portfolio Portfolio A"
- No position record created

---

## Use Case 11: Backdated BUY Trade (Historical Entry)

### Scenario
Today is **2026-03-18**. Portfolio A already has a position from trades executed on March 15-17.
A backdated BUY trade for **2026-03-14** is entered (before existing trades).

### Current Position (as of 2026-03-17)
| Field | Value |
|-------|-------|
| Quantity | 200 |
| Average Cost | $55.00 |
| Total Cost | $11,000.00 |
| Realized P&L | $0.00 |

### Backdated Trade Input
| Field | Value |
|-------|-------|
| Trade Date | 2026-03-14 (backdated) |
| Settlement Date | 2026-03-14 |
| Trade Type | BUY |
| Quantity | 50 |
| Price | $45.00 |

### Processing Logic
```
Backdated Trade Processing:
1. System detects settle_date (2026-03-14) < today (2026-03-18)
2. Trade is queued for settlement with status='PENDING'
3. EOD settlement processes trades in chronological order by settle_date
4. Position is recalculated from the backdated point forward

Recalculation Order:
  - 2026-03-14: BUY 50 @ $45.00 (backdated trade - processed first)
  - 2026-03-15: Original trade (reprocessed)
  - 2026-03-16: Original trade (reprocessed)
  - 2026-03-17: Original trade (reprocessed)
```

### Result After Backdated Settlement
| Field | Before Backdate | After Backdate |
|-------|-----------------|----------------|
| Quantity | 200 | 250 |
| Average Cost | $55.00 | **$53.00** (recalculated) |
| Total Cost | $11,000.00 | $13,250.00 |
| Realized P&L | $0.00 | $0.00 |

**Key Point:** Backdated trades are processed in settlement date order. The average cost is recalculated by replaying all trades from the backdated point forward.

---

## Use Case 12: Backdated SELL Trade (Historical Correction)

### Scenario
Today is **2026-03-18**. Portfolio A has 300 shares at $13.645 average cost.
A backdated SELL trade for **2026-03-16** is entered to correct a missing sale.

### Current Position (as of 2026-03-17)
| Field | Value |
|-------|-------|
| Quantity | 300 |
| Average Cost | $13.645 |
| Total Cost | $4,093.50 |
| Realized P&L | $0.00 |

### Backdated Trade Input
| Field | Value |
|-------|-------|
| Trade Date | 2026-03-16 (backdated) |
| Settlement Date | 2026-03-16 |
| Trade Type | SELL |
| Quantity | 100 |
| Price | $18.00 |

### Validation
```
Backdated SELL Validation:
1. System checks position as of 2026-03-16 (before the sell)
2. Available quantity on 2026-03-16: Must be >= 100
3. If sufficient quantity → PENDING for settlement
4. If insufficient → FAILED with error message
```

### Calculation (if valid)
```
Position as of 2026-03-16 (before backdated sell): 150 shares @ $17.29

Backdated SELL 100 @ $18.00:
New Quantity   = 150 - 100 = 50
Avg Cost       = $17.29 (unchanged)
Total Cost     = 2,593.50 × (50/150) = $864.50
Realized P&L   = 0 + (100 × (18.00 - 17.29)) = $71.00

Then subsequent trades (2026-03-17) are reprocessed with new starting position.
```

### Important Validation Rule
```
SELL Validation for Backdated Trades:
- System must verify quantity existed AT THAT POINT IN TIME
- Cannot sell more than what was held on the backdated date
- Error: "Insufficient quantity on 2026-03-16. Available: X, Requested: Y"
```

---

## Use Case 13: Future-Dated BUY Trade

### Scenario
Today is **2026-03-16**. Portfolio A enters a BUY trade with settlement date **2026-03-20** (T+2 settlement).

### Current Position
| Field | Value |
|-------|-------|
| Quantity | 100 |
| Average Cost | $50.00 |
| Total Cost | $5,000.00 |

### Future Trade Input
| Field | Value |
|-------|-------|
| Trade Date | 2026-03-16 (today) |
| Settlement Date | 2026-03-20 (future) |
| Trade Type | BUY |
| Quantity | 50 |
| Price | $55.00 |

### Processing Logic
```
Future-Dated Trade Processing:
1. Trade is created with status='PENDING'
2. Added to cis_settlement_queue with settle_date='2026-03-20'
3. Position is NOT updated immediately
4. EOD settlement on 2026-03-20 will process this trade

Current Position (unchanged until 2026-03-20):
  Quantity: 100, Avg Cost: $50.00

After EOD Settlement on 2026-03-20:
  Quantity: 150, Avg Cost: $51.67
```

### Timeline
| Date | Action | Position Qty | Avg Cost |
|------|--------|--------------|----------|
| 2026-03-16 | Trade entered (future-dated) | 100 | $50.00 |
| 2026-03-17 | No change (pending) | 100 | $50.00 |
| 2026-03-18 | No change (pending) | 100 | $50.00 |
| 2026-03-19 | No change (pending) | 100 | $50.00 |
| 2026-03-20 | **EOD Settlement processes trade** | **150** | **$51.67** |

### Calculation on Settlement Date
```
On 2026-03-20 EOD:
New Quantity   = 100 + 50 = 150
Buy Value      = 50 × 55.00 = $2,750.00
New Total Cost = 5,000.00 + 2,750.00 = $7,750.00
New Avg Cost   = 7,750.00 / 150 = $51.67
```

---

## Use Case 14: Future-Dated SELL Trade (Forward Sale)

### Scenario
Today is **2026-03-16**. Portfolio A has 200 shares and enters a forward SELL with settlement **2026-03-25**.

### Current Position
| Field | Value |
|-------|-------|
| Quantity | 200 |
| Average Cost | $45.00 |
| Total Cost | $9,000.00 |
| Realized P&L | $0.00 |

### Future Trade Input
| Field | Value |
|-------|-------|
| Trade Date | 2026-03-16 (today) |
| Settlement Date | 2026-03-25 (future) |
| Trade Type | SELL |
| Quantity | 80 |
| Price | $52.00 |

### Validation at Trade Entry
```
Future SELL Validation:
1. Check CURRENT quantity: 200 shares ✓
2. Requested sell: 80 shares
3. Available: 200 >= 80 ✓
4. Trade is ACCEPTED with status='PENDING'

Note: System validates against CURRENT position, not projected position.
Warning may be issued if other pending sells exist.
```

### Settlement Queue Status
```
Trade Status Lifecycle:
- 2026-03-16: Trade created → status='PENDING'
- 2026-03-16 to 2026-03-24: Remains in queue, position unchanged
- 2026-03-25 EOD: Processed → status='SETTLED'
```

### Calculation on Settlement Date (2026-03-25)
```
Position at start of 2026-03-25: 200 shares @ $45.00 (assuming no other trades)

SELL 80 @ $52.00:
New Quantity   = 200 - 80 = 120
Avg Cost       = $45.00 (unchanged)
New Total Cost = 9,000.00 × (120/200) = $5,400.00
Profit/Share   = 52.00 - 45.00 = $7.00
Realized P&L   = 0 + (80 × 7.00) = $560.00
```

### Result After Settlement
| Field | Before (2026-03-24) | After (2026-03-25) |
|-------|---------------------|-------------------|
| Quantity | 200 | 120 |
| Average Cost | $45.00 | $45.00 |
| Total Cost | $9,000.00 | $5,400.00 |
| Realized P&L | $0.00 | **$560.00** |

---

## Use Case 15: Mixed Backdated and Future Trades

### Scenario
Today is **2026-03-18**. Portfolio A has the following pending trades:

| Trade Date | Settlement Date | Type | Qty | Price | Status |
|------------|-----------------|------|-----|-------|--------|
| 2026-03-18 | 2026-03-14 | BUY | 30 | $40.00 | Backdated |
| 2026-03-18 | 2026-03-18 | BUY | 50 | $48.00 | Today |
| 2026-03-18 | 2026-03-22 | SELL | 20 | $55.00 | Future |

### Current Position (before any processing)
| Field | Value |
|-------|-------|
| Quantity | 100 |
| Average Cost | $50.00 |
| Total Cost | $5,000.00 |

### EOD Settlement Processing Order
```
EOD on 2026-03-18 processes trades where settle_date <= '2026-03-18':

Processing Order (by settle_date, then queue_id):
1. 2026-03-14: BUY 30 @ $40.00 (backdated - processed first)
2. 2026-03-18: BUY 50 @ $48.00 (today's trade)

Future trade (2026-03-22) remains PENDING - not processed yet.
```

### Step-by-Step Calculation

#### Step 1: Process Backdated BUY (2026-03-14)
```
Starting: 100 @ $50.00 = $5,000.00

BUY 30 @ $40.00:
New Qty      = 100 + 30 = 130
New Total    = 5,000 + 1,200 = $6,200.00
New Avg Cost = 6,200 / 130 = $47.69
```

#### Step 2: Process Today's BUY (2026-03-18)
```
Starting: 130 @ $47.69 = $6,200.00

BUY 50 @ $48.00:
New Qty      = 130 + 50 = 180
New Total    = 6,200 + 2,400 = $8,600.00
New Avg Cost = 8,600 / 180 = $47.78
```

### Position After EOD 2026-03-18
| Field | Value |
|-------|-------|
| Quantity | 180 |
| Average Cost | $47.78 |
| Total Cost | $8,600.00 |
| Pending Trades | SELL 20 @ $55 (settles 2026-03-22) |

### Future Settlement (2026-03-22)
```
Starting: 180 @ $47.78 = $8,600.00

SELL 20 @ $55.00:
New Qty      = 180 - 20 = 160
Avg Cost     = $47.78 (unchanged)
New Total    = 8,600 × (160/180) = $7,644.44
Profit/Share = 55.00 - 47.78 = $7.22
Realized P&L = 0 + (20 × 7.22) = $144.40
```

---

## Backdated & Future Trade Rules Summary

### Backdated Trades
| Rule | Description |
|------|-------------|
| Processing | Processed in chronological order by settle_date |
| BUY Validation | Always valid (adds to position) |
| SELL Validation | Must verify quantity existed on that date |
| Recalculation | All subsequent positions are recalculated |
| Status Flow | PENDING → PROCESSING → SETTLED |

### Future-Dated Trades
| Rule | Description |
|------|-------------|
| Entry Validation | Validates against CURRENT position |
| Position Impact | No immediate impact - position unchanged until settlement |
| Settlement | Processed on EOD when settle_date <= current_date |
| SELL Risk | Position may change before settlement (warning issued) |
| Status Flow | PENDING → (waits) → PROCESSING → SETTLED |

### Key System Behaviors
```
1. Trade Entry:
   - Backdated: settle_date < today → queued for immediate EOD processing
   - Same-day:  settle_date = today → queued for today's EOD
   - Future:    settle_date > today → queued, waits until settle_date

2. EOD Settlement:
   - Processes all trades WHERE settle_date <= current_eod_date
   - Ordered by settle_date ASC, then queue_id ASC
   - Each trade updates position, which affects subsequent trades

3. Validation:
   - BUY: Always valid (no quantity check needed)
   - SELL: Validates against position AT SETTLEMENT DATE
     - Backdated SELL: Checks historical position
     - Future SELL: Checks current position (warning if other pending sells)
```

---

## SQL Implementation Reference

### AVP Calculation in Step 6 (EOD Settlement)

```sql
-- Quantity after trade
CASE
  WHEN trade_type = 'BUY'  THEN q_prev + q_trd
  WHEN trade_type = 'SELL' THEN q_prev - q_trd
  ELSE q_prev
END AS qty_after,

-- Average cost after trade (unchanged on SELL)
CASE
  WHEN trade_type = 'BUY' THEN
    (tc_prev + (q_trd * p_trd) + charges) / (q_prev + q_trd)
  ELSE ac_prev  -- SELL: avg cost unchanged
END AS ac_after,

-- Total cost after trade
CASE
  WHEN trade_type = 'BUY' THEN
    tc_prev + (q_trd * p_trd) + charges
  WHEN trade_type = 'SELL' THEN
    tc_prev * (q_prev - q_trd) / q_prev
  ELSE tc_prev
END AS tc_after,

-- Realized P&L (only changes on SELL)
CASE
  WHEN trade_type = 'SELL' THEN
    rp_prev + (q_trd * (p_trd - ac_prev))
  ELSE rp_prev
END AS rp_after,

-- Position status
CASE
  WHEN trade_type = 'BUY' THEN 'OPEN'
  WHEN trade_type = 'SELL' AND qty_after <= 0 THEN 'CLOSED'
  ELSE 'OPEN'
END AS status
```

---

## Summary

| Operation | Quantity | Average Cost | Total Cost | Realized P&L |
|-----------|----------|--------------|------------|--------------|
| **BUY** | Increases | Recalculated (weighted avg) | Increases | No change |
| **SELL** | Decreases | No change | Decreases proportionally | Increases/Decreases |

### Key Points:
1. **Average Cost** only changes on BUY trades (weighted average)
2. **Realized P&L** only changes on SELL trades (profit/loss crystallized)
3. **Total Cost** increases on BUY, decreases proportionally on SELL
4. **Position closes** when quantity reaches zero
5. **Backdated trades** are processed in settlement date order, recalculating subsequent positions
6. **Future-dated trades** remain pending until their settlement date

---

## Use Case Index

| # | Use Case | Type | Key Concept |
|---|----------|------|-------------|
| 1 | Simple BUY (Opening) | BUY | New position creation |
| 2 | Averaging Up | BUY | Additional purchase at higher price |
| 3 | Averaging Down | BUY | Additional purchase at lower price |
| 4 | Partial SELL (Profit) | SELL | Realize gain on partial sale |
| 5 | Partial SELL (Loss) | SELL | Realize loss on partial sale |
| 6 | Full SELL (Closing) | SELL | Close position completely |
| 7 | Complete Trading Cycle | Mixed | Full lifecycle example |
| 8 | Multiple Trades Same Day | Mixed | Intraday trading |
| 9 | Insufficient Quantity | SELL | Validation failure |
| 10 | No Position | SELL | Validation failure |
| 11 | Backdated BUY | BUY | Historical entry |
| 12 | Backdated SELL | SELL | Historical correction |
| 13 | Future-Dated BUY | BUY | T+N settlement |
| 14 | Future-Dated SELL | SELL | Forward sale |
| 15 | Mixed Backdated/Future | Mixed | Complex scenario |

---

*Document Version: 1.1*
*Last Updated: 2026-03-16*
*System: CIS Trade Hive - EOD Settlement Processing*
