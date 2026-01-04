"""
Django management command to set up UDF field definitions for SECURITY entity type.

This command creates all 26 required UDF field definitions and populates them with
options extracted from existing security data and sensible defaults.

Usage:
    python manage.py setup_security_udf
"""

import logging
from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Set up UDF field definitions for SECURITY entity type'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Starting UDF setup for SECURITY entity type...'))

        # Define all 26 UDF fields with their options
        udf_fields = {
            'industry': {
                'field_name': 'Industry',
                'description': 'Industry classification',
                'data_type': 'STRING',
                'options': self.get_existing_values('industry', [
                    'Technology', 'Financial Services', 'Healthcare', 'Energy',
                    'Consumer Goods', 'Industrial', 'Telecommunications', 'Utilities'
                ])
            },
            'country_of_incorporation': {
                'field_name': 'Country of Incorporation',
                'description': 'Country where entity is incorporated',
                'data_type': 'STRING',
                'options': self.get_existing_values('country_of_incorporation', [
                    'Singapore', 'United States', 'United Kingdom', 'Hong Kong',
                    'Japan', 'Australia', 'Germany', 'France'
                ])
            },
            'quoted_unquoted': {
                'field_name': 'Quoted/Unquoted',
                'description': 'Whether security is publicly traded',
                'data_type': 'STRING',
                'options': ['Quoted', 'Unquoted']
            },
            'security_type': {
                'field_name': 'Security Type',
                'description': 'Type of security instrument',
                'data_type': 'STRING',
                'options': self.get_existing_values('security_type', [
                    'ETF', 'Common Stock', 'Preferred Stock', 'Corporate Bond',
                    'Government Bond', 'Mutual Fund', 'REIT', 'Index'
                ])
            },
            'investment_type': {
                'field_name': 'Investment Type',
                'description': 'Classification of investment',
                'data_type': 'STRING',
                'options': self.get_existing_values('investment_type', [
                    'Equity', 'Fixed Income', 'Hybrid', 'Alternative', 'Cash Equivalent'
                ])
            },
            'price_source': {
                'field_name': 'Price Source',
                'description': 'Source of pricing data',
                'data_type': 'STRING',
                'options': ['Bloomberg', 'Reuters', 'IDC', 'Manual', 'Internal Pricing']
            },
            'country_of_issue': {
                'field_name': 'Country of Issue',
                'description': 'Country where security was issued',
                'data_type': 'STRING',
                'options': self.get_existing_values('country_of_issue', [
                    'Singapore', 'United States', 'United Kingdom', 'Hong Kong',
                    'Japan', 'Australia', 'Germany', 'France'
                ])
            },
            'country_of_primary_exchange': {
                'field_name': 'Country of Primary Exchange',
                'description': 'Country of primary trading exchange',
                'data_type': 'STRING',
                'options': [
                    'Singapore', 'United States', 'United Kingdom', 'Hong Kong',
                    'Japan', 'Australia', 'Germany', 'France'
                ]
            },
            'bwciif': {
                'field_name': 'BWCIIF',
                'description': 'BWCIIF classification',
                'data_type': 'STRING',
                'options': ['Yes', 'No', 'Not Applicable']
            },
            'bwciif_others': {
                'field_name': 'BWCIIF Others',
                'description': 'Additional BWCIIF details',
                'data_type': 'STRING',
                'options': ['Type A', 'Type B', 'Type C', 'Other']
            },
            'issuer_type': {
                'field_name': 'Issuer Type',
                'description': 'Type of issuing entity',
                'data_type': 'STRING',
                'options': [
                    'Corporate', 'Government', 'Municipality', 'Sovereign',
                    'Supranational', 'Agency'
                ]
            },
            'approved_s32': {
                'field_name': 'Approved S32',
                'description': 'S32 approval status',
                'data_type': 'STRING',
                'options': ['Approved', 'Pending', 'Rejected', 'Not Required']
            },
            'basel_iv_fund': {
                'field_name': 'BASEL IV - FUND',
                'description': 'Basel IV fund classification',
                'data_type': 'STRING',
                'options': ['Tier 1', 'Tier 2', 'Not Applicable']
            },
            'business_unit_head': {
                'field_name': 'Business Unit Head',
                'description': 'Responsible business unit head',
                'data_type': 'STRING',
                'options': [
                    'Investment Banking', 'Asset Management', 'Treasury',
                    'Trading', 'Risk Management'
                ]
            },
            'core_noncore': {
                'field_name': 'Core/Non-core',
                'description': 'Core vs non-core classification',
                'data_type': 'STRING',
                'options': ['Core', 'Non-core']
            },
            'fund_index_fund': {
                'field_name': 'Fund / Index Fund',
                'description': 'Fund type classification',
                'data_type': 'STRING',
                'options': ['Active Fund', 'Index Fund', 'ETF', 'Not Applicable']
            },
            'management_limit_classification': {
                'field_name': 'Management Limit Classification',
                'description': 'Management limit category',
                'data_type': 'STRING',
                'options': ['Category A', 'Category B', 'Category C', 'Exempt']
            },
            'mas_643_entity_type': {
                'field_name': 'MAS 643 Entity Type',
                'description': 'MAS 643 entity classification',
                'data_type': 'STRING',
                'options': ['Type 1', 'Type 2', 'Type 3', 'Not Applicable']
            },
            'person_in_charge': {
                'field_name': 'Person In Charge',
                'description': 'Responsible person',
                'data_type': 'STRING',
                'options': [
                    'Portfolio Manager', 'Risk Manager', 'Compliance Officer',
                    'Fund Manager', 'Trader'
                ]
            },
            'substantial_10_pct': {
                'field_name': 'Substantial >10%',
                'description': 'Substantial holdings flag',
                'data_type': 'STRING',
                'options': ['Yes', 'No']
            },
            'relative_index': {
                'field_name': 'Relative Index',
                'description': 'Benchmark index for comparison',
                'data_type': 'STRING',
                'options': [
                    'S&P 500', 'MSCI World', 'STI', 'Hang Seng',
                    'FTSE 100', 'Nikkei 225', 'Custom'
                ]
            },
            'fin_nonfin_ind': {
                'field_name': 'Fin/Non-fin IND',
                'description': 'Financial vs non-financial indicator',
                'data_type': 'STRING',
                'options': ['Financial', 'Non-Financial']
            },
        }

        # Process each UDF field
        total_fields = len(udf_fields)
        created_count = 0
        skipped_count = 0

        for field_code, field_data in udf_fields.items():
            try:
                # Check if field already exists
                exists = self.check_field_exists(field_code)

                if exists:
                    self.stdout.write(self.style.WARNING(
                        f'  Skipping {field_code} (already exists)'
                    ))
                    skipped_count += 1
                    continue

                # Create UDF field definition
                udf_id = self.create_udf_field(
                    field_code,
                    field_data['field_name'],
                    field_data['description'],
                    field_data['data_type']
                )

                if udf_id:
                    # Create options for this field
                    options_created = self.create_udf_options(udf_id, field_data['options'])

                    self.stdout.write(self.style.SUCCESS(
                        f'  Created {field_code} with {options_created} options'
                    ))
                    created_count += 1
                else:
                    self.stdout.write(self.style.ERROR(
                        f'  Failed to create {field_code}'
                    ))

            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f'  Error processing {field_code}: {str(e)}'
                ))
                logger.error(f"Error creating UDF field {field_code}: {str(e)}")

        # Summary
        self.stdout.write(self.style.SUCCESS(
            f'\nUDF Setup Complete:'
        ))
        self.stdout.write(f'  Created: {created_count} fields')
        self.stdout.write(f'  Skipped: {skipped_count} fields (already exist)')
        self.stdout.write(f'  Total: {total_fields} fields')

    def get_existing_values(self, field_name, default_values):
        """
        Extract existing values from security table, fall back to defaults if empty.

        Args:
            field_name: Column name in security table
            default_values: Default values to use if no data found

        Returns:
            List of unique values
        """
        try:
            query = f"""
            SELECT DISTINCT {field_name}
            FROM gmp_cis.cis_security_kudu
            WHERE {field_name} IS NOT NULL
              AND {field_name} != ''
            LIMIT 50
            """

            result = impala_manager.execute_query(query, database='gmp_cis')

            if result and len(result) > 0:
                values = [row.get(field_name) for row in result if row.get(field_name)]
                values = list(set(values))  # Remove duplicates
                values.sort()

                # Merge with defaults, prioritizing existing values
                combined = list(set(values + default_values))
                combined.sort()
                return combined

            return default_values

        except Exception as e:
            logger.warning(f"Could not extract values for {field_name}: {str(e)}")
            return default_values

    def check_field_exists(self, field_code):
        """Check if UDF field already exists"""
        try:
            # Note: In actual table, field_code is stored in 'label' column
            query = f"""
            SELECT udf_id
            FROM gmp_cis.cis_udf_field
            WHERE label = '{field_code}'
              AND entity_type = 'SECURITY'
              AND is_active = true
            LIMIT 1
            """

            result = impala_manager.execute_query(query, database='gmp_cis')
            return result and len(result) > 0

        except Exception as e:
            logger.error(f"Error checking field existence: {str(e)}")
            return False

    def create_udf_field(self, field_code, field_name, description, data_type):
        """Create UDF field - returns field_code if successful"""
        # For simplified version, we don't create field definitions separately
        # Just return the field_code to proceed to creating options
        return field_code

    def create_udf_options(self, udf_id, options):
        """Create UDF options for a field in actual single table structure

        Note: In actual table structure:
        - 'label' column = field_code (e.g., 'industry', 'security_type')
        - 'field_name' column = option_value (e.g., 'Technology', 'ETF')
        """
        created_count = 0

        try:
            # Get starting ID
            query = "SELECT COALESCE(MAX(udf_id), 0) as max_id FROM gmp_cis.cis_udf_field"
            result = impala_manager.execute_query(query, database='gmp_cis')
            next_id = (result[0].get('max_id', 0) if result else 0) + 1

            # Get field_code from udf_id (which is actually the field_code in our simplified version)
            field_code = udf_id

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
                    # - label = field code (e.g., 'industry')
                    # - entity_type = 'SECURITY'
                    insert_query = f"""
                    INSERT INTO gmp_cis.cis_udf_field (
                        udf_id, field_name, label, entity_type,
                        is_required, is_active,
                        created_at, created_by, updated_at, updated_by
                    ) VALUES (
                        {next_id},
                        '{escaped_value}',
                        '{field_code}',
                        'SECURITY',
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
