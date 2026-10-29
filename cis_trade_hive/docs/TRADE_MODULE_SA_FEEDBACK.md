# Trade Module - SA Team Feedback Implementation Plan

## Document Info
| Field | Value |
|-------|-------|
| **Document Type** | Implementation Plan |
| **Module** | Trade |
| **Created Date** | 2026-03-04 |
| **Status** | In Progress |
| **Feedback Source** | SA Team Review |

---

## Executive Summary

This document captures the SA team's feedback on the Trade module and outlines the implementation plan. The feedback is categorized into **UI Changes/Refinements** and **Functional/Usability Issues**.

---

## Feedback Summary

### Category 1: UI Changes / Refinements

| # | Feedback Item | Priority | Status |
|---|--------------|----------|--------|
| 1 | Introduce Pending Validation button/screen applicable only for CIS trades (exclude GMP) | High | ✅ Done |
| 2 | Add Source and Settlement Date as searchable fields | Medium | ✅ Done |
| 3 | Remove Add Long, Deliver Long, Reduction Basis, and Income from Trade Type | High | ✅ Done |
| 4 | Rename "Deal #" to "Trade ID" | Medium | ✅ Done |
| 5 | Display Quantity and Price together | Low | Pending |
| 6 | Show currency for Amount labeled as "Amount (FC - Security Currency)" and add "Amount (LC - Portfolio Currency)" | Medium | Pending |
| 7 | Move Custodian and Broker fields to the first screen/page | Medium | ✅ Already Done |
| 8 | Provide an option to copy the Trade ID once the trade is booked | Low | Pending |

### Category 2: Functional / Usability Issues

| # | Feedback Item | Priority | Status |
|---|--------------|----------|--------|
| 9 | Remove redundant portfolio validation message when selecting portfolio | Medium | Pending |
| 10 | For Security, do not display text within brackets () | Medium | Pending |
| 11 | Trade Status should NOT be an editable/input field | High | ✅ Done |
| 12 | Unable to see UOB KAY HIAN PL* and UOB NOMINEES PL* - investigate missing portfolios | High | Pending |
| 13 | Remove Accrued Interest, Cash Balance, and Amortization/Accrual Method fields | Medium | ✅ Done |
| 14 | Auto-route Initial and Modified trades to Pending Validation (no separate "Send to Validation" button) | High | Pending |
| 15 | In Pending Validation, display only CIS trades (exclude GMP trades even if status is Initial) | High | ✅ Done |
| 16 | Allow Edit and Cancel actions for Validated, Modified, and Settled trades | Medium | Pending |
| 17 | Fix error when editing Initial status trade | Critical | Pending |

---

## Detailed Implementation Plan

### Phase 1: Critical Fixes (Immediate)

#### 1.1 Fix Edit Error on Initial Status Trade (#17)
**Problem:** Editing a trade in INITIAL status throws an error.

**Root Cause Analysis Required:**
- Check `trade_edit` view in `trade/views.py`
- Verify `MAKER_EDITABLE_STATUSES` includes 'INITIAL'
- Check repository update method

**Files to Modify:**
- `trade/views.py` - `trade_edit()` function
- `trade/repositories/trade_kudu_repository.py` - if needed

**Implementation:**
```python
# Verify MAKER_EDITABLE_STATUSES includes INITIAL
MAKER_EDITABLE_STATUSES = ['INITIAL', 'MODIFIED']
```

---

### Phase 2: High Priority Changes

#### 2.1 Remove Unused Trade Types (#3)
**Requirement:** Remove ADD_LONG, DELIVER_LONG, REDUCTION_BASIS, INCOME from Trade Type dropdown.

**Files to Modify:**
- `trade/services/trade_dropdown_service.py` - Filter trade types
- `templates/trade/trade_list.html` - Remove badge rendering for these types

**Current Trade Types:**
- BUY ✓ (Keep)
- SELL ✓ (Keep)
- ADD_LONG ✗ (Remove)
- DELIVER_LONG ✗ (Remove)
- REDUCTION_BASIS ✗ (Remove)
- INCOME ✗ (Remove)
- SPLIT_TRANSACTION (Keep if needed)

