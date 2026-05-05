"""
Django management command to export DDL for all tables in gmp_cis.

Uses Impala's SHOW CREATE TABLE to generate accurate DDL for both
Kudu and Hive external tables as they currently exist on the cluster.

Usage:
    python manage.py export_ddl
    python manage.py export_ddl --output /path/to/output.sql
    python manage.py export_ddl --database gmp_cis
    python manage.py export_ddl --table cis_trade
"""

import os
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from core.repositories.impala_connection import impala_manager


class Command(BaseCommand):
    help = 'Export DDL for all tables in gmp_cis using SHOW CREATE TABLE'

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

    def handle(self, *args, **options):
        db = options['database']
        single_table = options.get('table')

        # Resolve output path
        output_path = options.get('output')
        if not output_path:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            ddl_dir = os.path.join(base_dir, 'sql', 'ddl')
            os.makedirs(ddl_dir, exist_ok=True)
            output_path = os.path.join(ddl_dir, f'export_{db}_{ts}.sql')

        self.stdout.write(self.style.MIGRATE_HEADING(f'Exporting DDL from {db}'))

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

                # Impala returns rows with a single column; join them
                col_key = list(rows[0].keys())[0]
                ddl_text = '\n'.join(r.get(col_key, '') for r in rows).strip()

                # Detect table type from DDL
                upper = ddl_text.upper()
                if 'STORED AS KUDU' in upper:
                    kudu_tables.append(table)
                    ttype = 'KUDU'
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
            f.write(f'-- ============================================================\n')
            f.write(f'-- DDL Export: database {db}\n')
            f.write(f'-- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
            f.write(f'-- Tables:    {len(ddl_blocks)} exported, {len(failed)} failed\n')
            f.write(f'-- Kudu:      {len(kudu_tables)}\n')
            f.write(f'-- Hive:      {len(hive_tables)}\n')
            f.write(f'-- ============================================================\n\n')
            f.write(f'USE {db};\n\n')

            # Group: Kudu first, then Hive
            for section_label, filter_fn in [
                ('KUDU TABLES', lambda t: t[1] in ('KUDU',)),
                ('HIVE TABLES', lambda t: t[1] not in ('KUDU',)),
            ]:
                section_blocks = [b for b in ddl_blocks if filter_fn(b)]
                if not section_blocks:
                    continue
                f.write(f'-- ============================================================\n')
                f.write(f'-- {section_label} ({len(section_blocks)})\n')
                f.write(f'-- ============================================================\n\n')
                for table, ttype, ddl_text in section_blocks:
                    f.write(f'-- [{ttype}] {table}\n')
                    f.write(ddl_text)
                    f.write('\n;\n\n')

            if failed:
                f.write(f'-- ============================================================\n')
                f.write(f'-- FAILED ({len(failed)}) — could not retrieve DDL\n')
                f.write(f'-- ============================================================\n')
                for table, reason in failed:
                    f.write(f'-- {table}: {reason}\n')

        # --- Summary ---
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Exported {len(ddl_blocks)} tables ({len(kudu_tables)} Kudu, {len(hive_tables)} Hive)'
        ))
        if failed:
            self.stdout.write(self.style.WARNING(f'Failed: {len(failed)} tables'))
            for t, r in failed:
                self.stdout.write(f'  - {t}: {r}')
        self.stdout.write(self.style.SUCCESS(f'Output: {output_path}'))
