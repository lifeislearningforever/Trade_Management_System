# CIS EOD Control-M Scripts

## Script

Single script for all environments: `scripts/cis_eod.sh`

Pass `--env` to select the environment.

---

## Environment Config

| Env  | Host          | Impala Port | Keytab (PLACEHOLDER)       |
|------|---------------|-------------|----------------------------|
| SIT  | lxmrwtsgv0w1  | 21050       | `<SIT_KEYTAB>.keytab`      |
| UAT  | lxmrwusgv0w1  | 21050       | `<UAT_KEYTAB>.keytab`      |
| PROD | lxmrwpsgv0w1  | 21050       | `<PROD_KEYTAB>.keytab`     |
| DR   | lxmrwrsgv0w1  | 21050       | `<DR_KEYTAB>.keytab`       |

---

## Job Execution Order

| Step | Job | Command | Type | Schedule |
|------|-----|---------|------|----------|
| 1 | Equity Price Copy | `impala-shell equity_price_hive_copy_job.sql` | SQL | Daily |
| 2 | Corporate Actions | `manage.py process_corporate_actions --run-type EOD` | Django | Daily |
| 3 | Cash Flow | `manage.py process_approved_cashflows --run-type EOD` | Django | Daily |
| 4 | EOD Settlements | `manage.py process_settlements` | Django | Daily |
| 5 | SOD Snapshot | `manage.py create_sod_snapshot` | Django | Daily |
| 6 | Correction | `manage.py process_corporate_actions --run-type CORR` + `process_approved_cashflows --run-type CORR` | Django | Days 1–7 of month only |

---

## Processing Date Logic

Source file: `/sftp/ftptsp/TSPSG/CIS/gmpcisalldates.txt`

```
Line 1 : Header  — skip
Line 2 : 20260713|20260715|20260713|    ← body
          field 1   field 2   field 3
          trade     settle    report_date
Last   : Trailer — skip
```

| Variable | Source | Field |
|----------|--------|-------|
| `processing_date` | `report_date` | field 3 |
| `sod_date` | `settle_date` | field 2 — **PLACEHOLDER, confirm** |

Date is converted from `YYYYMMDD` → `YYYY-MM-DD` before passing to `manage.py`.

---

## Usage

```bash
# Full EOD — date from gmpcisalldates.txt
./cis_eod.sh --env SIT
./cis_eod.sh --env UAT
./cis_eod.sh --env PROD
./cis_eod.sh --env DR

# Override date explicitly
./cis_eod.sh --env SIT --date 20260713

# Resume from failed step (e.g. step 3 failed)
./cis_eod.sh --env SIT --start-from 3
./cis_eod.sh --env PROD --date 20260713 --start-from 4

# Environment variable form also works
START_FROM=3 ./cis_eod.sh --env UAT
```

---

## Re-run from Failed Step

On failure the script prints exactly what to run:

```
>>> FAILED at STEP 3 <<<
>>> To re-run from this step:
>>>   ./cis_eod.sh --env SIT --start-from 3
>>> Or with explicit date:
>>>   ./cis_eod.sh --env SIT --date 20260713 --start-from 3
```

State file written on failure: `logs/cis_eod_<ENV>_state.txt`
Cleared automatically on full success.

---

## Log Files

```
logs/cis_eod_SIT_20260713_183200.log
logs/cis_eod_UAT_20260713_183200.log
logs/cis_eod_PROD_20260713_183200.log
logs/cis_eod_DR_20260713_183200.log
```

---

## Keytab Placeholders — Update Before Deploying

Edit `scripts/cis_eod.sh` and replace:

| Env  | Replace | With |
|------|---------|------|
| SIT  | `<SIT_KEYTAB>` / `<SIT_PRINCIPAL>` | actual keytab filename / principal |
| UAT  | `<UAT_KEYTAB>` / `<UAT_PRINCIPAL>` | actual keytab filename / principal |
| PROD | `<PROD_KEYTAB>` / `<PROD_PRINCIPAL>` | actual keytab filename / principal |
| DR   | `<DR_KEYTAB>` / `<DR_PRINCIPAL>` | actual keytab filename / principal |

---

## Correction Job

- Runs **steps 2 and 3** with `--run-type CORR` (CA + Cash Flow correction)
- Triggered automatically when `day_of_month` is **1–7**
- No manual flag needed — the script checks the date itself
- Skipped silently on all other days

---

## Pending

- [ ] Confirm `sod_date` field index in `gmpcisalldates.txt` (currently field 2)
- [ ] Fill in keytab filenames and principals for all 4 environments
- [ ] Verify `create_sod_snapshot` should use `sod_date` not `processing_date`
