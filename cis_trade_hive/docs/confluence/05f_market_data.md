# Market Data (FX Rates & Equity Prices)

> **Audience:** User, BA, SA, Developer, Support
> **Read time:** ~6 minutes

---

## What Is Market Data in CIS?

CIS uses two types of market data from GMP:

1. **FX Rates** — Exchange rates between currency pairs, updated daily
2. **Equity Prices** — Daily prices for securities (bid, ask, spot)

Both are **read-only** in CIS — they come from GMP and CIS never writes to these tables.

---

## FX Rates

### Where They Come From

GMP pushes daily FX rates to HDFS every morning. The Hive external table `gmp_cis_sta_dly_fx_rates` points to those files. CIS reads via Impala.

### How They're Used

FX rates are used to convert trade amounts from the security's trading currency (foreign currency, FC) to the portfolio's base currency (local currency, LC):

```
Trade: BUY 100 AAPL @ USD 175
Portfolio base currency: SGD

FX rate (USD→SGD): 1.35 (from gmp_cis_sta_dly_fx_rates)

total_amount_fc = 100 × 175 = USD 17,500
total_amount_lc = 17,500 × 1.35 = SGD 23,625
```

FX rates are also used in position revaluation (calculating unrealised P&L in portfolio currency).

### Key Fields in gmp_cis_sta_dly_fx_rates

| Column | Description |
|--------|-------------|
| `ref_quot_ccy` | Currency pair code (e.g. `USD-SGD`) |
| `underlying_cur` | From currency (e.g. `USD`) |
| `base_cur` | To currency (e.g. `SGD`) |
| `bid_rate` | Bid rate |
| `ask_rate` | Ask rate |
| `spot_rate_d` | Spot/mid rate |
| `processing_date` | Date of this rate |

Spread (bps) is calculated on-the-fly in the application: `(ask_rate - bid_rate) / spot_rate_d × 10000`.

### FX Rate Screen in CIS

The **Market Data → FX Rates** screen shows all available rates for the latest processing date. You can filter by currency pair.

---

## Equity Prices

### Where They Come From

GMP pushes daily equity prices. CIS has two sources:

1. **`gmp_cis_sta_dly_equity_price`** — Hive external table, GMP data, read-only
2. **`cis_equity_price_kudu`** — CIS's own Kudu table, for prices that CIS manages directly

Most prices come from GMP. `cis_equity_price_kudu` exists for securities where CIS is the price source.

### Key Fields

| Column | Description |
|--------|-------------|
| `price_date` | Date of the price |
| `security_label` | Which security |
| `price_amount` | Official close/mid price |
| `bid_price` | Bid |
| `ask_price` | Ask |
| `currency` | Price currency |

---

## For Developers: Key Files

| File | Purpose |
|------|---------|
| `market_data/repositories/fx_rate_hive_repository.py` | SQL on `gmp_cis_sta_dly_fx_rates` |
| `market_data/repositories/equity_price_hive_repository.py` | SQL on GMP equity price table |
| `market_data/services/fx_rate_service.py` | FX rate business logic + spread calc |
| `market_data/services/equity_price_service.py` | Price lookups |
| `trade/services/multicurrency_service.py` | FC→LC conversion using FX rates |
| `sql/ddl/gmp_cis_sta_dly_fx_rates.sql` | FX rates DDL (Hive external) |
| `sql/ddl/cis_equity_price_kudu.sql` | CIS equity price DDL (Kudu) |

### FX Rate Query Pattern
```python
# Get latest FX rate for a currency pair
query = """
    SELECT spot_rate_d, bid_rate, ask_rate, processing_date
    FROM gmp_cis.gmp_cis_sta_dly_fx_rates
    WHERE underlying_cur = 'USD'
      AND base_cur = 'SGD'
      AND record_type = 'D'
      AND processing_date = (
          SELECT MAX(processing_date)
          FROM gmp_cis.gmp_cis_sta_dly_fx_rates
      )
    LIMIT 1
"""
```

---

## For Support: Common Issues

| Issue | Check |
|-------|-------|
| FX rate missing for a currency pair | Check if GMP feed arrived — query `gmp_cis_sta_dly_fx_rates` for latest `processing_date` |
| Trade showing wrong LC amount | Check FX rate for that currency pair on that trade date |
| FX rates screen showing "No data" | GMP may not have pushed today's file — check HDFS and yesterday's rates |
| Equity price not showing | Check if security label matches exactly what's in the price table |
