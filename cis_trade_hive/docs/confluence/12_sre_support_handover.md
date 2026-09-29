# CIS Trade Hive — System Architecture

2026-09-17 · @u_EZjOam0WaGdiwI513_uzcw

## 1. Purpose of this page

This is the SRE/Support handover page for **CIS Trade Hive**, a Django 5.2.9 trade management system covering portfolios, trades, positions (AVP), corporate actions, cash flows, and reference/security master data for a maker-checker (Four-Eyes) controlled workflow. It is hosted as a **Cloudera CML Application** and stores all business data in **Apache Kudu**, accessed through **Impala** (reads) and **Hive** (ACID writes), governed by **Ranger** policies.

A full 18-page architecture doc set already exists in the repo (see section 2) and covers the deep technical detail. **This page is deliberately narrower**: it's the operational quick-reference a support engineer reaches for during an incident — what runs where, what's known to be broken, and where to look first.

## 2. Full architecture docs already exist — start there for depth

The repo has a complete Confluence-ready doc set at `cis_trade_hive/docs/confluence/` (18 files, written for exactly this handover, index at `00_INDEX.md`). Copy these into Confluence as-is if they aren't there yet:

| Page | Covers |
| --- | --- |
| 01 What Is CIS | Plain-English intro for any reader |
| 02 System Architecture | Django app layout, repository→service→view layering |
| 03 Kudu vs Hive External | Why two engines, when each is used |
| 04 ETL & Data Flows | End-to-end data pipelines |
| 05a–05i | Per-module guides: portfolio, trade, position/AVP, corporate actions, securities, market data, UDF, file upload, RBAC |
| 06 Four-Eyes Workflow | Maker-checker status flow |
| 07 Audit Logging | What's logged, where |
| 08 Environments & Configuration | LOCAL/SIT/UAT/PROD/DR details |
| 09 Migration & Backup/Restore | DR tooling |
| 10 Glossary | Domain terms |
| 11 CDP Cluster Access Flow (Ranger) | How CIS reaches Impala/Hive/HDFS through Ranger-enforced service accounts — written specifically for the GIPS/Infrastructure team |

These were last updated April–May 2026; re-verify against current code before treating them as gospel on any fast-moving area (position/AVP logic and corporate actions have changed since).

## 3. Hosting & CDP platform quick-reference

**Hosting:** the app runs as a **Cloudera CML (Machine Learning) Application**, not a standalone server. CML injects `CDSW_APP_PORT` at runtime; `scripts/cml_startup.sh` reads it (`DJANGO_PORT=${CDSW_APP_PORT:-8000}`) and starts two processes together: the Django server and the **Position Queue Worker** (async position-processing background thread pool). `config/cml_app.py` is the CML-specific settings/bootstrap module — it also reads `CDSW_USERNAME` (the CML *service account* running the app, not the visiting user — see the known-issues section, this distinction matters for a real open vulnerability).

**CDP services in use:**

| Service | Role here |
| --- | --- |
| **Apache Kudu** | System of record for all business data (trades, positions, portfolios, audit log). No SQLite/MySQL/ORM. |
| **Impala** | Fast reads against Kudu (`impala-shell -i <host>:21050`). |
| **Hive** | ACID writes — INSERT/UPDATE/DELETE (`beeline -u 'jdbc:hive2://<host>:10000/'`). |
| **HDFS** | File-based upload/export flows (see `upload/` app and `sql/pyspark/` jobs). |
| **Apache Ranger** | Single enforcement point for all cluster access. No end user reaches CDP directly — all requests go through two shared Linux service accounts (`own_cis_svc`, `un_cis_svc`); Ranger policies gate what each account can read/write per database/table/HDFS path. Full flow diagrammed in confluence doc 11. |

**Auth:** LOCAL dev uses `NOSASL` (no Kerberos, Docker Kudu/Impala container). SIT/UAT/PROD/DR all use **Kerberos (GSSAPI)** — a valid ticket (`klist`) is required for the app's service account to reach Impala/Hive. CIS itself has its own login/RBAC layer (Kudu-backed `cis_user`/`cis_group_permissions` tables) which is a **separate, additional layer on top of** Ranger — Ranger only sees the shared Linux service account, not individual CIS users.

## 4. Environments quick-reference

Controlled by a single env var, `CIS_ENV` (defaults to `LOCAL`), read in `config/environments.py`.