#### 2.2 Trade Status Not Editable (#11)
**Requirement:** Trade Status should be display-only, not an input field.

**Files to Modify:**
- `templates/trade/trade_form.html` - Change from `<select>` to read-only display

**Current Code:**
```html
<select class="form-select" name="trade_status" id="trade_status">
```

**New Code:**
```html
<input type="text" class="form-control" value="{{ trade.trade_status }}" readonly disabled>
<!-- Or display as badge -->
<span class="badge badge-info">{{ trade.trade_status|default:"INITIAL" }}</span>
```

#### 2.3 Auto-Route to Pending Validation (#14)
**Requirement:** Automatically route INITIAL and MODIFIED trades to PENDING_VALIDATION when saved. Remove the separate "Send to Validation" button.

**Current Workflow:**
```
CREATE → INITIAL → [Manual Submit] → PENDING_VALIDATION → VALIDATED → SETTLED
```

**New Workflow:**
```
CREATE → PENDING_VALIDATION → VALIDATED → SETTLED
UPDATE → PENDING_VALIDATION → VALIDATED → SETTLED
```

**Files to Modify:**
- `trade/views.py` - `trade_create()` and `trade_edit()`
- `trade/repositories/trade_kudu_repository.py` - `insert_trade()` and `update_trade()`
- `templates/trade/trade_list.html` - Remove "Submit for Validation" button
- `templates/trade/trade_detail.html` - Remove "Submit for Validation" button

**Implementation:**
```python
# In trade_create()
trade_data['status'] = TradeKuduRepository.STATUS_PENDING_VALIDATION  # Not INITIAL

# In trade_edit()
updated_data['status'] = TradeKuduRepository.STATUS_PENDING_VALIDATION  # Not MODIFIED
```

#### 2.4 Pending Validation: CIS Only (#1, #15)
**Requirement:** Show only CIS trades in Pending Validation screen (exclude GMP trades).

**Files to Modify:**
- `trade/repositories/trade_kudu_repository.py` - `get_pending_validation_trades()`

**Current Query:**
```python
WHERE status = 'PENDING_VALIDATION' AND is_deleted = FALSE
```

**New Query:**
```python
WHERE status = 'PENDING_VALIDATION' AND is_deleted = FALSE AND UPPER(src_system) = 'CIS'
```

#### 2.5 Investigate Missing Portfolios (#12)
**Requirement:** UOB KAY HIAN PL* and UOB NOMINEES PL* not visible in dropdown.

**Investigation Steps:**
1. Query `cis_portfolio` table for these portfolios
2. Check if they have valid status (ACTIVE, APPROVED, etc.)
3. Check `get_valid_portfolios()` method filters

**SQL to Run:**
```sql
SELECT portfolio_short_name, status, is_deleted
FROM gmp_cis.cis_portfolio
WHERE portfolio_short_name LIKE 'UOB%';
```

---

### Phase 3: Medium Priority Changes

#### 3.1 Add Source and Settlement Date Filters (#2)
**Requirement:** Add Source (src_system) and Settlement Date as searchable fields.

**Files to Modify:**
- `templates/trade/trade_list.html` - Add filter dropdowns
- `trade/views.py` - `trade_list()` - Add filter parameters
- `trade/repositories/trade_kudu_repository.py` - `get_all_trades_multi_filter()`

**New Filters:**
```html
<!-- Source Filter -->
<div class="col-md-2">
    <label class="form-label">Source</label>
    <select class="form-select" name="src_system">
        <option value="">All Sources</option>
        <option value="CIS">CIS</option>
        <option value="GMP">GMP</option>
    </select>
</div>

<!-- Settlement Date Range -->
<div class="col-md-2">
    <label class="form-label">Settle Date From</label>
    <input type="date" class="form-control" name="settle_date_from">
</div>
<div class="col-md-2">
    <label class="form-label">Settle Date To</label>
    <input type="date" class="form-control" name="settle_date_to">
</div>
```

#### 3.2 Rename "Deal #" to "Trade ID" (#4)
**Requirement:** Rename column header from "Deal #" to "Trade ID".

**Files to Modify:**
- `templates/trade/trade_list.html` - Column header
- `templates/trade/trade_detail.html` - Labels
- `templates/trade/pending_approvals.html` - Column header

