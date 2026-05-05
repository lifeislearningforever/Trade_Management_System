"""
Django management command to export DDL for all tables in gmp_cis.

Uses Impala's SHOW CREATE TABLE to generate accurate DDL for both
Kudu and Hive external tables as they currently exist on the cluster.

For Kudu tables the raw DDL is cleaned so the output is portable across
environments (dev / SIT / UAT / PROD):
  - Column-level ENCODING and COMPRESSION clauses are stripped
  - Column DEFAULT values are stripped
  - TBLPROPERTIES reduced to only 'kudu.master_addresses' with a
    placeholder value so the file can be applied to any cluster

Usage:
    python manage.py export_ddl
    python manage.py export_ddl --output /path/to/output.sql
    python manage.py export_ddl --database gmp_cis
    python manage.py export_ddl --table cis_trade
"""

import os
import re
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from core.repositories.impala_connection import impala_manager


# ---------------------------------------------------------------------------
# Regex patterns for Kudu DDL cleaning
# ---------------------------------------------------------------------------

# Column-level storage attributes appended after the type, e.g.:
#   col_name STRING ENCODING AUTO_PLAIN_ENCODING COMPRESSION DEFAULT_COMPRESSION
#   col_name BIGINT ENCODING BIT_SHUFFLE COMPRESSION LZ4 DEFAULT 0
#   col_name STRING NOT NULL ENCODING PLAIN_ENCODING COMPRESSION SNAPPY
_COL_STORAGE_RE = re.compile(
    r'\s+ENCODING\s+\S+'          # ENCODING <name>
    r'(?:\s+COMPRESSION\s+\S+)?'  # optional COMPRESSION <name>
    r'(?:\s+DEFAULT\s+\S+)?',     # optional DEFAULT <value>
    re.IGNORECASE
)

# Also catch COMPRESSION without preceding ENCODING
_COL_COMPRESSION_RE = re.compile(
    r'\s+COMPRESSION\s+\S+'
    r'(?:\s+DEFAULT\s+\S+)?',
    re.IGNORECASE
)

# Standalone DEFAULT clause on a column (without ENCODING/COMPRESSION)
_COL_DEFAULT_RE = re.compile(
    r'\s+DEFAULT\s+\S+',
    re.IGNORECASE
)

# TBLPROPERTIES block — capture everything between the parens
_TBLPROPS_BLOCK_RE = re.compile(
    r'TBLPROPERTIES\s*\(.*?\)',
    re.IGNORECASE | re.DOTALL
)

# Properties to keep inside TBLPROPERTIES for Kudu tables (others dropped)
_KUDU_KEEP_PROPS = {'kudu.master_addresses', 'kudu.table_name'}

# kudu.master_addresses value to use in the cleaned output
_MASTER_PLACEHOLDER = '${KUDU_MASTERS}'


def _clean_tblproperties(block: str, is_kudu: bool) -> str:
    """
    Rebuild TBLPROPERTIES keeping only portable keys.
    For Kudu: keep kudu.master_addresses (with placeholder) and kudu.table_name.
    For Hive: return the block unchanged.
    """
    if not is_kudu:
        return block

    # Parse out individual key='value' pairs
    pairs = re.findall(r"'([^']+)'\s*=\s*'([^']*)'", block)
    kept = []
    for key, val in pairs:
        key_lower = key.lower()
        if key_lower == 'kudu.master_addresses':
            kept.append(f"  'kudu.master_addresses' = '{_MASTER_PLACEHOLDER}'")
        elif key_lower == 'kudu.table_name':
            kept.append(f"  'kudu.table_name' = '{val}'")
        # everything else (kudu.cluster_id, etc.) is dropped

    if kept:
        return 'TBLPROPERTIES (\n' + ',\n'.join(kept) + '\n)'
    return ''


