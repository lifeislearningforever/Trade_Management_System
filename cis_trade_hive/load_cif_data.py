"""
Load CIF data from sample file into cis_counterparty_cif_kudu table
"""

import os
import sys
import django
from datetime import datetime

# Setup Django environment
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.repositories.impala_connection import impala_manager

def escape_sql(value):
    """Escape single quotes in SQL values"""
    if value is None:
        return ''
    return str(value).replace("'", "''")

def load_cif_data(file_path, batch_size=100):
    """Load CIF data from pipe-delimited file"""

    print(f"Starting CIF data load from: {file_path}")
    print(f"Batch size: {batch_size}")

    total_records = 0
    success_count = 0
    error_count = 0
    batch_statements = []

    try:
        with open(file_path, 'r') as f:
            # Skip header line
            header = f.readline()
            print(f"Header: {header.strip()}")

            for line_num, line in enumerate(f, start=2):
                line = line.strip()
                if not line:
                    continue

                # Parse pipe-delimited line
                parts = line.split('|')
                if len(parts) < 5:
                    print(f"Skipping line {line_num}: Insufficient columns")
                    error_count += 1
                    continue

                record_type = parts[0]
                m_label = parts[1].strip()
                counterparty_short_name = parts[2].strip()
                country = parts[3].strip()
                isin = parts[4].strip()

                # Build UPSERT statement
                upsert = f"""
                UPSERT INTO cis_counterparty_cif_kudu (
                    counterparty_short_name, m_label, country, isin,
                    is_active, is_deleted, created_by, updated_by,
                    src_system, data_cat, processing_date
                )
                VALUES (
                    '{escape_sql(counterparty_short_name)}',
                    '{escape_sql(m_label)}',
                    '{escape_sql(country)}',
                    '{escape_sql(isin)}',
                    TRUE,
                    FALSE,
                    'system_load',
                    'system_load',
                    'GMP_CIS',
                    'REFERENCE',
                    '{datetime.now().strftime("%Y-%m-%d")}'
                )
                """

                batch_statements.append(upsert)
                total_records += 1

                # Execute batch when it reaches batch_size
                if len(batch_statements) >= batch_size:
                    try:
                        for stmt in batch_statements:
                            impala_manager.execute_write(stmt, database='gmp_cis')
                        success_count += len(batch_statements)
                        print(f"Loaded batch: {success_count}/{total_records} records")
                        batch_statements = []
                    except Exception as e:
                        print(f"Error executing batch: {str(e)}")
                        error_count += len(batch_statements)
                        batch_statements = []

            # Execute remaining statements
            if batch_statements:
                try:
                    for stmt in batch_statements:
                        impala_manager.execute_write(stmt, database='gmp_cis')
                    success_count += len(batch_statements)
                    print(f"Loaded final batch: {success_count}/{total_records} records")
                except Exception as e:
                    print(f"Error executing final batch: {str(e)}")
                    error_count += len(batch_statements)

        print("\n" + "="*60)
        print("CIF Data Load Summary:")
        print(f"Total records processed: {total_records}")
        print(f"Successfully loaded: {success_count}")
        print(f"Errors: {error_count}")
        print("="*60)

    except Exception as e:
        print(f"Error loading CIF data: {str(e)}")
        raise

if __name__ == '__main__':
    file_path = 'sql/sample_data/gmpcisissuercif 2.txt'
    load_cif_data(file_path, batch_size=100)
