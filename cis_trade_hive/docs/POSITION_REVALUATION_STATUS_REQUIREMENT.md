# Position Revaluation Status Requirement

**Status:** PENDING SA CONFIRMATION
**Date:** 2026-03-26
**Author:** Development Team

---

## Overview

Add logic to check portfolio `revaluation_status` when calculating trade position LC (Local Currency) values.

---

## Data Source

**Table:** `gmp_cis.cis_portfolio`
**Column:** `revaluation_status`
**Values:** `REVALUED` or `NON-REVALUED`

---

## Proposed Logic

### For NON-REVALUED Portfolios

When `cis_portfolio.revaluation_status = 'NON-REVALUED'`:
- **Skip FX conversion** for LC values
- LC values equal FC values (historical cost basis)
- Positions maintained at original trade cost in portfolio currency

| Field | Calculation |
|-------|-------------|
| `average_cost_lc` | = `average_cost` (no FX) |
| `total_cost_lc` | = `total_cost` (no FX) |
| `realized_pnl_lc` | = `realized_pnl` (no FX) |
| `unrealized_pnl_lc` | = `unrealized_pnl` (no FX) |
| `market_value_lc` | = `market_value` (no FX) |

### For REVALUED Portfolios

When `cis_portfolio.revaluation_status = 'REVALUED'`:
- **Apply FX conversion** for LC values
- Positions marked-to-market using current FX rates

| Field | Calculation |
|-------|-------------|
| `average_cost_lc` | = `average_cost * fx_rate` |
| `total_cost_lc` | = `total_cost * fx_rate` |
| `realized_pnl_lc` | = `realized_pnl * fx_rate` |
| `unrealized_pnl_lc` | = `unrealized_pnl * fx_rate` |
| `market_value_lc` | = `market_value * fx_rate` |

---

## Example Scenarios

### Scenario 1: NON-REVALUED Portfolio

```
Portfolio: ABC Fund (SGD base, NON-REVALUED)
Security: AAPL (USD)
Trade: BUY 100 shares @ $150 USD

FC Values (USD):
- total_cost = 15,000 USD
- realized_pnl = 0 USD

LC Values (SGD) - NO FX CONVERSION:
- total_cost_lc = 15,000 (same as FC)
- realized_pnl_lc = 0 (same as FC)

Note: Even though portfolio is SGD, LC values stored as-is without FX conversion
```

### Scenario 2: REVALUED Portfolio

```
Portfolio: XYZ Fund (SGD base, REVALUED)
Security: AAPL (USD)
Trade: BUY 100 shares @ $150 USD
FX Rate: USD/SGD = 1.35

FC Values (USD):
- total_cost = 15,000 USD
- realized_pnl = 0 USD

LC Values (SGD) - WITH FX CONVERSION:
- total_cost_lc = 15,000 * 1.35 = 20,250 SGD
- realized_pnl_lc = 0 * 1.35 = 0 SGD
```

---

## Implementation Impact

### Files to Modify

| File | Changes |
|------|---------|
| `trade/services/position_service.py` | Add revaluation_status check in `_save_position()` |
| `trade/repositories/trade_validation_repository.py` | Add method to fetch portfolio revaluation_status |

### Code Changes (Pseudocode)

```python
def _save_position(self, position_data, updated_by):
    # Get portfolio revaluation status
    portfolio_id = position_data['portfolio_short_name']
    revaluation_status = self._get_portfolio_revaluation_status(portfolio_id)

    if revaluation_status == 'NON-REVALUED':
        # Skip FX conversion - LC = FC
        average_cost_lc = average_cost
        total_cost_lc = total_cost
        realized_pnl_lc = realized_pnl
        unrealized_pnl_lc = unrealized_pnl
        market_value_lc = market_value
    else:  # REVALUED or default
        # Apply FX conversion
        average_cost_lc = average_cost * fx_rate
        total_cost_lc = total_cost * fx_rate
        realized_pnl_lc = realized_pnl * fx_rate
        unrealized_pnl_lc = unrealized_pnl * fx_rate
        market_value_lc = market_value * fx_rate
```

---

## Questions for SA

1. **Default Behavior:** If `revaluation_status` is NULL or empty, should we treat it as REVALUED (apply FX) or NON-REVALUED (skip FX)?

2. **Historical Positions:** Should existing positions be recalculated when portfolio revaluation_status changes?

3. **Mixed Currency:** For NON-REVALUED portfolios with securities in different currencies, are LC values still stored without conversion (effectively mixing currencies)?

4. **Reporting Impact:** How should reports handle NON-REVALUED portfolios where LC values may be in mixed currencies?

---

## Sign-off

| Role | Name | Date | Approval |
|------|------|------|----------|
| SA Lead | | | [ ] Approved / [ ] Rejected |
| Dev Lead | | | [ ] Reviewed |
| QA Lead | | | [ ] Test Plan Ready |

---

## Notes

- Implementation will begin after SA confirmation
- Unit tests will cover both REVALUED and NON-REVALUED scenarios
- Integration tests will verify end-to-end position calculation