def clean_kudu_ddl(ddl: str) -> str:
    """
    Strip environment-specific and storage-level noise from a Kudu DDL string
    so the result is portable across dev / SIT / UAT / PROD clusters.

    Removes:
      - ENCODING <name> on column definitions
      - COMPRESSION <name> on column definitions
      - DEFAULT <value> on column definitions
      - kudu.cluster_id and other non-portable TBLPROPERTIES keys
      - Replaces kudu.master_addresses value with ${KUDU_MASTERS} placeholder
    """
    # 1. Clean column-level storage attributes line by line so we don't
    #    accidentally touch the PARTITION BY or TBLPROPERTIES sections.
    lines = ddl.split('\n')
    cleaned_lines = []
    in_tblprops = False
    tblprops_buf = []

    for line in lines:
        stripped = line.strip().upper()

        # Detect start of TBLPROPERTIES block
        if stripped.startswith('TBLPROPERTIES'):
            in_tblprops = True
            tblprops_buf = [line]
            if ')' in line:  # single-line TBLPROPERTIES
                block = _TBLPROPS_BLOCK_RE.search('\n'.join(tblprops_buf))
                if block:
                    cleaned_lines.append(
                        _clean_tblproperties(block.group(0), is_kudu=True)
                    )
                in_tblprops = False
                tblprops_buf = []
            continue

        if in_tblprops:
            tblprops_buf.append(line)
            if ')' in line:  # end of multi-line TBLPROPERTIES
                full_block = '\n'.join(tblprops_buf)
                block = _TBLPROPS_BLOCK_RE.search(full_block)
                if block:
                    cleaned_lines.append(
                        _clean_tblproperties(block.group(0), is_kudu=True)
                    )
                in_tblprops = False
                tblprops_buf = []
            continue

        # Strip ENCODING / COMPRESSION / DEFAULT from column definition lines.
        # Only apply to lines that look like column defs (inside the CREATE block,
        # before PRIMARY KEY / PARTITION BY).
        # Heuristic: line starts with whitespace and contains a type keyword.
        if re.match(r'^\s+\w', line) and not stripped.startswith('PRIMARY KEY') \
                and not stripped.startswith('PARTITION') \
                and not stripped.startswith(')'):
            line = _COL_STORAGE_RE.sub('', line)
            line = _COL_COMPRESSION_RE.sub('', line)
            line = _COL_DEFAULT_RE.sub('', line)

        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


