# AVP Corner Cases Analysis

## Settlement Types Overview

| Type | Condition | Queue | Processing |
|------|-----------|-------|------------|
| T+0 | settle_date = today | cis_position_queue | Async worker (< 5 min) |
| T+N (Future) | settle_date > today | cis_settlement_queue | EOD job on settle_date |
| T-N (Backdated) | settle_date < today | cis_position_queue + CHAIN_RECALC | Async worker + chain recalc |

---

## Corner Case 1: T+0 (Same Day Settlement)

### Scenario
User enters trade on 7th March with settle date 7th March.

### Flow
```
1. Trade saved to cis_trade
2. settlement_service.process_trade_settlement() called with async_mode=True
3. settle_date = today → settlement_type = 'T+0'
4. Queued to cis_position_queue (status=PENDING)
5. Position worker picks up within SLA (< 5 min)
6. calculate_position() called with position_date = settle_date
7. Position saved to cis_trade_position
```

### Test Cases
| # | Scenario | Expected Result |
|---|----------|-----------------|
| 1.1 | First BUY 100 @ 130 | Position: qty=100, avg=130, total=13000 |
| 1.2 | Second BUY 50 @ 150 (same day) | Position: qty=150, avg=136.67, total=20500 |
| 1.3 | SELL 30 @ 140 (same day) | Position: qty=120, avg=136.67, realized_pnl=100 |
| 1.4 | SELL all (close position) | Position: qty=0, status=CLOSED |
| 1.5 | SELL more than owned | ERROR: Insufficient quantity |
| 1.6 | SELL without position | ERROR: No position found |

### Code Status: ✅ IMPLEMENTED

---

## Corner Case 2: T+N (Future Settlement)

### Scenario
User enters trade on 7th March with settle date 12th March (T+5).

### Flow
```
1. Trade saved to cis_trade
2. settlement_service.process_trade_settlement() called
3. settle_date > today → settlement_type = 'FUTURE'
4. Queued to cis_settlement_queue (status=PENDING)
5. NO immediate position calculation
6. On 12th March, EOD job runs:
   - eod_settlement_process.sql OR
   - python manage.py process_settlements --date 2026-03-12
7. Position calculated and saved
```

### Test Cases
| # | Scenario | Expected Result |
|---|----------|-----------------|
| 2.1 | BUY 100 @ 130 (settle T+5) | Queued, position empty until settle date |
| 2.2 | Multiple T+5 trades same day | All queued, processed in order on settle date |
| 2.3 | T+5 trade, then T+0 trade same security | T+0 processed immediately, T+5 later |
| 2.4 | EOD runs on settle date | All pending trades for that date processed |
| 2.5 | EOD runs before settle date | Trade skipped (settle_date > processing_date) |

### Code Status: ✅ IMPLEMENTED

---

## Corner Case 3: T-N (Backdated Settlement)

### Scenario
User enters trade on 7th March with settle date 4th March (T-3).

### Flow
```
1. Trade saved to cis_trade
2. settlement_service.process_trade_settlement() called
3. settle_date < today → settlement_type = 'BACKDATED'
4. Queued to cis_position_queue with CHAIN_RECALC flag
5. Position worker picks up:
   a. DELETE existing positions from 4th March onwards
   b. Calculate backdated trade position (4th March)
   c. Get ALL trades from 4th March to today
   d. Recalculate each trade's position in chronological order
```

### Test Cases
| # | Scenario | Expected Result |
|---|----------|-----------------|
| 3.1 | Backdated BUY, no prior positions | New position created for backdate |
| 3.2 | Backdated BUY, existing position after | Chain recalculated from backdate |
| 3.3 | Backdated SELL, no position | ERROR: No position found |
| 3.4 | Backdated SELL, position exists after | Must have position BEFORE backdate |
| 3.5 | Multiple backdated trades same day | Processed in trade_id order |
| 3.6 | Backdated to before existing position | Becomes new first position |

### Example: Chain Recalculation
```
Existing:
  T1: 5th March - BUY 100 @ 130 → Position: qty=100, avg=130

User adds backdated:
  T3: 3rd March - BUY 50 @ 150

After recalculation:
  3rd March: T3 → Position: qty=50, avg=150
  5th March: T1 → Position: qty=150, avg=136.67 (recalculated!)
```

### Code Status: ✅ IMPLEMENTED (Fixed in recent commits)

---

## Corner Case 4: Mixed Scenario

### Scenario
Same portfolio+security with T+0, T+5, and T-3 trades.