| Env | `CIS_ENV` | Impala/Hive host | Auth | Notes |
| --- | --- | --- | --- | --- |
| Local dev | `LOCAL` | `localhost` | NOSASL | Docker Kudu/Impala container |
| SIT | `SIT` | `lxmrwtsgyodt1.sg.uobnet.com` | GSSAPI (Kerberos) | TST.UOBNET.COM domain |
| UAT | `UAT` | `lxmrwtsgvqk2.sg.uobnet.com` | GSSAPI (Kerberos) | SG.UOBNET.COM domain |
| PROD | `PROD` | `lxmrwtsgvqk2.sg.uobnet.com` | GSSAPI (Kerberos) | Same host as UAT — confirm DB/schema separation, not host separation |
| DR | `DR` | `lxmrwtsgvqk2.sg.uobnet.com` | GSSAPI (Kerberos) | See DR sync tooling status in known issues |

Impala DB defaults to `gmp_cis`; Hive DB defaults to `mrw_ima` (non-LOCAL) or `gmp_cis` (LOCAL). All values are env-var-overridable (`IMPALA_HOST`, `IMPALA_PORT`, `IMPALA_DB`, `HIVE_HOST`, etc.) and the Impala DB name alone can also be retargeted without redeploying by editing `config/database.txt` on the gateway host.

**Verify connectivity:** `python manage.py test_hive`. **Verify Kerberos ticket:** `klist`. Full environment detail in confluence doc 08.

## 5. Scheduled/batch jobs runbook

These run as Django management commands, typically cron/scheduled outside the request cycle. A Python-3.6-compatible fork of several of them lives under `edge_jobs_py36/` for an older cluster runtime — **if a fix lands in one copy, check whether the other needs the same fix**, they drift silently.