class Command(BaseCommand):
    help = 'Export portable DDL for all tables in gmp_cis using SHOW CREATE TABLE'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database', default='gmp_cis',
            help='Impala database to export (default: gmp_cis)'
        )
        parser.add_argument(
            '--output',
            help='Output SQL file path (default: sql/ddl/export_<db>_<timestamp>.sql)'
        )
        parser.add_argument(
            '--table',
            help='Export a single table only'
        )
        parser.add_argument(
            '--raw', action='store_true', default=False,
            help='Write raw DDL without cleaning Kudu storage attributes'
        )

    def handle(self, *args, **options):
        db = options['database']
        single_table = options.get('table')
        raw_mode = options['raw']

        # Resolve output path
        output_path = options.get('output')
        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            ddl_dir = os.path.join(base_dir, 'sql', 'ddl')
            os.makedirs(ddl_dir, exist_ok=True)
            suffix = 'raw' if raw_mode else 'clean'
            output_path = os.path.join(ddl_dir, f'export_{db}_{ts}_{suffix}.sql')

        self.stdout.write(self.style.MIGRATE_HEADING(f'Exporting DDL from {db}'))
        if not raw_mode:
            self.stdout.write('  Mode: clean (ENCODING/COMPRESSION/DEFAULT/cluster_id stripped)')

        # --- Get table list ---
        if single_table:
            tables = [single_table]
        else:
            self.stdout.write('Fetching table list...')
            try:
                rows = impala_manager.execute_query(f'SHOW TABLES IN {db}', database=db)
                tables = sorted(r.get('name', '') for r in (rows or []) if r.get('name'))
            except Exception as e:
                raise CommandError(f'Failed to list tables in {db}: {e}')

            if not tables:
                raise CommandError(f'No tables found in database {db}')

        self.stdout.write(self.style.SUCCESS(f'Found {len(tables)} tables'))

        # --- Collect DDL ---
        kudu_tables, hive_tables, failed = [], [], []
        ddl_blocks = []

        for table in tables:
            fqn = f'{db}.{table}'
            try:
                rows = impala_manager.execute_query(
                    f'SHOW CREATE TABLE {fqn}', database=db
                )
                if not rows:
                    failed.append((table, 'Empty result from SHOW CREATE TABLE'))
                    continue

                col_key = list(rows[0].keys())[0]
                ddl_text = '\n'.join(r.get(col_key, '') for r in rows).strip()

                # Detect table type
                upper = ddl_text.upper()
                if 'STORED AS KUDU' in upper:
                    kudu_tables.append(table)
                    ttype = 'KUDU'
                    if not raw_mode:
                        ddl_text = clean_kudu_ddl(ddl_text)
                elif 'EXTERNAL' in upper:
                    hive_tables.append(table)
                    ttype = 'HIVE EXTERNAL'
                else:
                    hive_tables.append(table)
                    ttype = 'HIVE MANAGED'

                ddl_blocks.append((table, ttype, ddl_text))
                self.stdout.write(f'  [{ttype:14s}] {table}')

            except Exception as e:
                failed.append((table, str(e)))
                self.stdout.write(self.style.WARNING(f'  [FAILED       ] {table}: {e}'))

        # --- Write output file ---
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('-- ============================================================\n')
            f.write(f'-- DDL Export: database {db}\n')
            f.write(f'-- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'-- Mode:      {"RAW" if raw_mode else "CLEAN (portable)"}\n')
            f.write(f'-- Tables:    {len(ddl_blocks)} exported, {len(failed)} failed\n')
            f.write(f'-- Kudu:      {len(kudu_tables)}\n')
            f.write(f'-- Hive:      {len(hive_tables)}\n')
            if not raw_mode:
                f.write(f'--\n')
                f.write(f'-- KUDU NOTE: Replace ${{KUDU_MASTERS}} with the actual\n')
                f.write(f'--   kudu.master_addresses for the target environment before\n')
                f.write(f'--   running, e.g.:\n')
                f.write(f'--     sed "s/${{KUDU_MASTERS}}/kudu-master:7051/g" this_file.sql\n')
            f.write('-- ============================================================\n\n')
            f.write(f'USE {db};\n\n')

            for section_label, filter_fn in [
                ('KUDU TABLES', lambda t: t[1] == 'KUDU'),
                ('HIVE TABLES', lambda t: t[1] != 'KUDU'),
            ]:
                section_blocks = [b for b in ddl_blocks if filter_fn(b)]
                if not section_blocks:
                    continue
                f.write('-- ============================================================\n')
                f.write(f'-- {section_label} ({len(section_blocks)})\n')
                f.write('-- ============================================================\n\n')
                for table, ttype, ddl_text in section_blocks:
                    f.write(f'-- [{ttype}] {table}\n')
                    f.write(ddl_text)
                    f.write('\n;\n\n')

            if failed:
                f.write('-- ============================================================\n')
                f.write(f'-- FAILED ({len(failed)}) — could not retrieve DDL\n')
                f.write('-- ============================================================\n')
                for table, reason in failed:
                    f.write(f'-- {table}: {reason}\n')

        # --- Summary ---
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Exported {len(ddl_blocks)} tables '
            f'({len(kudu_tables)} Kudu, {len(hive_tables)} Hive)'
        ))
        if failed:
            self.stdout.write(self.style.WARNING(f'Failed: {len(failed)} tables'))
            for t, r in failed:
                self.stdout.write(f'  - {t}: {r}')
        self.stdout.write(self.style.SUCCESS(f'Output: {output_path}'))