### Example Timeline
```
Today: 7th March 2026

Trade Entry Order:
1. T1: BUY 100 @ 130, settle 7th March (T+0)
2. T2: BUY 50 @ 150, settle 12th March (T+5)
3. T3: BUY 50 @ 150, settle 4th March (T-3)
```

### Expected Processing
```
Step 1: T1 entered (T+0)
  - Queued to position_queue
  - Worker processes immediately
  - Position (7th March): qty=100, avg=130

Step 2: T2 entered (T+5)
  - Queued to settlement_queue
  - NO position change yet
  - Position still: qty=100, avg=130

Step 3: T3 entered (T-3)
  - Queued to position_queue with CHAIN_RECALC
  - Worker processes:
    1. DELETE positions from 4th March onwards (deletes T1's position)
    2. Calculate T3: qty=50, avg=150 (4th March)
    3. Recalculate T1: qty=150, avg=136.67 (7th March)

Final positions after all processing:
  4th March (T3): qty=50, avg=150, total=7500
  7th March (T1): qty=150, avg=136.67, total=20500

On 12th March (EOD job):
  Position (T2): qty=200, avg=140, total=28000
```

### Code Status: ✅ IMPLEMENTED

---

## Corner Case 5: SELL Scenarios

### 5.1 SELL with T+0
```
Existing: qty=100, avg=130
Trade: SELL 30 @ 150 (T+0)
Result: qty=70, avg=130 (unchanged), realized_pnl=600
```

### 5.2 SELL with T+5 (Future)
```
Existing: qty=100, avg=130
Trade: SELL 30 @ 150, settle 12th March
Result: Queued, position unchanged until 12th
On 12th: qty=70, avg=130, realized_pnl=600
```

### 5.3 SELL with T-3 (Backdated)
```
Position on 4th March: qty=100, avg=130
Position on 7th March: qty=150, avg=136.67 (after additional BUY)

User enters backdated SELL on 7th March:
Trade: SELL 20 @ 140, settle 4th March

Chain recalculation:
  4th March: qty=80, avg=130, realized_pnl=200
  7th March: qty=130, avg=??? (needs recalculation)
```

**ISSUE IDENTIFIED:** Backdated SELL with subsequent BUY may cause incorrect AVP calculation.

### Code Status: ⚠️ NEEDS REVIEW (Backdated SELL edge case)

---

## Corner Case 6: Position Closure and Reopening

### 6.1 Full Close then Reopen Same Day
```
Position: qty=100, avg=130
SELL 100 @ 150 (T+0) → CLOSED
BUY 50 @ 160 (T+0) → NEW position: qty=50, avg=160
```

### 6.2 Full Close T+0, Reopen T+5
```
Position: qty=100, avg=130
SELL 100 @ 150 (T+0) → CLOSED (7th March)
BUY 50 @ 160 (settle 12th March)
On 12th: NEW position: qty=50, avg=160
```

### Code Status: ✅ IMPLEMENTED (new position_id generated)

---

## Corner Case 7: Charges Impact

### Formula with Charges
```
BUY: new_avg_cost = (old_total_cost + (qty × price) + charges) / new_qty
```

### Example
```
BUY 100 @ 130, commission=10, sec_fee=5
Total cost = 100 × 130 + 15 = 13015
Avg cost = 13015 / 100 = 130.15
```

### Code Status: ✅ IMPLEMENTED

---

## Corner Case 8: Multi-Currency

### Scenario
Portfolio currency: SGD
Security currency: USD
FX rate: 1.35

### Calculation
```
BUY 100 @ $130 USD
Local (USD): avg=130, total=13000
Base (SGD): avg=130/1.35=96.30, total=9630
```

### Code Status: ✅ IMPLEMENTED (but FX rate lookup may need verification)

---

## Issues Identified

### Issue 1: Backdated SELL after BUY
**Severity:** Medium
**Scenario:** SELL backdated to before a subsequent BUY
**Problem:** The BUY recalculation needs to account for reduced base position

### Issue 2: Position ID consistency
**Severity:** Low
**Scenario:** Chain recalculation creates new version_ids
**Current:** ✅ position_id stays same, only version_id changes

### Issue 3: Concurrent trades
**Severity:** Low
**Scenario:** Two trades for same portfolio+security queued simultaneously
**Mitigation:** Queue processing is sequential (ORDER BY queued_at)

---

## Recommendations

1. **Add logging** for each position calculation step
2. **Add validation** for backdated SELL scenarios
3. **Add reconciliation report** to verify position consistency
4. **Consider locking** portfolio+security during chain recalculation
