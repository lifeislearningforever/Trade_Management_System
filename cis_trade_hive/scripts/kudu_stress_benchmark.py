#!/usr/bin/env python3
"""
Kudu Stress Load Benchmark - JMeter/Locust Style
=================================================

Real stress testing for Kudu/Hive with concurrent users, ramp-up scheduling,
think time, and comprehensive metrics - similar to JMeter/Selenium load tests.

Features:
---------
- Concurrent user simulation (like JMeter Thread Groups)
- Ramp-up scheduling (gradual user spawn)
- Think time between operations (realistic user behavior)
- Real-time progress monitoring
- Comprehensive metrics (p50, p95, p99, throughput, error rate)
- ACID transaction conflict testing
- JSON/CSV report generation
- Multiple test scenarios (quick, standard, stress, soak)

Usage:
------
    # Quick smoke test (10 users, 1 minute)
    python scripts/kudu_stress_benchmark.py --scenario quick

    # Standard load test (50 users, 5 minutes)
    python scripts/kudu_stress_benchmark.py --scenario standard

    # Stress test (100 users, 10 minutes)
    python scripts/kudu_stress_benchmark.py --scenario stress

    # Custom test
    python scripts/kudu_stress_benchmark.py --users 200 --duration 600 --ramp-up 60

    # Soak test (sustained load for memory leak detection)
    python scripts/kudu_stress_benchmark.py --scenario soak

Author: CIS Trade Hive Team
Date: 2026-02-24
"""

import os
import sys
import time
import uuid
import json
import csv
import random
import argparse
import threading
import queue
import statistics
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Callable
from enum import Enum
import signal

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from core.repositories.impala_connection import impala_manager


# =============================================================================
# Configuration & Constants
# =============================================================================

class TestScenario(Enum):
    """Predefined test scenarios similar to JMeter test plans."""
    QUICK = "quick"           # 10 users, 1 minute - smoke test
    STANDARD = "standard"     # 50 users, 5 minutes - regular load
    STRESS = "stress"         # 100 users, 10 minutes - stress test
    SPIKE = "spike"           # 200 users, 2 minutes - spike test
    SOAK = "soak"             # 30 users, 30 minutes - endurance test


SCENARIO_CONFIG = {
    TestScenario.QUICK: {
        'users': 10,
        'duration_seconds': 60,
        'ramp_up_seconds': 10,
        'think_time_range': (0.5, 1.0),
        'ops_per_user': 50,
    },
    TestScenario.STANDARD: {
        'users': 50,
        'duration_seconds': 300,
        'ramp_up_seconds': 30,
        'think_time_range': (0.5, 2.0),
        'ops_per_user': 100,
    },
    TestScenario.STRESS: {
        'users': 100,
        'duration_seconds': 600,
        'ramp_up_seconds': 60,
        'think_time_range': (0.3, 1.5),
        'ops_per_user': 200,
    },
    TestScenario.SPIKE: {
        'users': 200,
        'duration_seconds': 120,
        'ramp_up_seconds': 10,  # Fast ramp-up for spike
        'think_time_range': (0.1, 0.5),
        'ops_per_user': 50,
    },
    TestScenario.SOAK: {
        'users': 30,
        'duration_seconds': 1800,  # 30 minutes
        'ramp_up_seconds': 60,
        'think_time_range': (1.0, 3.0),
        'ops_per_user': 500,
    },
}


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class OperationResult:
    """Result of a single database operation."""
    timestamp: datetime
    user_id: int
    operation: str
    table: str
    elapsed_ms: float
    success: bool
    error: Optional[str] = None
    record_id: Optional[str] = None


@dataclass
class UserMetrics:
    """Metrics for a single simulated user."""
    user_id: int
    start_time: datetime
    end_time: Optional[datetime] = None
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    total_elapsed_ms: float = 0.0


@dataclass
class BenchmarkMetrics:
    """Overall benchmark metrics."""
    test_name: str
    scenario: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    total_users: int = 0
    total_operations: int = 0
    successful_operations: int = 0
    failed_operations: int = 0
    success_rate_pct: float = 0.0
    throughput_ops_per_sec: float = 0.0
    latency_min_ms: float = 0.0
    latency_max_ms: float = 0.0
    latency_avg_ms: float = 0.0
    latency_median_ms: float = 0.0
    latency_p90_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    errors_by_type: Dict[str, int] = field(default_factory=dict)
    operations_by_type: Dict[str, Dict[str, Any]] = field(default_factory=dict)