**Changes:**
```html
<!-- Old -->
<th>Deal #</th>

<!-- New -->
<th>Trade ID</th>
```

#### 3.3 Amount Display with Currency Labels (#6)
**Requirement:**
- Show "Amount (FC - Security Currency)" for foreign currency amount
- Add new field "Amount (LC - Portfolio Currency)" for local currency

**Files to Modify:**
- `templates/trade/trade_form.html` - Add LC Amount field
- `templates/trade/trade_list.html` - Update column display
- `trade/views.py` - Calculate LC amount using FX rate

**Implementation:**
```html
<div class="col-md-3">
    <label class="form-label">Amount (FC - {{ trade.currency_code }})</label>
    <input type="number" class="form-control" value="{{ trade.total_amount }}" readonly>
</div>
<div class="col-md-3">
    <label class="form-label">Amount (LC - {{ portfolio_currency }})</label>
    <input type="number" class="form-control" value="{{ trade.total_amount_lc }}" readonly>
    <small class="text-muted">FX Rate: {{ trade.fx_rate }}</small>
</div>
```

#### 3.4 Remove Redundant Validation Message (#9)
**Requirement:** Remove the redundant portfolio validation status message.

**Current Message:**
> "Trading (status: SETTLED). Portfolio 'UOB GLOBAL CAP' is valid for trading (status: SETTLED)."

**Files to Modify:**
- `templates/trade/trade_form.html` - Simplify validation message
- JavaScript validation handler

**New Behavior:**
- Show only status icon (✓ or ✗)
- Show simple "Valid" or "Invalid" message
- Remove redundant status information

#### 3.5 Security Display Without Brackets (#10)
**Requirement:** Don't display text within brackets () for security names.

**Files to Modify:**
- `trade/services/trade_dropdown_service.py` - Clean security labels
- Or handle in template with filter

**Implementation Option 1 - Template Filter:**
```html
{{ trade.security_label|cut:"("|cut:")" }}
```

**Implementation Option 2 - Service Layer:**
```python
def get_securities(self, search=None):
    # ... existing code ...
    # Clean label - remove text in brackets
    import re
    label = re.sub(r'\s*\([^)]*\)', '', security_name)
```

#### 3.6 Remove Unnecessary Fields (#13)
**Requirement:** Remove Accrued Interest, Cash Balance, and Amortization/Accrual Method fields.

**Files to Modify:**
- `templates/trade/trade_form.html` - Remove/hide these fields

**Fields to Remove:**
1. `accrued_interest` - Remove from Costs & Fees section
2. `cash_balance` - Remove from GL & Settlement section
3. `amor_accr_method` - Remove from Settlement section

**Note:** Keep fields in database for backward compatibility, just hide from UI.

#### 3.7 Allow Edit/Cancel for More Statuses (#16)
**Requirement:** Allow Edit and Cancel actions for VALIDATED, MODIFIED, and SETTLED trades.

**Current Behavior:**
```python
MAKER_EDITABLE_STATUSES = ['INITIAL', 'MODIFIED']
```

**New Behavior:**
```python
MAKER_EDITABLE_STATUSES = ['INITIAL', 'MODIFIED', 'VALIDATED', 'SETTLED']
```

**Files to Modify:**
- `trade/repositories/trade_kudu_repository.py` - Update `MAKER_EDITABLE_STATUSES`
- `trade/views.py` - Update `can_edit` and `can_cancel` logic

**Warning:** Editing SETTLED trades may require position recalculation. Need to confirm with SA team.

---

### Phase 4: Low Priority Changes

#### 4.1 Display Quantity and Price Together (#5)
**Requirement:** Display Quantity and Price in the same table cell or adjacent columns.

**Files to Modify:**
- `templates/trade/trade_list.html` - Combine columns

**Option 1 - Combined Cell:**
```html
<td class="text-end">{{ trade.quantity|floatformat:2 }} @ {{ trade.price|floatformat:4 }}</td>
```

**Option 2 - Adjacent with Visual Connection:**
```html
<td class="text-end border-end-0">{{ trade.quantity|floatformat:2 }}</td>
<td class="text-end border-start-0">{{ trade.price|floatformat:4 }}</td>
```

