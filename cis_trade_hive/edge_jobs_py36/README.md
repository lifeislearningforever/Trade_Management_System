# edge_jobs_py36

Standalone, **Django-free** forks of the trade/reference_data Control-M
commands, for running on edge nodes where the spark-submit driver is pinned
to Python 3.6. Django 5.2.9 (the version this project uses) requires Python
>= 3.10 to import at all, so the original `manage.py` commands cannot run
there under any configuration — this package re-implements the same
business logic without importing Django anywhere.

**This is a parallel fork, not a wrapper.** The original files in
`trade/management/commands/` and `reference_data/management/commands/`
(and the repositories/services they use) are untouched and continue to run
normally under the full Django app. Any future bugfix to shared business
logic must be applied to **both** copies — there is no shared code path.

## Layout

```
edge_jobs_py36/
  lib/                              Django-free support package
    __init__.py                     sys.path bootstrap (see below)
    config.py                       stand-in for django.conf.settings
    cache.py                        stand-in for django.core.cache.cache
    management_base.py              stand-in for BaseCommand/CommandError + CLI runner
    notifications.py                stand-in for core.notifications (no live WS; Kudu-persist only)
    impala_connection.py            fork of core/repositories/impala_connection.py
    system_date_repository.py       fork of core/repositories/system_date_repository.py
    system_date_service.py          fork of core/services/system_date_service.py
    trade_kudu_repository.py        fork of trade/repositories/trade_kudu_repository.py
    trade_validation_repository.py  fork of trade/repositories/trade_validation_repository.py
    cash_flow_repository.py         fork of trade/repositories/cash_flow_repository.py
    corporate_action_repository.py  fork of reference_data/repositories/corporate_action_repository.py
    ca_cash_flow_queue_repository.py fork of reference_data/repositories/ca_cash_flow_queue_repository.py
    ca_cash_flow_service.py         fork of reference_data/services/ca_cash_flow_service.py
    multicurrency_service.py        fork of trade/services/multicurrency_service.py
    position_id_service.py          fork of trade/services/position_id_service.py
    position_queue_service.py       fork of trade/services/position_queue_service.py
    position_service.py             fork of trade/services/position_service.py
    settlement_service.py           fork of trade/services/settlement_service.py
    trade_dropdown_service.py       fork of trade/services/trade_dropdown_service.py
    udf_field_repository.py         fork of udf/repositories/udf_field_repository.py

  sync_gmp_corporate_actions.py     fork of reference_data/management/commands/sync_gmp_corporate_actions.py
  process_corporate_actions.py      fork of reference_data/management/commands/process_corporate_actions.py
  process_approved_cashflows.py     fork of trade/management/commands/process_approved_cashflows.py
  process_settlements.py            fork of trade/management/commands/process_settlements.py
  refresh_positions.py              fork of trade/management/commands/refresh_positions.py
  create_sod_snapshot.py            fork of trade/management/commands/create_sod_snapshot.py
  backfill_cancelled_trade_visibility.py  fork of trade/management/commands/backfill_cancelled_trade_visibility.py
  backfill_zero_price_positions.py  fork of trade/management/commands/backfill_zero_price_positions.py
  delete_security_labels.py         fork of trade/management/commands/delete_security_labels.py
  rename_security_labels.py         fork of trade/management/commands/rename_security_labels.py
  extract_db_ddl.py                 fork of trade/management/commands/extract_db_ddl.py
  position_worker.py                fork of trade/management/commands/position_worker.py
  upload_amsiceq_positions.py       fork of trade/management/commands/upload_amsiceq_positions.py

  eod_ams_position_etl.py           fork of sql/pyspark/eod_ams_position_etl.py
  upload_equity_price_csv.py        fork of sql/pyspark/upload_equity_price_csv.py
```

The first 6 top-level scripts (`sync_gmp_corporate_actions.py` through
`create_sod_snapshot.py`) are the actual nightly Control-M EOD/CORR chain
(see `docs/CONTROL_M_EOD_JOBS.md`). The next 7 (`backfill_*` through
`upload_amsiceq_positions.py`) are maintenance/one-off commands, forked for
completeness since they live in the same two directories, but are not part
of the scheduled chain.

