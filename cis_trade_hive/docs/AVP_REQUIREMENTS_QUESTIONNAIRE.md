# AVP Position Logic - Requirements Questionnaire

## Document Info
| Field | Value |
|-------|-------|
| **Document Type** | Requirements Gathering |
| **Module** | Trade Position / AVP |
| **Created Date** | 2026-03-03 |
| **Status** | Pending Review |
| **Review By** | SA Team, Business Team |

---

## Instructions

Please review each section and provide answers/decisions. Mark your choice with **[X]** or provide details in the **Answer** field.

---

## Section 1: Position Calculation Timing

### Q1.1: When should position be calculated?

**Current Behavior:** Position is calculated immediately when trade is created (synchronous, blocking)

**Options:**
- [ ] **A. Immediate (Sync)** - Calculate position during trade save (current behavior, slower)
- [x] **B. Background (Async)** - Queue position calculation, process in background (faster trade save)
- [ ] **C. Scheduled Batch** - Calculate all positions at end of day
- [ ] **D. Hybrid** - Immediate for same-day settle, background for future-dated

**Answer:** _______________________

**Notes:** _______________________

---

### Q1.2: If async processing, what is acceptable delay?

- [ ] Less than 1 minute
- [x] Less than 5 minutes
- [ ] Less than 15 minutes
- [ ] End of day is acceptable

**Answer:** _______________________

---

### Q1.3: Should users see position status in trade screen?

- [ ] **Yes** - Show "Position: Processing...", "Position: Updated", "Position: Failed"
- [x] **No** - Position processing is transparent to users

**Answer:** _______________________

---

## Section 2: Settlement Date Logic

### Q2.1: Which date drives position calculation?

**Options:**
- [ X] **A. Trade Date** - Position reflects on the day trade is executed
- [ x] **B. Settle Date** - Position reflects on settlement date
- [ ] **C. User Choice** - Let user select per trade
- [ ] **D. Configurable** - System-wide setting

**Answer:** _______________________

---

### Q2.2: How to handle FUTURE settlement dates (T+1, T+2, T+3)?

**Example:** Trade executed today (2026-03-03), settles on 2026-03-05

**Options:**
- [ ] **A. Immediate** - Update position today, ignore settle date
- [ ] **B. Pending Position** - Create "PENDING" position, activate on settle date
- [ x] **C. Scheduled** - Don't create position until settle date arrives
- [ ] **D. Both Views** - Trade date position AND settle date position

**Answer:** _______________________

**If B or C:** Should pending positions be visible in position list?
- [ ] Yes, with "PENDING" status
- [ x] No, hide until settled

**Answer:** _______________________

---

### Q2.3: How to handle BACKDATED settlement dates?

**Example:** Today is 2026-03-03, entering trade with settle date 2026-02-28

**Options:**
- [ ] **A. Not Allowed** - Reject backdated settlements
- [ x] **B. Allowed with Limit** - Allow up to X days back
- [ ] **C. Allowed Unlimited** - Any past date allowed
- [ ] **D. Requires Approval** - Backdated trades need checker approval

**If B, maximum days allowed:** pervious month end

**Answer:** _______________________

---

### Q2.4: Backdated trade impact on existing positions?

**Scenario:** Position on 2026-03-03 shows qty=100. User enters backdated BUY 50 with settle date 2026-02-28.

**Options:**
- [x ] **A. Recalculate All** - Recalculate positions from 2026-02-28 to today
- [ ] **B. Append Only** - Just add to current position, don't recalculate history
- [ ] **C. Reject** - Don't allow if it would affect existing positions

**Answer:** _______________________

---

## Section 3: Trade Types & Position Impact

### Q3.1: Which trade types affect position?

| Trade Type | Affects Position? | Notes |
|------------|-----------------|-------|
| BUY | [x] Yes [ ] No  | |
| SELL | [x] Yes [ ] No  | |
| ADD_LONG | [ ] Yes [ ] No  | |
| DELIVER_LONG | [ ] Yes [ ] No  | |
| REDUCTION_BASIS | [ ] Yes [ ] No  | |
| INCOME | [ ] Yes [ ] No  | |
| SPLIT_TRANSACTION | [ ] Yes [ ] No  | |

---

### Q3.2: How to handle SELL quantity > position quantity?

**Example:** Position has 100 shares, user tries to SELL 150 shares

**Options:**
- [x] **A. Reject** - Error: "Insufficient quantity"
- [ ] **B. Allow Short** - Create short position (-50 shares)
- [ ] **C. Partial Fill** - Only sell available (100), reject remainder
- [ ] **D. Warning Only** - Allow with warning message

**Answer:** _______________________

---

### Q3.3: Is SHORT SELLING allowed?

