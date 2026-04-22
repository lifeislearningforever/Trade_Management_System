# Securities & Counterparties

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~8 minutes

---

## Securities

### What Is a Security?

A security is a tradeable financial instrument — shares, bonds, ETFs, etc. Before a trade can be entered in CIS, the security must exist in the system and be in an approved status.

### Security Lifecycle

```
INITIAL → VALIDATED → APPROVED → ACTIVE
                   └→ REJECTED
ACTIVE → INACTIVE → CLOSED
```

Only securities in `ACTIVE`, `APPROVED`, `INITIAL`, `VALIDATED`, or `SETTLED` status can be used in trades.

### Security Fields

| Field | Description |
|-------|-------------|
| `label` | Short code used in trades (e.g. `AAPL`, `UOB-SG`) |
| `full_name` | Full security name |
| `isin` | International Securities Identification Number |
| `currency` | Trading currency (e.g. USD, SGD, HKD) |
| `security_type` | EQUITY, BOND, ETF, FUND, etc. |
| `status` | Lifecycle status |
| `is_active` | Whether active |

### Security History

Every change to a security is recorded in `cis_security_history`. Audit trail of all modifications.

### User-Defined Fields on Securities

Securities support custom UDF fields. These are defined in `cis_udf_definition` with `entity_type = 'SECURITY'` and their values stored in `cis_udf_value`. This allows the business to add custom metadata to securities without code changes.

Seed UDF fields for securities are defined in `sql/ddl/51_security_udf_fields.sql`.

---

## Counterparties

### What Is a Counterparty?

A counterparty is the other party in a trade — typically the broker or bank you're trading with. Before a trade can be entered, the counterparty must exist in CIS and be active.

CIS manages counterparties in `cis_counterparty_kudu`. This is a CIS-owned Kudu table (not a GMP feed) — counterparties are set up and maintained directly in CIS.

> **Note:** The older `cis_party` table was replaced. Counterparties are now fully managed in `cis_counterparty_kudu` with a standard UDF-based extension model.

### Counterparty Fields

| Field | Description |
|-------|-------------|
| `counterparty_id` | Unique ID |
| `counterparty_name` | Full name |
| `counterparty_code` | Short code used in trades |
| `counterparty_type` | BROKER, BANK, CUSTODIAN, etc. |
| `is_active` | Whether active |
| `country_code` | Country of incorporation |
| `currency` | Default settlement currency |

### Validation in Trade Entry

When a trader selects a counterparty for a trade:
- `cis_counterparty_kudu` is queried for `is_active = true`
- Only active counterparties appear in the dropdown
- If a counterparty is deactivated mid-trade, the validation will reject the trade

---

## Reference Data (Currencies, Countries, Calendars)

These come from GMP (read-only Hive external tables):

| Table | Contents | Used for |
|-------|----------|---------|
| `gmp_cis_sta_dly_currency` | Currency codes, names, decimals | Currency dropdowns |
| `gmp_cis_sta_dly_country` | Country codes and names | Country dropdowns |
| `gmp_cis_sta_dly_calendar` | Trading calendars, holidays | Settle date validation |

These update daily from GMP. CIS reads them fresh each time — no local cache.

---

## Market Data (FX Rates & Equity Prices)

See [05f — Market Data](05f_market_data.md) for the full details.

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `security/repositories/security_kudu_repository.py` | SQL on `cis_security` |
| `security/services/security_dropdown_service.py` | Securities dropdown (filtered by status/currency) |
| `security/views.py` | Security CRUD views |
| `sql/ddl/cis_security_kudu.sql` | Security table DDL |
| `sql/ddl/cis_security_history_kudu.sql` | Security history DDL |
| `sql/ddl/51_security_udf_fields.sql` | Seed UDF fields for securities |
| `sql/ddl/cis_counterparty_kudu.sql` | Counterparty table DDL |

### Security Dropdown Query Pattern
```python
# security/services/security_dropdown_service.py
query = """
    SELECT label, full_name, isin, currency, security_type
    FROM gmp_cis.cis_security
    WHERE is_active = true
      AND status IN ('ACTIVE', 'APPROVED', 'INITIAL', 'VALIDATED', 'SETTLED')
    ORDER BY label
"""
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| Security not in trade dropdown | Check `cis_security` — is status ACTIVE/APPROVED? Is `is_active = true`? |
| Counterparty not in trade dropdown | Check `cis_counterparty_kudu` — is `is_active = true`? |
| Currency list empty in form | Check GMP feed — query `gmp_cis_sta_dly_currency` directly in impala-shell |
| Cannot enter trade for new security | Security must be created and approved first |
