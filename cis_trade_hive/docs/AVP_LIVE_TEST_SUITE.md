# AVP Live Test Suite — How to Run

Live-Kudu regression suite for the AVP (Average Price Position) engine. Unlike
`trade/tests/test_avp_scenarios.py` (mocked, single-currency), this suite hits
a real Kudu/Impala database using the real `position_service`/
`settlement_service` code paths — no mocking.

Files:

| File | Purpose |
|---|---|
| `trade/tests/avp_live_fixtures.py` | Shared helpers: test data setup, cleanup, position lookups |
| `trade/tests/test_avp_live_scenarios.py` | The 30 scenarios |
| `scripts/cleanup_avp_test_data.py` | Standalone cleanup (same logic the suite runs automatically) |

## Prerequisites

- A working Kudu/Impala connection (`python manage.py test_hive` should succeed)
- Dependencies installed (`pip install -r requirements.txt -r requirements-dev.txt`)

## Running it

Disabled by default — nothing runs unless you opt in:

```bash
RUN_LIVE_AVP_TESTS=1 pytest trade/tests/test_avp_live_scenarios.py -v
```

Drop `-v` for a terser run; add `-k <pattern>` to run a subset, e.g.:

```bash
RUN_LIVE_AVP_TESTS=1 pytest trade/tests/test_avp_live_scenarios.py -v -k backdated
RUN_LIVE_AVP_TESTS=1 pytest trade/tests/test_avp_live_scenarios.py -v -k sit_uat
RUN_LIVE_AVP_TESTS=1 pytest trade/tests/test_avp_live_scenarios.py -v -k sod_eod
```

**Run status is pytest's own summary line** at the end — `N passed, M failed`
— that's the one-click pass/fail report. No separate report to generate or
read; a nonzero exit code means something failed (useful for CI/scripting:
`echo $?` after the run).

## What it covers (30 scenarios)

| Group | Count | Covers |
|---|---|---|
| Same-currency lifecycle | 6 | Fresh buy, accumulate, sell, backdated buy, amend, cancel — sandbox `AVPTEST-*` entities |
| Cross-currency | 3 | REVALUED (FX-table cost), NON-REVALUED (`open_fx_rate` override), equity-method (Subsi) |
| SIT/UAT reference pairs | 19 | Full lifecycle (same-day, future settlement, new/existing position, backdated buy/amend/cancel, Traded vs Settled basis) × 3 QA-named pairs, plus the Non-Reval+Subsidiary combination |
| SOD/INT/EOD | 2 | Full `INT → EOD → SOD` chain via `refresh_positions`/`create_sod_snapshot`, and SOD folding in a pending future settlement |

These are the regression tests for the fixes made against `DEAL-20260724-8334`
(Scenarios 1, 3, 5, 6 — backdated backfill, chain-recalc double-counting,
equity-method LC gate).

## Test data — what's safe, what isn't

Two tiers, see `avp_live_fixtures.py`'s module docstring for full detail:

1. **`AVPTEST-*` sandbox** — generic names, fully owned and created/deleted by
   this suite. Safe by construction.
2. **`SIT_UAT_PAIRS`** — real, named entities (`UOBS_BCHAIN_FVE`/`UOB THAI (F) UQ`,
   `UOBS_CIU_FVE_OLT`/`AAPL UQ`, `UOBT_SHF_SUB`/`UOI SP`) confirmed to have no
   other trade history as of when this suite was written. Cleanup only deletes
   this suite's own transactional rows for them — never the portfolio/security
   master rows themselves.

**Do not repoint either tier at a real, actively-traded portfolio.**
Backdated/amend/cancel scenarios drive real chain recalculation
(`settlement_service._recalculate_position_chain`), which pre-invalidates and
rewrites `is_latest` flags across that portfolio+security's *entire* position
history for the affected date range — not just the rows this suite wrote.

If the `SIT_UAT_PAIRS` entities ever pick up real trading activity, either
swap them for a fresh dedicated set, or restrict those specific tests to
non-destructive scenarios only (fresh buy/sell, no chain recalc) — see the
conversation history / commit message for the original safety discussion.

## Cleanup

Runs automatically at the end of the test module, pass or fail. To clean up
manually (e.g. after a crashed/interrupted run, or just to confirm the
sandbox is clean):

```bash
python scripts/cleanup_avp_test_data.py
```

Safe to run any time, including when there's nothing to clean up.

## Known limitations / what's NOT covered

- No live Impala connection was available while writing this suite — it's
  been verified for syntax, collection, and safe default-skip behavior, but
  **not run against a real cluster**. Expect to need small fixes on first live
  run (e.g. if `cis_equity_price`'s real column shape differs slightly from
  what's assumed, or portfolio/security `status` values differ from what's
  used here).
- FX rate assertions don't hardcode QA-supplied historical rates (27-Feb/2-Mar)
  since the suite's dates are computed relative to whatever
  `system_date_service.get_system_date()` returns at run time, which won't
  necessarily match those exact calendar dates. Instead they independently
  re-query the live FX table for whatever "today" actually is. See
  `avp_live_fixtures.KNOWN_FX_RATES`/`KNOWN_EQUITY_PRICES` for the reference
  values if you want to pin an exact-value assertion for one specific known
  run.
- `refresh_positions.py`'s `--fill-gaps` and `--ams-no-reval` modes, and
  `create_sod_snapshot.py`'s `--fill-gaps` mode, aren't exercised — only the
  default full-recalc path.
