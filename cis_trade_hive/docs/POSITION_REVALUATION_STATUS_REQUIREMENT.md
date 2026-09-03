# Position Revaluation Status Requirement

**Status:** SA CONFIRMED - READY FOR IMPLEMENTATION
**Date:** 2026-03-26
**Author:** Development Team
**SA Feedback Date:** 2026-03-26

---

## Overview

Add logic to check portfolio `revaluation_status` when calculating trade position LC (Local Currency) values.

---

## Data Source

**Table:** `gmp_cis.cis_portfolio`
**Column:** `revaluation_status`
**Values:** `REVALUED` or `NON-REVALUED`

---

## SA Confirmed Logic

### For REVALUED Portfolios

When `cis_portfolio.revaluation_status = 'REVALUED'`:
- **Apply FX conversion** for LC values
- Positions **marked-to-market** using current FX rates
- LC values calculated by multiplying FC values with current FX rate

| Field | Formula |
|-------|---------|
| `average_cost_lc` | `average_cost * fx_rate` |
| `total_cost_lc` | `total_cost * fx_rate` (or `average_cost_lc * qty`) |
| `realized_pnl_lc` | `realized_pnl * fx_rate` |
| `market_value_lc` | `market_value * fx_rate` (or `qty * market_price * fx_rate`) |
| `unrealized_pnl_lc` | `market_value_lc - total_cost_lc` |

### For NON-REVALUED Portfolios

When `cis_portfolio.revaluation_status = 'NON-REVALUED'`:
- **Use historical LC amount from trade** (NOT `LC = FC`)
- Positions stay at **historical FC** - the LC values use the LC amount captured at trade time
- Cost values remain at historical rates, only market value uses current FX

| Field | Formula |
|-------|---------|
| `average_cost_lc` | Use LC amount from trade (historical rate at trade time) |
| `total_cost_lc` | `average_cost_lc * qty` |
| `realized_pnl_lc` | Use LC amount from trade (historical rate at trade time) |
| `market_value_lc` | `market_value * fx_rate` (current rate for market value) |
| `unrealized_pnl_lc` | `market_value_lc - total_cost_lc` |

---

## Daily Recalculation (BOTH Cases)

**Important:** For BOTH REVALUED and NON-REVALUED portfolios, the following fields need to be recalculated **every day**:

| Field | Daily Formula |
|-------|---------------|
| `market_value` | `qty * market_price` (current market price) |
| `unrealized_pnl` | `market_value - total_cost` |
| `market_value_lc` | `market_value * fx_rate` (current FX rate) |
| `unrealized_pnl_lc` | `market_value_lc - total_cost_lc` |

**Note:** All formulas using FX rate need to recalculate daily for accurate mark-to-market.

---

## Key Difference Summary

| Aspect | REVALUED | NON-REVALUED |
|--------|----------|--------------|
| Cost LC Values | Current FX rate | Historical FX rate (from trade) |
| Market Value LC | Current FX rate | Current FX rate |
| P&L LC | Fully revalued | Cost at historical, market at current |

---

## Example Scenarios

### Scenario 1: NON-REVALUED Portfolio

```
Portfolio: ABC Fund (SGD base, NON-REVALUED)
Security: AAPL (USD)
Trade: BUY 100 shares @ $150 USD
Historical FX at trade time: USD/SGD = 1.30
Current FX: USD/SGD = 1.35
Current Market Price: $160 USD

FC Values (USD):
- average_cost = 150 USD
- total_cost = 15,000 USD
- market_value = 16,000 USD (100 * 160)
- unrealized_pnl = 1,000 USD

LC Values (SGD) - HISTORICAL COST, CURRENT MARKET:
- average_cost_lc = 195 SGD (150 * 1.30 historical rate from trade)
- total_cost_lc = 19,500 SGD (195 * 100, stays at historical)
- market_value_lc = 21,600 SGD (16,000 * 1.35 current rate)
- unrealized_pnl_lc = 2,100 SGD (21,600 - 19,500)
```

