"""
Import portfolio data from CSV into Kudu table.

Usage:
    python manage.py import_portfolios --file /path/to/portfolio.csv
"""

import csv
import logging
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import portfolio data from CSV file into Kudu cis_portfolio table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default='/Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/kudu_ddl/cis_cis_portfolio.csv',
            help='Path to the CSV file to import'
        )

    def handle(self, *args, **options):
        csv_file = options['file']

        self.stdout.write(f"Starting portfolio import from: {csv_file}")

        try:
            # Read CSV file
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                portfolios = list(reader)

            total_count = len(portfolios)
            self.stdout.write(f"Found {total_count} portfolios to import")

            # Import each portfolio
            success_count = 0
            error_count = 0

            for idx, portfolio in enumerate(portfolios, 1):
                try:
                    if self.import_portfolio(portfolio):
                        success_count += 1
                        if idx % 50 == 0:
                            self.stdout.write(f"Processed {idx}/{total_count} portfolios...")
                    else:
                        error_count += 1
                        self.stderr.write(f"Failed to import portfolio: {portfolio.get('name', 'Unknown')}")
                except Exception as e:
                    error_count += 1
                    self.stderr.write(f"Error importing portfolio {portfolio.get('name', 'Unknown')}: {str(e)}")

            # Summary
            self.stdout.write(self.style.SUCCESS(
                f"\nImport completed!"
                f"\n  Total: {total_count}"
                f"\n  Success: {success_count}"
                f"\n  Errors: {error_count}"
            ))

        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_file}")
        except Exception as e:
            raise CommandError(f"Import failed: {str(e)}")

    def import_portfolio(self, portfolio_data):
        """
        Import a single portfolio record into Kudu table.

        Args:
            portfolio_data: Dictionary with portfolio data from CSV

        Returns:
            True if successful, False otherwise
        """
        try:
            # Prepare data for Kudu
            # Handle empty strings and None values
            def clean_value(value):
                if value is None or value == '' or value == 'NULL':
                    return None
                return value.strip() if isinstance(value, str) else value

            # Build column-value pairs (only non-null values)
            columns = []
            values = []

            # Map CSV columns to Kudu table columns
            field_mapping = {
                'name': 'name',
                'description': 'description',
                'currency': 'currency',
                'manager': 'manager',
                'portfolio_client': 'portfolio_client',
                'cash_balance_list': 'cash_balance_list',
                'cash_balance': 'cash_balance',
                'status': 'status',
                'cost_centre_code': 'cost_centre_code',
                'corp_code': 'corp_code',
                'account_group': 'account_group',
                'portfolio_group': 'portfolio_group',
                'report_group': 'report_group',
                'entity_group': 'entity_group',
                'revaluation_status': 'revaluation_status',
                'created_at': 'created_at',
                'updated_at': 'updated_at',
            }

            for csv_field, kudu_field in field_mapping.items():
                value = clean_value(portfolio_data.get(csv_field))

                if value is not None:
                    columns.append(f"`{kudu_field}`")

                    # All fields in Kudu table are string type
                    # Escape single quotes for SQL
                    escaped_value = value.replace("'", "''")
                    values.append(f"'{escaped_value}'")

            # Build UPSERT statement
            upsert_query = f"""
            UPSERT INTO gmp_cis.cis_portfolio
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            # Execute UPSERT
            success = impala_manager.execute_write(upsert_query, database='gmp_cis')

            if success:
                logger.debug(f"Imported portfolio: {portfolio_data.get('name')}")

            return success

        except Exception as e:
            logger.error(f"Error importing portfolio {portfolio_data.get('name')}: {str(e)}")
            logger.error(f"Portfolio data: {portfolio_data}")
            return False
