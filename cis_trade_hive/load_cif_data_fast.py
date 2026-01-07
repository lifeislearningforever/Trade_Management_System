"""
Fast bulk load CIF data into cis_counterparty_cif_kudu table
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

def load_cif_data_fast(file_path, batch_size=500):
    """Load CIF data using bulk UPSERT"""

    print(f"Starting fast CIF data load from: {file_path}")
    print(f"Batch size: {batch_size}")

    total_records = 0
    success_count = 0
    batch_values = []

    try:
        with open(file_path, 'r') as f:
            # Skip header
            header = f.readline()

            for line_num, line in enumerate(f, start=2):
                line = line.strip()
                if not line:
                    continue

                parts = line.split('|')
                if len(parts) < 5:
                    continue

                m_label = parts[1].strip()
                counterparty_short_name = parts[2].strip()
                country = parts[3].strip()
                isin = parts[4].strip()

                # Build value tuple
                value_str = f"""(
                    '{escape_sql(counterparty_short_name)}',
                    '{escape_sql(m_label)}',
                    '{escape_sql(country)}',
                    '{escape_sql(isin)}',
                    TRUE, FALSE,
                    'system_load', 'system_load',
                    'GMP_CIS', 'REFERENCE',
                    '{datetime.now().strftime("%Y-%m-%d")}'
                )"""

                batch_values.append(value_str)
                total_records += 1

                # Execute batch
                if len(batch_values) >= batch_size:
                    values_sql = ',\n'.join(batch_values)
                    upsert = f"""
                    UPSERT INTO cis_counterparty_cif_kudu (
                        counterparty_short_name, m_label, country, isin,
                        is_active, is_deleted,
                        created_by, updated_by,
                        src_system, data_cat, processing_date
                    )
                    VALUES {values_sql}
                    """

                    try:
                        impala_manager.execute_write(upsert, database='gmp_cis')
                        success_count += len(batch_values)
                        print(f"Loaded: {success_count}/{total_records} records")
                        batch_values = []
                    except Exception as e:
                        print(f"Error: {str(e)[:200]}")
                        batch_values = []

            # Execute remaining
            if batch_values:
                values_sql = ',\n'.join(batch_values)
                upsert = f"""
                UPSERT INTO cis_counterparty_cif_kudu (
                    counterparty_short_name, m_label, country, isin,
                    is_active, is_deleted,
                    created_by, updated_by,
                    src_system, data_cat, processing_date
                )
                VALUES {values_sql}
                """

                try:
                    impala_manager.execute_write(upsert, database='gmp_cis')
                    success_count += len(batch_values)
                    print(f"Loaded final batch: {success_count}/{total_records}")
                except Exception as e:
                    print(f"Error: {str(e)[:200]}")

        print("\n" + "="*60)
        print(f"Total processed: {total_records}")
        print(f"Successfully loaded: {success_count}")
        print("="*60)

    except Exception as e:
        print(f"Error: {str(e)}")
        raise

if __name__ == '__main__':
    load_cif_data_fast('sql/sample_data/gmpcisissuercif 2.txt', batch_size=500)