| Command | Purpose | If it fails / looks stuck |
| --- | --- | --- |
| `process_approved_cashflows` | Applies approved corporate-action cash flows (dividends, capital returns, YTD realise, etc.) to positions in `cis_trade_position`/`cis_position` | Check `cf_processed` flag on the cash flow row; check logs for which basis (SETTLED/TRADED) it queried |
| `refresh_positions` | EOD/CORR batch position recompute; includes a self-heal step (`_cleanup_stale_duplicates`) that retires stale duplicate `is_latest=true` rows in `cis_position` | Check for `LIQN`/equity accounting-section handling and `average_cost_lc` calc (recently fixed, PR #7) |
| `process_settlements` | Settlement date processing (T+0/T+1/backdated) | See `check_settlement_queue.sh`, `cis_settlement_queue` table |
| `position_worker` | Async position-queue worker (ThreadPoolExecutor, 4 workers, 100-item batches, 10s poll, 3 retries then dead-letter) | Also started by `scripts/cml_startup.sh` alongside the Django server — check both processes are up, not just Django |
| `process_corporate_actions` / `sync_gmp_corporate_actions` (reference\_data) | Ingest/sync corporate action events | — |
| `upload_amsiceq_positions` | One-off/manual Excel (`CIS_position_amsiceq.xlsx`) position upload utility | **Do not re-run for the same portfolio/security without checking first** — it has no natural-key dedup and will create duplicate rows if run twice for the same position (see known issues) |
| `create_sod_snapshot` | Start-of-day snapshot | — |
| `backfill_*` / `cleanup_corr_duplicate_positions` | One-time data-correction utilities, not recurring jobs | — |

Related scripts (not management commands, run directly): `scripts/cis_eod.sh`, `scripts/eod_settlement_process.sh`, `scripts/position_worker_daemon.sh`, `scripts/cis_ingestion_wrapper.sh`, `scripts/kudu_maintenance.sh`. Backup/restore tooling: `scripts/kudu_full_backup.py`, `kudu_full_restore.py`, `kudu_incremental_backup.py` (see DR status in known issues). Full pipeline detail in confluence doc 04.

## 6. Known open issues & risks (as of 2026-09-17)

### 🔴 Critical — CML/LDAP login accepts any LANID with no password check

`LoginView.post` in `core/views/auth_views.py` (\~line 64) only checks whether the submitted LANID exists/is enabled — it never verifies a password. Because the app is a CML Application with users added as LDAP collaborators, and LANIDs are visible internally (e.g. in Jira), **anyone who knows a colleague's LANID can log in as them**, with full maker-checker impersonation risk. `CDSW_USERNAME` is the CML service account running the app process, not the visiting user, so there's currently no reliable per-request identity signal. **Planned fix (agreed, not implemented):** drop the free-text login form, trust CML's own LDAP/SSO gate by reading the authenticated LANID from whatever trusted header CML's proxy injects per request, reject with 403 if absent. Blocked on live CML env access to confirm the exact header name — do not guess and ship this blind.

### 🟡 Unresolved — Pending Settlement page blank in UAT

The Trade Pending Settlement page showed 0 rows in UAT despite the DB having 20 matching VALIDATED trades. Two real bugs were found and fixed along the way (case-sensitive status matching in `get_all_trades_multi_filter()`; `ImpalaConnectionManager` silently ignoring the `database` param on reused pooled connections) but a live retest still showed the trade missing afterward — **root cause not yet found**. If this resurfaces, don't re-derive from scratch; re-verify the two fixes actually shipped to UAT, then trace the settlement view's query path.

### 🟡 Data-integrity risk — `position_id` generated by two different algorithms

Most of the codebase computes `position_id` deterministically (MD5 hash of `portfolio|security|basis|date|src_system`, or its SQL `fnv_hash` equivalent), so repeated writes correctly UPDATE the same Kudu row (`cis_position`'s PK is `position_id` alone). Two places still generate a fresh timestamp+UUID id with no natural-key lookup, which creates a **duplicate row instead of updating** if run twice for the same position:

- `upload_amsiceq_positions.py` (Excel upload utility) — live risk if re-run.
- `refresh_positions.py`'s `_insert_eod_position()` — marked "legacy, kept for reference"; appears unused but not yet confirmed dead. A live duplicate was confirmed in `cis_position` for `UOBS_BCHAIN_FVE`/`UQ-UOB-102 CH` (TRADED basis, 2 rows both `is_latest=true`) — **manual data cleanup still outstanding**.

### 🟢 DR sync tooling — partially verified

After the 2026-08-14 DR drill, full backup/restore of Kudu tables (`kudu_full_backup.py`, `kudu_full_restore.py`) was confirmed working against real PROD/DR clusters. **Not yet re-verified on real clusters:** Hive dynamic-partition restore fix, `--latest` auto-discovery, multi-table `--table a,b,c` support, and real `--auto-since` incremental timestamp discovery. Treat any reported issue in those specific features as a fresh bug, not a regression.

## 7. Health checks & first-response steps

| Symptom | First checks |
| --- | --- |
| App unreachable / blank pages everywhere | Is the CML Application running (both Django + position worker per `cml_startup.sh`)? Check `/tmp/cis_django.log`, `/tmp/cis_position_worker.log` on the CML instance. |
| "Impala connection fails" | `klist` for a valid Kerberos ticket (SIT/UAT/PROD/DR); `python manage.py test_hive`; confirm `IMPALA_HOST`/`CIS_ENV` match the target environment. |
| "Permission denied" in-app | Check `cis_user`, `cis_user_group`, `cis_group_permissions` Kudu tables — this is CIS's own RBAC layer, separate from Ranger. |
| A specific page blank but data exists in Kudu (e.g. Pending Settlement) | Known unresolved issue, see section 6 — don't re-diagnose from zero, check the memory notes on that bug first. |
| Upload stuck in `ETL_RUNNING` | No automated watchdog exists yet for stuck uploads — currently a manual DB check/reset via the `upload` app's Kudu tables. |
| Duplicate rows for the same portfolio/security in `cis_position` | Likely the position\_id dual-algorithm issue (section 6) — check which of the two ids is stale before deleting anything. |
| Trade detail/list buttons look wrong for maker vs checker | Four-Eyes button visibility is driven by the `{% can_act %}` template tag in `core/templatetags/core_filters.py`, **not** by the view's own context — fixed for known gaps as of 2026-09-17, but if a new maker/checker gap is reported, look there first. |

All writes go to Kudu `cis_audit_log` (action type, old/new values as JSON, user, IP, timestamp, Four-Eyes approval status) — the first place to check "who did what, when" during an incident. Detail in confluence doc 07.

## 8. Support handover essentials

- **Repo:** `Trade_Management_System`, active project at `cis_trade_hive/` (branch `cis_trade_hive`; `Trade_V1/` is an unrelated legacy prototype — ignore it).
- **Deep architecture reference:** `cis_trade_hive/docs/confluence/` (18 pages, section 2 above).
- **DR drill runbook:** `cis_trade_hive/docs/KUDU_DR_RESTORE_DRILL.md`.
- **Project-level dev guide:** `cis_trade_hive/CLAUDE.md` (app structure, common commands, troubleshooting for local dev).
- **Contacts / escalation path:** *placeholder — fill in the actual on-call rotation, CDP platform team contact, and Ranger/GIPS contact before publishing to Confluence.*
- **Before escalating a Kudu/Impala/Ranger-layer issue:** confirm it isn't a CIS-layer bug first (section 7) — Ranger only sees the shared service account, so "access denied" often means CIS's own RBAC tables, not a Ranger policy.
