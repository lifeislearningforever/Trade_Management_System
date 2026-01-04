"""
Django management command to create the equity_price Kudu table.

Usage:
    python manage.py create_equity_price_table
"""

import logging
from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Create the equity_price Kudu table'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Creating equity_price Kudu table...'))

        # Drop existing table if needed (optional)
        drop_kudu_query = "DROP TABLE IF EXISTS gmp_cis.cis_equity_price_kudu"
        drop_external_query = "DROP TABLE IF EXISTS gmp_cis.cis_equity_price"

        # Create Kudu table
        create_kudu_query = """
        CREATE TABLE IF NOT EXISTS gmp_cis.cis_equity_price_kudu (
            equity_price_id BIGINT NOT NULL,
            currency_code STRING NOT NULL,
            security_label STRING NOT NULL,
            isin STRING,
            price_date STRING NOT NULL,
            main_closing_price DECIMAL(18, 6),
            market STRING,
            price_timestamp BIGINT,
            group_name STRING,
            is_active BOOLEAN DEFAULT true,
            created_by STRING NOT NULL,
            created_at BIGINT NOT NULL,
            updated_by STRING,
            updated_at BIGINT,
            PRIMARY KEY (equity_price_id)
        )
        PARTITION BY HASH (equity_price_id) PARTITIONS 16
        STORED AS KUDU
        TBLPROPERTIES('kudu.num_tablet_replicas' = '1')
        """

        # Create external table mapping
        create_external_query = """
        CREATE EXTERNAL TABLE IF NOT EXISTS gmp_cis.cis_equity_price
        STORED AS KUDU
        TBLPROPERTIES('kudu.table_name' = 'impala::gmp_cis.cis_equity_price_kudu')
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

            self.stdout.write(self.style.SUCCESS('\nTable creation complete!'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating table: {str(e)}'))
            logger.error(f"Error creating equity_price table: {str(e)}")