- [ ] **Yes** - Allow negative positions
- [x] **No** - Positions must always be >= 0

**If Yes, any limits on short quantity?** _______________________

---

### Q3.4: DELIVER_LONG (Transfer) handling?

**Scenario:** Transfer 100 shares from Portfolio A to Portfolio B

**Options:**
- [ ] **A. Two Trades** - DELIVER_LONG in A, separate BUY/receive in B
- [ ] **B. Single Trade** - One trade affects both portfolios
- [ ] **C. Manual** - User manually adjusts both portfolios

**Cost basis transfer:**
- [ ] Transfer at original average cost
- [ ] Transfer at current market price
- [ ] Transfer at zero cost
- [ ] User specifies transfer price

**Answer:** NA

---

## Section 4: Average Cost Calculation

### Q4.1: AVP calculation method?

**Options:**
- [x] **A. Weighted Average** - (Old Value + New Value) / Total Qty
- [ ] **B. FIFO** - First In, First Out
- [ ] **C. LIFO** - Last In, First Out
- [ ] **D. Specific Lot** - User selects which lots to sell
- [ ] **E. Configurable per Portfolio** - Different methods per portfolio

**Answer:** _______________________

---

### Q4.2: What costs are included in average cost?

| Cost Component | Include in Avg Cost? |
|----------------|----------------------|
| Trade Price | [ x] Yes [ ] No      |
| Commission | [ x] Yes [ ] No      |
| SEC Fee | [ x] Yes [ ] No      |
| Other Charges | [ x] Yes [ ] No      |


---

### Q4.3: Decimal precision for AVP?

- [ ] 2 decimal places
- [ ] 4 decimal places
- [ ] 6 decimal places
- [x ] 8 decimal places

**Answer:** _______________________

---

## Section 5: Multi-Currency

### Q5.1: Multi-currency support required?

- [ x] **Yes** - Track positions in both local (security) and base (portfolio) currency
- [ ] **No** - Single currency only

---

### Q5.2: FX rate source for conversions?

**Options:**
- [ ] **A. Trade FX Rate** - Use FX rate from trade entry
- [ ] **B. Daily Rate** - Use end-of-day FX rate
- [ ] **C. Real-time Rate** - Fetch current FX rate
- [ ] **D. User Input** - User specifies FX rate per trade

**Answer:** _______________________

---

### Q5.3: FX rate for position valuation?

**When calculating market value in base currency:**
- [ ] Use original trade FX rate (locked)
- [ x] Use current/latest FX rate (floating)
- [ ] Both (show FX P&L separately)

**Answer:** _______________________

---

### Q5.4: FX gain/loss tracking?

- [ ] **Yes** - Track currency gain/loss separately from position P&L
- [x ] **No** - Combined P&L only

**Answer:** _______________________

---

## Section 6: Corporate Actions

### Q6.1: Which corporate actions should affect positions?

| Corporate Action | Support? | Auto or Manual? |
|------------------|----------|-----------------|
| Stock Split | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Reverse Split | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Stock Dividend | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Cash Dividend | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Rights Issue | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Merger/Acquisition | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Spin-off | [ ] Yes [ ] No | [ ] Auto [ ] Manual |
| Name/Ticker Change | [ ] Yes [ ] No | [ ] Auto [ ] Manual |

---

### Q6.2: Dividend reinvestment (DRIP)?

- [ ] **Yes** - Support automatic dividend reinvestment
- [ ] **No** - Cash dividends only

**If Yes, reinvestment price:**
- [ ] Market price on pay date
- [ ] Discounted price (specify %)
- [ ] User specified

**Answer:** _______________________

---

## Section 7: Trade Amendments & Cancellations

### Q7.1: When can trades be amended?

| Trade Status | Allow Amendment? |
|--------------|------------------|
| INITIAL | [ ] Yes [ ] No |
| MODIFIED | [ ] Yes [ ] No |
| PENDING_VALIDATION | [ ] Yes [ ] No |
| VALIDATED | [ ] Yes [ ] No |
| SETTLED | [ ] Yes [ ] No |

---

### Q7.2: Which fields can be amended after position created?

| Field | Amendable?      | Recalculate Position? |
|-------|-----------------|-----------------------|
| Quantity | [ x] Yes [ ] No | [x ] Yes [ ] No       |
| Price | [ x] Yes [ ] No | [x ] Yes [ ] No       |
| Trade Date | [ x] Yes [ ] No | [ x] Yes [ ] No       |
| Settle Date | [ x] Yes [ ] No | [ x] Yes [ ] No       |
| Security | [ x] Yes [ ] No | [ x] Yes [ ] No       |
| Portfolio | [ x] Yes [ ] No | [ x] Yes [ ] No       |

---

### Q7.3: Trade cancellation impact?

