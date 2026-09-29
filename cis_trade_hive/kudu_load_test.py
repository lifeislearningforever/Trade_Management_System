#!/usr/bin/env python3
"""
Direct Kudu/Impala Load Testing Script

This script directly stress tests the Kudu database without needing Django web app.
It tests connection pool, queries, and concurrent operations.

Usage:
    # Set environment
    export CIS_ENV=SIT

    # Run load test
    python kudu_load_test.py

    # With options
    python kudu_load_test.py --users 50 --duration 300 --test-type all
"""

import os
import sys
import time
import random
import threading
import statistics
import argparse
from datetime import datetime, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.repositories.impala_connection import ImpalaConnectionManager, IMPALA_AVAILABLE


class LoadTestMetrics:
    """Collect and report load test metrics."""

    def __init__(self):
        self.lock = threading.Lock()
        self.requests = defaultdict(list)  # {operation: [response_times]}
        self.errors = defaultdict(list)     # {operation: [error_messages]}
        self.start_time = None
        self.end_time = None

    def record_success(self, operation: str, response_time_ms: float):
        with self.lock:
            self.requests[operation].append(response_time_ms)

    def record_error(self, operation: str, error: str):
        with self.lock:
            self.errors[operation].append(error)

    def start(self):
        self.start_time = time.time()

    def stop(self):
        self.end_time = time.time()

    def report(self):
        """Generate load test report."""
        duration = self.end_time - self.start_time if self.end_time else 0

        print("\n" + "=" * 70)
        print("  KUDU LOAD TEST REPORT")
        print("=" * 70)
        print(f"  Duration: {duration:.2f} seconds")
        print(f"  Environment: {os.environ.get('CIS_ENV', 'LOCAL')}")
        print("=" * 70)

        total_requests = 0
        total_errors = 0

        for operation, times in sorted(self.requests.items()):
            errors = len(self.errors.get(operation, []))
            total_requests += len(times)
            total_errors += errors

            if times:
                avg = statistics.mean(times)
                p50 = sorted(times)[len(times) // 2]
                p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 1 else times[0]
                p99 = sorted(times)[int(len(times) * 0.99)] if len(times) > 1 else times[0]
                max_time = max(times)
                min_time = min(times)
                rps = len(times) / duration if duration > 0 else 0

                print(f"\n  {operation}:")
                print(f"    Requests:  {len(times):,}")
                print(f"    Errors:    {errors}")
                print(f"    RPS:       {rps:.2f}")
                print(f"    Avg:       {avg:.2f} ms")
                print(f"    Min:       {min_time:.2f} ms")
                print(f"    P50:       {p50:.2f} ms")
                print(f"    P95:       {p95:.2f} ms")
                print(f"    P99:       {p99:.2f} ms")
                print(f"    Max:       {max_time:.2f} ms")

        print("\n" + "-" * 70)
        print(f"  TOTAL REQUESTS: {total_requests:,}")
        print(f"  TOTAL ERRORS:   {total_errors}")
        print(f"  ERROR RATE:     {(total_errors/total_requests*100) if total_requests else 0:.2f}%")
        print(f"  THROUGHPUT:     {total_requests/duration:.2f} req/sec" if duration else "")
        print("=" * 70 + "\n")

        # Print errors if any
        if any(self.errors.values()):
            print("\n  ERRORS:")
            for operation, errs in self.errors.items():
                if errs:
                    print(f"\n  {operation}:")
                    for err in errs[:5]:  # Show first 5 errors
                        print(f"    - {err[:100]}")
                    if len(errs) > 5:
                        print(f"    ... and {len(errs) - 5} more")


class KuduLoadTest:
    """Direct Kudu load testing."""

    def __init__(self, num_users: int = 50, duration_sec: int = 60):
        self.num_users = num_users
        self.duration_sec = duration_sec
        self.metrics = LoadTestMetrics()
        self.running = False
        self.manager = ImpalaConnectionManager()

        # Test data
        self.portfolios = ['AIIF CP II LTD', 'GLOBAL MACRO FUND', 'ASIAN EQUITY FUND']
        self.securities = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META']
        self.currencies = ['USD', 'EUR', 'GBP', 'SGD']

    def test_connection_pool(self):
        """Test connection acquisition and release."""
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Connection Pool", elapsed)
        except Exception as e:
            self.metrics.record_error("Connection Pool", str(e))

    def test_trade_list_query(self):
        """Test trade list query."""
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT trade_id, portfolio_short_name, security_label,
                           trade_type, quantity, price, trade_date
                    FROM gmp_cis.cis_trade
                    WHERE is_deleted = false
                    ORDER BY created_at DESC
                    LIMIT 100
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Trade List Query", elapsed)
        except Exception as e:
            self.metrics.record_error("Trade List Query", str(e))

    def test_position_query(self):
        """Test position query with aggregation."""
        portfolio = random.choice(self.portfolios)
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT portfolio_short_name, security_label, currency_code,
                           quantity, average_price, total_cost, market_value
                    FROM gmp_cis.cis_position
                    WHERE portfolio_short_name = '{portfolio}'
                    AND position_date = (
                        SELECT MAX(position_date) FROM gmp_cis.cis_position
                        WHERE portfolio_short_name = '{portfolio}'
                    )
                    LIMIT 50
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Position Query", elapsed)
        except Exception as e:
            self.metrics.record_error("Position Query", str(e))

    def test_avp_calculation_query(self):
        """Test AVP (Average Price) calculation query."""
        portfolio = random.choice(self.portfolios)
        security = random.choice(self.securities)
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT
                        portfolio_short_name,
                        security_label,
                        SUM(quantity) as total_qty,
                        SUM(total_cost) as total_cost,
                        CASE WHEN SUM(quantity) > 0
                             THEN SUM(total_cost) / SUM(quantity)
                             ELSE 0 END as avg_price
                    FROM gmp_cis.cis_position
                    WHERE portfolio_short_name = '{portfolio}'
                    GROUP BY portfolio_short_name, security_label
                    LIMIT 20
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("AVP Calculation", elapsed)
        except Exception as e:
            self.metrics.record_error("AVP Calculation", str(e))

    def test_security_lookup(self):
        """Test security master lookup."""
        security = random.choice(self.securities)
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT security_id, security_label, security_name,
                           security_type, currency_code, country_code
                    FROM gmp_cis.cis_security_kudu
                    WHERE is_active = true
                    LIMIT 50
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Security Lookup", elapsed)
        except Exception as e:
            self.metrics.record_error("Security Lookup", str(e))

    def test_portfolio_list(self):
        """Test portfolio list query."""
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT portfolio_id, portfolio_short_name, portfolio_full_name,
                           base_currency, status
                    FROM gmp_cis.cis_portfolio
                    WHERE is_deleted = false
                    LIMIT 100
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Portfolio List", elapsed)
        except Exception as e:
            self.metrics.record_error("Portfolio List", str(e))

    def test_fx_rate_lookup(self):
        """Test FX rate lookup."""
        from_ccy = random.choice(self.currencies)
        to_ccy = random.choice([c for c in self.currencies if c != from_ccy])
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(f"""
                    SELECT from_currency, to_currency, rate_date, exchange_rate
                    FROM gmp_cis.cis_fx_rate
                    WHERE from_currency = '{from_ccy}'
                    ORDER BY rate_date DESC
                    LIMIT 10
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("FX Rate Lookup", elapsed)
        except Exception as e:
            self.metrics.record_error("FX Rate Lookup", str(e))

    def test_complex_join_query(self):
        """Test complex join query (trade + security + portfolio)."""
        start = time.time()
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT t.trade_id, t.portfolio_short_name, t.security_label,
                           t.trade_type, t.quantity, t.price,
                           p.base_currency as portfolio_currency
                    FROM gmp_cis.cis_trade t
                    LEFT JOIN gmp_cis.cis_portfolio p
                        ON t.portfolio_short_name = p.portfolio_short_name
                    WHERE t.is_deleted = false
                    ORDER BY t.created_at DESC
                    LIMIT 50
                """)
                results = cursor.fetchall()
                cursor.close()
            elapsed = (time.time() - start) * 1000
            self.metrics.record_success("Complex Join Query", elapsed)
        except Exception as e:
            self.metrics.record_error("Complex Join Query", str(e))

    def worker(self, worker_id: int):
        """Worker thread that runs random operations."""
        operations = [
            self.test_connection_pool,
            self.test_trade_list_query,
            self.test_position_query,
            self.test_avp_calculation_query,
            self.test_security_lookup,
            self.test_portfolio_list,
            self.test_fx_rate_lookup,
            self.test_complex_join_query,
        ]

        while self.running:
            # Pick random operation
            operation = random.choice(operations)
            try:
                operation()
            except Exception as e:
                pass  # Already recorded in metrics

            # Small random delay between operations
            time.sleep(random.uniform(0.1, 0.5))

    def run(self, test_type: str = "all"):
        """Run the load test."""
        if not IMPALA_AVAILABLE:
            print("ERROR: Impala library not available!")
            return

        # Test connection first
        print("Testing database connection...")
        try:
            with self.manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                cursor.close()
            print("Database connection: OK")
        except Exception as e:
            print(f"ERROR: Cannot connect to database: {e}")
            return

        print(f"\nStarting Kudu Load Test")
        print(f"  Users: {self.num_users}")
        print(f"  Duration: {self.duration_sec} seconds")
        print(f"  Test Type: {test_type}")
        print("-" * 50)

        self.running = True
        self.metrics.start()

        # Start worker threads
        with ThreadPoolExecutor(max_workers=self.num_users) as executor:
            futures = [executor.submit(self.worker, i) for i in range(self.num_users)]

            # Run for specified duration
            try:
                time.sleep(self.duration_sec)
            except KeyboardInterrupt:
                print("\nStopping test...")

            self.running = False

            # Wait for workers to finish
            for future in futures:
                try:
                    future.result(timeout=5)
                except:
                    pass

        self.metrics.stop()
        self.metrics.report()


def main():
    parser = argparse.ArgumentParser(description="Kudu Direct Load Testing")
    parser.add_argument("--users", type=int, default=50, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--test-type", default="all", choices=["all", "read", "write", "avp"],
                        help="Type of test to run")

    args = parser.parse_args()

    print("=" * 60)
    print("  KUDU DIRECT LOAD TESTING")
    print("=" * 60)
    print(f"  Environment: {os.environ.get('CIS_ENV', 'LOCAL')}")
    print(f"  Users: {args.users}")
    print(f"  Duration: {args.duration} seconds")
    print("=" * 60)

    test = KuduLoadTest(num_users=args.users, duration_sec=args.duration)
    test.run(test_type=args.test_type)


if __name__ == "__main__":
    main()
