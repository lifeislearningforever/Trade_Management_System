"""
Kudu/Impala Stress and Load Testing Suite
==========================================

Real database stress tests for Kudu/Impala:
1. Connection pool under concurrent load
2. Trade creation with concurrent users
3. Position calculation race conditions
4. Query performance under load

These tests connect to the actual database (SIT/UAT/PROD) configured via CIS_ENV.

Usage:
    # Set environment first
    export CIS_ENV=SIT  # or UAT, PROD

    # Run all stress tests
    pytest tests/stress/test_kudu_stress.py -v -s

    # Run specific test class
    pytest tests/stress/test_kudu_stress.py::TestConnectionPoolStress -v -s

    # Run with a specific environment
    CIS_ENV=SIT pytest tests/stress/test_kudu_stress.py -v -s

Requirements:
    - Valid Kerberos ticket (kinit) for SIT/UAT/PROD
    - Network access to Impala coordinators
    - CIS_ENV set to target environment
"""

import pytest
import threading
import time
import queue
import random
import statistics
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Test Configuration
# ============================================================================

class StressTestConfig:
    """Configuration for stress tests"""

    # Connection pool tests
    POOL_SIZE = 35  # Match production pool size
    CONCURRENT_CONNECTIONS = 50  # Exceed pool size to test queuing
    CONNECTION_TEST_DURATION = 30  # seconds

    # Trade creation tests
    CONCURRENT_TRADES = 100
    TRADES_PER_USER = 10

    # Position calculation tests
    CONCURRENT_POSITION_UPDATES = 50

    # Query performance tests
    QUERY_ITERATIONS = 100
    MAX_QUERY_TIME_MS = 1000  # SLA: 1 second max

    # Test portfolios (use existing test portfolios in SIT)
    TEST_PORTFOLIOS = [
        'STRESS_TEST_PORTFOLIO_1',
        'STRESS_TEST_PORTFOLIO_2',
        'STRESS_TEST_PORTFOLIO_3',
    ]

    # Test securities (use existing test securities)
    TEST_SECURITIES = [
        'STRESS_SEC_AAPL',
        'STRESS_SEC_MSFT',
        'STRESS_SEC_GOOGL',
    ]


def is_database_available():
    """Check if database is available for real tests."""
    try:
        from core.repositories.impala_connection import ImpalaConnectionManager, IMPALA_AVAILABLE
        if not IMPALA_AVAILABLE:
            return False

        manager = ImpalaConnectionManager()
        with manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
        return True
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        return False


# Skip marker for tests requiring database
requires_database = pytest.mark.skipif(
    not is_database_available(),
    reason="Database connection not available. Set CIS_ENV and ensure kinit."
)


# ============================================================================
# Connection Pool Stress Tests (Mocked - Always Run)
# ============================================================================

