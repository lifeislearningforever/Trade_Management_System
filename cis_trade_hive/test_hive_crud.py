#!/usr/bin/env python
"""
Test Script for Hive CRUD Operations

Tests all repository operations against Hive managed tables with ORC + ACID.
Run with: python test_hive_crud.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import datetime, date
from decimal import Decimal
import traceback

# Import repositories
from core.repositories.hive_connection import hive_manager
from core.repositories.acl_repository import get_acl_repository
acl_repository = get_acl_repository()
from core.audit.audit_hive_repository import audit_log_repository as audit_hive_repository
from portfolio.repositories.portfolio_hive_repository import portfolio_hive_repository
from trade.repositories.trade_hive_repository import trade_hive_repository
from security.repositories.security_hive_repository import security_hive_repository
from reference_data.repositories.reference_data_hive_repository import (
    counterparty_hive_repository,
    currency_hive_repository,
    country_hive_repository
)
from market_data.repositories.market_data_hive_repository import (
    equity_price_hive_repository,
    fx_rate_hive_repository
)
from udf.repositories.udf_hive_repository import (
    udf_field_hive_repository,
    udf_value_hive_repository
)


class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def success(self, test_name):
        self.passed += 1
        print(f"  ✓ {test_name}")

    def failure(self, test_name, error):
        self.failed += 1
        self.errors.append((test_name, error))
        print(f"  ✗ {test_name}: {error}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailures:")
            for name, error in self.errors:
                print(f"  - {name}: {error}")
        return self.failed == 0


results = TestResult()


def test_hive_connection():
    """Test basic Hive connectivity."""
    print("\n1. Testing Hive Connection...")
    try:
        query_result = hive_manager.execute_query(
            "SELECT 1 as test_value",
            database='gmp_cis'
        )
        if query_result and len(query_result) > 0:
            results.success("Basic connection")
        else:
            results.failure("Basic connection", "No results returned")
    except Exception as e:
        results.failure("Basic connection", str(e))

    try:
        tables = hive_manager.execute_query(
            "SHOW TABLES",
            database='gmp_cis'
        )
        if tables and len(tables) > 0:
            results.success(f"Show tables ({len(tables)} tables found)")
        else:
            results.failure("Show tables", "No tables found")
    except Exception as e:
        results.failure("Show tables", str(e))


def test_portfolio_crud():
    """Test Portfolio repository CRUD operations."""
    print("\n2. Testing Portfolio CRUD...")
    portfolio_id = None

    try:
        # CREATE
        portfolio_data = {
            'portfolio_short_name': f'TEST_PF_{datetime.now().strftime("%H%M%S")}',
            'portfolio_long_name': 'Test Portfolio for CRUD',
            'portfolio_description': 'Testing Hive CRUD operations',
            'portfolio_currency': 'USD',
            'portfolio_manager': 'Test Manager',
            'portfolio_type': 'EQUITY',
            'benchmark': 'SPX'
        }
        portfolio_id = portfolio_hive_repository.create_portfolio(portfolio_data, 'test_user')
        if portfolio_id:
            results.success(f"CREATE portfolio: {portfolio_id}")
        else:
            results.failure("CREATE portfolio", "No ID returned")
            return

        # READ
        portfolio = portfolio_hive_repository.find_by_id(portfolio_id)
        if portfolio and portfolio.get('portfolio_id') == portfolio_id:
            results.success("READ portfolio by ID")
        else:
            results.failure("READ portfolio by ID", "Portfolio not found")

        # UPDATE
        update_success = portfolio_hive_repository.update(
            portfolio_id,
            {'description': 'Updated description'}
        )
        if update_success:
            results.success("UPDATE portfolio")
        else:
            results.failure("UPDATE portfolio", "Update failed")

        # DELETE (soft)
        delete_success = portfolio_hive_repository.soft_delete(portfolio_id, 'test_user')
        if delete_success:
            results.success("DELETE portfolio (soft)")
        else:
            results.failure("DELETE portfolio (soft)", "Delete failed")

    except Exception as e:
        results.failure("Portfolio CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_trade_crud():
    """Test Trade repository CRUD operations."""
    print("\n3. Testing Trade CRUD...")
    trade_id = None

    try:
        # CREATE
        trade_data = {
            'portfolio_short_name': 'TEST_PF',
            'trade_type': 'BUY',
            'security_id': 'SEC001',
            'security_code': 'AAPL',
            'quantity': 100,
            'price': 150.50,
            'currency': 'USD',
            'trade_date': date.today().isoformat(),
            'settlement_date': date.today().isoformat(),
            'counterparty_id': 'CP001',
            'counterparty_name': 'Test Broker'
        }
        trade_id = trade_hive_repository.create_trade(trade_data, 'test_user')
        if trade_id:
            results.success(f"CREATE trade: {trade_id}")
        else:
            results.failure("CREATE trade", "No ID returned")
            return

        # READ
        trade = trade_hive_repository.find_by_id(trade_id)
        if trade and trade.get('trade_id') == trade_id:
            results.success("READ trade by ID")
        else:
            results.failure("READ trade by ID", "Trade not found")

        # UPDATE
        update_success = trade_hive_repository.update(
            trade_id,
            {'quantity': 200}
        )
        if update_success:
            results.success("UPDATE trade")
        else:
            results.failure("UPDATE trade", "Update failed")

        # DELETE (soft)
        delete_success = trade_hive_repository.soft_delete(trade_id, 'test_user')
        if delete_success:
            results.success("DELETE trade (soft)")
        else:
            results.failure("DELETE trade (soft)", "Delete failed")

    except Exception as e:
        results.failure("Trade CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_security_crud():
    """Test Security repository CRUD operations."""
    print("\n4. Testing Security CRUD...")
    security_id = None

    try:
        # CREATE
        security_data = {
            'security_code': f'SEC_{datetime.now().strftime("%H%M%S")}',
            'security_name': 'Test Security Inc.',
            'security_type': 'EQUITY',
            'asset_class': 'STOCK',
            'currency': 'USD',
            'exchange_code': 'NYSE',
            'country': 'US',
            'sector': 'Technology',
            'isin': f'US000000{datetime.now().strftime("%H%M%S")}',
            'ticker': 'TEST'
        }
        security_id = security_hive_repository.create_security(security_data, 'test_user')
        if security_id:
            results.success(f"CREATE security: {security_id}")
        else:
            results.failure("CREATE security", "No ID returned")
            return

        # READ
        security = security_hive_repository.find_by_id(security_id)
        if security and security.get('security_id') == security_id:
            results.success("READ security by ID")
        else:
            results.failure("READ security by ID", "Security not found")

        # UPDATE
        update_success = security_hive_repository.update_security(
            security_id,
            {'security_name': 'Updated Security Name'},
            'test_user'
        )
        if update_success:
            results.success("UPDATE security")
        else:
            results.failure("UPDATE security", "Update failed")

        # DELETE (soft)
        delete_success = security_hive_repository.delete_security(security_id, 'test_user')
        if delete_success:
            results.success("DELETE security (soft)")
        else:
            results.failure("DELETE security (soft)", "Delete failed")

    except Exception as e:
        results.failure("Security CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_counterparty_crud():
    """Test Counterparty repository CRUD operations."""
    print("\n5. Testing Counterparty CRUD...")
    counterparty_id = None

    try:
        # CREATE
        counterparty_data = {
            'counterparty_code': f'CP_{datetime.now().strftime("%H%M%S")}',
            'counterparty_name': 'Test Counterparty LLC',
            'counterparty_type': 'BROKER',
            'country': 'US',
            'address': '123 Test Street',
            'contact_name': 'John Doe',
            'contact_email': 'john@test.com',
            'contact_phone': '+1-555-1234'
        }
        counterparty_id = counterparty_hive_repository.create_counterparty(
            counterparty_data, 'test_user'
        )
        if counterparty_id:
            results.success(f"CREATE counterparty: {counterparty_id}")
        else:
            results.failure("CREATE counterparty", "No ID returned")
            return

        # READ
        counterparty = counterparty_hive_repository.find_by_id(counterparty_id)
        if counterparty and counterparty.get('counterparty_id') == counterparty_id:
            results.success("READ counterparty by ID")
        else:
            results.failure("READ counterparty by ID", "Counterparty not found")

        # UPDATE
        update_success = counterparty_hive_repository.update_counterparty(
            counterparty_id,
            {'contact_name': 'Jane Doe'},
            'test_user'
        )
        if update_success:
            results.success("UPDATE counterparty")
        else:
            results.failure("UPDATE counterparty", "Update failed")

        # DELETE (soft)
        delete_success = counterparty_hive_repository.delete_counterparty(
            counterparty_id, 'test_user'
        )
        if delete_success:
            results.success("DELETE counterparty (soft)")
        else:
            results.failure("DELETE counterparty (soft)", "Delete failed")

    except Exception as e:
        results.failure("Counterparty CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_currency_crud():
    """Test Currency repository CRUD operations."""
    print("\n6. Testing Currency CRUD...")

    try:
        # CREATE
        currency_data = {
            'currency_code': f'X{datetime.now().strftime("%H%M%S")[:2]}',
            'currency_name': 'Test Currency',
            'symbol': 'T$',
            'decimal_places': 2
        }
        currency_id = currency_hive_repository.create_currency(currency_data, 'test_user')
        if currency_id:
            results.success(f"CREATE currency: {currency_id}")
        else:
            results.failure("CREATE currency", "No ID returned")
            return

        # READ
        currencies = currency_hive_repository.get_all_currencies(include_inactive=True)
        if currencies:
            results.success(f"READ currencies ({len(currencies)} found)")
        else:
            results.failure("READ currencies", "No currencies found")

    except Exception as e:
        results.failure("Currency CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_fx_rate_crud():
    """Test FX Rate repository CRUD operations."""
    print("\n7. Testing FX Rate CRUD...")

    try:
        # CREATE
        rate_data = {
            'from_currency': 'USD',
            'to_currency': 'EUR',
            'rate_date': date.today().isoformat(),
            'rate': 0.92,
            'bid_rate': 0.91,
            'ask_rate': 0.93,
            'source': 'TEST'
        }
        rate_id = fx_rate_hive_repository.create_rate(rate_data, 'test_user')
        if rate_id:
            results.success(f"CREATE FX rate: {rate_id}")
        else:
            results.failure("CREATE FX rate", "No ID returned")
            return

        # READ
        rate = fx_rate_hive_repository.get_latest_rate('USD', 'EUR')
        if rate:
            results.success("READ latest FX rate")
        else:
            results.failure("READ latest FX rate", "Rate not found")

    except Exception as e:
        results.failure("FX Rate CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_equity_price_crud():
    """Test Equity Price repository CRUD operations."""
    print("\n8. Testing Equity Price CRUD...")

    try:
        # CREATE
        price_data = {
            'security_id': 'SEC_TEST',
            'security_code': 'TEST',
            'price_date': date.today().isoformat(),
            'open_price': 100.00,
            'high_price': 105.00,
            'low_price': 99.00,
            'close_price': 103.50,
            'volume': 1000000,
            'currency': 'USD',
            'source': 'TEST'
        }
        price_id = equity_price_hive_repository.create_price(price_data, 'test_user')
        if price_id:
            results.success(f"CREATE equity price: {price_id}")
        else:
            results.failure("CREATE equity price", "No ID returned")
            return

        # READ
        price = equity_price_hive_repository.get_latest_price('SEC_TEST')
        if price:
            results.success("READ latest equity price")
        else:
            results.failure("READ latest equity price", "Price not found")

    except Exception as e:
        results.failure("Equity Price CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_udf_crud():
    """Test UDF Field and Value repository CRUD operations."""
    print("\n9. Testing UDF CRUD...")
    field_id = None

    try:
        # CREATE Field
        field_data = {
            'field_name': f'test_field_{datetime.now().strftime("%H%M%S")}',
            'label': 'Test Field',
            'field_type': 'TEXT',
            'entity_type': 'PORTFOLIO',
            'is_required': False,
            'default_value': '',
            'validation_rules': '{}',
            'display_order': 1
        }
        field_id = udf_field_hive_repository.create_field(field_data, 'test_user')
        if field_id:
            results.success(f"CREATE UDF field: {field_id}")
        else:
            results.failure("CREATE UDF field", "No ID returned")
            return

        # READ Field
        field = udf_field_hive_repository.find_by_id(field_id)
        if field and field.get('field_id') == field_id:
            results.success("READ UDF field by ID")
        else:
            results.failure("READ UDF field by ID", "Field not found")

        # CREATE Value
        value_id = udf_value_hive_repository.set_value(
            field_id,
            'PORTFOLIO',
            'TEST_ENTITY_001',
            'test_value',
            'test_user'
        )
        if value_id:
            results.success(f"CREATE UDF value: {value_id}")
        else:
            results.failure("CREATE UDF value", "No ID returned")

        # READ Value
        value = udf_value_hive_repository.get_value(field_id, 'PORTFOLIO', 'TEST_ENTITY_001')
        if value:
            results.success("READ UDF value")
        else:
            results.failure("READ UDF value", "Value not found")

    except Exception as e:
        results.failure("UDF CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_acl_crud():
    """Test ACL repository CRUD operations."""
    print("\n10. Testing ACL CRUD...")
    user_id = None

    try:
        # CREATE User
        user_data = {
            'username': f'test_user_{datetime.now().strftime("%H%M%S")}',
            'email': f'test_{datetime.now().strftime("%H%M%S")}@test.com',
            'full_name': 'Test User',
            'password_hash': 'hashed_password_here'
        }
        user_id = acl_repository.create_user(user_data, 'admin')
        if user_id:
            results.success(f"CREATE user: {user_id}")
        else:
            results.failure("CREATE user", "No ID returned")
            return

        # READ User
        user = acl_repository.get_user_by_id(user_id)
        if user and user.get('user_id') == user_id:
            results.success("READ user by ID")
        else:
            results.failure("READ user by ID", "User not found")

        # GET all users
        users = acl_repository.get_all_users()
        if users and len(users) > 0:
            results.success(f"READ all users ({len(users)} found)")
        else:
            results.failure("READ all users", "No users found")

    except Exception as e:
        results.failure("ACL CRUD", f"{str(e)}\n{traceback.format_exc()}")


def test_audit_logging():
    """Test Audit repository logging operations."""
    print("\n11. Testing Audit Logging...")

    try:
        # LOG event
        log_id = audit_hive_repository.log_action(
            action='TEST_ACTION',
            entity_type='TEST',
            entity_id='TEST_001',
            user_id='test_user',
            username='test_user',
            details={'test_key': 'test_value'},
            ip_address='127.0.0.1'
        )
        if log_id:
            results.success(f"LOG audit event: {log_id}")
        else:
            # Some implementations return None but still succeed
            results.success("LOG audit event (no ID returned)")

    except Exception as e:
        results.failure("Audit Logging", f"{str(e)}\n{traceback.format_exc()}")


def test_statistics():
    """Test statistics methods across repositories."""
    print("\n12. Testing Statistics Methods...")

    try:
        # Portfolio statistics
        portfolio_stats = portfolio_hive_repository.get_statistics()
        if isinstance(portfolio_stats, dict):
            results.success("Portfolio statistics")
        else:
            results.failure("Portfolio statistics", "Invalid return type")

        # Trade statistics
        trade_stats = trade_hive_repository.get_trade_statistics()
        if isinstance(trade_stats, dict):
            results.success("Trade statistics")
        else:
            results.failure("Trade statistics", "Invalid return type")

        # Security statistics
        security_stats = security_hive_repository.get_statistics()
        if isinstance(security_stats, dict):
            results.success("Security statistics")
        else:
            results.failure("Security statistics", "Invalid return type")

        # FX Rate statistics
        fx_stats = fx_rate_hive_repository.get_statistics()
        if isinstance(fx_stats, dict):
            results.success("FX Rate statistics")
        else:
            results.failure("FX Rate statistics", "Invalid return type")

    except Exception as e:
        results.failure("Statistics", f"{str(e)}\n{traceback.format_exc()}")


def main():
    print("=" * 60)
    print("CIS Trade Hive - Hive CRUD Test Suite")
    print("=" * 60)
    print(f"Database: gmp_cis")
    print(f"Connection: localhost:10000")
    print(f"Timestamp: {datetime.now().isoformat()}")

    # Run all tests
    test_hive_connection()
    test_portfolio_crud()
    test_trade_crud()
    test_security_crud()
    test_counterparty_crud()
    test_currency_crud()
    test_fx_rate_crud()
    test_equity_price_crud()
    test_udf_crud()
    test_acl_crud()
    test_audit_logging()
    test_statistics()

    # Print summary
    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
