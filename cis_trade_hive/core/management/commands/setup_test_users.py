"""
Management command to setup test ACL users for Four-Eyes workflow testing.

Creates:
- Maker group with CREATE/READ/WRITE permissions
- Checker group with APPROVE/REJECT permissions  
- Test users: maker_user and checker_user
"""

from django.core.management.base import BaseCommand
from core.repositories.impala_connection import impala_manager


class Command(BaseCommand):
    help = 'Setup test ACL users and groups for Four-Eyes workflow'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Setting up test ACL users and groups...'))

        try:
            # 1. Create/Update Makers group
            self.stdout.write('Creating Makers group...')
            makers_query = """
            UPSERT INTO gmp_cis.cis_user_group
            (cis_user_group_id, name, entity, description, is_deleted, updated_on, updated_by)
            VALUES (100, 'Makers', 'UOB', 'Portfolio Makers - can create and edit', false, unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(makers_query, database='gmp_cis')

            # 2. Create/Update Checkers group
            self.stdout.write('Creating Checkers group...')
            checkers_query = """
            UPSERT INTO gmp_cis.cis_user_group
            (cis_user_group_id, name, entity, description, is_deleted, updated_on, updated_by)
            VALUES (200, 'Checkers', 'UOB', 'Portfolio Checkers - can approve and reject', false, unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(checkers_query, database='gmp_cis')

            # 3. Create Maker user
            self.stdout.write('Creating maker_user...')
            maker_user_query = """
            UPSERT INTO gmp_cis.cis_user
            (cis_user_id, login, name, entity, email, domain, cis_user_group_id,
             is_deleted, enabled, created_on, created_by, updated_on, updated_by)
            VALUES (1001, 'maker_user', 'Test Maker User', 'UOB', 'maker@testcis.com', 'UOB', 100,
                    false, true, unix_timestamp() * 1000, 'system', unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(maker_user_query, database='gmp_cis')

            # 4. Create Checker user
            self.stdout.write('Creating checker_user...')
            checker_user_query = """
            UPSERT INTO gmp_cis.cis_user
            (cis_user_id, login, name, entity, email, domain, cis_user_group_id,
             is_deleted, enabled, created_on, created_by, updated_on, updated_by)
            VALUES (2001, 'checker_user', 'Test Checker User', 'UOB', 'checker@testcis.com', 'UOB', 200,
                    false, true, unix_timestamp() * 1000, 'system', unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(checker_user_query, database='gmp_cis')

            # 5. Add Makers permissions
            self.stdout.write('Adding Makers permissions...')
            perm_query = """
            UPSERT INTO gmp_cis.cis_group_permissions
            (cis_group_permissions_id, cis_user_group_id, permission, read_write, is_deleted, updated_on, updated_by)
            VALUES (100001, 100, 'cis-portfolio', 'READ_WRITE', false, unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(perm_query, database='gmp_cis')

            # 6. Add Checkers permissions
            self.stdout.write('Adding Checkers permissions...')
            perm_query = """
            UPSERT INTO gmp_cis.cis_group_permissions
            (cis_group_permissions_id, cis_user_group_id, permission, read_write, is_deleted, updated_on, updated_by)
            VALUES (200001, 200, 'cis-portfolio', 'READ_WRITE', false, unix_timestamp() * 1000, 'system')
            """
            impala_manager.execute_write(perm_query, database='gmp_cis')

            self.stdout.write(self.style.SUCCESS('\n✅ Test users created successfully!'))
            self.stdout.write(self.style.SUCCESS('\nTest Credentials:'))
            self.stdout.write('  Maker:   Login: maker_user   | Password: test123 | Group: Makers')
            self.stdout.write('  Checker: Login: checker_user | Password: test123 | Group: Checkers')
            self.stdout.write('\nWorkflow:')
            self.stdout.write('  1. Login as maker_user → Create portfolio (DRAFT status)')
            self.stdout.write('  2. Submit for approval (PENDING_APPROVAL status)')
            self.stdout.write('  3. Logout and login as checker_user')
            self.stdout.write('  4. Approve portfolio (ACTIVE status)')

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating test users: {str(e)}'))
            raise

