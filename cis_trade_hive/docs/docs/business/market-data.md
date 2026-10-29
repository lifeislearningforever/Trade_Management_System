# Market Data Guide

Access and manage foreign exchange rates and other market data for accurate portfolio valuation and risk management.

## Overview

Market Data module provides:

- **FX Rates**: Foreign exchange rates for currency conversion
- **Rate History**: Historical rate tracking
- **Real-time Dashboard**: Visual rate monitoring
- **Data Sources**: Integration with market data providers

## FX Rate Dashboard

**Navigation**: Market Data → FX Dashboard

### Key Features

**Visual Rate Display**:

- Latest FX rates for all currency pairs
- Percentage change indicators
- Trend sparklines
- Last update timestamp

**Quick Filters**:

- Filter by base currency
- Filter by quote currency
- Search currency pairs
- Sort by rate or change

**Rate Highlights**:

- 🟢 Green: Rate increased
- 🔴 Red: Rate decreased
- ⚪ Gray: No change

### Dashboard Layout

```
┌─────────────────────────────────────────────┐
│  FX Rate Dashboard                          │
├─────────────────────────────────────────────┤
│  Currency Pair  │  Rate  │  Change  │ Trend │
├─────────────────────────────────────────────┤
│  USD/SGD        │ 1.3450 │  +0.15%  │  ↗    │
│  EUR/SGD        │ 1.4520 │  -0.08%  │  ↘    │
│  GBP/SGD        │ 1.6780 │  +0.22%  │  ↗    │
└─────────────────────────────────────────────┘
```

## FX Rate List

**Navigation**: Market Data → FX Rates

### View Rates

**Default View**: Shows all active FX rates

**Columns**:

- Base Currency (e.g., USD)
- Quote Currency (e.g., SGD)
- Rate (e.g., 1.3450)
- Effective Date
- Bid/Ask Spread
- Source
- Last Updated

### Search & Filter

**Search Options**:

- Currency pair (e.g., "USD/SGD")
- Base currency (e.g., "USD")
- Quote currency (e.g., "SGD")

**Filters**:

- Date range (effective dates)
- Source (Bloomberg, Reuters, Manual)
- Rate type (Spot, Forward, Swap)

### Export Rates

**CSV Export**: Download FX rates

Format:
```csv
Base Currency,Quote Currency,Rate,Effective Date,Source,Last Updated
USD,SGD,1.3450,2025-12-27,Bloomberg,2025-12-27 09:00:00
EUR,SGD,1.4520,2025-12-27,Bloomberg,2025-12-27 09:00:00
GBP,SGD,1.6780,2025-12-27,Bloomberg,2025-12-27 09:00:00
```

## Rate Sources

### Bloomberg Integration

**Data Feed**: Real-time rates from Bloomberg

- **Update Frequency**: Every 15 minutes
- **Coverage**: 150+ currency pairs
- **Reliability**: 99.9% uptime
- **Delay**: < 2 seconds

### Reuters Integration

**Data Feed**: Market rates from Refinitiv

- **Update Frequency**: Every 30 minutes
- **Coverage**: 120+ currency pairs
- **Reliability**: 99.5% uptime
- **Delay**: < 5 seconds

### Manual Entry

**Custom Rates**: For special situations

- Exotic currency pairs
- Historical corrections
- Adjustment rates
- Test scenarios

## Working with FX Rates

### View Rate History

Click any currency pair to see historical rates:

**Timeline View**:
```
2025-12-27 09:00: USD/SGD = 1.3450 (Bloomberg)
2025-12-27 06:00: USD/SGD = 1.3445 (Bloomberg)
2025-12-26 16:00: USD/SGD = 1.3430 (Bloomberg)
2025-12-26 09:00: USD/SGD = 1.3425 (Bloomberg)
```

**Chart View**:

- Line chart showing rate movement
- Configurable date range (1D, 1W, 1M, 3M, 1Y)
- Zoom and pan controls
- Export chart as image

### Compare Rates

**Side-by-Side Comparison**:

Select multiple currency pairs to compare:

```
       │ USD/SGD │ EUR/SGD │ GBP/SGD
───────┼─────────┼─────────┼─────────
Today  │ 1.3450  │ 1.4520  │ 1.6780
1W Ago │ 1.3430  │ 1.4510  │ 1.6750
Change │ +0.15%  │ +0.07%  │ +0.18%
```

### Rate Alerts

