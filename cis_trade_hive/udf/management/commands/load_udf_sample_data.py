"""
Management command to load sample UDF definitions and options into Kudu tables.

Usage:
    python manage.py load_udf_sample_data
"""

from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load sample UDF definitions and options into Kudu tables'

    def handle(self, *args, **options):
        self.stdout.write('Loading UDF sample data...')

        # Sample data for Portfolio UDFs
        udf_definitions = [
            {
                'udf_id': 1,
                'field_name': 'manager',
                'label': 'Portfolio Manager',
                'description': 'Person responsible for managing the portfolio',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': True,
                'is_active': True,
            },
            {
                'udf_id': 2,
                'field_name': 'account_group',
                'label': 'Account Group',
                'description': 'Account group classification',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
            },
            {
                'udf_id': 3,
                'field_name': 'report_group',
                'label': 'Report Group',
                'description': 'Reporting group classification',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
            },
            {
                'udf_id': 4,
                'field_name': 'portfolio_group',
                'label': 'Portfolio Group',
                'description': 'Portfolio group classification',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
            },
            {
                'udf_id': 5,
                'field_name': 'entity_group',
                'label': 'Entity Group',
                'description': 'Entity group classification',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
            },
            {
                'udf_id': 6,
                'field_name': 'revaluation_status',
                'label': 'Revaluation Status',
                'description': 'Current revaluation status',
                'field_type': 'DROPDOWN',
                'entity_type': 'PORTFOLIO',
                'is_required': False,
                'is_active': True,
            },
        ]

        # Sample options data
        managers = [
            "Alice Foong Yee Quan", "Arthur Leong Kian Chong", "CB-Restructured equities",
            "CBR-warrants", "CIU", "CSD", "Caroline Chong Li Ching/Tan Kim Chuan",
            "Chow Poh Heng", "Chua Siok Lian", "DCM", "ECM", "For UIS buyback program",
            "For monitoring purposes", "For record purpose", "For record purposes",
            "For recording purposes", "For reporting purposes", "Fund managed by UOBAM",
            "Fund managed by UOBGC", "GLOBAL CAPITAL", "GMIM-Sebastian Xu Wei Ming",
            "Low Han Seng", "Miscellaneous legacy investments", "OTHERS", "PING AN UOB FD",
            "Peh Kian Heng", "REGIONAL DIGITAL BANKING", "Reporting-P/L for Y2012",
            "Shareholder's fund", "Tam Kwok Fun", "Terence Ong Sea Eng c/o IAC",
            "Thomas Siah Han Ling", "To capture investments", "To capture warrant if any",
            "Transformation Office", "UOB AIP", "UOBAM", "UOBAM(VIET)", "UOBGC",
            "UOBVM", "Wong Ann Derk", "Yee Foong Leng", "Yee Foong Leng/ Jasline Liew"
        ]

        account_groups = [
            "HAWPAR GROUP", "KHENG LEONG", "OUB GROUP", "OUBARB GROUP", "OUBASSOC GROUP",
            "OUD GROUP", "OUS-TAX GROUP", "SEC INVT GROUP", "UIS GROUP", "UOB ASSOC GROU",
            "UOB ASSOC GROUP", "UOB ASSOCIATE", "UOB GROUP", "UOL GROUP"
        ]

        report_groups = [
            "AAF", "AAMB", "AFFIN-UOB HLDG", "AIIF CP", "AIIF CP II", "ASEAN CHINA FD II",
            "ASFINCO SPORE", "AVATEC", "AXA INSURANCE", "BIRCH RE BIZ", "CEDAR CONS LLC",
            "CHINA F&B VI", "CKB HK", "CKB(ACU)", "CKB(ACU)-CF", "CKBM", "CKF", "CKR",
            "DAISY LLC", "EUCALYPTUS JS", "FEB", "GABELHORN INVT", "GC F&B (HK)",
            "GC F&B (INVT)", "GC F&B CAP PAR", "GHC", "GHP", "GRAND ORIENT",
            "GUANGXI-A F M P", "GUANGXI-ASEAN F", "HAWPAR", "HAWPAR(CAP)", "HAWPAR(INT)",
            "HOTEL NEGARA", "HPL", "HUH REAL EST P2", "ICB GROUP", "ICR", "INNOVEN CAP",
            "INNOVEN CAP ASI", "INNOVEN CAP(CN)", "INNOVEN CAP(S)", "INNOVEN ZIYANG",
            "LINDEN P I VN", "UOB", "UOBAM", "UOBGC", "UOBVM"
        ]

        portfolio_groups = [
            "AAF", "AAMB", "AFFIN-UOB HLDGS", "AIIF CP", "AIIF CP II", "CIU ALPHA",
            "DISCF", "FEB", "FEB-CF", "ICB", "ICB(ACU)", "ICB(ACU)-CF", "KHENG LEONG",
            "UIS", "UIS BUYBACK", "UOB", "UOB AUSTRALIA", "UOB BULLION", "UOB CARD CENTRE",
            "UOBAM", "UOBGC", "UOBVM"
        ]

        entity_groups = [
            "CORPORATE", "INSTITUTIONAL", "RETAIL", "FUND", "GOVERNMENT"
        ]

        revaluation_statuses = [
            "Pending", "Completed", "Not Required", "In Progress", "On Hold"
        ]

        # Map UDF IDs to their options
        udf_options_map = {
            1: managers,
            2: account_groups,
            3: report_groups,
            4: portfolio_groups,
            5: entity_groups,
            6: revaluation_statuses,
        }

        try:
            # Insert UDF definitions
            self.stdout.write('Inserting UDF definitions...')
            timestamp = int(datetime.now().timestamp() * 1000)

            for udf in udf_definitions:
                query = f"""
                UPSERT INTO gmp_cis.cis_udf_definition
                (udf_id, field_name, label, description, field_type, entity_type,
                 is_required, is_unique, is_active, display_order, created_by, created_at, updated_by, updated_at)
                VALUES (
                    {udf['udf_id']},
                    '{udf['field_name']}',
                    '{udf['label']}',
                    '{udf['description']}',
                    '{udf['field_type']}',
                    '{udf['entity_type']}',
                    {str(udf['is_required']).lower()},
                    false,
                    {str(udf['is_active']).lower()},
                    {udf['udf_id'] * 10},
                    'SYSTEM',
                    {timestamp},
                    'SYSTEM',
                    {timestamp}
                )
                """
                success = impala_manager.execute_write(query, database='gmp_cis')
                if success:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ Created UDF: {udf["field_name"]}'))
                else:
                    self.stdout.write(self.style.ERROR(f'  ✗ Failed to create UDF: {udf["field_name"]}'))

            # Insert UDF options
            self.stdout.write('\nInserting UDF options...')
            for udf_id, options in udf_options_map.items():
                self.stdout.write(f'\n  Loading options for UDF ID {udf_id}...')
                for idx, option_value in enumerate(options):
                    # Escape single quotes in option value
                    escaped_value = option_value.replace("'", "''")

                    query = f"""
                    UPSERT INTO gmp_cis.cis_udf_option
                    (udf_id, option_value, display_order, is_active, created_by, created_at, updated_by, updated_at)
                    VALUES (
                        {udf_id},
                        '{escaped_value}',
                        {idx + 1},
                        true,
                        'SYSTEM',
                        {timestamp},
                        'SYSTEM',
                        {timestamp}
                    )
                    """
                    success = impala_manager.execute_write(query, database='gmp_cis')
                    if not success:
                        self.stdout.write(self.style.WARNING(f'    ⚠ Failed to insert option: {option_value}'))

                self.stdout.write(self.style.SUCCESS(f'    ✓ Inserted {len(options)} options for UDF ID {udf_id}'))

            self.stdout.write(self.style.SUCCESS('\n✓ Sample UDF data loaded successfully!'))

            # Summary
            self.stdout.write('\n' + '='*60)
            self.stdout.write('Summary:')
            self.stdout.write(f'  - UDF Definitions: {len(udf_definitions)}')
            self.stdout.write(f'  - Managers: {len(managers)}')
            self.stdout.write(f'  - Account Groups: {len(account_groups)}')
            self.stdout.write(f'  - Report Groups: {len(report_groups)}')
            self.stdout.write(f'  - Portfolio Groups: {len(portfolio_groups)}')
            self.stdout.write(f'  - Entity Groups: {len(entity_groups)}')
            self.stdout.write(f'  - Revaluation Statuses: {len(revaluation_statuses)}')
            self.stdout.write('='*60)

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n✗ Error loading UDF data: {str(e)}'))
            logger.error(f"Error loading UDF data: {str(e)}", exc_info=True)