**Options:**
- [ x] **A. Full Reversal** - Completely reverse position impact
- [ ] **B. Soft Delete** - Mark cancelled, keep position as-is
- [ ] **C. Correction Entry** - Create offsetting trade

**Answer:** _______________________

---

### Q7.4: Can SETTLED trades be cancelled?

- [ ] **Yes** - With full position recalculation
- [ ] **Yes** - But requires special approval
- [ x] **No** - Settled trades are final

**Answer:** _______________________

---

## Section 8: Position Corrections

### Q8.1: Allow manual position adjustments?

- [ ] **Yes** - Users can manually adjust positions
- [ x] **No** - Positions only from trades

**If Yes, who can adjust?**
- [ ] Any user
- [ ] Checker/Approver only
- [ ] Admin only

**Answer:** _______________________

---

### Q8.2: Position adjustment requires approval?

- [ ] **Yes** - Four-eyes principle for adjustments
- [ x] **No** - Direct adjustment allowed

**Answer:** _______________________

---

### Q8.3: Position reconciliation?

**Should system support position reconciliation with external systems?**
- [ x] **Yes** - Import external positions, highlight differences
- [ ] **No** - Not required

**Answer:** _______________________

---

## Section 9: Reporting & Audit

### Q9.1: Position history retention?

**How long to keep position version history?**
- [ ] 1 year
- [ ] 3 years
- [ ] 5 years
- [x ] 7 years
- [ ] Forever

**Answer:** _______________________

---

### Q9.2: What position reports are needed?

| Report | Required? | Frequency |
|--------|-----------|-----------|
| Current Positions | [ ] Yes [ ] No | |
| Position History | [ ] Yes [ ] No | |
| P&L Report | [ ] Yes [ ] No | |
| Realized P&L | [ ] Yes [ ] No | |
| Unrealized P&L | [ ] Yes [ ] No | |
| Position by Portfolio | [ ] Yes [ ] No | |
| Position by Security | [ ] Yes [ ] No | |
| Position by Currency | [ ] Yes [ ] No | |

---

### Q9.3: Audit trail requirements?

| Audit Item | Required? |
|------------|-----------|
| Who changed position | [ ] Yes [ ] No |
| When changed | [ ] Yes [ ] No |
| What changed (old/new values) | [ ] Yes [ ] No |
| Why changed (comments) | [ ] Yes [ ] No |
| Source trade reference | [ ] Yes [ ] No |

---

## Section 10: Performance & Scalability

### Q10.1: Expected data volumes?

| Metric | Expected Volume |
|--------|-----------------|
| Trades per day | |
| Active positions | |
| Position versions per month | |
| Concurrent users | |

---

### Q10.2: Performance requirements?

| Operation | Max Acceptable Time |
|-----------|---------------------|
| Trade save (without position) | |
| Position calculation | |
| Position list load | |
| Position history query | |

---

### Q10.3: Real-time position updates?

- [ ] **Yes** - Position list auto-refreshes
- [ x] **No** - Manual refresh acceptable

**If Yes, refresh interval:** _______________________

---

## Section 11: Integration

### Q11.1: External system integrations?

| System | Integration Required? | Direction |
|--------|----------------------|-----------|
| Trading System | [ ] Yes [ ] No | [ ] Import [ ] Export [ ] Both |
| Accounting System | [ ] Yes [ ] No | [ ] Import [ ] Export [ ] Both |
| Risk System | [ ] Yes [ ] No | [ ] Import [ ] Export [ ] Both |
| Reporting System | [ ] Yes [ ] No | [ ] Import [ ] Export [ ] Both |
| Custodian | [ ] Yes [ ] No | [ ] Import [ ] Export [ ] Both |

---

### Q11.2: Position data export format?

- [ ] CSV
- [ ] Excel
- [ ] JSON
- [ ] XML
- [ ] API only

---

## Section 12: Additional Requirements

### Q12.1: Any regulatory requirements affecting position calculation?

**Answer:** _______________________

---

### Q12.2: Any specific business rules not covered above?

**Answer:** _______________________

---

### Q12.3: Priority of features?

**Mark as: H (High), M (Medium), L (Low), N (Not Required)**

| Feature | Priority |
|---------|----------|
| Basic AVP calculation | H        |
| Multi-currency | M        |
| Future settlement | M        |
| Backdated settlement | ,        |
| Short selling | N        |
| Corporate actions | N        |
| Position corrections | M        |
| Trade amendments | M        |
| Async processing | M        |
| Real-time updates | M        |

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Business Analyst | | | |
| Solution Architect | | | |
| Product Owner | | | |
| Compliance | | | |
| Operations | | | |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-03 | Claude | Initial version |

---

**Please return completed questionnaire to the development team for implementation planning.**
