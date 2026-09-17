# Database Config Normalization

## Problem

The Kudu/Impala database name (`gmp_cis`) is hardcoded in 55 files instead of
being read from a single, overridable source. There's no way to point the
application at a different database (e.g. `gmp_cis_dev`) without editing
code.

A proper config mechanism already exists — `config/environments.py` reads
`IMPALA_DB` from the environment, defaulting to `gmp_cis`, and
`config/settings.py` exposes it as `settings.IMPALA_CONFIG['DATABASE']`. Most
of the codebase just doesn't use it.

## Scope

Found via:
```bash
grep -rlE "DATABASE\s*=\s*['\"]gmp_cis['\"]" . --include="*.py"
```

56 files matched. Two are handled differently:

| Group | Count | Fix |
|---|---|---|
| Django app code (repositories, services, management commands) | 41 | `DATABASE = settings.IMPALA_CONFIG['DATABASE']` |
| Standalone scripts with no Django context (`scripts/`, `sql/pyspark/`, `sql/kudu_setup/`, `config/cml_app.py`) | 14 | `DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')` |
| `scripts/db_migration/sit_db_copy/extract_sit_ddl.py` | 1 | **Excluded** — see below |

Both fixed groups ultimately read the same `IMPALA_DB` environment variable,
so after the change the database name becomes a single override point.

### Why `extract_sit_ddl.py` is excluded

That script already solves a harder version of this problem: it takes
`--source-database` and `--target-database` as CLI arguments so a copy can
be extracted from `gmp_cis` and deployed into a *differently-named* target
(e.g. `gmp_cis_dev`), rewriting every `source_db.table` qualifier in the
generated DDL via `requalify_ddl()`. Its `DATABASE = 'gmp_cis'` constant is
just the CLI default for `--source-database`, not a hardcode blocking reuse.
Forcing it onto the shared `IMPALA_DB` env var would be redundant at best and
would blur its actual (correct) design.

### Deliberately not touched: SQL DDL and shell scripts

~149 `.sql` files under `sql/` and ~10 shell scripts also contain the literal
string `gmp_cis`, but many of those occurrences are **table name prefixes**,
not the schema name — e.g. `gmp_cis_sta_dly_fx_rates` is a *table*, not
`database.table`. A blind find/replace of the substring `gmp_cis` across
those files would corrupt table names, not just retarget the schema. If
these need to be templatized too, that's a separate, more careful pass —
see `extract_sit_ddl.py`'s `requalify_ddl()` for the pattern to follow
(rewrite only `db.table` qualifiers, not arbitrary substrings).

## The fix: `scripts/normalize_db_config.py`

A script that performs the replacement above, plus adds the corresponding
import (`from django.conf import settings` or `import os`) to any file that
doesn't already have it. It correctly handles multi-line parenthesized
imports (`from x import (\n a, b,\n)`) when deciding where to insert.

### Usage

```bash
cd cis_trade_hive

# 1. Dry run -- shows exactly which files/lines would change, touches nothing
python3 scripts/normalize_db_config.py .

# 2. Apply for real
python3 scripts/normalize_db_config.py . --apply

# 3. Review before committing
git diff --stat
git diff

# 4. Sanity-check nothing is syntactically broken
python3 -m compileall -q .
```

All 55 target files were dry-run and apply-tested against a scratch copy of
this repo prior to landing the script; every resulting file parses
(`py_compile`) cleanly. One edge case was caught and fixed in the process: a
file with a multi-line parenthesized import block, where a naive
"insert after the last import line" heuristic would have landed the new
import inside the parentheses and broken syntax.

## After applying

- Set `IMPALA_DB=<name>` in the environment (or `.env`) to point the whole
  application at a different database — no code changes needed for any of
  the 55 files.
- Existing behavior is unchanged when `IMPALA_DB` is unset: everything still
  defaults to `gmp_cis`.