### Scenario 2: REVALUED Portfolio

```
Portfolio: XYZ Fund (SGD base, REVALUED)
Security: AAPL (USD)
Trade: BUY 100 shares @ $150 USD
Current FX: USD/SGD = 1.35
Current Market Price: $160 USD

FC Values (USD):
- average_cost = 150 USD
- total_cost = 15,000 USD
- market_value = 16,000 USD (100 * 160)
- unrealized_pnl = 1,000 USD

LC Values (SGD) - FULLY REVALUED WITH CURRENT FX:
- average_cost_lc = 202.50 SGD (150 * 1.35 current rate)
- total_cost_lc = 20,250 SGD (15,000 * 1.35 current rate)
- market_value_lc = 21,600 SGD (16,000 * 1.35 current rate)
- unrealized_pnl_lc = 1,350 SGD (1,000 * 1.35 current rate)
```

---

## Implementation Requirements

### Data Requirements

1. **Trade Table**: Need to store `total_amount_lc` (LC amount at trade time) for NON-REVALUED calculations
2. **Position Table**: Store both FC and LC values
3. **Portfolio Table**: `revaluation_status` column must be populated

### Files to Modify

| File | Changes |
|------|---------|
| `trade/services/position_service.py` | Add revaluation_status check in `_save_position()` |
| `trade/repositories/trade_validation_repository.py` | Add method to fetch portfolio revaluation_status |
| `cis_trade` table | Ensure `total_amount_lc` is captured at trade time |

### Code Changes (Pseudocode)

```python
def _save_position(self, position_data, updated_by):
    portfolio_id = position_data['portfolio_short_name']
    revaluation_status = self._get_portfolio_revaluation_status(portfolio_id)

    # Get current FX rate (always needed for market_value_lc)
    fx_rate = self._get_fx_rate(security_currency, portfolio_currency)

    # Market value always uses current price and FX
    market_value = qty * current_market_price
    market_value_lc = market_value * fx_rate

    if revaluation_status == 'NON-REVALUED':
        # Cost values use historical LC from trade
        average_cost_lc = trade_data.get('average_cost_lc')  # From trade at historical rate
        total_cost_lc = average_cost_lc * qty
        # Unrealized P&L = current market LC - historical cost LC
        unrealized_pnl_lc = market_value_lc - total_cost_lc
        # Realized P&L uses historical LC from trade
        realized_pnl_lc = trade_data.get('realized_pnl_lc')  # From trade
    else:  # REVALUED
        # All values use current FX rate
        average_cost_lc = average_cost * fx_rate
        total_cost_lc = total_cost * fx_rate
        realized_pnl_lc = realized_pnl * fx_rate
        unrealized_pnl_lc = market_value_lc - total_cost_lc
```

---

## EOD Batch Job Requirements

An EOD (End-of-Day) batch job is required to recalculate daily:

1. Fetch latest market prices for all securities
2. Fetch latest FX rates
3. For each open position:
   - Recalculate `market_value = qty * market_price`
   - Recalculate `unrealized_pnl = market_value - total_cost`
   - Recalculate `market_value_lc = market_value * fx_rate`
   - Recalculate `unrealized_pnl_lc = market_value_lc - total_cost_lc`

---

## Sign-off

| Role | Name | Date | Approval |
|------|------|------|----------|
| SA Lead | Prakash HOSALLI | 2026-03-26 | [x] Approved |
| Dev Lead | | | [ ] Reviewed |
| QA Lead | | | [ ] Test Plan Ready |

---

## Notes

- SA confirmed on 2026-03-26 via Teams chat
- Key clarification: NON-REVALUED uses historical LC from trade, NOT `LC = FC`
- Market value LC always uses current FX rate (both cases)
- Daily recalculation required for market value and unrealized P&L
