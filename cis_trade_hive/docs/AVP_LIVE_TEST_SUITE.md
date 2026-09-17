# AVP Live Test Suite — How to Run

Live-Kudu regression suite for the AVP (Average Price Position) engine. Unlike
`trade/tests/test_avp_scenarios.py` (mocked, single-currency), this suite hits
a real Kudu/Impala database — no mocking.

**UI-driven, not direct DB writes.** Trade actions (create/amend/cancel) go
through the REAL views (`trade_create`, `trade_edit`, `trade_cancel`) via
Django's test Client — simulating a real user filling the form and clicking
submit. The suite never writes to `cis_trade`/`cis_trade_position` directly.
That means the real async pipeline (event queue → trade event worker →
position queue → position worker — both persistent background threads
started from `config/cml_app.py`'s gunicorn post_fork hook, running in your
actual deployed app, entirely separate from this test process) is what
actually produces the position rows. The suite only *reads* the DB
afterward — polling with a timeout — to check what the real pipeline
produced and decide pass/fail.

**No reference/master data is created either.** Portfolios, securities, and
counterparties are all assumed to already exist in your environment. At the
start of the run the suite only *verifies* the 3 SIT/UAT pairs exist with the
expected `revaluation_status` (`verify_sit_uat_master_data` — reads, not
writes) and raises a clear error naming exactly what's missing if not.
Counterparty is derived automatically per security — see "Counterparty" below.

Files:

| File | Purpose |
|---|---|
| `trade/tests/avp_live_fixtures.py` | Shared helpers: verification, cleanup, position lookups, UI-driven trade actions |
| `trade/tests/test_avp_live_scenarios.py` | The 23 scenarios |
| `scripts/cleanup_avp_test_data.py` | Standalone cleanup (same logic the suite runs automatically) |

## Prerequisites

- A working Kudu/Impala connection (`python manage.py test_hive` should succeed)
- Dependencies installed (`pip install -r requirements.txt -r requirements-dev.txt`)
- **The real background workers must be running** — trade event worker and
  position worker, started via `config/cml_app.py`'s gunicorn post_fork hook
  (or `scripts/position_worker_daemon.sh` for the position worker standalone).
  Without them, trades created through the UI just sit `PENDING` in
  `cis_trade_event_queue`/`cis_position_queue` forever and every test will
  time out waiting for a position that never gets calculated. If your SIT/UAT
  app is deployed normally (not just `manage.py runserver`), these should
  already be running continuously.
