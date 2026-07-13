# CIS EOD Control-M Scripts

## Script Files

| Environment | Script | Host | Impala |
|-------------|--------|------|--------|
| SIT  | `scripts/cis_eod_sit.sh`  | lxmrwtsgv0w1 | lxmrwtsgv0w1:21050 |
| UAT  | `scripts/cis_eod_uat.sh`  | lxmrwusgv0w1 | lxmrwusgv0w1:21050 |
| PROD | `scripts/cis_eod_prod.sh` | lxmrwpsgv0w1 | lxmrwpsgv0w1:21050 |
| DR   | `scripts/cis_eod_dr.sh`   | lxmrwrsgv0w1 | lxmrwrsgv0w1:21050 |

---

## Job Execution Order (all environments)

| Step | Job | Source ID | Type | Trigger |
|------|-----|-----------|------|---------|
| 1 | Equity Price Copy | — | impala-shell | Daily |
| 2 | Corporate Actions | `cis_corporate_actions` | spark-submit | Daily |
| 3 | Cash Flow | `cis_cash_flow` | spark-submit | Daily |
| 4 | EOD | `cis_eod` | spark-submit | Daily |
| 5 | SOD | `cis_sod` | spark-submit | Daily (next contextual date) |
| 6 | Correction | `cis_correction` | spark-submit | First week of month (day 1–7) only |

---

## Processing Date Logic

Source file: `/sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt`

```
Line 1 : Header  — skip
Line 2 : trade_date|settle_date|report_date|    ← body
          field 1   field 2     field 3
Last   : Trailer — skip
```

- `processing_date` = field 3 (`report_date`)
- `sod_date`        = field 2 (`settle_date`) ← **PLACEHOLDER — confirm field index**

---

## Re-run from Failed Step

If step N fails, re-run from that step without repeating earlier steps:

```bash
# Re-run from step 3 (Cash Flow) onwards
START_FROM=3 ./cis_eod_sit.sh

# Re-run from step 3 with explicit date
START_FROM=3 ./cis_eod_sit.sh -d 20260713
```

State file written on failure: `logs/cis_eod_<REGION>_state.txt`
Cleared automatically on full success.

---

## Usage

```bash
# Run full EOD (all steps, date from gmpcisalldates.txt)
./cis_eod_sit.sh
./cis_eod_uat.sh
./cis_eod_prod.sh
./cis_eod_dr.sh

# Run with explicit date override
./cis_eod_sit.sh -d 20260713

# Resume from specific step
START_FROM=2 ./cis_eod_sit.sh
START_FROM=4 ./cis_eod_prod.sh -d 20260713
```

---

## Keytab Placeholders (update before deploying)

| Environment | Keytab | Principal |
|-------------|--------|-----------|
| SIT  | `/app/prodlib/<SIT_KEYTAB>.keytab`  | `<SIT_PRINCIPAL>@SG.UOBNET.COM`  |
| UAT  | `/app/prodlib/<UAT_KEYTAB>.keytab`  | `<UAT_PRINCIPAL>@SG.UOBNET.COM`  |
| PROD | `/app/prodlib/<PROD_KEYTAB>.keytab` | `<PROD_PRINCIPAL>@SG.UOBNET.COM` |
| DR   | `/app/prodlib/<DR_KEYTAB>.keytab`   | `<DR_PRINCIPAL>@SG.UOBNET.COM`   |

---

## Log Files

Written to `logs/` under the project base directory:
```
logs/cis_eod_SIT_20260713_183200.log
logs/cis_eod_UAT_20260713_183200.log
logs/cis_eod_PROD_20260713_183200.log
logs/cis_eod_DR_20260713_183200.log
```

---

## Correction Job Schedule

Runs **only on days 1–7 of each month** (month-end correction window).
Automatically skipped on all other days — no manual intervention needed.
