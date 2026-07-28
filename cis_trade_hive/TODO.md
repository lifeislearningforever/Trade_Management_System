# TODO

## Centralize hardcoded database/table names

**Why:** A new Kudu/Impala database is being stood up for the dev team, with
all the same tables as `gmp_cis`. The application needs to point at it
without breaking, but ~90 application files (excl. `sql/` DDL) hardcode the
literal string `'gmp_cis'` — 376 occurrences total.

**Key finding:** the mechanism for this already exists and works —
`config/environments.py` builds `IMPALA_CONFIG['DATABASE']` from
`os.environ.get('IMPALA_DB', 'gmp_cis')` for every environment. Setting
`IMPALA_DB=<new_db_name>` in `.env` would work today with zero code changes
*if* the rest of the codebase actually read that setting. It doesn't — most
repository/service classes declare `self.DATABASE = 'gmp_cis'` as a literal
and pass `database=self.DATABASE` on every query, which silently overrides
whatever the connection layer would have defaulted to.

**Plan:**
1. ~46 files already have a local `DATABASE = 'gmp_cis'` (or similar
   `*_TABLE`) class constant. One-line fix per file:
   `DATABASE = settings.IMPALA_CONFIG['DATABASE']` — since their SQL text
   already interpolates `{self.DATABASE}`/`{db}` rather than the literal,
   this cascades to every query in the class for free. Low risk, mechanical.
2. ~31 files inline `gmp_cis.table_name` directly in SQL strings with no
   variable at all — these need real per-occurrence edits.
3. Resolve two inconsistencies found during the scan *before* centralizing,
   or a shared module just enshrines them:
   - `cis_security` vs `cis_security_kudu` — genuinely different table names
     used for what looks like the same concept in different files
     (`security_hive_repository.py` vs `upload_amsiceq_positions.py` /
     `setup_security_udf.py`). Confirmed as real drift in the DDL, not a typo.
   - Mixed qualification conventions, sometimes in the same file — some
     queries embed `{DATABASE}.{TABLE}` in the SQL text, others leave the
     table bare and pass `database=` as a separate connection kwarg.
4. `sql/` DDL (165 files) and `scripts/migrate_uat_to_sit.py` are out of
   scope for this pass — separate follow-on effort.

**Not in scope for code changes:** table *existence* in the new database —
that's a DDL/ops step (running the same DDL against the new DB), independent
of the above.
