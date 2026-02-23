#!/usr/bin/env python3
"""
Kudu Direct Database Benchmark
==============================

Tests actual Kudu/Impala INSERT, UPDATE, DELETE performance directly
without going through Django views - matching real user experience.

This measures the TRUE database operation time that users experience.

Usage:
    # Quick test (10 operations each)
    python scripts/kudu_benchmark.py --quick

    # Standard test (100 operations each)
    python scripts/kudu_benchmark.py

    # Full benchmark (500 operations each, concurrent users)
    python scripts/kudu_benchmark.py --full --users 10

    # Custom test
    python scripts/kudu_benchmark.py --operations 50 --users 5

Docker Setup:
    docker-compose up -d
    # Wait for Impala to be ready (~60 seconds)
    docker exec kudu-impala-new impala-shell -q "SELECT 1"

Author: CIS Trade Hive Team
Date: 2026-02-22
"""

import os
import sys
import time
import uuid
import argparse
import statistics
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from core.repositories.impala_connection import impala_manager


@dataclass
class BenchmarkResult:
    """Result of a single benchmark operation"""
    operation: str
    table: str
    success: bool
    elapsed_ms: float
    error: Optional[str] = None


@dataclass
class BenchmarkSummary:
    """Summary statistics for a benchmark"""
    operation: str
    table: str
    total_ops: int
    successful: int
    failed: int
    min_ms: float
    max_ms: float
    avg_ms: float
    median_ms: float
    p95_ms: float
    p99_ms: float
    ops_per_sec: float


