# Frequently Asked Questions

Quick answers to common questions about CisTrade.

## General Questions

### What is CisTrade?

CisTrade is a comprehensive trade and portfolio management system designed for financial institutions to manage portfolios, track trades, and ensure compliance with four-eyes principle.

### Who can access CisTrade?

Users authenticated through the UOB ACL system with assigned permissions. Contact your system administrator for access.

### What browsers are supported?

- Chrome (recommended)
- Firefox
- Safari
- Edge

## Portfolio Management

### How do I create a new portfolio?

1. Navigate to Portfolio → Create New
2. Fill required fields (Code, Name, Currency, Manager)
3. Click "Save as Draft"
4. Submit for approval when ready

See [Portfolio Management Guide](portfolio-management.md) for details.

### Why can't I edit an Active portfolio?

Active portfolios are locked to prevent unauthorized changes. To modify:
1. Close the portfolio
2. Make changes
3. Reactivate through approval process

### What's the difference between Draft and Pending?

- **Draft**: Work in progress, only visible to creator
- **Pending Approval**: Submitted for checker review, cannot be edited

### Can I delete a portfolio?

No. Portfolios use soft delete (Close) to maintain audit trail. Closed portfolios can be reactivated if needed.

## Four-Eyes Workflow

### What is Four-Eyes principle?

A compliance control requiring two different people for any critical operation:
- **Maker**: Creates/updates
- **Checker**: Approves/rejects

See [Four-Eyes Workflow](four-eyes-workflow.md) for complete guide.

### Can I approve my own work?

No. The system prevents self-approval to maintain segregation of duties.

### What if checker rejects my submission?

1. Review rejection comments
2. Make necessary corrections
3. Resubmit for approval

### Who can be a Checker?

Users in the "Checkers" group with appropriate permissions. Contact admin if you need checker access.

## Reference Data

### Where does currency data come from?

Currency reference data comes from GMP system via daily ETL process. It's read-only in CisTrade.

### How often is reference data updated?

- **Currencies**: Daily
- **Countries**: Quarterly or as needed
- **Calendars**: Annually + adhoc updates
- **Counterparties**: Daily

### Can I add new currencies?

No. Currency additions must be requested through GMP system team.

## UDFs (User Defined Fields)

### What are UDFs used for?

UDFs allow custom fields for business-specific attributes without database changes. Examples:
- Risk ratings
- Investment strategies
- Compliance flags
- Review dates

See [UDF Management Guide](udf-management.md).

### How do I add a new UDF?

Contact your system administrator. UDF creation requires special permissions.

### Can UDF values change over time?

Yes! UDFs maintain full value history with effective dates.

## Market Data

### How current are FX rates?

FX rates update every 15-30 minutes from Bloomberg/Reuters feeds during market hours.

### Can I enter manual FX rates?

Yes, for special cases (exotic pairs, corrections, testing). Requires "market data admin" permission.

### What if FX rate looks wrong?

1. Compare with external source (xe.com, Bloomberg)
2. Check if pair is inverted
3. Report to market data team

See [Market Data Guide](market-data.md).

## Permissions & Access

### How do I request access to a module?

Contact your manager or system administrator with:
- Module name (Portfolio, UDF, Market Data, etc.)
- Access level needed (READ, WRITE, READ_WRITE)
- Business justification

### Why am I getting "Access Denied"?

Your user account doesn't have required permission for that action. Contact admin to request access.

### How long does permission approval take?

Typically 1-2 business days, depending on approval workflow.

## Audit & Compliance

### Are all my actions tracked?

Yes. CisTrade logs all significant actions:
- Logins
- Data views
- Updates/changes
- Exports
- Approvals/rejections

### Who can view audit logs?

Users with "audit log viewer" permission. Typically compliance officers and management.

### How long are audit logs retained?

7 years to comply with regulatory requirements.

## Reports & Exports

### What report formats are available?

- PDF: Professional reports with charts
- Excel: Detailed data with formulas
- CSV: Raw data for imports

See [Reports Guide](reports.md).

### Can I schedule automated reports?

Yes! Go to Reports → Schedule to set up recurring reports with email delivery.

### Why is my export failing?

Common causes:
- Too much data (reduce date range)
- Network timeout (try CSV format)
- Insufficient permissions

## Technical Issues

### System is slow

**Try**:
1. Clear browser cache
2. Close unused tabs
3. Check internet connection
4. Contact IT if persistent

### I can't log in

**Check**:
1. Correct user ID
2. Account is active
3. Not locked due to failed attempts
4. Contact helpdesk if needed

### Page shows error message

**Steps**:
1. Note exact error message
2. Refresh page (F5)
3. Clear cache and retry
4. Contact support with error details

### Data looks incorrect

**Verify**:
1. Date range filters
2. Status filters
3. Compare with source system
4. Report to support if discrepancy confirmed

## Training & Support

### Where can I get training?

- **Documentation**: Click ? icon or Documentation link
- **Quick Reference**: [Print this guide](quick-reference.md)
- **Training Sessions**: Contact training team
- **Video Tutorials**: Coming soon

### How do I report a bug?

Email: cistrade-support@yourcompany.com

Include:
- What you were trying to do
- What happened (error message, screenshot)
- When it occurred
- Your user ID

### Who do I contact for help?

**General Support**: cistrade-support@yourcompany.com
**Technical Issues**: IT helpdesk
**Permission Requests**: Your manager
**Training**: training@yourcompany.com
**Market Data**: marketdata@yourcompany.com

## Best Practices

### Tips for new users

1. **Start with Dashboard**: Familiarize yourself with layout
2. **Read Quick Reference**: Print and keep handy
3. **Practice in TEST**: Use test portfolios before real data
4. **Ask Questions**: No question is too basic
5. **Check Permissions**: Know what you can/can't do

### Keyboard Shortcuts

- `Ctrl + S`: Save (when in edit mode)
- `Ctrl + F`: Search current page
- `Esc`: Close modal/dialog
- `Tab`: Navigate between fields

### Working Efficiently

1. **Use Search**: Faster than browsing lists
2. **Set Filters**: Reduce clutter
3. **Export Data**: Analyze in Excel if needed
4. **Save Filters**: Reuse common searches
5. **Bookmark Pages**: Quick access to frequent tasks

## Still Have Questions?

- **In-App Help**: Click ? icon (top right)
- **Full Documentation**: Documentation menu
- **Support Email**: cistrade-support@yourcompany.com
- **Phone**: +65-6xxx-xxxx (business hours)
