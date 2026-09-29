"""
Django management command to test Hive connectivity.

Usage:
    python manage.py test_hive
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from core.repositories import hive_manager


class Command(BaseCommand):
    help = 'Test Hive database connectivity'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Testing Hive Connection...'))
        self.stdout.write('')

        # Display configuration
        config = settings.HIVE_CONFIG
        self.stdout.write('Configuration:')
        self.stdout.write(f"  Host: {config['HOST']}")
        self.stdout.write(f"  Port: {config['PORT']}")
        self.stdout.write(f"  Database: {config['DATABASE']}")
        self.stdout.write(f"  Auth: {config['AUTH']}")
        self.stdout.write('')

        # Test connection
        self.stdout.write('Testing connection...')
        if hive_manager.test_connection():
            self.stdout.write(self.style.SUCCESS('✓ Connection successful!'))
        else:
            self.stdout.write(self.style.ERROR('✗ Connection failed!'))
            return

        self.stdout.write('')

        # List tables
        self.stdout.write('Fetching tables...')
        tables = hive_manager.get_tables()
        if tables:
            self.stdout.write(self.style.SUCCESS(f'✓ Found {len(tables)} tables:'))
            for table in tables[:10]:  # Show first 10 tables
                self.stdout.write(f'  - {table}')
            if len(tables) > 10:
                self.stdout.write(f'  ... and {len(tables) - 10} more')
        else:
            self.stdout.write(self.style.WARNING('No tables found or unable to list tables'))

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Hive connection test complete!'))