class KuduBenchmark:
    """
    Direct Kudu/Impala database benchmark.

    Tests INSERT, UPDATE, DELETE, SELECT operations on actual Kudu tables.
    """

    # Test tables - using existing tables from cis_trade_hive
    # Schemas based on actual gmp_cis table definitions
    TABLES = {
        'portfolio': {
            'table': 'cis_portfolio',
            'pk': 'name',
            'insert_cols': [
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
            'insert_cols': [
                # Core trade fields from gmp_cis.cis_trade schema
                'trade_id', 'trade_type', 'deal_number', 'portfolio_short_name',
                'portfolio_full_name', 'security_label', 'security_full_name',
                'security_type', 'trade_status', 'trade_date', 'settle_date',
                'expiry_date', 'quantity', 'face_value', 'lot', 'price',
                'commission', 'accrued_interest', 'sec_fee', 'other_charges',
                'total_amount', 'open_close_position', 'extension', 'broker_name',
                'gl_fund_type', 'gl_cost_centre', 'gl_account_code', 'contract_ref',
                'fd_receipt', 'org_pur_date', 'open_fx_rate', 'curr_dealing',
                'open_dealing', 'input_tax_oth', 'qty_entitled', 'selling_rule',
                'cash_balance', 'custodian', 'amor_accr_method', 'lots_held',
                'quantity_held', 'remarks', 'udf_fund_type', 'udf_section_31_26',
                'udf_sub_custodian', 'udf_disclosure_req', 'udf_counter_pledged',
                'udf_revision_code', 'udf_uobn_uobn_hk', 'udf_income_exp_type',
                'udf_currency_hedge', 'parent_trade_id', 'realized_pnl',
                'delivery_type_id', 'counterparty', 'reduction_type',
                'reduction_amount', 'units_affected', 'income_type',
                'ex_date_date', 'record_date', 'pay_date', 'amount_per_unit',
                'gross_amount', 'withholding_tax', 'net_amount', 'split_type',
                'split_ratio_new', 'split_ratio_old', 'effective_date',
                'status', 'is_active', 'currency', 'entry_type', 'counterparty_type',
                'sub_trade_ref', 'ori_trade_ref', 'pnl_amount', 'tax_type',
                'rate_ratio_old', 'rate_ratio_new', 'src_system', 'si_status',
                'si_delayed', 'created_by', 'created_at', 'updated_by', 'updated_at',
                'deleted_by', 'deleted_at', 'approved_by', 'approved_at'
            ],
        },
        'security': {
            'table': 'cis_security',
            'pk': 'security_id',
            'insert_cols': [
                # Core security fields from gmp_cis.cis_security schema
                'security_id', 'security_name', 'isin', 'security_description',
                'security_type', 'industry', 'issuer_type', 'quoted_unquoted',
                'currency', 'country_of_incorporation', 'country_of_issue',
                'country_of_primary_exchange', 'country_code', 'beta_value',
                'beta_currency', 'par_value', 'pct_hkd_entity_1', 'pct_hkd_entity_2',
                'pct_hkd_entity_3', 'pct_hkd_entity_trigger', 'attr_s32_denom',
                'attr_pct_hld_by_fund', 'base_int_fund', 'base_fv_fund_type',
                'principal_currency', 'primary_risk_ccy', 'lot_size', 'put_call',
                'pct_hkd_entity_4_pct', 'datastream_id_10_pct', 'first_int_code',
                'fin_issuer_level', 'fx_scale_fund', 'last_int_date',
                'maturity_date', 'interest_rate_index', 'classification',
                'src_system', 'is_approved_sil', 'status', 'is_active',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ],
        },
        'udf_field': {
            'table': 'cis_udf_field',
            'pk': 'object_type',  # Composite key: object_type + field_name
            'insert_cols': [
                'object_type', 'field_name', 'field_value', 'is_active',
                'created_by', 'created_at', 'updated_by', 'updated_at'
            ],
        },
        'fx_rate': {
            'table': 'cis_fx_rate',
            'pk': 'rate_id',
            'insert_cols': [
                'rate_id', 'from_currency', 'to_currency', 'rate_date',
                'rate', 'source', 'created_at', 'created_by'
            ],
        },
        'equity_price': {
            'table': 'cis_equity_price',
            'pk': 'price_id',
            'insert_cols': [
                'price_id', 'security_id', 'security_code', 'price_date',
                'close_price', 'currency', 'source', 'created_at', 'created_by'
            ],
        },
    }

    def __init__(self, database: str = 'gmp_cis'):
        self.database = database
        self.results: List[BenchmarkResult] = []
        self._lock = threading.Lock()

    def _generate_test_data(self, table_key: str) -> Dict[str, Any]:
        """Generate test data for a table."""
        now = datetime.now()
        test_id = f"BENCH_{uuid.uuid4().hex[:12].upper()}"

        if table_key == 'portfolio':
            return {
                'name': test_id,
                'description': f'Benchmark Portfolio {test_id}',
                'currency': 'USD',
                'manager': 'Benchmark Test',
                'portfolio_client': 'BENCH_CLIENT',
                'cash_balance': '0',
                'cost_centre_code': 'CC001',
                'corp_code': 'CORP001',
                'account_group': 'AG001',
                'portfolio_group': 'PG001',
                'report_group': 'RG001',
                'entity_group': 'EG001',
                'revaluation_status': 'PENDING',
                'src_system': 'BENCHMARK',
                'status': 'DRAFT',
                'is_active': True,
                'created_by': 'benchmark',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': 'benchmark',
                'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            }
        elif table_key == 'trade':
            return {
                # Core fields
                'trade_id': test_id,
                'trade_type': 'BUY',
                'deal_number': f'DEAL_{test_id[-8:]}',
                'portfolio_short_name': 'BENCH_PF',
                'portfolio_full_name': 'Benchmark Portfolio',
                'security_label': 'BENCH_SEC',
                'security_full_name': 'Benchmark Security',
                'security_type': 'EQUITY',
                'trade_status': 'DRAFT',
                'trade_date': now.strftime('%Y-%m-%d'),
                'settle_date': (now + timedelta(days=2)).strftime('%Y-%m-%d'),
                'expiry_date': None,
                'quantity': 1000.0,
                'face_value': 100000.0,
                'lot': 1,
                'price': 100.50,
                'commission': 10.0,
                'accrued_interest': 0.0,
                'sec_fee': 5.0,
                'other_charges': 0.0,
                'total_amount': 100515.0,
                'open_close_position': 'OPEN',
                'extension': None,
                'broker_name': 'BENCH_BROKER',
                'gl_fund_type': 'EQUITY',
                'gl_cost_centre': 'CC001',
                'gl_account_code': 'ACC001',
                'contract_ref': f'CONTRACT_{test_id[-6:]}',
                'fd_receipt': None,
                'org_pur_date': now.strftime('%Y-%m-%d'),
                'open_fx_rate': 1.0,
                'curr_dealing': 'USD',
                'open_dealing': 100.50,
                'input_tax_oth': 0.0,
                'qty_entitled': 1000.0,
                'selling_rule': 'FIFO',
                'cash_balance': 0.0,
                'custodian': 'BENCH_CUSTODIAN',
                'amor_accr_method': 'STRAIGHT_LINE',
                'lots_held': 1,
                'quantity_held': 1000.0,
                'remarks': 'Benchmark test trade',
                'udf_fund_type': None,
                'udf_section_31_26': None,
                'udf_sub_custodian': None,
                'udf_disclosure_req': False,
                'udf_counter_pledged': False,
                'udf_revision_code': None,
                'udf_uobn_uobn_hk': None,
                'udf_income_exp_type': None,
                'udf_currency_hedge': False,
                'parent_trade_id': None,
                'realized_pnl': 0.0,
                'delivery_type_id': 'DVP',
                'counterparty': 'BENCH_COUNTERPARTY',
                'reduction_type': None,
                'reduction_amount': 0.0,
                'units_affected': 0,
                'income_type': None,
                'ex_date_date': None,
                'record_date': None,
                'pay_date': None,
                'amount_per_unit': 100.50,
                'gross_amount': 100500.0,
                'withholding_tax': 0.0,
                'net_amount': 100500.0,
                'split_type': None,
                'split_ratio_new': 1,
                'split_ratio_old': 1,
                'effective_date': now.strftime('%Y-%m-%d'),
                'status': 'DRAFT',
                'is_active': True,
                'currency': 'USD',
                'entry_type': 'MANUAL',
                'counterparty_type': 'BROKER',
                'sub_trade_ref': None,
                'ori_trade_ref': None,
                'pnl_amount': 0.0,
                'tax_type': None,
                'rate_ratio_old': 1.0,
                'rate_ratio_new': 1.0,
                'src_system': 'BENCHMARK',
                'si_status': 'PENDING',
                'si_delayed': False,
                'created_by': 'benchmark',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': 'benchmark',
                'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'deleted_by': None,
                'deleted_at': None,
                'approved_by': None,
                'approved_at': None,
            }
        elif table_key == 'security':
            return {
                # Core fields
                'security_id': test_id,
                'security_name': f'Benchmark Security {test_id}',
                'isin': f'US{test_id[-10:]}',
                'security_description': f'Benchmark Security Description {test_id}',
                'security_type': 'EQUITY',
                'industry': 'TECHNOLOGY',
                'issuer_type': 'CORPORATE',
                'quoted_unquoted': 'QUOTED',
                'currency': 'USD',
                'country_of_incorporation': 'US',
                'country_of_issue': 'US',
                'country_of_primary_exchange': 'US',
                'country_code': 'USA',
                'beta_value': 1.0,
                'beta_currency': 'USD',
                'par_value': 1.0,
                'pct_hkd_entity_1': 0.0,
                'pct_hkd_entity_2': 0.0,
                'pct_hkd_entity_3': 0.0,
                'pct_hkd_entity_trigger': 0.0,
                'attr_s32_denom': None,
                'attr_pct_hld_by_fund': 0.0,
                'base_int_fund': None,
                'base_fv_fund_type': None,
                'principal_currency': 'USD',
                'primary_risk_ccy': 'USD',
                'lot_size': 100,
                'put_call': None,
                'pct_hkd_entity_4_pct': 0.0,
                'datastream_id_10_pct': None,
                'first_int_code': None,
                'fin_issuer_level': None,
                'fx_scale_fund': 1.0,
                'last_int_date': None,
                'maturity_date': None,
                'interest_rate_index': None,
                'classification': 'COMMON_STOCK',
                'src_system': 'BENCHMARK',
                'is_approved_sil': False,
                'status': 'ACTIVE',
                'is_active': True,
                'created_by': 'benchmark',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': 'benchmark',
                'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            }
        elif table_key == 'udf_field':
            return {
                'object_type': f'TRADE_{test_id[-8:]}',
                'field_name': f'custom_field_{test_id[-6:]}',
                'field_value': f'Value for {test_id}',
                'is_active': True,
                'created_by': 'benchmark',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'updated_by': 'benchmark',
                'updated_at': now.strftime('%Y-%m-%d %H:%M:%S'),
            }
        elif table_key == 'fx_rate':
            return {
                'rate_id': test_id,
                'from_currency': 'USD',
                'to_currency': 'EUR',
                'rate_date': now.strftime('%Y-%m-%d'),
                'rate': 0.92,
                'source': 'BENCHMARK',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': 'benchmark',
            }
        elif table_key == 'equity_price':
            return {
                'price_id': test_id,
                'security_id': 'BENCH_SECURITY',
                'security_code': 'BENCH',
                'price_date': now.strftime('%Y-%m-%d'),
                'close_price': 150.75,
                'currency': 'USD',
                'source': 'BENCHMARK',
                'created_at': now.strftime('%Y-%m-%d %H:%M:%S'),
                'created_by': 'benchmark',
            }
        else:
            raise ValueError(f"Unknown table key: {table_key}")

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

    def _add_result(self, result: BenchmarkResult):
        """Thread-safe add result."""
        with self._lock:
            self.results.append(result)

    def benchmark_insert(self, table_key: str) -> BenchmarkResult:
        """Benchmark single INSERT operation."""
        table_info = self.TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"
        data = self._generate_test_data(table_key)

        # Build INSERT query
        columns = table_info['insert_cols']
        values = [self._format_value(data.get(col)) for col in columns]

        # Use UPSERT for Kudu tables
        query = f"""
            UPSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(values)})
        """

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            result = BenchmarkResult(
                operation='INSERT',
                table=table_key,
                success=success,
                elapsed_ms=elapsed,
                error=None if success else "Write returned False"
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            result = BenchmarkResult(
                operation='INSERT',
                table=table_key,
                success=False,
                elapsed_ms=elapsed,
                error=str(e)
            )

        self._add_result(result)
        return result

    def benchmark_update(self, table_key: str, record_id: str) -> BenchmarkResult:
        """Benchmark single UPDATE operation."""
        table_info = self.TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"
        pk = table_info['pk']

        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Use UPSERT for Kudu (Kudu doesn't support UPDATE directly via Impala)
        # We need to read, modify, write back
        query = f"""
            UPSERT INTO {table_name} ({pk}, status, updated_at, updated_by)
            SELECT {pk}, 'UPDATED', '{now}', 'benchmark'
            FROM {table_name}
            WHERE {pk} = '{record_id}'
        """

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            result = BenchmarkResult(
                operation='UPDATE',
                table=table_key,
                success=success,
                elapsed_ms=elapsed,
                error=None if success else "Write returned False"
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            result = BenchmarkResult(
                operation='UPDATE',
                table=table_key,
                success=False,
                elapsed_ms=elapsed,
                error=str(e)
            )

        self._add_result(result)
        return result

    def benchmark_delete(self, table_key: str, record_id: str) -> BenchmarkResult:
        """Benchmark single DELETE operation."""
        table_info = self.TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"
        pk = table_info['pk']

        query = f"DELETE FROM {table_name} WHERE {pk} = '{record_id}'"

        start = time.perf_counter()
        try:
            success = impala_manager.execute_write(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            result = BenchmarkResult(
                operation='DELETE',
                table=table_key,
                success=success,
                elapsed_ms=elapsed,
                error=None if success else "Write returned False"
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            result = BenchmarkResult(
                operation='DELETE',
                table=table_key,
                success=False,
                elapsed_ms=elapsed,
                error=str(e)
            )

        self._add_result(result)
        return result

    def benchmark_select(self, table_key: str, limit: int = 100) -> BenchmarkResult:
        """Benchmark SELECT operation."""
        table_info = self.TABLES[table_key]
        table_name = f"{self.database}.{table_info['table']}"

        query = f"SELECT * FROM {table_name} LIMIT {limit}"

        start = time.perf_counter()
        try:
            results = impala_manager.execute_query(query, database=self.database)
            elapsed = (time.perf_counter() - start) * 1000

            result = BenchmarkResult(
                operation='SELECT',
                table=table_key,
                success=True,
                elapsed_ms=elapsed,
                error=None
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            result = BenchmarkResult(
                operation='SELECT',
                table=table_key,
                success=False,
                elapsed_ms=elapsed,
                error=str(e)
            )

        self._add_result(result)
        return result

    def run_crud_cycle(self, table_key: str) -> List[BenchmarkResult]:
        """Run a full CRUD cycle: INSERT -> SELECT -> UPDATE -> DELETE."""
        results = []

        # INSERT
        insert_result = self.benchmark_insert(table_key)
        results.append(insert_result)

        if not insert_result.success:
            return results

        # Extract the ID we just inserted
        data = self._generate_test_data(table_key)
        record_id = data[self.TABLES[table_key]['pk']]

        # SELECT (read it back)
        select_result = self.benchmark_select(table_key, limit=1)
        results.append(select_result)

        # UPDATE
        update_result = self.benchmark_update(table_key, record_id)
        results.append(update_result)

        # DELETE (cleanup)
        delete_result = self.benchmark_delete(table_key, record_id)
        results.append(delete_result)

        return results

    def run_benchmark(self, operations: int, tables: List[str], concurrent_users: int = 1) -> Dict[str, BenchmarkSummary]:
        """
        Run full benchmark.

        Args:
            operations: Number of operations per table per operation type
            tables: List of table keys to test
            concurrent_users: Number of concurrent users to simulate
        """
        print(f"\n{'='*70}")
        print("KUDU DIRECT DATABASE BENCHMARK")
        print(f"{'='*70}")
        print(f"Operations per type: {operations}")
        print(f"Tables: {', '.join(tables)}")
        print(f"Concurrent users: {concurrent_users}")
        print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        self.results = []  # Reset results

        # Test connection first
        print("Testing Impala connection...")
        if not impala_manager.test_connection():
            print("ERROR: Cannot connect to Impala. Make sure Docker is running:")
            print("  docker-compose up -d")
            print("  docker exec kudu-impala-new impala-shell -q 'SELECT 1'")
            return {}
        print("Connection OK\n")

        # Run benchmarks
        for table_key in tables:
            print(f"\n--- Benchmarking {table_key.upper()} table ---")

            # INSERT benchmark
            print(f"  INSERT ({operations} ops, {concurrent_users} users)... ", end='', flush=True)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [executor.submit(self.benchmark_insert, table_key) for _ in range(operations)]
                for f in as_completed(futures):
                    pass  # Wait for all
            elapsed = time.perf_counter() - start
            insert_results = [r for r in self.results if r.operation == 'INSERT' and r.table == table_key]
            success_count = sum(1 for r in insert_results if r.success)
            print(f"{success_count}/{operations} OK, {elapsed:.2f}s total")

            # Collect IDs for UPDATE/DELETE
            test_ids = [f"BENCH_{uuid.uuid4().hex[:12].upper()}" for _ in range(operations)]

            # INSERT records for UPDATE/DELETE tests
            print(f"  Preparing data for UPDATE/DELETE tests... ", end='', flush=True)
            prep_start = time.perf_counter()
            for test_id in test_ids:
                data = self._generate_test_data(table_key)
                pk_col = self.TABLES[table_key]['pk']
                data[pk_col] = test_id
                columns = self.TABLES[table_key]['insert_cols']
                values = [self._format_value(data.get(col)) for col in columns]
                table_name = f"{self.database}.{self.TABLES[table_key]['table']}"
                query = f"UPSERT INTO {table_name} ({', '.join(columns)}) VALUES ({', '.join(values)})"
                impala_manager.execute_write(query, database=self.database)
            print(f"done ({time.perf_counter() - prep_start:.2f}s)")

            # UPDATE benchmark
            print(f"  UPDATE ({operations} ops, {concurrent_users} users)... ", end='', flush=True)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [executor.submit(self.benchmark_update, table_key, test_id) for test_id in test_ids]
                for f in as_completed(futures):
                    pass
            elapsed = time.perf_counter() - start
            update_results = [r for r in self.results if r.operation == 'UPDATE' and r.table == table_key]
            success_count = sum(1 for r in update_results if r.success)
            print(f"{success_count}/{operations} OK, {elapsed:.2f}s total")

            # SELECT benchmark
            print(f"  SELECT ({operations} ops, {concurrent_users} users)... ", end='', flush=True)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [executor.submit(self.benchmark_select, table_key) for _ in range(operations)]
                for f in as_completed(futures):
                    pass
            elapsed = time.perf_counter() - start
            select_results = [r for r in self.results if r.operation == 'SELECT' and r.table == table_key]
            success_count = sum(1 for r in select_results if r.success)
            print(f"{success_count}/{operations} OK, {elapsed:.2f}s total")

            # DELETE benchmark (cleanup)
            print(f"  DELETE ({operations} ops, {concurrent_users} users)... ", end='', flush=True)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrent_users) as executor:
                futures = [executor.submit(self.benchmark_delete, table_key, test_id) for test_id in test_ids]
                for f in as_completed(futures):
                    pass
            elapsed = time.perf_counter() - start
            delete_results = [r for r in self.results if r.operation == 'DELETE' and r.table == table_key]
            success_count = sum(1 for r in delete_results if r.success)
            print(f"{success_count}/{operations} OK, {elapsed:.2f}s total")

        # Calculate summaries
        summaries = self._calculate_summaries()

        # Print results
        self._print_results(summaries)

        return summaries

    def _calculate_summaries(self) -> Dict[str, BenchmarkSummary]:
        """Calculate summary statistics for each operation/table combination."""
        summaries = {}

        # Group results by operation and table
        groups = {}
        for result in self.results:
            key = f"{result.operation}_{result.table}"
            if key not in groups:
                groups[key] = []
            groups[key].append(result)

        for key, results in groups.items():
            operation, table = key.split('_', 1)

            successful = [r for r in results if r.success]
            failed = [r for r in results if not r.success]

            if successful:
                times = [r.elapsed_ms for r in successful]
                sorted_times = sorted(times)

                summary = BenchmarkSummary(
                    operation=operation,
                    table=table,
                    total_ops=len(results),
                    successful=len(successful),
                    failed=len(failed),
                    min_ms=min(times),
                    max_ms=max(times),
                    avg_ms=statistics.mean(times),
                    median_ms=statistics.median(times),
                    p95_ms=sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 1 else sorted_times[0],
                    p99_ms=sorted_times[int(len(sorted_times) * 0.99)] if len(sorted_times) > 1 else sorted_times[0],
                    ops_per_sec=len(successful) / (sum(times) / 1000) if sum(times) > 0 else 0,
                )
            else:
                summary = BenchmarkSummary(
                    operation=operation,
                    table=table,
                    total_ops=len(results),
                    successful=0,
                    failed=len(failed),
                    min_ms=0, max_ms=0, avg_ms=0, median_ms=0, p95_ms=0, p99_ms=0, ops_per_sec=0,
                )

            summaries[key] = summary

        return summaries

    def _print_results(self, summaries: Dict[str, BenchmarkSummary]):
        """Print formatted benchmark results."""
        print(f"\n{'='*90}")
        print("BENCHMARK RESULTS")
        print(f"{'='*90}")

        # Header
        print(f"\n{'Operation':<10} {'Table':<15} {'Total':<6} {'OK':<6} {'Fail':<6} "
              f"{'Min':<8} {'Avg':<8} {'Median':<8} {'P95':<8} {'Max':<8} {'Ops/s':<8}")
        print("-" * 90)

        # Sort by operation then table
        for key in sorted(summaries.keys()):
            s = summaries[key]
            print(f"{s.operation:<10} {s.table:<15} {s.total_ops:<6} {s.successful:<6} {s.failed:<6} "
                  f"{s.min_ms:<8.1f} {s.avg_ms:<8.1f} {s.median_ms:<8.1f} {s.p95_ms:<8.1f} "
                  f"{s.max_ms:<8.1f} {s.ops_per_sec:<8.1f}")

        print("-" * 90)

        # Aggregate by operation
        print("\nAGGREGATED BY OPERATION:")
        print(f"{'Operation':<10} {'Total':<8} {'Success':<8} {'Avg ms':<10} {'P95 ms':<10} {'Ops/sec':<10}")
        print("-" * 60)

        ops_aggregated = {}
        for s in summaries.values():
            if s.operation not in ops_aggregated:
                ops_aggregated[s.operation] = {'total': 0, 'success': 0, 'times': [], 'elapsed': 0}
            ops_aggregated[s.operation]['total'] += s.total_ops
            ops_aggregated[s.operation]['success'] += s.successful
            if s.successful > 0:
                # Approximate total time
                ops_aggregated[s.operation]['times'].extend([s.avg_ms] * s.successful)

        for op, data in sorted(ops_aggregated.items()):
            if data['times']:
                avg = statistics.mean(data['times'])
                sorted_times = sorted(data['times'])
                p95 = sorted_times[int(len(sorted_times) * 0.95)] if len(sorted_times) > 1 else sorted_times[0]
                ops_sec = data['success'] / (sum(data['times']) / 1000) if sum(data['times']) > 0 else 0
            else:
                avg = p95 = ops_sec = 0

            print(f"{op:<10} {data['total']:<8} {data['success']:<8} {avg:<10.1f} {p95:<10.1f} {ops_sec:<10.1f}")

        # Print errors if any
        errors = [r for r in self.results if r.error]
        if errors:
            print(f"\n{'='*90}")
            print("ERRORS:")
            print(f"{'='*90}")
            for e in errors[:10]:  # Show first 10 errors
                print(f"  [{e.operation}] {e.table}: {e.error}")
            if len(errors) > 10:
                print(f"  ... and {len(errors) - 10} more errors")

        print(f"\n{'='*90}")
        print(f"Benchmark completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*90}\n")


def main():
    parser = argparse.ArgumentParser(description='Kudu Direct Database Benchmark')
    parser.add_argument('--quick', action='store_true', help='Quick test (10 operations)')
    parser.add_argument('--full', action='store_true', help='Full benchmark (500 operations)')
    parser.add_argument('--operations', '-n', type=int, default=100, help='Number of operations per type')
    parser.add_argument('--users', '-u', type=int, default=1, help='Number of concurrent users')
    parser.add_argument('--tables', '-t', nargs='+', default=['portfolio', 'trade', 'security', 'udf_field'],
                       help='Tables to benchmark')
    parser.add_argument('--database', '-d', default='gmp_cis', help='Database name')

    args = parser.parse_args()

    # Determine operation count
    if args.quick:
        operations = 10
        users = 1
    elif args.full:
        operations = 500
        users = args.users if args.users > 1 else 10
    else:
        operations = args.operations
        users = args.users

    # Run benchmark
    benchmark = KuduBenchmark(database=args.database)
    benchmark.run_benchmark(
        operations=operations,
        tables=args.tables,
        concurrent_users=users
    )


if __name__ == '__main__':
    main()
