"""
Django management command to create Hive database.

Usage:
    python manage.py create_hive_db
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from core.repositories import hive_manager


class Command(BaseCommand):
    help = 'Create Hive database "cis"'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Creating Hive Database...'))
        self.stdout.write('')

        db_name = settings.HIVE_CONFIG['DATABASE']

        self.stdout.write(f'Database name: {db_name}')
        self.stdout.write('')

        try:
            # Create database
            self.stdout.write('Executing: CREATE DATABASE IF NOT EXISTS cis')

            # Connect to Hive without specifying a database (use 'default')
            success = hive_manager.execute_write(
                query=f"CREATE DATABASE IF NOT EXISTS {db_name}",
                database='default'
            )

            if success:
                self.stdout.write(self.style.SUCCESS(f'✓ Database "{db_name}" created successfully!'))
            else:
                self.stdout.write(self.style.ERROR(f'✗ Failed to create database "{db_name}"'))
                return

            self.stdout.write('')

            # Verify database exists
            self.stdout.write('Verifying database...')
            result = hive_manager.execute_query(
                query="SHOW DATABASES",
                database='default'
            )

            databases = [row.get('database_name', row.get('database', '')) for row in result]

            if db_name in databases:
                self.stdout.write(self.style.SUCCESS(f'✓ Database "{db_name}" verified!'))
                self.stdout.write('')
                self.stdout.write('Available databases:')
                for db in databases:
                    marker = '→' if db == db_name else ' '
                    self.stdout.write(f'  {marker} {db}')
            else:
                self.stdout.write(self.style.WARNING(f'Database "{db_name}" not found in database list'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('Alternative: Create database manually using beeline:'))
            self.stdout.write('  beeline -u jdbc:hive2://localhost:10000')
            self.stdout.write(f'  CREATE DATABASE IF NOT EXISTS {db_name};')

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Done!'))
