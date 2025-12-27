# Reports Guide

Generate comprehensive reports for portfolios, trades, compliance, and analytics.

## Available Reports

### Portfolio Reports

#### 1. Portfolio Summary Report
**Purpose**: Overview of all portfolios
**Includes**: Name, manager, currency, NAV, status
**Format**: PDF, Excel, CSV
**Frequency**: Daily, Weekly, Monthly

#### 2. Portfolio Valuation Report
**Purpose**: Detailed portfolio valuations
**Includes**: Holdings, prices, FX rates, NAV calculation
**Format**: PDF, Excel
**Frequency**: Daily, Monthly, Quarterly

#### 3. Portfolio Performance Report
**Purpose**: Performance metrics and returns
**Includes**: Returns, benchmarks, attribution
**Format**: PDF, Excel
**Frequency**: Monthly, Quarterly, Annual

### Compliance Reports

#### 4. Four-Eyes Audit Report
**Purpose**: Track maker-checker workflow
**Includes**: Pending approvals, rejection reasons, audit trail
**Format**: Excel, CSV
**Frequency**: Weekly, Monthly

#### 5. Change Log Report
**Purpose**: All changes to portfolios
**Includes**: What changed, who changed, when, why
**Format**: Excel, CSV
**Frequency**: Daily, Weekly

### Operational Reports

#### 6. User Activity Report
**Purpose**: Track user actions
**Includes**: Logins, views, updates, exports
**Format**: Excel, CSV
**Frequency**: Weekly, Monthly

#### 7. Data Quality Report
**Purpose**: Identify data issues
**Includes**: Missing data, inconsistencies, validation errors
**Format**: Excel, PDF
**Frequency**: Weekly

## Generating Reports

### Quick Reports

1. Navigate to desired section
2. Click "Export" or "Download CSV"
3. Report generated instantly

### Scheduled Reports

1. Go to Reports → Schedule
2. Select report type
3. Configure parameters
4. Set frequency and recipients
5. Save schedule

### Custom Reports

1. Reports → Create Custom Report
2. Select data sources
3. Choose fields
4. Apply filters
5. Save template

## Report Parameters

### Common Filters

- **Date Range**: From/To dates
- **Portfolio**: Specific or all
- **Currency**: SGD, USD, EUR, etc.
- **Status**: Active, Inactive, All
- **Manager**: Filter by manager name

### Output Options

- **Format**: PDF, Excel, CSV
- **Orientation**: Portrait, Landscape
- **Include Charts**: Yes/No
- **Email**: Send to recipients

## Report Examples

### Portfolio Summary

```
Portfolio Summary Report
As of: 2025-12-27

Portfolio          Manager      Currency  NAV (Local)    Status
─────────────────────────────────────────────────────────────
TECH_FUND          J. Smith     USD       15,234,567     Active
BALANCED_FUND      M. Lee       SGD       8,123,456      Active
GROWTH_ASIA        K. Tan       HKD       45,678,901     Active

Total Portfolios: 238 Active, 293 Inactive
```

### Audit Trail

```
Change Log - Last 7 Days

Date/Time           User     Action    Portfolio         Details
──────────────────────────────────────────────────────────────────
2025-12-27 14:30    JSmith   APPROVE   TECH_FUND         Approved NAV calculation
2025-12-27 10:15    MLee     UPDATE    BALANCED_FUND     Changed manager
2025-12-26 16:45    KTan     CREATE    NEW_FUND          New portfolio created
```

## Scheduled Report Management

### View Schedules

Reports → Scheduled Reports

Shows:
- Report name
- Frequency (Daily, Weekly, Monthly)
- Next run date/time
- Recipients
- Last run status

### Modify Schedule

1. Find report in list
2. Click "Edit"
3. Update parameters
4. Save changes

### Disable Schedule

1. Find report
2. Toggle "Active" switch to OFF
3. Confirm

## Export Formats

### PDF

- Professional layout
- Charts and graphs
- Page numbers
- Headers/footers
- Best for: Formal reports, printing

### Excel

- Multiple worksheets
- Formulas intact
- Pivot tables
- Formatting preserved
- Best for: Analysis, manipulation

### CSV

- Plain text, comma-separated
- Universal compatibility
- No formatting
- Best for: Data import, scripts

## Performance Tips

### Large Reports

For reports with > 10,000 rows:

1. Use CSV format (faster)
2. Split by date range
3. Filter to specific portfolios
4. Run during off-peak hours

### Scheduled vs On-Demand

- **Scheduled**: Pre-generated, instant access
- **On-Demand**: Fresh data, may take time

## Audit Logging

All report generation logged:

- Who requested
- When generated
- Parameters used
- Format selected
- Number of records

## Troubleshooting

### Report Timing Out

**Solutions**:
- Reduce date range
- Filter to fewer portfolios
- Use CSV instead of PDF/Excel
- Contact support for large datasets

### Missing Data in Report

**Check**:
- Date range includes data
- Filters not too restrictive
- User has permission to view data
- Data exists in system

### Formatting Issues

**Try**:
- Different format (PDF vs Excel)
- Update browser
- Clear cache
- Re-generate report

## Related Documentation

- [Portfolio Management](portfolio-management.md)
- [Four-Eyes Workflow](four-eyes-workflow.md)
- [Audit Logs](../technical/api-reference.md#audit-repository)
