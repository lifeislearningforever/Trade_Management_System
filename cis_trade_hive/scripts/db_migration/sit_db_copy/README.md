# SIT Database Copy Suite

Copies **all tables** from a source Impala/Kudu database — Hive external
tables, Hive managed tables, and native Kudu tables — into a target database,
including one with a **different name** (e.g. restoring a SIT snapshot into a
freshly-created `gmp_cis_dev` database instead of overwriting `gmp_cis`).

## Why this exists

None of the other backup/restore scripts in `scripts/` handle all three table
types *and* a differently-named target in one pass:

| Script | All 3 table types | DDL + data | Rename target DB |
|---|---|---|---|
| `extract_sit_ddl.py` (this suite) | Yes | Yes | Yes |
| `migrate_uat_to_sit.py` | Kudu only | Data only | No |
| `kudu_full_backup.py` / `kudu_full_restore.py` | Kudu only | Yes | No |
| `backup_sit_to_local.py` / `restore_sit_from_local.py` | Yes | Yes | Partial (Hive-managed tables get mis-restored as EXTERNAL; Kudu tables must pre-exist) |

`extract_sit_ddl.py` uses `SHOW CREATE TABLE`, which Impala already fully
qualifies with the source database name for every table type (including the
`kudu.table_name` entry in a native Kudu table's `TBLPROPERTIES`), so
rewriting `source_db.table` → `target_db.table` in the extracted text is
sufficient to retarget the whole DDL to a new database name.

## How this works when source and target can't reach each other

This is **not** a live DB-to-DB copy, and it does not need a network path
between the source and target Impala clusters. It's two decoupled steps
connected by flat files:

```
[machine with access to SOURCE]  extract_sit_ddl.py  ->  output/*.sql, deploy_to_uat.sh
              |
              |  copy the output/ folder over (scp, jump host, artifact
              |  store, USB — any transport your org allows)
              v
[machine with access to TARGET]  ./deploy_to_uat.sh --host target-host --kerberos --include-data
```

1. **Extract** runs wherever you *can* reach the source (old SIT). It reads
   DDL and data over that connection and writes everything to local `.sql`
   files under `output/`. Nothing is sent to the target at this stage —
   the target host isn't even contacted.
2. **Deploy** (`output/deploy_to_uat.sh`) runs wherever you *can* reach the
   target (new SIT/UAT). It only reads those local `.sql` files and applies
   them via `impala-shell` against whatever `--host` you give it.

So the only thing that has to cross the network boundary between the two
environments is the generated `output/` folder itself, not a database
connection. If neither machine can reach both clusters, run extraction from
a bastion/jump box that has access to the source, copy `output/` to one that
has access to the target, and run `deploy_to_uat.sh` there.

## Files

- `extract_sit_ddl.py` — does the extraction. Connects to the source Impala
  (via `impala-shell` or PyHive), reads `SHOW CREATE TABLE` / data for every
  table, requalifies the DDL to the target database name, and writes SQL
  files plus a `deploy_to_uat.sh` script for applying them to the target.
- `run_extraction.sh` — a convenience wrapper around `extract_sit_ddl.py`
  with friendlier flag names, Kerberos ticket checking, and colored status
  output. Optional — you can call `extract_sit_ddl.py` directly instead.
- `output/` — created on first run. Holds the generated DDL, data, summary,
  and `deploy_to_uat.sh` files. Not committed to git (regenerated per run).

## Prerequisites

- Network access / Kerberos ticket (`kinit`) for the source Impala host if
  using `--kerberos`.
- Python 3 with either `impala-shell` on `PATH` (recommended for
  Kerberos/CML) or the `pyhive` package installed (for local Docker, no
  Kerberos).
- The **target** database does not need to exist beforehand — the generated
  DDL includes `CREATE DATABASE IF NOT EXISTS <target_db>`.

## Usage

### 1. Extract from the source (reads only, writes nothing on the source)

```bash
cd scripts/db_migration/sit_db_copy

# Same-name copy (target defaults to source) — e.g. refreshing SIT from itself
./run_extraction.sh --use-impala-shell --host sit-impala-host --kerberos --include-data

# Copy into a DIFFERENTLY-NAMED target database (the SIT-with-new-name case)
./run_extraction.sh --use-impala-shell --host sit-impala-host --kerberos --include-data \
    --source-database gmp_cis --target-database gmp_cis_dev

# Local Docker, no Kerberos
./run_extraction.sh --host localhost --port 21050 --include-data \
    --source-database gmp_cis --target-database gmp_cis_dev
```

Or call the Python script directly (same flags):

```bash
python3 extract_sit_ddl.py --use-impala-shell --host sit-impala-host --kerberos \
    --source-database gmp_cis --target-database gmp_cis_dev --include-data
```

This produces, under `output/`:

- `00_migration_summary_<ts>.txt` — table list, row counts, success/fail status
- `01_all_tables_ddl_<ts>.sql` — every table's `CREATE TABLE`, requalified to
  the target database, with `CREATE TABLE IF NOT EXISTS` by default (see
  `--drop-existing` below)
- `02_all_tables_data_<ts>.sql` — `UPSERT INTO` statements for every table's
  data (only if `--include-data` was passed)
- `tables/<table>.sql` — the same DDL split per table
- `data/<table>_data.sql` — the same data split per table
- `deploy_to_uat.sh` — executable script that runs the DDL (and data, with
  `--include-data`) against a target host via `impala-shell`

### 2. Apply to the target

```bash
cd output
./deploy_to_uat.sh --host target-impala-host --kerberos            # DDL only
./deploy_to_uat.sh --host target-impala-host --kerberos --include-data   # DDL + data
```

### 3. Verify the copy

```bash
impala-shell -i target-impala-host:21050 -d gmp_cis_dev -q "SHOW TABLES"
impala-shell -i target-impala-host:21050 -d gmp_cis_dev -q "SELECT COUNT(*) FROM cis_trade"
```

Compare table list and row counts against `00_migration_summary_<ts>.txt`
from the extraction step.

## Key flags (`extract_sit_ddl.py`)

| Flag | Default | Purpose |
|---|---|---|
| `--source-database` | `gmp_cis` | Database to read DDL/data from |
| `--target-database` | same as source | Database name to generate DDL/data for — set this to restore into a differently-named database |
| `--drop-existing` | off | Emit `DROP TABLE IF EXISTS` before every `CREATE TABLE` (destructive — wipes the target table first). Default is `CREATE TABLE IF NOT EXISTS`, safe to re-run against a target that already has some tables |
| `--tables` | all | Comma-separated list to limit extraction |
| `--include-data` | off | Also extract row data as `UPSERT` statements |
| `--data-limit` | none | Cap rows per table (useful for a first test run) |
| `--use-impala-shell` | off (uses PyHive) | Recommended for Kerberos/CML; PyHive mode is for local Docker without Kerberos |

Run `python3 extract_sit_ddl.py --help` for the full list (host/port/SSL/auth
options).

## Testing this safely before a real SIT copy

1. Run extraction with `--data-limit 10` against the source first, so
   `deploy_to_uat.sh --include-data` only loads a handful of rows per table.
2. Point `--target-database` at a throwaway database name and deploy to a
   non-production Impala/Kudu instance (e.g. local Docker).
3. Confirm `SHOW TABLES IN <target_db>` matches the source's table count
   from `00_migration_summary_<ts>.txt`, and spot-check row counts on a few
   tables (including at least one Kudu-native table and one Hive external
   table) to confirm both DDL requalification and data load worked.
4. Only after that passes, re-run without `--data-limit` against the real
   SIT source and target.