### sql/pyspark/ scripts

`sql/pyspark/` has 9 scripts total, but only 2 needed forking:
`eod_ams_position_etl.py` and `upload_equity_price_csv.py` — both do
`django.setup()` and import `core.repositories.impala_connection`, same
problem as the 13 management commands, so they're forked here the same way
(their Django bootstrap block is swapped for `lib`'s; both already used
plain `argparse` + their own `if __name__ == '__main__':`, not Django's
`BaseCommand`, so no `management_base.py`/`run_command()` involvement).

The other 7 (`eod_ca_cash_flow.py`, `generic_file_ingest.py`,
`ingest_trade_hive_to_kudu.py`, `ingest_trade_simple.py`,
`merge_gmp_equity_price.py`, `merge_gmp_security.py`,
`merge_position_master.py`) are genuine PySpark DataFrame jobs
(`SparkSession`/`functions`/`Window`) with **zero Django or app-module
imports already** — they were not forked, and don't need to be. Nothing in
this whole `sql/pyspark/` directory (all 9 files) uses any 3.7+/3.8+/3.9+/
3.10+-only syntax (no walrus, no `match`, no `X | Y` type hints, no
`removeprefix`/`removesuffix`) — confirmed by a full-directory scan.

## What changed vs. the original files

Only import lines changed. Every `add_arguments()` / `handle()` method body
is byte-for-byte identical to the Django original. Specifically:

- `django.conf.settings` → `lib.config.settings` (reads `config/environments.py`
  directly plus the same env-var overrides `config/settings.py` applies —
  `config/environments.py` has zero Django dependency, so it's imported
  directly rather than duplicated).
- `django.core.cache.cache` → `lib.cache.cache` (simple in-process TTL dict;
  each script is a short-lived batch process, so no cross-run cache sharing
  was ever relied upon).
