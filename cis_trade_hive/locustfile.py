"""
Locust Load Testing Configuration for CisTrade
===============================================

Simulates realistic user behavior for performance benchmarking.

Target: 500 concurrent users
Scenarios: Dashboard, Portfolio, Trade, Security, Counterparty, Market Data (FX/Equity), UDF

Usage:
    # Web UI mode (recommended for visualization)
    locust --host=http://localhost:8000

    # Headless mode for CI/CD
    locust --host=http://localhost:8000 --users 500 --spawn-rate 10 --run-time 10m --headless

    # With specific scenario
    locust --host=http://localhost:8000 --users 100 --spawn-rate 5 TradeUser

Author: CisTrade Team
Last Updated: 2026-02-10
"""

from locust import HttpUser, task, between, SequentialTaskSet
import random
from datetime import datetime, timedelta
import string


# ===========================
# Test Data Generators
# ===========================

def random_string(length=8):
    """Generate random string for test data"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def random_date(days_ago=30):
    """Generate random date within the last N days"""
    date = datetime.now() - timedelta(days=random.randint(0, days_ago))
    return date.strftime('%Y-%m-%d')


def random_price():
    """Generate random price"""
    return round(random.uniform(10.0, 1000.0), 2)


def random_quantity():
    """Generate random quantity"""
    return random.randint(100, 10000)


# Sample test data
PORTFOLIOS = ['AIIF CP II LTD', 'GLOBAL MACRO FUND', 'ASIAN EQUITY FUND', 'FIXED INCOME FUND']
SECURITIES = ['Hodges-Thompson', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA']
CURRENCIES = ['USD', 'EUR', 'GBP', 'SGD', 'JPY', 'HKD', 'CHF', 'AUD']
COUNTERPARTIES = ['21ST CT FOX AMERICA*', 'GOLDMAN SACHS', 'JP MORGAN', 'MORGAN STANLEY', 'CITIBANK']
TRADE_TYPES = ['BUY', 'SELL']
SECURITY_TYPES = ['Equity', 'Bond', 'Fund', 'ETF', 'Derivative']


class AuthenticationMixin:
    """Mixin for handling authentication across user types"""

    def on_start(self):
        """Authenticate user at the start of the test - uses auto-login for dev mode"""
        response = self.client.get('/auto-login/', name="Auto Login")
        if response.status_code != 302:
            print(f"Auto-login failed: {response.status_code}")


# ===========================
# Trade User Behavior
# ===========================

class TradeUserBehavior(SequentialTaskSet):
    """Trade management workflow - list, create, update"""

    @task
    def view_trade_list(self):
        """View trade list"""
        with self.client.get('/trade/', name="Trade List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_trades(self):
        """Search trades"""
        search_terms = ['BUY', 'SELL', 'USD', 'PENDING']
        search_term = random.choice(search_terms)
        self.client.get(f'/trade/?search={search_term}', name="Trade Search")

    @task
    def filter_trades_by_type(self):
        """Filter trades by type"""
        trade_type = random.choice(TRADE_TYPES)
        self.client.get(f'/trade/?trade_type={trade_type}', name="Trade Filter")

    @task
    def view_trade_create_form(self):
        """View trade create form"""
        self.client.get('/trade/create/', name="Trade Create Form")

    @task
    def create_trade(self):
        """Create a new trade"""
        trade_data = {
            'trade_type': random.choice(TRADE_TYPES),
            'portfolio_short_name': random.choice(PORTFOLIOS),
            'security_label': random.choice(SECURITIES),
            'quantity': random_quantity(),
            'price': random_price(),
            'trade_date': random_date(7),
            'settlement_date': random_date(0),
            'currency_code': random.choice(CURRENCIES),
            'counterparty': random.choice(COUNTERPARTIES),
        }
        trade_data['total_amount'] = trade_data['quantity'] * trade_data['price']

        with self.client.post('/trade/create/', data=trade_data,
                              name="Trade Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def view_trade_detail(self):
        """View trade detail"""
        trade_id = random.randint(1000000, 1000050)
        with self.client.get(f'/trade/{trade_id}/',
                            name="Trade Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Detail failed: {response.status_code}")

    @task
    def export_trades_csv(self):
        """Export trades to CSV"""
        self.client.get('/trade/?export=csv', name="Trade CSV Export")


# ===========================
# Security User Behavior
# ===========================

class SecurityUserBehavior(SequentialTaskSet):
    """Security master management workflow"""

    @task
    def view_security_list(self):
        """View security list"""
        with self.client.get('/security/', name="Security List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_securities(self):
        """Search securities"""
        search_terms = ['AAPL', 'Equity', 'USD', 'US', 'Bond']
        search_term = random.choice(search_terms)
        self.client.get(f'/security/?search={search_term}', name="Security Search")

    @task
    def filter_by_type(self):
        """Filter securities by type"""
        security_type = random.choice(SECURITY_TYPES)
        self.client.get(f'/security/?security_type={security_type}', name="Security Filter")

    @task
    def view_security_create_form(self):
        """View security create form"""
        self.client.get('/security/create/', name="Security Create Form")

    @task
    def create_security(self):
        """Create a new security"""
        security_data = {
            'security_name': f'TEST_SEC_{random_string(6)}',
            'security_type': random.choice(SECURITY_TYPES),
            'currency_code': random.choice(CURRENCIES),
            'country_code': random.choice(['US', 'GB', 'SG', 'JP', 'HK']),
            'isin': f'US{random_string(10)}',
            'ticker': random_string(4),
            'exchange_code': random.choice(['NYSE', 'NASDAQ', 'LSE', 'SGX']),
            'is_active': True,
        }

        with self.client.post('/security/create/', data=security_data,
                              name="Security Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def view_security_detail(self):
        """View security detail"""
        security_id = random.randint(1, 100)
        with self.client.get(f'/security/{security_id}/',
                            name="Security Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Detail failed: {response.status_code}")

    @task
    def export_securities_csv(self):
        """Export securities to CSV"""
        self.client.get('/security/?export=csv', name="Security CSV Export")


# ===========================
# Counterparty User Behavior
# ===========================

class CounterpartyUserBehavior(SequentialTaskSet):
    """Counterparty (Party) management workflow"""

    @task
    def view_counterparty_list(self):
        """View counterparty list"""
        with self.client.get('/reference-data/counterparty/',
                            name="Counterparty List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_counterparties(self):
        """Search counterparties"""
        search_terms = ['Bank', 'Corp', 'Fund', 'LLC', 'Goldman', 'Morgan']
        search_term = random.choice(search_terms)
        self.client.get(f'/reference-data/counterparty/?search={search_term}',
                       name="Counterparty Search")

    @task
    def filter_by_type(self):
        """Filter counterparties by type"""
        party_types = ['BROKER', 'CUSTODIAN', 'COUNTERPARTY', 'EXCHANGE']
        party_type = random.choice(party_types)
        self.client.get(f'/reference-data/counterparty/?party_type={party_type}',
                       name="Counterparty Filter")

    @task
    def view_counterparty_create_form(self):
        """View counterparty create form"""
        self.client.get('/reference-data/counterparty/create/', name="Counterparty Create Form")

    @task
    def create_counterparty(self):
        """Create a new counterparty"""
        party_data = {
            'party_name': f'TEST_PARTY_{random_string(6)}',
            'party_short_name': random_string(8),
            'party_type': random.choice(['BROKER', 'CUSTODIAN', 'COUNTERPARTY']),
            'country_code': random.choice(['US', 'GB', 'SG', 'JP']),
            'is_active': True,
        }

        with self.client.post('/reference-data/counterparty/create/', data=party_data,
                              name="Counterparty Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def view_counterparty_detail(self):
        """View counterparty detail"""
        party_id = random.randint(1, 50)
        with self.client.get(f'/reference-data/counterparty/{party_id}/',
                            name="Counterparty Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Detail failed: {response.status_code}")

    @task
    def export_counterparties_csv(self):
        """Export counterparties to CSV"""
        self.client.get('/reference-data/counterparty/?export=csv', name="Counterparty CSV Export")


# ===========================
# Equity Price User Behavior
# ===========================

class EquityPriceUserBehavior(SequentialTaskSet):
    """Equity price management workflow"""

    @task
    def view_equity_price_list(self):
        """View equity price list"""
        with self.client.get('/market-data/equity-prices/',
                            name="Equity Price List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_equity_prices(self):
        """Search equity prices"""
        search_terms = ['AAPL', 'MSFT', 'USD', 'EUR']
        search_term = random.choice(search_terms)
        self.client.get(f'/market-data/equity-prices/?search={search_term}',
                       name="Equity Price Search")

    @task
    def filter_by_currency(self):
        """Filter equity prices by currency"""
        currency = random.choice(CURRENCIES)
        self.client.get(f'/market-data/equity-prices/?currency={currency}',
                       name="Equity Price Filter")

    @task
    def view_equity_price_create_form(self):
        """View equity price create form"""
        self.client.get('/market-data/equity-prices/create/', name="Equity Price Create Form")

    @task
    def create_equity_price(self):
        """Create a new equity price"""
        price_data = {
            'security_label': random.choice(SECURITIES),
            'currency_code': random.choice(CURRENCIES),
            'price_date': random_date(7),
            'main_closing_price': random_price(),
            'isin': f'US{random_string(10)}',
        }

        with self.client.post('/market-data/equity-prices/create/', data=price_data,
                              name="Equity Price Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def get_equity_price_api(self):
        """Get equity price via API (for trade form auto-fill)"""
        security = random.choice(SECURITIES)
        currency = random.choice(CURRENCIES)
        self.client.get(f'/trade/api/equity-price/?security={security}&currency={currency}',
                       name="Equity Price API")

    @task
    def export_equity_prices_csv(self):
        """Export equity prices to CSV"""
        self.client.get('/market-data/equity-prices/?export=csv', name="Equity Price CSV Export")


# ===========================
# FX Rate User Behavior
# ===========================

class FXRateUserBehavior(SequentialTaskSet):
    """FX rate management workflow"""

    @task
    def view_fx_rate_list(self):
        """View FX rate list"""
        with self.client.get('/market-data/fx-rates/',
                            name="FX Rate List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_fx_rates(self):
        """Search FX rates"""
        search_terms = ['USD', 'EUR', 'GBP', 'SGD']
        search_term = random.choice(search_terms)
        self.client.get(f'/market-data/fx-rates/?search={search_term}',
                       name="FX Rate Search")

    @task
    def filter_by_currency_pair(self):
        """Filter FX rates by currency pair"""
        from_currency = random.choice(CURRENCIES)
        to_currency = random.choice([c for c in CURRENCIES if c != from_currency])
        self.client.get(f'/market-data/fx-rates/?from_currency={from_currency}&to_currency={to_currency}',
                       name="FX Rate Filter")

    @task
    def view_fx_rate_create_form(self):
        """View FX rate create form"""
        self.client.get('/market-data/fx-rates/create/', name="FX Rate Create Form")

    @task
    def create_fx_rate(self):
        """Create a new FX rate"""
        from_currency = random.choice(CURRENCIES)
        to_currency = random.choice([c for c in CURRENCIES if c != from_currency])
        fx_data = {
            'from_currency': from_currency,
            'to_currency': to_currency,
            'rate_date': random_date(7),
            'exchange_rate': round(random.uniform(0.5, 2.0), 6),
            'rate_type': random.choice(['SPOT', 'FORWARD']),
        }

        with self.client.post('/market-data/fx-rates/create/', data=fx_data,
                              name="FX Rate Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def export_fx_rates_csv(self):
        """Export FX rates to CSV"""
        self.client.get('/market-data/fx-rates/?export=csv', name="FX Rate CSV Export")


# ===========================
# UDF User Behavior
# ===========================

class UDFUserBehavior(SequentialTaskSet):
    """UDF definition management with create and update"""

    @task
    def view_udf_list(self):
        """View UDF definitions"""
        with self.client.get('/udf/', name="UDF List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def filter_udf_by_entity(self):
        """Filter UDFs by entity type"""
        entity_types = ['PORTFOLIO', 'TRADE', 'COUNTERPARTY', 'SECURITY']
        entity = random.choice(entity_types)
        self.client.get(f'/udf/?entity_type={entity}', name="UDF Filter")

    @task
    def view_udf_create_form(self):
        """View UDF create form"""
        self.client.get('/udf/create/', name="UDF Create Form")

    @task
    def create_udf(self):
        """Create a new UDF definition"""
        udf_data = {
            'field_name': f'custom_field_{random_string(4).lower()}',
            'display_name': f'Custom Field {random_string(4)}',
            'entity_type': random.choice(['PORTFOLIO', 'TRADE', 'SECURITY']),
            'data_type': random.choice(['STRING', 'NUMBER', 'DATE', 'BOOLEAN']),
            'is_required': random.choice([True, False]),
            'is_active': True,
        }

        with self.client.post('/udf/create/', data=udf_data,
                              name="UDF Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def view_udf_detail(self):
        """View UDF detail"""
        udf_id = random.randint(1, 20)
        with self.client.get(f'/udf/{udf_id}/',
                            name="UDF Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"UDF detail failed: {response.status_code}")


# ===========================
# Portfolio User Behavior
# ===========================

class PortfolioUserBehavior(SequentialTaskSet):
    """Realistic portfolio management workflow"""

    @task
    def view_portfolio_list(self):
        """View portfolio list"""
        with self.client.get('/portfolio/', name="Portfolio List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_portfolios(self):
        """Search portfolios"""
        search_terms = ['USD', 'EUR', 'ACTIVE', 'DRAFT', 'FUND']
        search_term = random.choice(search_terms)
        self.client.get(f'/portfolio/?search={search_term}', name="Portfolio Search")

    @task
    def filter_by_status(self):
        """Filter portfolios by status"""
        statuses = ['ACTIVE', 'DRAFT', 'PENDING_APPROVAL', 'CLOSED']
        status = random.choice(statuses)
        self.client.get(f'/portfolio/?status={status}', name="Portfolio Filter")

    @task
    def view_portfolio_create_form(self):
        """View portfolio create form"""
        self.client.get('/portfolio/create/', name="Portfolio Create Form")

    @task
    def create_portfolio(self):
        """Create a new portfolio"""
        portfolio_data = {
            'portfolio_short_name': f'TEST_{random_string(6)}',
            'portfolio_full_name': f'Test Portfolio {random_string(8)}',
            'base_currency': random.choice(CURRENCIES),
            'fund_type': random.choice(['HEDGE', 'MUTUAL', 'ETF', 'PENSION']),
            'status': 'DRAFT',
        }

        with self.client.post('/portfolio/create/', data=portfolio_data,
                              name="Portfolio Create", catch_response=True) as response:
            if response.status_code in [200, 302]:
                response.success()
            else:
                response.failure(f"Create failed: {response.status_code}")

    @task
    def view_portfolio_detail(self):
        """View portfolio detail"""
        portfolio_id = random.randint(1, 50)
        with self.client.get(f'/portfolio/{portfolio_id}/',
                            name="Portfolio Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:
                response.success()
            else:
                response.failure(f"Detail view failed: {response.status_code}")

    @task
    def export_portfolios_csv(self):
        """Export portfolios to CSV"""
        self.client.get('/portfolio/?export=csv', name="Portfolio CSV Export")


# ===========================
# Reference Data User Behavior
# ===========================

class ReferenceDataUserBehavior(SequentialTaskSet):
    """Reference data browsing and searching"""

    @task
    def view_currencies(self):
        """View currency list"""
        self.client.get('/reference-data/currency/', name="Currency List")

    @task
    def view_countries(self):
        """View country list"""
        self.client.get('/reference-data/country/', name="Country List")

    @task
    def view_calendars(self):
        """View calendar list"""
        self.client.get('/reference-data/calendar/', name="Calendar List")

    @task
    def view_counterparties(self):
        """View counterparty list"""
        self.client.get('/reference-data/counterparty/', name="Counterparty List")

    @task
    def search_counterparties(self):
        """Search counterparties"""
        search_terms = ['Bank', 'Corp', 'Fund', 'LLC']
        search_term = random.choice(search_terms)
        self.client.get(f'/reference-data/counterparty/?search={search_term}',
                       name="Counterparty Search")

    @task
    def export_reference_data_csv(self):
        """Export reference data to CSV"""
        endpoints = ['currency', 'country', 'calendar', 'counterparty']
        endpoint = random.choice(endpoints)
        self.client.get(f'/reference-data/{endpoint}/?export=csv',
                       name=f"{endpoint.title()} CSV Export")


# ===========================
# Dashboard User Behavior
# ===========================

class DashboardUserBehavior(SequentialTaskSet):
    """Dashboard viewing and navigation"""

    @task
    def view_dashboard(self):
        """View main dashboard"""
        self.client.get('/dashboard/', name="Dashboard")

    @task
    def view_market_data_dashboard(self):
        """View market data dashboard"""
        self.client.get('/market-data/dashboard/', name="Market Data Dashboard")


# ===========================
# User Type Definitions
# ===========================

class TradeUser(AuthenticationMixin, HttpUser):
    """
    Trade-focused user (25% of users)
    - Traders executing trades
    - Heavy trade CRUD operations
    """
    wait_time = between(2, 5)
    weight = 25
    tasks = [TradeUserBehavior]


class SecurityUser(AuthenticationMixin, HttpUser):
    """
    Security master user (15% of users)
    - Operations team managing securities
    """
    wait_time = between(3, 7)
    weight = 15
    tasks = [SecurityUserBehavior]


class CounterpartyUser(AuthenticationMixin, HttpUser):
    """
    Counterparty management user (10% of users)
    - Managing broker/counterparty data
    """
    wait_time = between(4, 8)
    weight = 10
    tasks = [CounterpartyUserBehavior]


class EquityPriceUser(AuthenticationMixin, HttpUser):
    """
    Equity price management user (10% of users)
    - Market data team updating prices
    """
    wait_time = between(3, 6)
    weight = 10
    tasks = [EquityPriceUserBehavior]


class FXRateUser(AuthenticationMixin, HttpUser):
    """
    FX rate management user (10% of users)
    - Market data team updating FX rates
    """
    wait_time = between(3, 6)
    weight = 10
    tasks = [FXRateUserBehavior]


class PortfolioUser(AuthenticationMixin, HttpUser):
    """
    Portfolio-focused user (15% of users)
    - Portfolio managers
    """
    wait_time = between(2, 5)
    weight = 15
    tasks = [PortfolioUserBehavior]


class ReferenceDataUser(AuthenticationMixin, HttpUser):
    """
    Reference data user (5% of users)
    - Operations team checking reference data
    """
    wait_time = between(3, 8)
    weight = 5
    tasks = [ReferenceDataUserBehavior]


class UDFUser(AuthenticationMixin, HttpUser):
    """
    UDF management user (5% of users)
    - Admin configuring custom fields
    """
    wait_time = between(5, 10)
    weight = 5
    tasks = [UDFUserBehavior]


class DashboardUser(AuthenticationMixin, HttpUser):
    """
    Dashboard monitoring user (5% of users)
    - Managers checking dashboards
    """
    wait_time = between(10, 20)
    weight = 5
    tasks = [DashboardUserBehavior]


class MixedUser(AuthenticationMixin, HttpUser):
    """
    Mixed behavior user (realistic workflow)
    - Navigates across all modules
    - Represents power users
    """
    wait_time = between(3, 10)

    @task(4)
    def trade_workflow(self):
        """Trade operations"""
        self.client.get('/trade/')

    @task(3)
    def portfolio_workflow(self):
        """Portfolio operations"""
        self.client.get('/portfolio/')

    @task(2)
    def security_workflow(self):
        """Security operations"""
        self.client.get('/security/')

    @task(2)
    def market_data_workflow(self):
        """Market data checks"""
        endpoints = ['/market-data/equity-prices/', '/market-data/fx-rates/']
        self.client.get(random.choice(endpoints))

    @task(1)
    def reference_data_workflow(self):
        """Reference data checks"""
        self.client.get('/reference-data/counterparty/')

    @task(1)
    def udf_workflow(self):
        """UDF checks"""
        self.client.get('/udf/')

    @task(1)
    def dashboard_workflow(self):
        """Dashboard monitoring"""
        self.client.get('/dashboard/')


# ===========================
# Event Hooks for Monitoring
# ===========================

from locust import events


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Actions to perform when test starts"""
    print(f"\n{'='*60}")
    print(f"CisTrade Load Test Started")
    print(f"Target: {environment.parsed_options.num_users if environment.parsed_options else 'Web UI'} users")
    print(f"Host: {environment.host}")
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Actions to perform when test stops"""
    print(f"\n{'='*60}")
    print(f"CisTrade Load Test Completed")
    print(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    """Log slow requests (>2 seconds)"""
    if response_time > 2000:
        print(f"SLOW REQUEST: {name} took {response_time}ms")


# ===========================
# Custom Test Scenarios
# ===========================

class StressTestUser(AuthenticationMixin, HttpUser):
    """
    Stress test scenario - rapid-fire requests
    Use this to test system limits

    Usage: locust --host=http://localhost:8000 StressTestUser
    """
    wait_time = between(0.5, 1)

    @task(3)
    def rapid_trade_list(self):
        """Rapid trade list requests"""
        self.client.get('/trade/')

    @task(2)
    def rapid_security_list(self):
        """Rapid security list requests"""
        self.client.get('/security/')

    @task(2)
    def rapid_equity_prices(self):
        """Rapid equity price requests"""
        self.client.get('/market-data/equity-prices/')

    @task(1)
    def rapid_portfolio_list(self):
        """Rapid portfolio list requests"""
        self.client.get('/portfolio/')


class SoakTestUser(AuthenticationMixin, HttpUser):
    """
    Soak test scenario - sustained load over time
    Use this to test memory leaks and resource exhaustion

    Usage: locust --host=http://localhost:8000 --users 200 --spawn-rate 5 --run-time 2h SoakTestUser
    """
    wait_time = between(10, 30)

    @task(3)
    def normal_operations(self):
        """Mix of normal operations"""
        endpoints = [
            '/trade/', '/portfolio/', '/security/',
            '/market-data/equity-prices/', '/market-data/fx-rates/',
            '/reference-data/counterparty/', '/udf/', '/dashboard/'
        ]
        self.client.get(random.choice(endpoints))

    @task(1)
    def export_operations(self):
        """Occasional exports"""
        endpoints = [
            '/trade/?export=csv',
            '/portfolio/?export=csv',
            '/security/?export=csv',
            '/market-data/equity-prices/?export=csv',
            '/reference-data/counterparty/?export=csv'
        ]
        self.client.get(random.choice(endpoints))


class CRUDTestUser(AuthenticationMixin, HttpUser):
    """
    CRUD-focused test user - tests create/update/list operations

    Usage: locust --host=http://localhost:8000 CRUDTestUser
    """
    wait_time = between(2, 5)

    @task(3)
    def trade_crud(self):
        """Trade CRUD operations"""
        # List
        self.client.get('/trade/', name="CRUD: Trade List")
        # Create form
        self.client.get('/trade/create/', name="CRUD: Trade Create Form")
        # Create
        trade_data = {
            'trade_type': random.choice(TRADE_TYPES),
            'portfolio_short_name': random.choice(PORTFOLIOS),
            'security_label': random.choice(SECURITIES),
            'quantity': random_quantity(),
            'price': random_price(),
            'trade_date': random_date(7),
            'currency_code': random.choice(CURRENCIES),
            'counterparty': random.choice(COUNTERPARTIES),
        }
        trade_data['total_amount'] = trade_data['quantity'] * trade_data['price']
        self.client.post('/trade/create/', data=trade_data, name="CRUD: Trade Create")

    @task(2)
    def security_crud(self):
        """Security CRUD operations"""
        self.client.get('/security/', name="CRUD: Security List")
        self.client.get('/security/create/', name="CRUD: Security Create Form")
        security_data = {
            'security_name': f'TEST_{random_string(6)}',
            'security_type': random.choice(SECURITY_TYPES),
            'currency_code': random.choice(CURRENCIES),
            'is_active': True,
        }
        self.client.post('/security/create/', data=security_data, name="CRUD: Security Create")

    @task(2)
    def equity_price_crud(self):
        """Equity price CRUD operations"""
        self.client.get('/market-data/equity-prices/', name="CRUD: Equity Price List")
        self.client.get('/market-data/equity-prices/create/', name="CRUD: Equity Price Create Form")
        price_data = {
            'security_label': random.choice(SECURITIES),
            'currency_code': random.choice(CURRENCIES),
            'price_date': random_date(7),
            'main_closing_price': random_price(),
        }
        self.client.post('/market-data/equity-prices/create/', data=price_data,
                        name="CRUD: Equity Price Create")

    @task(1)
    def fx_rate_crud(self):
        """FX rate CRUD operations"""
        self.client.get('/market-data/fx-rates/', name="CRUD: FX Rate List")
        self.client.get('/market-data/fx-rates/create/', name="CRUD: FX Rate Create Form")
        from_currency = random.choice(CURRENCIES)
        to_currency = random.choice([c for c in CURRENCIES if c != from_currency])
        fx_data = {
            'from_currency': from_currency,
            'to_currency': to_currency,
            'rate_date': random_date(7),
            'exchange_rate': round(random.uniform(0.5, 2.0), 6),
        }
        self.client.post('/market-data/fx-rates/create/', data=fx_data, name="CRUD: FX Rate Create")

    @task(1)
    def counterparty_crud(self):
        """Counterparty CRUD operations"""
        self.client.get('/reference-data/counterparty/', name="CRUD: Counterparty List")
        self.client.get('/reference-data/counterparty/create/', name="CRUD: Counterparty Create Form")
        party_data = {
            'party_name': f'TEST_{random_string(6)}',
            'party_short_name': random_string(8),
            'party_type': 'BROKER',
            'is_active': True,
        }
        self.client.post('/reference-data/counterparty/create/', data=party_data,
                        name="CRUD: Counterparty Create")