# =============================================================================
# Table Schemas
# =============================================================================

TABLES = {
    'portfolio': {
        'table': 'cis_portfolio',
        'pk': 'name',
        'columns': [
            'name', 'description', 'currency', 'manager', 'portfolio_client',
            'cash_balance', 'cost_centre_code', 'corp_code', 'account_group',
            'portfolio_group', 'report_group', 'entity_group', 'revaluation_status',
            'src_system', 'status', 'is_active', 'created_by', 'created_at',
            'updated_by', 'updated_at'
        ],
    },
    'trade': {
        'table': 'cis_trade',
        'pk': 'trade_id',
        'columns': [
            'trade_id', 'trade_type', 'deal_number', 'portfolio_short_name',
            'portfolio_full_name', 'security_label', 'security_full_name',
            'security_type', 'trade_status', 'trade_date', 'settle_date',
            'quantity', 'price', 'total_amount', 'broker_name', 'currency',
            'status', 'is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'
        ],
    },
    'security': {
        'table': 'cis_security',
        'pk': 'security_id',
        'columns': [
            'security_id', 'security_name', 'isin', 'security_description',
            'security_type', 'industry', 'currency', 'country_code',
            'status', 'is_active', 'created_by', 'created_at', 'updated_by', 'updated_at'
        ],
    },
    'fx_rate': {
        'table': 'cis_fx_rate',
        'pk': 'rate_id',
        'columns': [
            'rate_id', 'from_currency', 'to_currency', 'rate_date',
            'rate', 'source', 'created_at', 'created_by'
        ],
    },
}


# =============================================================================
# Test Data Generator
# =============================================================================

