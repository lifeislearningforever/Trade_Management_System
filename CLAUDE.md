# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

This directory holds two separate Django projects plus a shared virtualenv. Almost all active work happens in `cis_trade_hive/` — check with the user before touching `Trade_V1/`.

- **`cis_trade_hive/`** — the active project ("CIS Trade Hive"). Has its own detailed `cis_trade_hive/CLAUDE.md` — **read that file before working in this directory**; it covers the Django app structure, Impala/Kudu data layer, testing, and troubleshooting in depth. This top-level file only adds context that spans the whole repo.
- **`Trade_V1/`** — an earlier prototype of the same trade-management concept, built on Django ORM + MySQL (not Kudu/Impala). No recent commit activity. Treat as legacy/reference unless the user explicitly says otherwise.
- **`.venv/`** — shared Python 3.14 virtualenv (`uv`-managed) used by `cis_trade_hive/`. Activate with `source .venv/bin/activate` from the repo root, or reference it directly since `cis_trade_hive` does not have its own venv.

## cis_trade_hive at a glance

Full detail lives in `cis_trade_hive/CLAUDE.md`; the essentials:

- Django 5.2.9 trade management system. **No SQLite/MySQL/Django ORM for business data** — trade, portfolio, position, and reference data are all read/written through raw Impala SQL against Apache Kudu tables, via `core/repositories/impala_connection.py` (`ImpalaConnectionManager`). Writes use Kudu's `UPSERT INTO ... VALUES (?, ...)` syntax, not `INSERT`.
- Layering: `*_kudu_repository.py` (data access) → `*_service.py` (business logic) → views. ~33 repository files across `trade/`, `portfolio/`, `security/`, `reference_data/`, `core/audit/`, `lookup/`.
- Four-Eyes (maker-checker) workflow drives portfolio/trade status transitions: `INITIAL → MODIFIED → PENDING_VALIDATION → VALIDATED/CANCELLED → SETTLED`.
- Local dev talks to a Docker Kudu/Impala container (`NOSASL` auth); SIT/UAT/CML (Cloudera) use Kerberos/LDAP. Config resolution lives in `config/environments.py`.
- Run from `cis_trade_hive/`: `python manage.py runserver`, `pytest`, `python manage.py test_hive` (connection check), `python manage.py create_hive_db` (DDL).

### edge_jobs_py36 fork

`cis_trade_hive/edge_jobs_py36/` is a Python 3.6-compatible fork of select scripts (backfills, ETL/sync jobs, position workers) that run on an older cluster runtime. **When fixing a bug in a file that has a counterpart under `edge_jobs_py36/`, mirror the fix into the fork** — the two copies drift silently otherwise since the fork isn't covered by the main test suite.

## Working notes from past sessions

- The Pending Settlement UAT blank-page bug is still open — two fixes have shipped without finding the root cause. If touching `trade/services/settlement_service.py` or the pending-settlement view/template, be aware prior attempted fixes may not have addressed the actual cause.