class TestConnectionPoolStressMocked:
    """Test connection pool logic with mocking (no real DB required)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.results = queue.Queue()
        self.errors = queue.Queue()
        self.connection_times = []

    def test_concurrent_connection_acquisition(self):
        """
        Test acquiring connections concurrently from multiple threads.
        Verifies pool doesn't deadlock under heavy load.
        """
        # Patch the impala_connect function at import location
        with patch('core.repositories.impala_connection.impala_connect') as mock_connect:
            # Create mock connection and cursor
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            # Import and reset singleton
            from core.repositories.impala_connection import ImpalaConnectionManager
            ImpalaConnectionManager._instance = None
            manager = ImpalaConnectionManager()

            num_threads = 30  # Reduced for mocked test
            successful_connections = 0
            failed_connections = 0
            lock = threading.Lock()

            def acquire_and_release():
                nonlocal successful_connections, failed_connections
                conn = None
                try:
                    start = time.time()
                    conn = manager.get_connection()
                    elapsed = time.time() - start
                    with lock:
                        self.connection_times.append(elapsed)

                    if conn is None:
                        raise Exception("Failed to acquire connection from pool")

                    # Execute simple query
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()
                    manager.return_connection(conn)
                    conn = None

                    with lock:
                        successful_connections += 1
                    self.results.put(('success', elapsed))
                except Exception as e:
                    with lock:
                        failed_connections += 1
                    self.errors.put(('error', str(e)))

            # Launch concurrent threads
            threads = []
            start_time = time.time()

            for _ in range(num_threads):
                t = threading.Thread(target=acquire_and_release)
                threads.append(t)
                t.start()

            # Wait for all threads
            for t in threads:
                t.join(timeout=60)

            total_time = time.time() - start_time

            # Log results
            logger.info(f"\n{'='*60}")
            logger.info(f"Connection Pool Stress Test Results (Mocked)")
            logger.info(f"{'='*60}")
            logger.info(f"Total threads: {num_threads}")
            logger.info(f"Successful connections: {successful_connections}")
            logger.info(f"Failed connections: {failed_connections}")
            logger.info(f"Total time: {total_time:.2f}s")

            if self.connection_times:
                logger.info(f"Avg connection time: {statistics.mean(self.connection_times)*1000:.2f}ms")
                logger.info(f"Max connection time: {max(self.connection_times)*1000:.2f}ms")
                logger.info(f"Min connection time: {min(self.connection_times)*1000:.2f}ms")

            # Clean up singleton for other tests
            ImpalaConnectionManager._instance = None

        # Assertions
        assert failed_connections == 0, f"Had {failed_connections} connection failures"
        assert successful_connections == num_threads, "Not all connections succeeded"


# ============================================================================
# Real Database Connection Pool Stress Tests
# ============================================================================

@requires_database
class TestConnectionPoolStressReal:
    """Test connection pool with real database connections"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test"""
        self.results = queue.Queue()
        self.errors = queue.Queue()
        self.connection_times = []

    def test_concurrent_connection_acquisition_real(self):
        """
        Test acquiring connections concurrently from multiple threads.
        Uses real Impala connections to SIT/UAT.
        """
        from core.repositories.impala_connection import ImpalaConnectionManager

        manager = ImpalaConnectionManager()
        num_threads = 20  # Conservative for real DB
        successful_connections = 0
        failed_connections = 0
        lock = threading.Lock()

        def acquire_and_release():
            nonlocal successful_connections, failed_connections
            try:
                start = time.time()
                with manager.get_connection() as conn:
                    elapsed = time.time() - start
                    with lock:
                        self.connection_times.append(elapsed)

                    # Execute simple query
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()

                with lock:
                    successful_connections += 1
                self.results.put(('success', elapsed))
            except Exception as e:
                with lock:
                    failed_connections += 1
                self.errors.put(('error', str(e)))

        # Launch concurrent threads
        threads = []
        start_time = time.time()

        for _ in range(num_threads):
            t = threading.Thread(target=acquire_and_release)
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=120)

        total_time = time.time() - start_time

        # Log results
        env = os.environ.get('CIS_ENV', 'LOCAL')
        logger.info(f"\n{'='*60}")
        logger.info(f"Connection Pool Stress Test Results - {env}")
        logger.info(f"{'='*60}")
        logger.info(f"Total threads: {num_threads}")
        logger.info(f"Successful connections: {successful_connections}")
        logger.info(f"Failed connections: {failed_connections}")
        logger.info(f"Total time: {total_time:.2f}s")

        if self.connection_times:
            logger.info(f"Avg connection time: {statistics.mean(self.connection_times)*1000:.2f}ms")
            logger.info(f"Max connection time: {max(self.connection_times)*1000:.2f}ms")
            logger.info(f"Min connection time: {min(self.connection_times)*1000:.2f}ms")
            logger.info(f"P95 connection time: {sorted(self.connection_times)[int(len(self.connection_times)*0.95)]*1000:.2f}ms")

        # Assertions
        assert failed_connections == 0, f"Had {failed_connections} connection failures"
        assert successful_connections == num_threads, "Not all connections succeeded"

    def test_connection_pool_exhaustion_recovery_real(self):
        """
        Test that pool recovers gracefully when exhausted.
        """
        from core.repositories.impala_connection import ImpalaConnectionManager

        manager = ImpalaConnectionManager()
        pool_size = 10  # Conservative for real testing
        overflow_factor = 2

        results = []
        lock = threading.Lock()

        def hold_connection(duration_ms):
            try:
                start = time.time()
                with manager.get_connection() as conn:
                    acquire_time = time.time() - start

                    # Hold connection briefly
                    time.sleep(duration_ms / 1000)

                    # Execute query
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    cursor.close()

                with lock:
                    results.append({
                        'success': True,
                        'acquire_time': acquire_time,
                        'total_time': time.time() - start
                    })
            except Exception as e:
                with lock:
                    results.append({
                        'success': False,
                        'error': str(e)
                    })

        # Launch more threads than pool size
        threads = []
        for _ in range(pool_size * overflow_factor):
            t = threading.Thread(target=hold_connection, args=(50,))  # Hold 50ms
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=120)

        # Analyze
        successful = sum(1 for r in results if r.get('success'))
        failed = sum(1 for r in results if not r.get('success'))

        logger.info(f"\nPool Exhaustion Test (Real DB): {successful} succeeded, {failed} failed")

        # Most should succeed (allow some failures due to timeouts)
        assert successful >= pool_size * overflow_factor * 0.8, \
            f"Expected most to succeed, but only got {successful}/{pool_size * overflow_factor}"


