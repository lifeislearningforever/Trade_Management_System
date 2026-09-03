#!/usr/bin/env python3
"""
Normalize hardcoded DATABASE = 'gmp_cis' literals to read from central config.

- Django app files (repositories/services/management commands): replaced with
  settings.IMPALA_CONFIG['DATABASE']  (import added if missing).
- Standalone scripts (scripts/, sql/pyspark/, sql/kudu_setup/, config/cml_app.py)
  that don't run inside Django: replaced with os.environ.get('IMPALA_DB', 'gmp_cis')
  (import os added if missing).

Not included: scripts/db_migration/sit_db_copy/extract_sit_ddl.py. That script
already takes the database as a real --source-database/--target-database CLI
parameter (needed so source and target can differ, e.g. gmp_cis -> gmp_cis_dev)
and its DATABASE constant is documented as just the CLI default -- it doesn't
need this treatment. See docs/DATABASE_CONFIG_NORMALIZATION.md.

Usage:
    python3 scripts/normalize_db_config.py .            # dry run from repo root
    python3 scripts/normalize_db_config.py . --apply     # actually writes the changes
"""
import re
import sys
from pathlib import Path

DATABASE_RE = re.compile(r"DATABASE\s*=\s*['\"]gmp_cis['\"]")

STANDALONE_FILES = [
    "config/cml_app.py",
    "scripts/backup_sit_to_local.py",
    "scripts/backup_uat_to_local.py",
    "scripts/kudu_full_backup.py",
    "scripts/load_migration_data.py",
    "scripts/load_portfolio_data.py",
    "scripts/load_security_data.py",
    "scripts/migrate_uat_to_sit.py",
    "scripts/restore_sit_from_local.py",
    "sql/kudu_setup/run_setup.py",
    "sql/pyspark/eod_ca_cash_flow.py",
    "sql/pyspark/merge_gmp_equity_price.py",
    "sql/pyspark/merge_gmp_security.py",
    "sql/pyspark/merge_position_master.py",
]

DJANGO_FILES = [
    "core/audit/audit_kudu_repository.py",
    "core/notifications/kudu_store.py",
    "core/repositories/system_date_repository.py",
    "market_data/repositories/equity_price_hive_repository.py",
    "portfolio/repositories/portfolio_hive_repository.py",
    "portfolio/services/portfolio_dropdown_service.py",
    "query_builder/repositories/query_builder_repository.py",
    "query_builder/repositories/report_template_repository.py",
    "query_builder/services/sql_builder_service.py",
    "reference_data/management/commands/process_corporate_actions.py",
    "reference_data/management/commands/sync_gmp_corporate_actions.py",
    "reference_data/repositories/ca_cash_flow_queue_repository.py",
    "reference_data/repositories/corporate_action_repository.py",
    "reference_data/services/ca_cash_flow_service.py",
    "reference_data/services/corporate_action_dropdown_service.py",
    "security/repositories/security_hive_repository.py",
    "security/services/security_dropdown_service.py",
    "trade/management/commands/backfill_zero_price_positions.py",
    "trade/management/commands/create_sod_snapshot.py",
    "trade/management/commands/delete_security_labels.py",
    "trade/management/commands/extract_db_ddl.py",
    "trade/management/commands/process_approved_cashflows.py",
    "trade/management/commands/refresh_positions.py",
    "trade/management/commands/rename_security_labels.py",
    "trade/management/commands/upload_amsiceq_positions.py",
    "trade/repositories/cash_flow_repository.py",
    "trade/repositories/position_repository.py",
    "trade/repositories/trade_kudu_repository.py",
    "trade/repositories/trade_validation_repository.py",
    "trade/services/cash_flow_dropdown_service.py",
    "trade/services/multicurrency_service.py",
    "trade/services/position_queue_service.py",
    "trade/services/position_service.py",
    "trade/services/settlement_service.py",
    "trade/services/trade_dropdown_service.py",
    "trade/services/trade_event_queue_service.py",
    "trade/tests/avp_live_fixtures.py",
    "udf/repositories/udf_field_repository.py",
    "udf/repositories/udf_hive_repository.py",
    "upload/repositories/datasource_repository.py",
    "upload/repositories/upload_kudu_repository.py",
]


def insert_import_after_last_toplevel_import(lines, import_line):
    last_import_idx = None
    i = 0
    limit = min(len(lines), 80)
    while i < limit:
        line = lines[i]
        if re.match(r"^(import |from )\S", line):
            last_import_idx = i
            # handle multi-line parenthesized imports: from x import (\n a, b,\n)
            if "(" in line and ")" not in line:
                j = i + 1
                while j < len(lines) and ")" not in lines[j]:
                    j += 1
                last_import_idx = min(j, len(lines) - 1)
                i = last_import_idx
        i += 1
    if last_import_idx is not None:
        lines.insert(last_import_idx + 1, import_line)
    else:
        # no imports found; insert after module docstring or shebang/encoding lines
        insert_at = 0
        i = 0
        while i < len(lines) and (lines[i].startswith("#") or lines[i].strip() == ""):
            i += 1
        if i < len(lines) and (lines[i].startswith('"""') or lines[i].startswith("'''")):
            quote = lines[i][:3]
            j = i + 1
            if lines[i].count(quote) >= 2 and len(lines[i].strip()) > 3:
                insert_at = i + 1
            else:
                while j < len(lines) and quote not in lines[j]:
                    j += 1
                insert_at = j + 1
        else:
            insert_at = i
        lines.insert(insert_at, import_line)
        lines.insert(insert_at + 1, "")
    return lines


def process_file(path, replacement, import_line, import_check_re, apply):
    text = path.read_text()
    if not DATABASE_RE.search(text):
        print(f"  SKIP (no match): {path}")
        return False

    new_text = DATABASE_RE.sub(replacement, text)

    if not import_check_re.search(new_text):
        lines = new_text.splitlines(keepends=True)
        lines = [l if l.endswith("\n") else l + "\n" for l in lines]
        lines = insert_import_after_last_toplevel_import(lines, import_line + "\n")
        new_text = "".join(lines)
        import_note = " (+import added)"
    else:
        import_note = ""

    if apply:
        path.write_text(new_text)
        print(f"  APPLIED{import_note}: {path}")
    else:
        print(f"  WOULD CHANGE{import_note}: {path}")
    return True


def main():
    apply = "--apply" in sys.argv
    root_arg = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(root_arg[0]) if root_arg else Path.cwd()

    print(f"Root: {root}")
    print(f"Mode: {'APPLY' if apply else 'DRY RUN (pass --apply to write changes)'}\n")

    print("== Django-context files (-> settings.IMPALA_CONFIG['DATABASE']) ==")
    for rel in DJANGO_FILES:
        p = root / rel
        if not p.exists():
            print(f"  MISSING: {p}")
            continue
        process_file(
            p,
            replacement="DATABASE = settings.IMPALA_CONFIG['DATABASE']",
            import_line="from django.conf import settings",
            import_check_re=re.compile(r"from django\.conf import settings"),
            apply=apply,
        )

    print("\n== Standalone scripts (-> os.environ.get('IMPALA_DB', 'gmp_cis')) ==")
    for rel in STANDALONE_FILES:
        p = root / rel
        if not p.exists():
            print(f"  MISSING: {p}")
            continue
        process_file(
            p,
            replacement="DATABASE = os.environ.get('IMPALA_DB', 'gmp_cis')",
            import_line="import os",
            import_check_re=re.compile(r"^import os\s*$", re.MULTILINE),
            apply=apply,
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