**Set up notifications** for rate movements:

**Alert Types**:

- Rate crosses threshold (e.g., USD/SGD > 1.35)
- Percentage change (e.g., > 1% daily move)
- Volatility spike (e.g., unusual movement)

**Delivery**:

- Email notification
- In-app notification
- SMS (optional)

## Portfolio Valuation

### Multi-Currency Portfolios

FX rates automatically applied for valuation:

**Example Portfolio**:
```
Portfolio: GLOBAL_EQUITY
Base Currency: SGD

Holdings:
  - USD Assets:  $1,000,000 × 1.3450 = SGD 1,345,000
  - EUR Assets:    €500,000 × 1.4520 = SGD   726,000
  - GBP Assets:    £300,000 × 1.6780 = SGD   503,400
                                      ─────────────────
Total NAV (SGD):                              SGD 2,574,400
```

### Revaluation

**Automatic**: Portfolio NAV updated when rates change

**Manual**: Force revaluation on demand

**Batch**: Revalue all portfolios at month-end

## Data Quality

### Rate Validation

**Automated Checks**:

- ✓ Rate within expected range
- ✓ No sudden jumps (> 5% without news)
- ✓ Source is reliable
- ✓ Timestamp is recent (< 1 hour old)

**Quality Indicators**:

- 🟢 High Quality: All checks pass
- 🟡 Medium Quality: Some checks fail
- 🔴 Low Quality: Multiple checks fail

### Data Refresh

**Scheduled Updates**:

- **Peak Hours** (9am-6pm): Every 15 minutes
- **Off-Peak**: Every 60 minutes
- **Weekends**: Manual only

**Manual Refresh**:

Click "Refresh Rates" button to force update

## Historical Analysis

### Rate Trends

**Moving Averages**:

- 7-day MA
- 30-day MA
- 90-day MA

**Volatility Metrics**:

- Daily standard deviation
- Intraday range (high-low)
- Annualized volatility

### Performance Reports

**Monthly Summary**:

```
Currency Pair: USD/SGD
Period: December 2025

Opening Rate:   1.3420
Closing Rate:   1.3450
High:           1.3480
Low:            1.3410
Average:        1.3445
Std Deviation:  0.0018
Volatility:     1.2%
```

## Integration with Reference Data

### Currency Master

FX rates linked to currency reference:

**Currency Attributes**:

- ISO Code (USD, EUR, GBP)
- Currency Name
- Decimal Places (2 for most currencies)
- Calendar (for holiday adjustments)
- Spot Settlement (T+2 typically)

### Calendar Integration

**Non-Trading Days**: Rates use previous business day

**Holiday Logic**:
```
If today is holiday:
  Use last valid business day rate
Else:
  Use today's rate
```

## Troubleshooting

### Rates Not Updating

**Check**:

1. Is data feed connected?
2. Check last successful update time
3. Review error logs
4. Contact market data support

### Rate Seems Incorrect

**Verify**:

1. Compare with external source (e.g., xe.com)
2. Check if currency pair inverted
3. Review recent news/events
4. Contact market data team

### Missing Currency Pair

**Solution**:

1. Add to watchlist in data provider
2. Request new feed subscription
3. Enter manual rate temporarily

## Audit Trail

All market data access is logged:

**Logged Actions**:

- VIEW: Accessed FX dashboard/list
- SEARCH: Searched for rates
- EXPORT: Downloaded rate data
- UPDATE: Manual rate entry
- REFRESH: Forced data update

## Best Practices

### Rate Usage

1. **Always use latest rates** for current valuations
2. **Historical rates** for backdated calculations
3. **Forward rates** for future projections
4. **Verify rates** before critical operations

### Data Management

1. **Monitor data quality** daily
2. **Archive old rates** (keep 7 years)
3. **Document exceptions** (manual entries)
4. **Regular reconciliation** with source

### Risk Management

1. **Set rate alerts** for key currencies
2. **Monitor volatility** during market events
3. **Have backup data source** for critical rates
4. **Review rate assumptions** monthly

## Related Documentation

- [Portfolio Management](portfolio-management.md) - Multi-currency portfolios
- [Database Schema](../technical/database-schema.md) - FX rate table structure
- [API Reference](../technical/api-reference.md) - Market data services

## Need Help?

- **In-App**: Click ? icon (top right)
- **Market Data Support**: marketdata@yourcompany.com
- **Bloomberg Helpdesk**: +65-6212-1000
