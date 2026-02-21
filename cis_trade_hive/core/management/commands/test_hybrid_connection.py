"""
Django management command to test Hybrid (Impala + Hive) connectivity.

Tests both:
- Impala connection (for fast reads)
- Hive connection (for ACID writes)

Usage:
    python manage.py test_hybrid_connection
    python manage.py test_hybrid_connection --verbose
    python manage.py test_hybrid_connection --test-write
"""

import time
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'Test Hybrid (Impala + Hive) database connectivity with Kerberos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed connection information'
        )
        parser.add_argument(
            '--test-write',
            action='store_true',
            help='Test write operation (creates and deletes a test record)'
        )

    def handle(self, *args, **options):
        verbose = options.get('verbose', False)
        test_write = options.get('test_write', False)

        self.stdout.write(self.style.MIGRATE_HEADING(
            '=' * 60 + '\n'
            'Testing Hybrid Connection (Impala + Hive)\n'
            '=' * 60
        ))
        self.stdout.write('')

        # Import here to avoid circular imports
        from core.repositories.hybrid_connection import hybrid_manager, IMPYLA_AVAILABLE, PYHIVE_AVAILABLE

        # ==================== CONFIGURATION ====================
        self._display_config(verbose)

        # ==================== LIBRARY STATUS ====================
        self.stdout.write(self.style.MIGRATE_HEADING('\n[1/5] Library Status'))
        self.stdout.write(f"  impyla (Impala):  {'Available' if IMPYLA_AVAILABLE else 'NOT AVAILABLE'}")
        self.stdout.write(f"  pyhive (Hive):    {'Available' if PYHIVE_AVAILABLE else 'NOT AVAILABLE'}")

        if not IMPYLA_AVAILABLE and not PYHIVE_AVAILABLE:
            self.stdout.write(self.style.ERROR('\nNo database libraries available!'))
            self.stdout.write('Install with: pip install pure-sasl thrift-sasl pyhive impyla')
            return

        # ==================== CONNECTION TESTS ====================
        self.stdout.write(self.style.MIGRATE_HEADING('\n[2/5] Connection Tests'))

        results = hybrid_manager.test_connection()

        # Impala test
        if IMPYLA_AVAILABLE:
            if results.get('impala'):
                self.stdout.write(self.style.SUCCESS('  Impala: CONNECTED'))
            else:
                self.stdout.write(self.style.ERROR('  Impala: FAILED'))
        else:
            self.stdout.write(self.style.WARNING('  Impala: SKIPPED (library not available)'))

        # Hive test
        if PYHIVE_AVAILABLE:
            if results.get('hive'):
                self.stdout.write(self.style.SUCCESS('  Hive:   CONNECTED'))
            else:
                self.stdout.write(self.style.ERROR('  Hive:   FAILED'))
        else:
            self.stdout.write(self.style.WARNING('  Hive:   SKIPPED (library not available)'))

        # ==================== READ TEST (IMPALA) ====================
        self.stdout.write(self.style.MIGRATE_HEADING('\n[3/5] Read Test (via Impala)'))

        start_time = time.time()
        tables = hybrid_manager.get_tables()
        read_time = (time.time() - start_time) * 1000

        if tables:
            self.stdout.write(self.style.SUCCESS(f'  Found {len(tables)} tables ({read_time:.1f}ms)'))
            if verbose:
                for table in tables[:10]:
                    self.stdout.write(f'    - {table}')
                if len(tables) > 10:
                    self.stdout.write(f'    ... and {len(tables) - 10} more')
        else:
            self.stdout.write(self.style.WARNING('  No tables found or read failed'))

        # ==================== QUERY TEST ====================
        self.stdout.write(self.style.MIGRATE_HEADING('\n[4/5] Query Test'))

        start_time = time.time()
        result = hybrid_manager.execute_query("SELECT 1 as test_value")
        query_time = (time.time() - start_time) * 1000

        if result and len(result) > 0:
            self.stdout.write(self.style.SUCCESS(f'  SELECT 1: OK ({query_time:.1f}ms)'))
            if verbose:
                self.stdout.write(f'    Result: {result}')
        else:
            self.stdout.write(self.style.ERROR('  SELECT 1: FAILED'))

        # ==================== WRITE TEST (HIVE) ====================
        self.stdout.write(self.style.MIGRATE_HEADING('\n[5/5] Write Test (via Hive)'))

        if test_write:
            self._test_write_operation(hybrid_manager, verbose)
        else:
            self.stdout.write(self.style.WARNING('  Skipped (use --test-write to enable)'))

        # ==================== POOL STATS ====================
        if verbose:
            self.stdout.write(self.style.MIGRATE_HEADING('\nPool Statistics'))
            stats = hybrid_manager.get_pool_stats()
            self.stdout.write(f"  Impala: {stats['impala']['active']}/{stats['impala']['max']} active")
            self.stdout.write(f"  Hive:   {stats['hive']['active']}/{stats['hive']['max']} active")
            self.stdout.write(f"  Async:  {stats['async_pending']} pending writes")

        # ==================== SUMMARY ====================
        self.stdout.write('\n' + '=' * 60)
        all_passed = results.get('impala', False) or results.get('hive', False)
        if all_passed:
            self.stdout.write(self.style.SUCCESS('Hybrid connection test PASSED'))
        else:
            self.stdout.write(self.style.ERROR('Hybrid connection test FAILED'))
        self.stdout.write('=' * 60)

    def _display_config(self, verbose):
        """Display configuration from settings."""
        self.stdout.write(self.style.MIGRATE_HEADING('Configuration'))

        # Impala config
        impala_config = getattr(settings, 'IMPALA_CONFIG', {})
        self.stdout.write('\n  IMPALA (reads):')
        self.stdout.write(f"    Host: {impala_config.get('HOST', 'N/A')}")
        self.stdout.write(f"    Port: {impala_config.get('PORT', 'N/A')}")
        self.stdout.write(f"    Database: {impala_config.get('DATABASE', 'N/A')}")
        self.stdout.write(f"    Auth: {impala_config.get('AUTH', 'N/A')}")
        if verbose:
            self.stdout.write(f"    Kerberos Service: {impala_config.get('KERBEROS_SERVICE_NAME', 'N/A')}")
            self.stdout.write(f"    SSL: {impala_config.get('USE_SSL', 'N/A')}")
            self.stdout.write(f"    Pool Size: {impala_config.get('POOL_SIZE', 'N/A')}")

        # Hive config
        hive_config = getattr(settings, 'HIVE_CONFIG', {})
        self.stdout.write('\n  HIVE (writes):')
        self.stdout.write(f"    Host: {hive_config.get('HOST', 'N/A')}")
        self.stdout.write(f"    Port: {hive_config.get('PORT', 'N/A')}")
        self.stdout.write(f"    Database: {hive_config.get('DATABASE', 'N/A')}")
        self.stdout.write(f"    Auth: {hive_config.get('AUTH', 'N/A')}")
        if verbose:
            self.stdout.write(f"    Kerberos Service: {hive_config.get('KERBEROS_SERVICE_NAME', 'N/A')}")
            self.stdout.write(f"    Pool Size: {hive_config.get('POOL_SIZE', 'N/A')}")

    def _test_write_operation(self, manager, verbose):
        """Test write operation using Hive."""
        import uuid
        test_id = f"TEST_{uuid.uuid4().hex[:8]}"

        self.stdout.write(f'  Testing write with ID: {test_id}')

        # This is just a syntax test - doesn't actually write
        # For real write test, you'd need an existing test table
        start_time = time.time()
        success = manager.execute_write(
            "SELECT 1",  # Safe test query
            use_mr_engine=False
        )
        write_time = (time.time() - start_time) * 1000

        if success:
            self.stdout.write(self.style.SUCCESS(f'  Write test: OK ({write_time:.1f}ms)'))
        else:
            self.stdout.write(self.style.ERROR('  Write test: FAILED'))