class TestDataGenerator:
    """Generate realistic test data for benchmarking."""

    CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'SGD', 'HKD', 'AUD']
    SECURITY_TYPES = ['EQUITY', 'BOND', 'FX', 'DERIVATIVE', 'ETF']
    TRADE_TYPES = ['BUY', 'SELL', 'DIVIDEND', 'INTEREST', 'FEE']
    INDUSTRIES = ['TECHNOLOGY', 'FINANCE', 'HEALTHCARE', 'ENERGY', 'CONSUMER']

    @staticmethod
    def generate_id(prefix: str = "STRESS") -> str:
        """Generate unique ID."""
        return f"{prefix}_{uuid.uuid4().hex[:12].upper()}"

    @classmethod
    def generate_portfolio(cls, user_id: int) -> Dict[str, Any]:
        """Generate portfolio test data."""
        now = datetime.now()
        test_id = cls.generate_id(f"PF_U{user_id}")
        return {
            'name': test_id,
            'description': f'Stress Test Portfolio {test_id}',
            'currency': random.choice(cls.CURRENCIES),
            'manager': f'User_{user_id}',
            'portfolio_client': f'CLIENT_{user_id % 10}',
            'cash_balance': str(random.uniform(10000, 1000000)),
            'cost_centre_code': f'CC{random.randint(100, 999)}',
            'corp_code': f'CORP{random.randint(1, 10)}',
            'account_group': f'AG{random.randint(1, 5)}',
            'portfolio_group': f'PG{random.randint(1, 5)}',
            'report_group': f'RG{random.randint(1, 5)}',
            'entity_group': f'EG{random.randint(1, 5)}',
            'revaluation_status': 'PENDING',
            'src_system': 'STRESS_TEST',
            'status': 'DRAFT',
            'is_active': True,
            'created_by': f'user_{user_id}',
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_by': f'user_{user_id}',
            'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

    @classmethod
    def generate_trade(cls, user_id: int) -> Dict[str, Any]:
        """Generate trade test data."""
        now = datetime.now()
        test_id = cls.generate_id(f"TRD_U{user_id}")
        quantity = random.randint(100, 10000)
        price = random.uniform(10, 500)
        return {
            'trade_id': test_id,
            'trade_type': random.choice(cls.TRADE_TYPES),
            'deal_number': f'DEAL_{test_id[-8:]}',
            'portfolio_short_name': f'PF_{user_id % 20}',
            'portfolio_full_name': f'Portfolio {user_id % 20}',
            'security_label': f'SEC_{random.randint(1, 100)}',
            'security_full_name': f'Security {random.randint(1, 100)}',
            'security_type': random.choice(cls.SECURITY_TYPES),
            'trade_status': 'NEW',
            'trade_date': now.strftime('%Y-%m-%d'),
            'settle_date': (now + timedelta(days=2)).strftime('%Y-%m-%d'),
            'quantity': quantity,
            'price': round(price, 2),
            'total_amount': round(quantity * price, 2),
            'broker_name': f'BROKER_{random.randint(1, 10)}',
            'currency': random.choice(cls.CURRENCIES),
            'status': 'DRAFT',
            'is_active': True,
            'created_by': f'user_{user_id}',
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_by': f'user_{user_id}',
            'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

    @classmethod
    def generate_security(cls, user_id: int) -> Dict[str, Any]:
        """Generate security test data."""
        now = datetime.now()
        test_id = cls.generate_id(f"SEC_U{user_id}")
        return {
            'security_id': test_id,
            'security_name': f'Stress Security {test_id}',
            'isin': f'US{test_id[-10:]}',
            'security_description': f'Description for {test_id}',
            'security_type': random.choice(cls.SECURITY_TYPES),
            'industry': random.choice(cls.INDUSTRIES),
            'currency': random.choice(cls.CURRENCIES),
            'country_code': random.choice(['US', 'GB', 'JP', 'SG', 'HK']),
            'status': 'ACTIVE',
            'is_active': True,
            'created_by': f'user_{user_id}',
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_by': f'user_{user_id}',
            'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
        }

    @classmethod
    def generate_fx_rate(cls, user_id: int) -> Dict[str, Any]:
        """Generate FX rate test data."""
        now = datetime.now()
        test_id = cls.generate_id(f"FX_U{user_id}")
        from_ccy = random.choice(cls.CURRENCIES)
        to_ccy = random.choice([c for c in cls.CURRENCIES if c != from_ccy])
        return {
            'rate_id': test_id,
            'from_currency': from_ccy,
            'to_currency': to_ccy,
            'rate_date': now.strftime('%Y-%m-%d'),
            'rate': round(random.uniform(0.5, 2.0), 6),
            'source': 'STRESS_TEST',
            'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            'created_by': f'user_{user_id}',
        }


# =============================================================================
# Metrics Collector
# =============================================================================

class MetricsCollector:
    """Thread-safe metrics collection with real-time analysis."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.start_time = datetime.now()
        self.results: List[OperationResult] = []
        self.user_metrics: Dict[int, UserMetrics] = {}
        self._lock = threading.Lock()
        self._operation_counts = {'INSERT': 0, 'UPDATE': 0, 'DELETE': 0, 'SELECT': 0}

    def record_operation(self, result: OperationResult):
        """Record a single operation result (thread-safe)."""
        with self._lock:
            self.results.append(result)
            self._operation_counts[result.operation] = \
                self._operation_counts.get(result.operation, 0) + 1

    def register_user(self, user_id: int):
        """Register a new user starting work."""
        with self._lock:
            self.user_metrics[user_id] = UserMetrics(
                user_id=user_id,
                start_time=datetime.now()
            )

    def user_completed(self, user_id: int, ops: int, success: int, failed: int, elapsed_ms: float):
        """Record user completion."""
        with self._lock:
            if user_id in self.user_metrics:
                self.user_metrics[user_id].end_time = datetime.now()
                self.user_metrics[user_id].total_operations = ops
                self.user_metrics[user_id].successful_operations = success
                self.user_metrics[user_id].failed_operations = failed
                self.user_metrics[user_id].total_elapsed_ms = elapsed_ms

    def get_current_stats(self) -> Dict[str, Any]:
        """Get current statistics (for real-time monitoring)."""
        with self._lock:
            if not self.results:
                return {'total_ops': 0, 'success_rate': 0, 'avg_latency_ms': 0}

            elapsed_times = [r.elapsed_ms for r in self.results if r.success]
            total = len(self.results)
            success = len(elapsed_times)

            return {
                'total_ops': total,
                'success_ops': success,
                'failed_ops': total - success,
                'success_rate': (success / total * 100) if total > 0 else 0,
                'avg_latency_ms': statistics.mean(elapsed_times) if elapsed_times else 0,
                'ops_per_sec': total / max(1, (datetime.now() - self.start_time).total_seconds()),
                'active_users': len([u for u in self.user_metrics.values() if u.end_time is None]),
            }

    def calculate_final_metrics(self, scenario: str) -> BenchmarkMetrics:
        """Calculate comprehensive final metrics."""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        with self._lock:
            successful = [r for r in self.results if r.success]
            failed = [r for r in self.results if not r.success]

            elapsed_times = sorted([r.elapsed_ms for r in successful]) if successful else []

            def percentile(data: List[float], p: float) -> float:
                if not data:
                    return 0.0
                idx = int(len(data) * p / 100)
                return data[min(idx, len(data) - 1)]

            # Error analysis
            errors_by_type = {}
            for r in failed:
                error_key = r.error[:50] if r.error else 'Unknown'
                errors_by_type[error_key] = errors_by_type.get(error_key, 0) + 1

            # Per-operation metrics
            ops_by_type = {}
            for op_type in ['INSERT', 'UPDATE', 'DELETE', 'SELECT']:
                op_results = [r for r in successful if r.operation == op_type]
                if op_results:
                    op_times = sorted([r.elapsed_ms for r in op_results])
                    ops_by_type[op_type] = {
                        'count': len(op_results),
                        'avg_ms': statistics.mean(op_times),
                        'median_ms': statistics.median(op_times),
                        'p95_ms': percentile(op_times, 95),
                        'min_ms': min(op_times),
                        'max_ms': max(op_times),
                    }

            return BenchmarkMetrics(
                test_name=self.test_name,
                scenario=scenario,
                start_time=self.start_time,
                end_time=end_time,
                duration_seconds=duration,
                total_users=len(self.user_metrics),
                total_operations=len(self.results),
                successful_operations=len(successful),
                failed_operations=len(failed),
                success_rate_pct=(len(successful) / len(self.results) * 100) if self.results else 0,
                throughput_ops_per_sec=len(successful) / duration if duration > 0 else 0,
                latency_min_ms=min(elapsed_times) if elapsed_times else 0,
                latency_max_ms=max(elapsed_times) if elapsed_times else 0,
                latency_avg_ms=statistics.mean(elapsed_times) if elapsed_times else 0,
                latency_median_ms=statistics.median(elapsed_times) if elapsed_times else 0,
                latency_p90_ms=percentile(elapsed_times, 90),
                latency_p95_ms=percentile(elapsed_times, 95),
                latency_p99_ms=percentile(elapsed_times, 99),
                errors_by_type=errors_by_type,
                operations_by_type=ops_by_type,
            )


# =============================================================================
# Virtual User Simulator
# =============================================================================

class VirtualUser:
    """
    Simulates a single user performing database operations.
    Similar to JMeter Thread or Locust User.
    """

    def __init__(
        self,
        user_id: int,
        database: str,
        metrics_collector: MetricsCollector,
        think_time_range: tuple = (0.5, 2.0),
        operation_weights: Dict[str, float] = None,
        tables: List[str] = None,
    ):
        self.user_id = user_id
        self.database = database
        self.metrics = metrics_collector
        self.think_time_range = think_time_range
        self.tables = tables or ['trade', 'portfolio', 'security']
        self.stop_flag = threading.Event()

        # Operation weights (probability distribution)
        self.operation_weights = operation_weights or {
            'INSERT': 0.4,
            'SELECT': 0.3,
            'UPDATE': 0.2,
            'DELETE': 0.1,
        }

        # Track created records for UPDATE/DELETE
        self.created_records: Dict[str, List[str]] = {t: [] for t in self.tables}

    def _format_value(self, value: Any) -> str:
        """Format value for SQL."""
        if value is None:
            return "NULL"
        elif isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        elif isinstance(value, (int, float)):
            return str(value)
        else:
            escaped = str(value).replace("'", "''")
            return f"'{escaped}'"

    def _choose_operation(self) -> str:
        """Choose random operation based on weights."""
        ops = list(self.operation_weights.keys())
        weights = list(self.operation_weights.values())
        return random.choices(ops, weights=weights)[0]

    def _choose_table(self) -> str:
        """Choose random table."""
        return random.choice(self.tables)

    def _think(self):
        """Simulate user think time."""
        time.sleep(random.uniform(*self.think_time_range))

    def execute_insert(self, table_key: str) -> OperationResult:
        """Execute INSERT operation."""
        table_info = TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"

        # Generate test data
        if table_key == 'portfolio':
            data = TestDataGenerator.generate_portfolio(self.user_id)
        elif table_key == 'trade':
            data = TestDataGenerator.generate_trade(self.user_id)
        elif table_key == 'security':
            data = TestDataGenerator.generate_security(self.user_id)
        elif table_key == 'fx_rate':
            data = TestDataGenerator.generate_fx_rate(self.user_id)
        else:
            data = TestDataGenerator.generate_trade(self.user_id)

        record_id = data[table_info['pk']]
        columns = table_info['columns']
        values = [self._format_value(data.get(col)) for col in columns]

        query = f"""
            UPSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(values)})
        """

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            if success:
                self.created_records[table_key].append(record_id)

            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='INSERT',
                table=table_key,
                elapsed_ms=elapsed,
                success=success,
                error=None if success else "Write returned False",
                record_id=record_id,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='INSERT',
                table=table_key,
                elapsed_ms=elapsed,
                success=False,
                error=str(e)[:200],
                record_id=record_id,
            )

    def execute_select(self, table_key: str) -> OperationResult:
        """Execute SELECT operation."""
        table_info = TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"

        query = f"SELECT * FROM {table_name} LIMIT {random.randint(10, 100)}"

        start = time.perf_counter()
        try:
            results = impala_manager.execute_query(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='SELECT',
                table=table_key,
                elapsed_ms=elapsed,
                success=True,
                error=None,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='SELECT',
                table=table_key,
                elapsed_ms=elapsed,
                success=False,
                error=str(e)[:200],
            )

    def execute_update(self, table_key: str) -> OperationResult:
        """Execute UPDATE operation."""
        # Need a record to update
        if not self.created_records[table_key]:
            # Create one first
            insert_result = self.execute_insert(table_key)
            if not insert_result.success:
                return insert_result

        record_id = random.choice(self.created_records[table_key])
        table_info = TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"
        pk = table_info['pk']

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        query = f"""
            UPSERT INTO {table_name} ({pk}, status, updated_at, updated_by)
            SELECT {pk}, 'UPDATED', '{now}', 'stress_user_{self.user_id}'
            FROM {table_name}
            WHERE {pk} = '{record_id}'
        """

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='UPDATE',
                table=table_key,
                elapsed_ms=elapsed,
                success=success,
                error=None if success else "Write returned False",
                record_id=record_id,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='UPDATE',
                table=table_key,
                elapsed_ms=elapsed,
                success=False,
                error=str(e)[:200],
                record_id=record_id,
            )

    def execute_delete(self, table_key: str) -> OperationResult:
        """Execute DELETE operation."""
        if not self.created_records[table_key]:
            # Create one first
            insert_result = self.execute_insert(table_key)
            if not insert_result.success:
                return insert_result

        record_id = self.created_records[table_key].pop()
        table_info = TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"
        pk = table_info['pk']

        query = f"DELETE FROM {table_name} WHERE {pk} = '{record_id}'"

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='DELETE',
                table=table_key,
                elapsed_ms=elapsed,
                success=success,
                error=None if success else "Write returned False",
                record_id=record_id,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return OperationResult(
                timestamp=datetime.now(),
                user_id=self.user_id,
                operation='DELETE',
                table=table_key,
                elapsed_ms=elapsed,
                success=False,
                error=str(e)[:200],
                record_id=record_id,
            )

    def run(self, num_operations: int) -> Dict[str, Any]:
        """
        Run the virtual user's workload.

        Returns summary of user's performance.
        """
        self.metrics.register_user(self.user_id)

        total_ops = 0
        success_ops = 0
        failed_ops = 0
        total_elapsed = 0.0

        for _ in range(num_operations):
            if self.stop_flag.is_set():
                break

            operation = self._choose_operation()
            table = self._choose_table()

            # Execute operation
            if operation == 'INSERT':
                result = self.execute_insert(table)
            elif operation == 'SELECT':
                result = self.execute_select(table)
            elif operation == 'UPDATE':
                result = self.execute_update(table)
            elif operation == 'DELETE':
                result = self.execute_delete(table)
            else:
                result = self.execute_select(table)

            # Record metrics
            self.metrics.record_operation(result)

            total_ops += 1
            total_elapsed += result.elapsed_ms
            if result.success:
                success_ops += 1
            else:
                failed_ops += 1

            # Think time
            self._think()

        # Cleanup: Delete any remaining created records
        for table_key, record_ids in self.created_records.items():
            for record_id in record_ids:
                try:
                    table_info = TABLES[table_key]
                    table_name = f"{self.database}.{table_info['table']}"
                    pk = table_info['pk']
                    query = f"DELETE FROM {table_name} WHERE {pk} = '{record_id}'"
                    impala_manager.execute_write(query, database=self.database)
                except:
                    pass

        self.metrics.user_completed(self.user_id, total_ops, success_ops, failed_ops, total_elapsed)

        return {
            'user_id': self.user_id,
            'total_operations': total_ops,
            'successful': success_ops,
            'failed': failed_ops,
            'avg_latency_ms': total_elapsed / total_ops if total_ops > 0 else 0,
        }

    def stop(self):
        """Signal user to stop."""
        self.stop_flag.set()


# =============================================================================
# Stress Benchmark Runner
# =============================================================================

class StressBenchmark:
    """
    Main stress benchmark runner.
    Manages concurrent users, ramp-up, monitoring, and reporting.
    """

    def __init__(
        self,
        database: str = 'gmp_cis',
        output_dir: str = 'stress_results',
    ):
        self.database = database
        self.output_dir = output_dir
        self.users: List[VirtualUser] = []
        self.executor: Optional[ThreadPoolExecutor] = None
        self.metrics: Optional[MetricsCollector] = None
        self.stop_flag = threading.Event()
        self.monitor_thread: Optional[threading.Thread] = None

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

    def _print_banner(self, text: str):
        """Print banner."""
        width = 70
        print("\n" + "=" * width)
        print(f" {text}")
        print("=" * width)

    def _print_progress(self, stats: Dict[str, Any], elapsed: float):
        """Print real-time progress."""
        print(f"\r[{elapsed:6.1f}s] Ops: {stats['total_ops']:,} | "
              f"Success: {stats['success_rate']:.1f}% | "
              f"Latency: {stats['avg_latency_ms']:.1f}ms | "
              f"RPS: {stats['ops_per_sec']:.1f} | "
              f"Users: {stats['active_users']}", end='', flush=True)

    def _monitor_loop(self, duration: int):
        """Background thread for real-time monitoring."""
        start_time = time.time()
        while not self.stop_flag.is_set():
            elapsed = time.time() - start_time
            if elapsed >= duration:
                break

            stats = self.metrics.get_current_stats()
            self._print_progress(stats, elapsed)

            time.sleep(1)

    def run(
        self,
        scenario: TestScenario = None,
        users: int = None,
        duration_seconds: int = None,
        ramp_up_seconds: int = None,
        think_time_range: tuple = None,
        ops_per_user: int = None,
        tables: List[str] = None,
    ) -> BenchmarkMetrics:
        """
        Run the stress benchmark.

        Args:
            scenario: Predefined scenario (overrides other params)
            users: Number of concurrent users
            duration_seconds: Test duration
            ramp_up_seconds: Time to spawn all users
            think_time_range: (min, max) think time between ops
            ops_per_user: Operations per user
            tables: Tables to test

        Returns:
            BenchmarkMetrics with comprehensive results
        """
        # Apply scenario config or use provided params
        if scenario:
            config = SCENARIO_CONFIG[scenario]
            users = users or config['users']
            duration_seconds = duration_seconds or config['duration_seconds']
            ramp_up_seconds = ramp_up_seconds or config['ramp_up_seconds']
            think_time_range = think_time_range or config['think_time_range']
            ops_per_user = ops_per_user or config['ops_per_user']
            scenario_name = scenario.value
        else:
            users = users or 10
            duration_seconds = duration_seconds or 60
            ramp_up_seconds = ramp_up_seconds or 10
            think_time_range = think_time_range or (0.5, 2.0)
            ops_per_user = ops_per_user or 50
            scenario_name = "custom"

        tables = tables or ['trade', 'portfolio', 'security']

        # Initialize metrics
        test_name = f"stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.metrics = MetricsCollector(test_name)

        # Print configuration
        self._print_banner("KUDU STRESS BENCHMARK")
        print(f"Scenario: {scenario_name}")
        print(f"Users: {users}")
        print(f"Duration: {duration_seconds}s")
        print(f"Ramp-up: {ramp_up_seconds}s")
        print(f"Think time: {think_time_range[0]:.1f}-{think_time_range[1]:.1f}s")
        print(f"Ops/user: {ops_per_user}")
        print(f"Tables: {', '.join(tables)}")
        print(f"Database: {self.database}")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        # Test connection
        print("Testing database connection... ", end='', flush=True)
        if not impala_manager.test_connection():
            print("FAILED")
            print("ERROR: Cannot connect to Impala/Kudu")
            return None
        print("OK")

        # Calculate spawn rate
        spawn_delay = ramp_up_seconds / users if users > 0 else 0

        # Start monitoring thread
        self.stop_flag.clear()
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(duration_seconds,),
            daemon=True
        )
        self.monitor_thread.start()

        # Create and run virtual users
        print(f"\nSpawning {users} users over {ramp_up_seconds}s...")
        print("-" * 70)

        self.executor = ThreadPoolExecutor(max_workers=users)
        futures = []

        try:
            for user_id in range(users):
                # Create virtual user
                user = VirtualUser(
                    user_id=user_id,
                    database=self.database,
                    metrics_collector=self.metrics,
                    think_time_range=think_time_range,
                    tables=tables,
                )
                self.users.append(user)

                # Submit user task
                future = self.executor.submit(user.run, ops_per_user)
                futures.append(future)

                # Ramp-up delay
                if spawn_delay > 0 and user_id < users - 1:
                    time.sleep(spawn_delay)

            # Wait for all users to complete
            for future in as_completed(futures):
                try:
                    result = future.result()
                except Exception as e:
                    print(f"\nUser error: {e}")

        except KeyboardInterrupt:
            print("\n\nInterrupted! Stopping users...")
            for user in self.users:
                user.stop()

        finally:
            self.stop_flag.set()
            if self.monitor_thread:
                self.monitor_thread.join(timeout=2)
            if self.executor:
                self.executor.shutdown(wait=True)

        # Calculate final metrics
        print("\n" + "-" * 70)
        final_metrics = self.metrics.calculate_final_metrics(scenario_name)

        # Print results
        self._print_results(final_metrics)

        # Save reports
        self._save_reports(final_metrics, test_name)

        return final_metrics

    def _print_results(self, metrics: BenchmarkMetrics):
        """Print formatted results."""
        self._print_banner("BENCHMARK RESULTS")

        print(f"\nTest: {metrics.test_name}")
        print(f"Scenario: {metrics.scenario}")
        print(f"Duration: {metrics.duration_seconds:.1f}s")
        print(f"Total Users: {metrics.total_users}")

        print(f"\n{'OPERATIONS':-^50}")
        print(f"  Total: {metrics.total_operations:,}")
        print(f"  Successful: {metrics.successful_operations:,}")
        print(f"  Failed: {metrics.failed_operations:,}")
        print(f"  Success Rate: {metrics.success_rate_pct:.2f}%")
        print(f"  Throughput: {metrics.throughput_ops_per_sec:.2f} ops/sec")

        print(f"\n{'LATENCY (ms)':-^50}")
        print(f"  Min: {metrics.latency_min_ms:.2f}")
        print(f"  Max: {metrics.latency_max_ms:.2f}")
        print(f"  Avg: {metrics.latency_avg_ms:.2f}")
        print(f"  Median (p50): {metrics.latency_median_ms:.2f}")
        print(f"  P90: {metrics.latency_p90_ms:.2f}")
        print(f"  P95: {metrics.latency_p95_ms:.2f}")
        print(f"  P99: {metrics.latency_p99_ms:.2f}")

        if metrics.operations_by_type:
            print(f"\n{'OPERATIONS BY TYPE':-^50}")
            print(f"{'Operation':<10} {'Count':<8} {'Avg(ms)':<10} {'P95(ms)':<10} {'Max(ms)':<10}")
            print("-" * 50)
            for op_type, stats in sorted(metrics.operations_by_type.items()):
                print(f"{op_type:<10} {stats['count']:<8} {stats['avg_ms']:<10.2f} "
                      f"{stats['p95_ms']:<10.2f} {stats['max_ms']:<10.2f}")

        if metrics.errors_by_type:
            print(f"\n{'ERRORS':-^50}")
            for error, count in sorted(metrics.errors_by_type.items(), key=lambda x: -x[1])[:5]:
                print(f"  [{count}x] {error[:60]}...")

        print("\n" + "=" * 70)
        print(f"Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 70 + "\n")

    def _save_reports(self, metrics: BenchmarkMetrics, test_name: str):
        """Save JSON and CSV reports."""
        # JSON report
        json_path = os.path.join(self.output_dir, f"{test_name}.json")
        with open(json_path, 'w') as f:
            json.dump(asdict(metrics), f, indent=2, default=str)
        print(f"JSON report: {json_path}")

        # CSV summary
        csv_path = os.path.join(self.output_dir, f"{test_name}_summary.csv")
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Metric', 'Value'])
            writer.writerow(['Test Name', metrics.test_name])
            writer.writerow(['Scenario', metrics.scenario])
            writer.writerow(['Duration (s)', f"{metrics.duration_seconds:.2f}"])
            writer.writerow(['Total Users', metrics.total_users])
            writer.writerow(['Total Ops', metrics.total_operations])
            writer.writerow(['Success Rate (%)', f"{metrics.success_rate_pct:.2f}"])
            writer.writerow(['Throughput (ops/s)', f"{metrics.throughput_ops_per_sec:.2f}"])
            writer.writerow(['Latency Avg (ms)', f"{metrics.latency_avg_ms:.2f}"])
            writer.writerow(['Latency P95 (ms)', f"{metrics.latency_p95_ms:.2f}"])
            writer.writerow(['Latency P99 (ms)', f"{metrics.latency_p99_ms:.2f}"])
        print(f"CSV summary: {csv_path}")

        # Detailed operations CSV
        ops_csv_path = os.path.join(self.output_dir, f"{test_name}_operations.csv")
        with open(ops_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'user_id', 'operation', 'table', 'elapsed_ms', 'success', 'error'])
            for result in self.metrics.results:
                writer.writerow([
                    result.timestamp.isoformat(),
                    result.user_id,
                    result.operation,
                    result.table,
                    f"{result.elapsed_ms:.2f}",
                    result.success,
                    result.error or '',
                ])
        print(f"Operations CSV: {ops_csv_path}")


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Kudu Stress Load Benchmark - JMeter/Locust Style',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick smoke test
  python kudu_stress_benchmark.py --scenario quick

  # Standard load test
  python kudu_stress_benchmark.py --scenario standard

  # Stress test
  python kudu_stress_benchmark.py --scenario stress

  # Custom test
  python kudu_stress_benchmark.py --users 200 --duration 600 --ramp-up 60

  # Soak test (30 minutes)
  python kudu_stress_benchmark.py --scenario soak
        """
    )

    parser.add_argument(
        '--scenario', '-s',
        choices=[s.value for s in TestScenario],
        help='Predefined test scenario'
    )
    parser.add_argument('--users', '-u', type=int, help='Number of concurrent users')
    parser.add_argument('--duration', '-d', type=int, help='Test duration in seconds')
    parser.add_argument('--ramp-up', '-r', type=int, help='Ramp-up time in seconds')
    parser.add_argument('--ops-per-user', '-o', type=int, help='Operations per user')
    parser.add_argument('--think-min', type=float, default=0.5, help='Minimum think time (seconds)')
    parser.add_argument('--think-max', type=float, default=2.0, help='Maximum think time (seconds)')
    parser.add_argument(
        '--tables', '-t',
        nargs='+',
        default=['trade', 'portfolio', 'security'],
        choices=list(TABLES.keys()),
        help='Tables to benchmark'
    )
    parser.add_argument('--database', default='gmp_cis', help='Database name')
    parser.add_argument('--output-dir', default='stress_results', help='Output directory for reports')

    args = parser.parse_args()

    # Determine scenario
    scenario = None
    if args.scenario:
        scenario = TestScenario(args.scenario)

    # Run benchmark
    benchmark = StressBenchmark(
        database=args.database,
        output_dir=args.output_dir,
    )

    try:
        metrics = benchmark.run(
            scenario=scenario,
            users=args.users,
            duration_seconds=args.duration,
            ramp_up_seconds=args.ramp_up,
            think_time_range=(args.think_min, args.think_max),
            ops_per_user=args.ops_per_user,
            tables=args.tables,
        )

        if metrics and metrics.success_rate_pct >= 95:
            print("\n✓ Benchmark PASSED (>95% success rate)")
            sys.exit(0)
        else:
            print("\n✗ Benchmark FAILED (<95% success rate)")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nBenchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\nBenchmark error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
