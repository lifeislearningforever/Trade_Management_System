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

---

*Document Version: 1.0*
*Last Updated: 2026-03-16*
*System: CIS Trade Hive - EOD Settlement Processing*