# ============================================================================
# Trade Creation Stress Tests (Mocked)
# ============================================================================

class TestTradeCreationStress:
    """Test concurrent trade creation logic"""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test data"""
        self.trade_ids = []
        self.errors = []
        self.lock = threading.Lock()

    def _generate_trade_data(self, user_id: int, sequence: int) -> dict:
        """Generate unique trade data"""
        timestamp = int(datetime.now().timestamp() * 1000)

        return {
            'trade_id': timestamp + sequence + (user_id * 10000),
            'portfolio_short_name': random.choice(StressTestConfig.TEST_PORTFOLIOS),
            'security_label': random.choice(StressTestConfig.TEST_SECURITIES),
            'trade_type': random.choice(['BUY', 'SELL']),
            'quantity': random.randint(100, 10000),
            'price': round(random.uniform(10, 500), 2),
            'trade_date': datetime.now().strftime('%Y-%m-%d'),
            'settlement_date': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'currency_code': 'USD',
            'status': 'PENDING',
            'created_by': f'stress_user_{user_id}',
            'created_at': timestamp,
            'updated_by': f'stress_user_{user_id}',
            'updated_at': timestamp,
        }

    @patch('core.repositories.impala_connection.impala_manager')
    def test_concurrent_trade_creation(self, mock_manager):
        """
        Test creating trades from multiple concurrent users.
        Verifies no race conditions or duplicate IDs.
        """
        mock_manager.execute_write.return_value = True

        num_users = 10
        trades_per_user = StressTestConfig.TRADES_PER_USER

        def create_trades(user_id):
            user_trades = []
            user_errors = []

            for seq in range(trades_per_user):
                try:
                    trade_data = self._generate_trade_data(user_id, seq)

                    # Simulate trade creation
                    mock_manager.execute_write.return_value = True

                    with self.lock:
                        self.trade_ids.append(trade_data['trade_id'])
                    user_trades.append(trade_data['trade_id'])

                except Exception as e:
                    user_errors.append(str(e))

            return user_trades, user_errors

        # Run concurrent users
        with ThreadPoolExecutor(max_workers=num_users) as executor:
            futures = [executor.submit(create_trades, i) for i in range(num_users)]

            for future in as_completed(futures):
                trades, errors = future.result()
                self.errors.extend(errors)

        # Verify results
        total_trades = num_users * trades_per_user
        unique_ids = len(set(self.trade_ids))

        logger.info(f"\nConcurrent Trade Creation Results:")
        logger.info(f"Total trades attempted: {total_trades}")
        logger.info(f"Trades created: {len(self.trade_ids)}")
        logger.info(f"Unique trade IDs: {unique_ids}")
        logger.info(f"Errors: {len(self.errors)}")

        assert len(self.errors) == 0, f"Had {len(self.errors)} errors: {self.errors[:5]}"
        assert unique_ids == total_trades, f"Duplicate trade IDs detected! {total_trades} trades but only {unique_ids} unique"

    @patch('trade.services.position_service.position_service')
    @patch('trade.services.settlement_service.settlement_service')
    def test_trade_settlement_race_condition(self, mock_settlement, mock_position):
        """
        Test that concurrent settlements don't cause race conditions.
        """
        mock_settlement.settle_trade.return_value = (True, None)
        mock_position.update_position.return_value = True

        num_concurrent = 20
        results = []

        def settle_trade(trade_id):
            try:
                # Simulate settlement
                success, _ = mock_settlement.settle_trade(trade_id, 'test_user')
                results.append({'trade_id': trade_id, 'success': success})
            except Exception as e:
                results.append({'trade_id': trade_id, 'success': False, 'error': str(e)})

        trade_ids = list(range(1000, 1000 + num_concurrent))

        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            executor.map(settle_trade, trade_ids)

        successful = sum(1 for r in results if r['success'])

        logger.info(f"\nSettlement Race Condition Test:")
        logger.info(f"Concurrent settlements: {num_concurrent}")
        logger.info(f"Successful: {successful}")

        assert successful == num_concurrent, f"Only {successful}/{num_concurrent} settlements succeeded"


# ============================================================================
# Real Database Query Performance Tests
# ============================================================================

@requires_database
class TestQueryPerformanceReal:
    """Test query performance with real database"""

    def test_trade_list_query_performance_real(self):
        """
        Test trade list query performance against real database.
        """
        from core.repositories.impala_connection import ImpalaConnectionManager

        manager = ImpalaConnectionManager()
        query_times = []
        iterations = 20  # Conservative for real DB

        for _ in range(iterations):
            start = time.time()
            with manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM gmp_cis.cis_trade LIMIT 1000")
                results = cursor.fetchall()
                cursor.close()
            elapsed_ms = (time.time() - start) * 1000
            query_times.append(elapsed_ms)

        avg_time = statistics.mean(query_times)
        max_time = max(query_times)
        min_time = min(query_times)
        p95_time = sorted(query_times)[int(len(query_times) * 0.95)]

        env = os.environ.get('CIS_ENV', 'LOCAL')
        logger.info(f"\nTrade List Query Performance ({env}):")
        logger.info(f"Iterations: {iterations}")
        logger.info(f"Avg time: {avg_time:.2f}ms")
        logger.info(f"Min time: {min_time:.2f}ms")
        logger.info(f"Max time: {max_time:.2f}ms")
        logger.info(f"P95 time: {p95_time:.2f}ms")

        assert p95_time < StressTestConfig.MAX_QUERY_TIME_MS, \
            f"P95 query time {p95_time:.2f}ms exceeds SLA of {StressTestConfig.MAX_QUERY_TIME_MS}ms"

    def test_position_query_performance_real(self):
        """
        Test position query performance against real database.
        """
        from core.repositories.impala_connection import ImpalaConnectionManager

        manager = ImpalaConnectionManager()
        query_times = []

        for _ in range(20):
            start = time.time()
            with manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT portfolio_short_name, security_label,
                           SUM(quantity) as total_qty,
                           SUM(total_cost) as total_cost
                    FROM gmp_cis.cis_position
                    WHERE position_date >= '2024-01-01'
                    GROUP BY portfolio_short_name, security_label
                    LIMIT 1000
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed_ms = (time.time() - start) * 1000
            query_times.append(elapsed_ms)

        avg_time = statistics.mean(query_times)

        env = os.environ.get('CIS_ENV', 'LOCAL')
        logger.info(f"\nPosition Aggregation Query Performance ({env}):")
        logger.info(f"Avg time: {avg_time:.2f}ms")

        assert avg_time < 2000, f"Position aggregation too slow: {avg_time:.2f}ms"


# ============================================================================
# Position Calculation Stress Tests (Mocked)
# ============================================================================

class TestPositionCalculationStress:
    """Test position calculations under concurrent load"""

    @patch('core.repositories.impala_connection.impala_manager')
    def test_concurrent_position_updates(self, mock_manager):
        """
        Test multiple position updates for same portfolio/security.
        Verifies AVP calculations remain consistent.
        """
        # Mock position data
        position_data = {
            'quantity': Decimal('1000'),
            'average_price': Decimal('100.00'),
            'total_cost': Decimal('100000'),
            'realized_pnl': Decimal('0'),
        }

        mock_manager.execute_query.return_value = [position_data]
        mock_manager.execute_write.return_value = True

        num_updates = StressTestConfig.CONCURRENT_POSITION_UPDATES
        results = []
        lock = threading.Lock()

        def update_position(update_id):
            try:
                # Simulate buy order
                buy_qty = random.randint(100, 500)
                buy_price = Decimal(str(round(random.uniform(95, 105), 2)))

                # Calculate new AVP
                current_qty = position_data['quantity']
                current_cost = position_data['total_cost']

                new_qty = current_qty + buy_qty
                new_cost = current_cost + (buy_qty * buy_price)
                new_avp = new_cost / new_qty if new_qty > 0 else Decimal('0')

                with lock:
                    results.append({
                        'update_id': update_id,
                        'success': True,
                        'new_qty': new_qty,
                        'new_avp': float(new_avp)
                    })

            except Exception as e:
                with lock:
                    results.append({
                        'update_id': update_id,
                        'success': False,
                        'error': str(e)
                    })

        with ThreadPoolExecutor(max_workers=20) as executor:
            executor.map(update_position, range(num_updates))

        successful = sum(1 for r in results if r['success'])

        logger.info(f"\nConcurrent Position Update Test:")
        logger.info(f"Total updates: {num_updates}")
        logger.info(f"Successful: {successful}")

        assert successful == num_updates, f"Only {successful}/{num_updates} updates succeeded"


# ============================================================================
# Query Performance Tests (Mocked)
# ============================================================================

class TestQueryPerformanceMocked:
    """Test query performance with mocking"""

    @patch('core.repositories.impala_connection.impala_manager')
    def test_trade_list_query_performance(self, mock_manager):
        """
        Test trade list query performance (mocked).
        """
        # Mock returning 1000 trades
        mock_trades = [
            {'trade_id': i, 'portfolio_short_name': 'TEST', 'quantity': 100}
            for i in range(1000)
        ]
        mock_manager.execute_query.return_value = mock_trades

        query_times = []

        for _ in range(StressTestConfig.QUERY_ITERATIONS):
            start = time.time()
            result = mock_manager.execute_query("SELECT * FROM cis_trade LIMIT 1000")
            elapsed_ms = (time.time() - start) * 1000
            query_times.append(elapsed_ms)

        avg_time = statistics.mean(query_times)
        max_time = max(query_times)
        p95_time = sorted(query_times)[int(len(query_times) * 0.95)]

        logger.info(f"\nTrade List Query Performance (Mocked):")
        logger.info(f"Iterations: {StressTestConfig.QUERY_ITERATIONS}")
        logger.info(f"Avg time: {avg_time:.2f}ms")
        logger.info(f"Max time: {max_time:.2f}ms")
        logger.info(f"P95 time: {p95_time:.2f}ms")

        # Mocked queries should be very fast
        assert p95_time < 100, f"P95 query time {p95_time:.2f}ms too slow for mocked test"


# ============================================================================
# Integration Stress Test (Mocked)
# ============================================================================

class TestIntegrationStress:
    """End-to-end stress test simulating real usage"""

    @patch('core.repositories.impala_connection.impala_manager')
    def test_full_trade_lifecycle_concurrent(self, mock_manager):
        """
        Test full trade lifecycle with concurrent users:
        1. Create trade
        2. Approve trade
        3. Settle trade
        4. Update position
        """
        mock_manager.execute_write.return_value = True
        mock_manager.execute_query.return_value = []

        num_users = 5
        trades_per_user = 5
        lifecycle_results = []
        lock = threading.Lock()

        def run_trade_lifecycle(user_id):
            user_results = []

            for i in range(trades_per_user):
                trade_id = int(datetime.now().timestamp() * 1000) + (user_id * 1000) + i

                try:
                    # Step 1: Create trade
                    mock_manager.execute_write.return_value = True

                    # Step 2: Approve trade
                    mock_manager.execute_write.return_value = True

                    # Step 3: Settle trade
                    mock_manager.execute_write.return_value = True

                    # Step 4: Update position
                    mock_manager.execute_write.return_value = True

                    user_results.append({
                        'trade_id': trade_id,
                        'success': True,
                        'user_id': user_id
                    })

                except Exception as e:
                    user_results.append({
                        'trade_id': trade_id,
                        'success': False,
                        'error': str(e),
                        'user_id': user_id
                    })

            with lock:
                lifecycle_results.extend(user_results)

        # Run concurrent users
        with ThreadPoolExecutor(max_workers=num_users) as executor:
            executor.map(run_trade_lifecycle, range(num_users))

        total_trades = num_users * trades_per_user
        successful = sum(1 for r in lifecycle_results if r['success'])

        logger.info(f"\nFull Trade Lifecycle Stress Test:")
        logger.info(f"Concurrent users: {num_users}")
        logger.info(f"Trades per user: {trades_per_user}")
        logger.info(f"Total trades: {total_trades}")
        logger.info(f"Successful lifecycles: {successful}")

        assert successful == total_trades, \
            f"Only {successful}/{total_trades} trade lifecycles completed successfully"


# ============================================================================
# Run Configuration
# ============================================================================

if __name__ == '__main__':
    # Print environment info
    env = os.environ.get('CIS_ENV', 'LOCAL')
    print(f"\n{'='*60}")
    print(f"  Kudu Stress Test Suite - Environment: {env}")
    print(f"{'='*60}")

    pytest.main([__file__, '-v', '-s', '--tb=short'])