- The 3 SIT/UAT reference pairs below must already exist (portfolio +
  security + a counterparty matching the security's `issuer` field).

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

**Expect this to take longer than the old mocked suite.** Every trade
creation waits on the real background workers (poll every 5s for the trade
event worker, 10s for the position worker — see `config/cml_app.py`), so each
scenario that books a trade can take anywhere from a few seconds to
`avp_live_fixtures.POLL_TIMEOUT_SECONDS` (90s) if something's slow or stuck.
23 scenarios end-to-end could reasonably take several minutes, not seconds.

## What it covers (23 scenarios)

All scenarios run against the 3 real SIT/UAT reference pairs QA supplied —
there is no separate "sandbox" tier anymore:

| Pair | Portfolio | Security | Currency shape |
|---|---|---|---|
| `non_reval_quoted` | `UOBS_BCHAIN_FVE` (SGD, NON-REVALUED) | `UOB THAI (F) UQ` (THB) | cross-currency |
| `reval` | `UOBS_CIU_FVE_OLT` (SGD, REVALUED) | `AAPL UQ` (USD) | cross-currency |
| `non_reval_subsidiary` | `UOBT_SHF_SUB` (THB, NON-REVALUED) | `UOI SP` (SGD, Subsidiary) | cross-currency, equity-method |

| Group | Count | Covers |
|---|---|---|
| FX / cost exact-value checks | 2 | REVALUED cost_lc vs. live FX table (`reval` pair), NON-REVALUED cost_lc vs. `open_fx_rate` override (`non_reval_quoted` pair) |
| SIT/UAT full lifecycle | 19 | Same-day, future settlement, new/existing position, backdated buy/amend/cancel, Traded vs Settled basis — × all 3 pairs, plus the Non-Reval+Subsidiary unrealized-P&L combination |
| SOD/INT/EOD | 2 | Full `INT → EOD → SOD` chain via `refresh_positions`/`create_sod_snapshot` (`reval` pair), and SOD folding in a pending future settlement (`non_reval_quoted` pair) |

These are the regression tests for the fixes made against `DEAL-20260724-8334`
(Scenarios 1, 3, 5, 6 — backdated backfill, chain-recalc double-counting,
equity-method LC gate).

### Date-anchor registry

Since every test shares only 3 real pairs, tests needing an *exact-value*
check on a fresh position (rather than a before/after delta) use dedicated,
non-overlapping `trade_date` offsets from "today" so they don't collide with
other tests' cumulative state on the same pair:

| Offset from today | Used by |
|---|---|
| `0` (today) | SIT/UAT same-day fresh buy, future settlement, today cancellation |
| `-6` | SIT/UAT backdated cancellation |
| `-10` | SIT/UAT backdated amendment |
| `-15` | SIT/UAT backdated buy |
| `-20` | FX/cost check — `reval` pair |
| `-21` | FX/cost check — `non_reval_quoted` pair |
| `-23` / `-22` | SOD/EOD pending-settlement fold — `non_reval_quoted` pair |
| `-25` / `-24` | SOD/EOD full lifecycle — `reval` pair |

Keep this updated when adding a new exact-value test (also documented as a
comment in `test_avp_live_scenarios.py`).

## Test data — what's safe, what isn't

Nothing is created by this suite — see `avp_live_fixtures.py`'s module
docstring for full detail. The 3 SIT/UAT pairs (table above) are confirmed to
have no other trade history as of when this suite was written.

Cleanup only deletes this suite's own transactional rows (trades, positions,
queue entries) for these pairs — never the portfolio/security master rows.

**Counterparty** is never created or hardcoded — `get_counterparty_for_
security()` reads the security's `issuer` field and matches it (case-
insensitive) to a `cis_party.party_short_name`, exactly mirroring
`trade_form.html`'s client-side `autoSelectCounterpartyFromSecurity()` JS. If
a security's issuer has no matching counterparty, that's surfaced as a clear
assertion error — same as the real UI would show "not found" for it.

**Do not repoint SIT_UAT_PAIRS at a real, actively-traded portfolio.**
Backdated/amend/cancel scenarios drive real chain recalculation
(`settlement_service._recalculate_position_chain`), which pre-invalidates and
rewrites `is_latest` flags across that portfolio+security's *entire* position
history for the affected date range — not just the rows this suite wrote.

If these entities ever pick up real trading activity, either swap them for a
fresh dedicated set, or restrict tests to non-destructive scenarios only
(fresh buy/sell, no chain recalc) — see the conversation history / commit
messages for the original safety discussion.

## Cleanup

Runs automatically at the end of the test module, pass or fail. To clean up
manually (e.g. after a crashed/interrupted run, or just to confirm things are
clean):

```bash
python scripts/cleanup_avp_test_data.py
```

Safe to run any time, including when there's nothing to clean up.

## Known limitations / what's NOT covered

- No live Impala connection was available while writing this suite — it's
  been verified for syntax, collection, and safe default-skip behavior, but
  **not run against a real cluster**. Expect to need small fixes on first live
  run (e.g. if `cis_equity_price`'s real column shape differs slightly from
  what's assumed).
- `ui_create_trade`/`ui_amend_trade` build the full POST payload
  `trade_create`/`trade_edit` expect based on reading `trade/views.py`'s field
  list directly — if that view's required fields change, the payload builder
  in `avp_live_fixtures._trade_post_payload` needs updating too.
- Authentication is a synthetic session (`get_authenticated_client()` sets
  `user_login`/`user_permissions` directly in the test Client's session,
  bypassing the real `/login/` flow) — this satisfies
  `core.middleware.permission_middleware` but doesn't exercise the actual
  login view/ACL lookup.
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
- With only 3 pairs shared across 23 scenarios, running the suite repeatedly
  without cleanup in between will build up cumulative quantity on the shared
  `today`-anchored tests (delta-checked, so this doesn't break assertions,
  but worth knowing if you're inspecting `cis_trade_position` manually
  mid-run).