#### 4.2 Copy Trade ID Button (#8)
**Requirement:** Provide option to copy Trade ID to clipboard after trade is booked.

**Files to Modify:**
- `templates/trade/trade_detail.html` - Add copy button
- Add JavaScript copy functionality

**Implementation:**
```html
<span class="trade-id">
    {{ trade.trade_id }}
    <button class="btn btn-sm btn-outline-secondary" onclick="copyTradeId('{{ trade.trade_id }}')" title="Copy Trade ID">
        <i class="bi bi-clipboard"></i>
    </button>
</span>

<script>
function copyTradeId(tradeId) {
    navigator.clipboard.writeText(tradeId).then(function() {
        // Show toast notification
        showToast('Trade ID copied to clipboard!');
    });
}
</script>
```

---

## Implementation Priority Matrix

```
┌─────────────────────────────────────────────────────────────────┐
│                    IMPLEMENTATION PRIORITY                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  CRITICAL (Do First)                                            │
│  ├── #17: Fix edit error on Initial status                     │
│                                                                  │
│  HIGH PRIORITY (Phase 2)                                        │
│  ├── #3: Remove unused trade types                              │
│  ├── #11: Trade Status read-only                                │
│  ├── #14: Auto-route to Pending Validation                      │
│  ├── #1, #15: CIS-only Pending Validation                       │
│  └── #12: Investigate missing portfolios                        │
│                                                                  │
│  MEDIUM PRIORITY (Phase 3)                                      │
│  ├── #2: Add Source & Settlement Date filters                   │
│  ├── #4: Rename Deal # to Trade ID                              │
│  ├── #6: Amount with currency labels (FC/LC)                    │
│  ├── #9: Remove redundant validation message                    │
│  ├── #10: Security display without brackets                     │
│  ├── #13: Remove unnecessary fields                             │
│  └── #16: Allow Edit/Cancel for more statuses                   │
│                                                                  │
│  LOW PRIORITY (Phase 4)                                         │
│  ├── #5: Display Qty & Price together                           │
│  └── #8: Copy Trade ID button                                   │
│                                                                  │
│  ALREADY DONE ✓                                                 │
│  └── #7: Move Custodian and Broker to first screen              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files Summary

| File | Changes Required |
|------|------------------|
| `trade/views.py` | Edit error fix, auto-route, filter params |
| `trade/repositories/trade_kudu_repository.py` | CIS filter, editable statuses |
| `trade/services/trade_dropdown_service.py` | Remove trade types, clean security labels |
| `templates/trade/trade_form.html` | Remove fields, status read-only |
| `templates/trade/trade_list.html` | Rename columns, add filters, remove buttons |
| `templates/trade/trade_detail.html` | Rename labels, add copy button |
| `templates/trade/pending_approvals.html` | CIS badge filter |

---

## Testing Checklist

### Phase 1: Critical Fixes
- [ ] Create a new trade - verify no errors
- [ ] Edit an INITIAL status trade - verify no errors
- [ ] Save edited trade - verify status updates correctly

### Phase 2: High Priority
- [ ] Trade Type dropdown shows only BUY, SELL
- [ ] Trade Status field is read-only
- [ ] New trades auto-route to PENDING_VALIDATION
- [ ] Pending Validation screen shows only CIS trades
- [ ] Missing portfolios (UOB KAY HIAN, UOB NOMINEES) are visible

### Phase 3: Medium Priority
- [ ] Source filter works correctly
- [ ] Settlement Date filter works correctly
- [ ] "Trade ID" label appears instead of "Deal #"
- [ ] Amount shows FC and LC with currency codes
- [ ] Portfolio validation shows simple message
- [ ] Security names don't show text in brackets
- [ ] Hidden fields (Accrued Interest, etc.) not visible
- [ ] Edit/Cancel works for VALIDATED and SETTLED trades

### Phase 4: Low Priority
- [ ] Quantity and Price displayed together
- [ ] Copy Trade ID button works

---

## Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| SA Team Lead | | | |
| Developer | | | |
| QA | | | |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-03-04 | Claude | Initial version from SA feedback |
