"""
Django management command to set up UDF field definitions for EQUITY_PRICE entity type.

This command creates the Market dropdown field with common stock exchanges.

Usage:
    python manage.py setup_equity_price_udf
"""

import logging
from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set up UDF field definitions for EQUITY_PRICE entity type'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting UDF setup for EQUITY_PRICE entity type...'))

        # Define Market UDF field with options
        market_options = [
            'NYSE',          # New York Stock Exchange
            'NASDAQ',        # NASDAQ
            'SGX',           # Singapore Exchange
            'LSE',           # London Stock Exchange
            'HKEX',          # Hong Kong Stock Exchange
            'TSE',           # Tokyo Stock Exchange
            'SSE',           # Shanghai Stock Exchange
            'SZSE',          # Shenzhen Stock Exchange
            'ASX',           # Australian Securities Exchange
            'BSE',           # Bombay Stock Exchange
            'NSE',           # National Stock Exchange (India)
            'JSE',           # Johannesburg Stock Exchange
            'EURONEXT',      # Euronext
            'TSX',           # Toronto Stock Exchange
            'FSE',           # Frankfurt Stock Exchange
        ]

        try:
            # Check if field already exists
            exists = self.check_field_exists('market')

            if exists:
                self.stdout.write(self.style.WARNING(
                    '  Market field already exists - skipping'
                ))
            else:
                # Create UDF options for market field
                options_created = self.create_udf_options('market', market_options)

                self.stdout.write(self.style.SUCCESS(
                    f'  Created market field with {options_created} options'
                ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'  Error processing market field: {str(e)}'
            ))
            logger.error(f"Error creating UDF field market: {str(e)}")

        # Summary
        self.stdout.write(self.style.SUCCESS(
            '\nUDF Setup Complete for EQUITY_PRICE entity type'
        ))

    def check_field_exists(self, field_code):
        """Check if UDF field already exists"""
        try:
            # Note: In actual table, field_code is stored in 'label' column
            query = f"""
            SELECT udf_id
            FROM gmp_cis.cis_udf_field
            WHERE label = '{field_code}'
              AND entity_type = 'EQUITY_PRICE'
              AND is_active = true
            LIMIT 1
            """

            result = impala_manager.execute_query(query, database='gmp_cis')
            return result and len(result) > 0

        except Exception as e:
            logger.error(f"Error checking field existence: {str(e)}")
            return False

    def create_udf_options(self, field_code, options):
        """Create UDF options for a field in actual single table structure

        Note: In actual table structure:
        - 'label' column = field_code (e.g., 'market')
        - 'field_name' column = option_value (e.g., 'NYSE', 'NASDAQ')
        """
        created_count = 0

        try:
            # Get starting ID
            query = "SELECT COALESCE(MAX(udf_id), 0) as max_id FROM gmp_cis.cis_udf_field"
            result = impala_manager.execute_query(query, database='gmp_cis')
            next_id = (result[0].get('max_id', 0) if result else 0) + 1

            for idx, option_value in enumerate(options):
                try:
                    # Escape single quotes in option value
                    escaped_value = option_value.replace("'", "\\'")

                    # Generate timestamp
                    import time
                    timestamp = int(time.time() * 1000)

                    # Note: In actual table:
                    # - udf_id = primary key ID
                    # - field_name = option value (the actual dropdown option)
                    # - label = field code (e.g., 'market')
                    # - entity_type = 'EQUITY_PRICE'
                    insert_query = f"""
                    INSERT INTO gmp_cis.cis_udf_field (
                        udf_id, field_name, label, entity_type,
                        is_required, is_active,
                        created_at, created_by, updated_at, updated_by
                    ) VALUES (
                        {next_id},
                        '{escaped_value}',
                        '{field_code}',
                        'EQUITY_PRICE',
                        false,
                        true,
                        {timestamp},
                        'SYSTEM',
                        {timestamp},
                        'SYSTEM'
                    )
                    """

                    success = impala_manager.execute_write(insert_query, database='gmp_cis')
                    if success:
                        created_count += 1
                        next_id += 1

                except Exception as e:
                    logger.error(f"Error creating option '{option_value}': {str(e)}")

        except Exception as e:
            logger.error(f"Error creating UDF options: {str(e)}")

        return created_count