- `django.core.management.base.BaseCommand` / `CommandError` →
  `lib.management_base` (reproduces `self.style.{SUCCESS,ERROR,WARNING,
  HTTP_INFO,MIGRATE_HEADING}`, `self.stdout`/`self.stderr`, and a
  `run_command(Command)` CLI entrypoint replacing manage.py's dispatch).
- `core.notifications` (`notify_user`/`notify_admins`) → `lib.notifications`
  — used only by `position_worker.py` via `position_queue_service.py`. The
  original pushes to a live Django Channels WebSocket group; there's no
  live UI connected to a batch job, so this shim skips the WS push and the
  in-process pending-queue, but still UPSERTs into `cis_notification` so
  the event is visible next time someone opens the CIS web UI, and always
  logs locally.
- `core.notifications.constants` is imported **directly from the original
  tree**, unforked — it's pure constants/string-helpers with zero Django
  dependency.

`edge_jobs_py36/lib/__init__.py` inserts both the project root and the
`edge_jobs_py36/` directory onto `sys.path` on first import, so `lib.*`
modules can do `import config.environments` / `import core.notifications.constants`
directly, and each top-level script can do `from lib.xxx import yyy`
regardless of the current working directory it's invoked from.

## One incidental bug found (not fixed in the original)

`trade/management/commands/upload_amsiceq_positions.py` line 30 reads
`settings.IMPALA_CONFIG['DATABASE']` at **module level**, but the file only
ever imports `django.conf.settings` **locally inside `_load_excel()`**
(line 155) — there is no module-level import of `settings` anywhere in the
original file. This means `python manage.py upload_amsiceq_positions`
currently raises `NameError: name 'settings' is not defined` the moment
Django loads the command module, on the unmodified original. The fork here
(`edge_jobs_py36/upload_amsiceq_positions.py`) adds the missing
`from lib.config import settings` import so it actually runs — the
original file was intentionally left untouched per instruction, so this bug
still needs a real fix there separately.

## Required packages for the Python 3.6 venv

Everything below is already in the main `requirements.txt`; this is the
subset actually needed (no Django, no Channels/daphne/redis, no DRF):

```
impyla                       # the impala.dbapi module — actually needed to talk to Impala at all;
                              # optional only at *import* time (impala_connection.py degrades
                              # gracefully with a warning if missing, matching the original)
PyHive==0.7.0
thrift==0.16.0
thrift-sasl==0.4.3
python-dotenv==1.0.1         # optional — only if you want .env loading; config.py works from plain env vars otherwise
pandas>=1.1                  # upload_amsiceq_positions.py only (reads .xlsx)
openpyxl>=3.1.0              # pandas' .xlsx engine, for the same script
dataclasses                  # PyPI backport — stdlib only from Python 3.7+; system_date_service.py and trade_validation_repository.py use @dataclass
```

## Environment variables

Same as the main app: `CIS_ENV` (`LOCAL`/`SIT`/`UAT`/`PROD`/`DR`),
`IMPALA_HOST`, `IMPALA_PORT`, `IMPALA_DB`, `IMPALA_AUTH`, `IMPALA_USE_SSL`,
`IMPALA_TIMEOUT`, `IMPALA_POOL_SIZE`, `IMPALA_QUERY_TIMEOUT_S`,
`IMPALA_KRB_SERVICE_NAME` / `KRB_SERVICE_NAME`. See
`config/environments.py` for full defaults per `CIS_ENV`.

## How to run these — no spark-submit needed

None of the 15 scripts in this package touch Spark's distributed engine
(`SparkSession`/`SparkContext`/executor tasks) — they're pure Python +
Impala via `impyla`, same as `sql/pyspark/eod_ams_position_etl.py` always
was despite living in a directory named `pyspark`. `spark-submit` would
only ever be acting as a pass-through process launcher here, adding
indirection (YARN scheduling, log-fetching via `yarn logs` in cluster
mode) with zero functional benefit. As long as `python3.6` is directly
callable on the edge node's shell, just run these as plain scripts.

**One-time setup:**

```bash
cd /app/CISGW/cis_etl_env_11          # or wherever you keep this on the edge node
python3.6 -m venv edge_py36_env
source edge_py36_env/bin/activate
pip install impyla PyHive==0.7.0 thrift==0.16.0 thrift-sasl==0.4.3 \
            python-dotenv==1.0.1 dataclasses pandas openpyxl
```

Copy (or `git pull`) the full `cis_trade_hive` project tree onto the edge
node — `edge_jobs_py36/lib/__init__.py`'s `sys.path` bootstrap expects
`edge_jobs_py36/` to sit at its normal relative location inside the repo,
so it can reach the Django-free `config/environments.py` and
`core/notifications/constants.py` modules directly.

**Set environment variables** (same ones the app / Control-M already uses):

```bash
export CIS_ENV=SIT            # or UAT / PROD
export IMPALA_AUTH=GSSAPI     # only if overriding the CIS_ENV default
# ...whatever else your .env / Control-M job variables normally set
```

**Run:**

```bash
cd edge_jobs_py36
source /app/CISGW/cis_etl_env_11/edge_py36_env/bin/activate

python3.6 sync_gmp_corporate_actions.py
python3.6 process_corporate_actions.py
python3.6 process_approved_cashflows.py --run-type EOD
python3.6 process_settlements.py
python3.6 refresh_positions.py --run-type EOD
python3.6 create_sod_snapshot.py

python3.6 eod_ams_position_etl.py --processing-date 20260806
python3.6 upload_equity_price_csv.py --file prices.csv
```

Same arguments as the Django originals / the original standalone scripts
(`add_arguments()` bodies and `argparse` setups are unchanged) — see
`docs/CONTROL_M_EOD_JOBS.md` for the full flag reference per command.

If a bare `python3.6` interpreter later turns out not to be directly
callable on some other edge node (only reachable through spark-submit's
bundled environment, or ops mandates spark-submit for queue accounting /
logging consistency), these same scripts still work unchanged as
`spark3-submit`'s pass-through target in **client mode** — no `--conf`
Python overrides needed as long as 3.6 is already that node's pinned
default:

```bash
/usr/bin/spark3-submit --master yarn --deploy-mode client \
    sync_gmp_corporate_actions.py
```

## Running as YARN applications via spark-submit

`run_via_spark.py` is a thin generic wrapper (added for ops that want each
job registered as a real YARN application — ResourceManager UI visibility,
`yarn logs -applicationId ...` retrieval, queue accounting — rather than a
bare background process). It opens a minimal `SparkSession` purely to
register the app, then runs the target script's unmodified `__main__`
block via `runpy`. No job logic is duplicated here; the six EOD/CORR
scripts (and the maintenance ones) are unchanged.

```bash
cd edge_jobs_py36
source /app/CISGW/cis_etl_env_11/edge_py36_env/bin/activate

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py sync_gmp_corporate_actions.py

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py process_corporate_actions.py

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py process_approved_cashflows.py --run-type EOD

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py process_settlements.py

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py refresh_positions.py --run-type EOD

/usr/bin/spark3-submit --master yarn --deploy-mode client \
    run_via_spark.py create_sod_snapshot.py
```

Each invocation shows up in the YARN ResourceManager UI as
`cis_edge_job:<script>.py`. Job-specific arguments go **after** the target
script name, exactly as they would with a plain `python3.6 <script>.py`
call — `run_via_spark.py` only intercepts `sys.argv[0]` to register the
Spark app, then hands the rest through untouched.

Requires `pyspark` in the edge node's Python 3.6 venv
(`pip install pyspark==<version matching the cluster's Spark3>`), on top
of the packages listed above. `deploy-mode cluster` also works if ops
prefers it, but client mode keeps job stdout/stderr on the invoking
terminal, which is usually more convenient for Control-M log capture.

## Verification performed

- Every file in this package was diffed against its original: only import
  lines (plus the sys.path bootstrap / `run_command()` trailer on the
  command-style scripts) differ — everything else (docstrings, SQL,
  business logic) is byte-for-byte identical.
- All 36 files (21 in `lib/`, 15 top-level scripts) pass `py_compile`
  (checked under Python 3.14 as a superset proxy — no walrus operator,
  `match` statement, `X | Y` type-hint syntax, `str.removeprefix`/
  `removesuffix`, or positional-only `/` parameters appear anywhere in
  this dependency closure, so nothing here needs 3.7+/3.8+/3.9+/3.10+
  syntax beyond `dataclasses`, which has an official PyPI backport for
  3.6).
  **Caveat found in real use (2026-08-11):** `py_compile` only checks
  syntax, not runtime semantics — `tuple[bool, Optional[int]]` (a bare
  builtin generic subscript, PEP 585) is syntactically valid on every
  Python 3 version, so `py_compile` never flags it, but `tuple` doesn't
  support `[]` at all until 3.9; under 3.6 it raises `TypeError: 'type'
  object is not subscriptable` at import time (annotations are evaluated
  eagerly), not a `SyntaxError`. Found via a live failure on the SIT edge
  node in `lib/corporate_action_repository.py`,
  `lib/cash_flow_repository.py`, and `lib/trade_kudu_repository.py`;
  fixed by importing `Tuple` from `typing` and using `Tuple[...]` instead.
  If you add new code to this package, grep for bare
  `tuple[`/`list[`/`dict[`/`set[`/`type[` before trusting `py_compile`
  alone.
- All 15 top-level scripts were imported standalone (not via `__main__`)
  under the project's actual Python 3.14 venv (no Django installed on the
  import path). The 13 command-style scripts additionally had their
  `Command` class instantiated and `add_arguments()` run against a real
  `argparse.ArgumentParser` — confirming the whole `lib/` dependency graph
  resolves with zero Django imports anywhere.
- Not yet tested: an actual `impyla` connection against real Impala under
  a real Python 3.6 interpreter, since neither is available in this
  development environment. Test that on the edge node before relying on
  this for a live Control-M run.
