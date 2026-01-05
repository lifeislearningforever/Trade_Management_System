"""
Django management command to recreate the cis_udf_field Kudu table with simplified schema.

Usage:
    python manage.py recreate_udf_field_table
"""

import logging
from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Recreate the cis_udf_field Kudu table with simplified schema'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Recreating cis_udf_field Kudu table...'))
        self.stdout.write(self.style.WARNING('⚠️  This will DROP all existing UDF field data!'))

        # Drop existing tables
        self.stdout.write('Dropping existing tables...')
        drop_external_query = "DROP TABLE IF EXISTS gmp_cis.cis_udf_field"
        drop_kudu_query = "DROP TABLE IF EXISTS gmp_cis.cis_udf_field_kudu"

        try:
            impala_manager.execute_write(drop_external_query, database='gmp_cis')
            impala_manager.execute_write(drop_kudu_query, database='gmp_cis')
            self.stdout.write(self.style.SUCCESS('  Existing tables dropped'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'  Drop tables warning: {str(e)}'))

        # Create Kudu table
        create_kudu_query = """
        CREATE TABLE IF NOT EXISTS gmp_cis.cis_udf_field_kudu(
            udf_id BIGINT NOT NULL,
            object_type STRING NOT NULL,
            field_name STRING NOT NULL,
            field_value STRING NOT NULL,
            is_active BOOLEAN DEFAULT true,
            created_by STRING NOT NULL,
            created_at BIGINT NOT NULL,
            updated_by STRING NOT NULL,
            updated_at BIGINT NOT NULL,
            PRIMARY KEY (udf_id)
        )
        PARTITION BY HASH (udf_id) PARTITIONS 4
        STORED AS KUDU
        TBLPROPERTIES('kudu.num_tablet_replicas' = '1')
        """

        # Create external table mapping
        create_external_query = """
        CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_udf_field
        STORED AS KUDU
        TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_udf_field_kudu')
        """

        try:
            # Execute create Kudu table
            self.stdout.write('Creating Kudu table...')
            success = impala_manager.execute_write(create_kudu_query, database='gmp_cis')
            if success:
                self.stdout.write(self.style.SUCCESS('  Kudu table created successfully'))
            else:
                self.stdout.write(self.style.ERROR('  Failed to create Kudu table'))
                return

            # Execute create external table
            self.stdout.write('Creating external table mapping...')
            success = impala_manager.execute_write(create_external_query, database='gmp_cis')
            if success:
                self.stdout.write(self.style.SUCCESS('  External table created successfully'))
            else:
                self.stdout.write(self.style.WARNING('  External table may already exist'))

            # Insert sample data
            self.stdout.write('Inserting sample data...')
            self._insert_sample_data()

            self.stdout.write(self.style.SUCCESS('\n✅ Table recreation complete!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating table: {str(e)}'))
            logger.error(f"Error creating cis_udf_field table: {str(e)}")

    def _insert_sample_data(self):
        """Insert sample entity types and fields."""
        import time
        timestamp = int(time.time() * 1000)

        sample_data = [
            # Entity Types (field_value is empty)
            (1, 'PORTFOLIO', 'object_type', '', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (2, 'EQUITY_PRICE', 'object_type', '', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (3, 'SECURITY', 'object_type', '', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),

            # PORTFOLIO fields
            (100, 'PORTFOLIO', 'portfolio_type', 'Portfolio Type', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (101, 'PORTFOLIO', 'portfolio_category', 'Portfolio Category', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (102, 'PORTFOLIO', 'investment_strategy', 'Investment Strategy', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),

            # EQUITY_PRICE fields
            (200, 'EQUITY_PRICE', 'market', 'Market', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (201, 'EQUITY_PRICE', 'price_source', 'Price Source', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),

            # SECURITY fields
            (300, 'SECURITY', 'security_type', 'Security Type', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
            (301, 'SECURITY', 'industry', 'Industry', 'true', 'SYSTEM', timestamp, 'SYSTEM', timestamp),
        ]

        for data in sample_data:
            query = f"""
            UPSERT INTO gmp_cis.cis_udf_field_kudu VALUES
            ({data[0]}, '{data[1]}', '{data[2]}', '{data[3]}', {data[4]}, '{data[5]}', {data[6]}, '{data[7]}', {data[8]})
            """
            try:
                impala_manager.execute_write(query, database='gmp_cis')
            except Exception as e:
                self.stdout.write(self.style.WARNING(f'  Warning inserting record {data[0]}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'  Inserted {len(sample_data)} sample records'))
