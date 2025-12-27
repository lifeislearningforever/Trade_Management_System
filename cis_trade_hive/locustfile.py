"""
Locust Load Testing Configuration for CisTrade
===============================================

Simulates realistic user behavior for performance benchmarking.

Target: 500 concurrent users
Scenarios: Dashboard, Portfolio CRUD, Reference Data, UDF Management, CSV Exports

Usage:
    # Web UI mode (recommended for visualization)
    locust --host=http://localhost:8000

    # Headless mode for CI/CD
    locust --host=http://localhost:8000 --users 500 --spawn-rate 10 --run-time 10m --headless

    # With specific scenario
    locust --host=http://localhost:8000 --users 100 --spawn-rate 5 Portfolio User

Author: CisTrade Team
Last Updated: 2025-12-27
"""

from locust import HttpUser, task, between, SequentialTaskSet
import random
from datetime import datetime


class AuthenticationMixin:
    """Mixin for handling authentication across user types"""

    def on_start(self):
        """Authenticate user at the start of the test - uses auto-login for dev mode"""
        # Use auto-login endpoint (development mode)
        response = self.client.get('/auto-login/', name="Auto Login")

        if response.status_code != 302:
            print(f"Auto-login failed: {response.status_code}")


class PortfolioUserBehavior(SequentialTaskSet):
    """Realistic portfolio management workflow"""

    @task
    def view_portfolio_list(self):
        """View portfolio list (most common action)"""
        with self.client.get('/portfolio/', name="Portfolio List", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed with status {response.status_code}")

    @task
    def search_portfolios(self):
        """Search portfolios by various criteria"""
        search_terms = ['USD', 'EUR', 'ACTIVE', 'DRAFT', 'PORT']
        search_term = random.choice(search_terms)

        with self.client.get(f'/portfolio/?search={search_term}',
                            name="Portfolio Search", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Search failed: {response.status_code}")

    @task
    def filter_by_status(self):
        """Filter portfolios by status"""
        statuses = ['ACTIVE', 'DRAFT', 'PENDING_APPROVAL', 'CLOSED']
        status = random.choice(statuses)

        self.client.get(f'/portfolio/?status={status}', name="Portfolio Filter")

    @task
    def view_portfolio_detail(self):
        """View portfolio detail page"""
        # Simulate viewing portfolio with random ID (1-50)
        portfolio_id = random.randint(1, 50)

        with self.client.get(f'/portfolio/{portfolio_id}/',
                            name="Portfolio Detail", catch_response=True) as response:
            if response.status_code in [200, 404]:  # 404 is acceptable (portfolio doesn't exist)
                response.success()
            else:
                response.failure(f"Detail view failed: {response.status_code}")

    @task
    def export_portfolios_csv(self):
        """Export portfolios to CSV"""
        with self.client.get('/portfolio/?export=csv',
                            name="Portfolio CSV Export", catch_response=True) as response:
            if response.status_code == 200 and 'text/csv' in response.headers.get('Content-Type', ''):
                response.success()
            else:
                response.failure(f"CSV export failed: {response.status_code}")


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


class UDFUserBehavior(SequentialTaskSet):
    """UDF definition management"""

    @task
    def view_udf_list(self):
        """View UDF definitions"""
        self.client.get('/udf/', name="UDF List")

    @task
    def filter_udf_by_entity(self):
        """Filter UDFs by entity type"""
        entity_types = ['PORTFOLIO', 'TRADE', 'COUNTERPARTY']
        entity = random.choice(entity_types)

        self.client.get(f'/udf/?entity_type={entity}', name="UDF Filter")

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


class DashboardUserBehavior(SequentialTaskSet):
    """Dashboard viewing and navigation"""

    @task
    def view_dashboard(self):
        """View main dashboard"""
        self.client.get('/dashboard/', name="Dashboard")


# ===========================
# User Type Definitions
# ===========================

class PortfolioUser(AuthenticationMixin, HttpUser):
    """
    Portfolio-focused user (40% of users)
    - Traders managing portfolios
    - Heavy portfolio CRUD operations
    """
    wait_time = between(2, 5)  # Wait 2-5 seconds between tasks
    weight = 40  # 40% of total users
    tasks = [PortfolioUserBehavior]


class ReferenceDataUser(AuthenticationMixin, HttpUser):
    """
    Reference data user (30% of users)
    - Operations team checking reference data
    - Frequent searches and exports
    """
    wait_time = between(3, 8)
    weight = 30
    tasks = [ReferenceDataUserBehavior]


class UDFUser(AuthenticationMixin, HttpUser):
    """
    UDF management user (15% of users)
    - Admin configuring custom fields
    - Less frequent but detailed operations
    """
    wait_time = between(5, 10)
    weight = 15
    tasks = [UDFUserBehavior]


class DashboardUser(AuthenticationMixin, HttpUser):
    """
    Dashboard monitoring user (15% of users)
    - Managers checking dashboard
    - Auditors reviewing logs
    """
    wait_time = between(10, 20)
    weight = 15
    tasks = [DashboardUserBehavior]


class MixedUser(AuthenticationMixin, HttpUser):
    """
    Mixed behavior user (realistic workflow)
    - Navigates across all modules
    - Represents power users
    """
    wait_time = between(3, 10)

    @task(3)
    def portfolio_workflow(self):
        """Portfolio operations"""
        self.client.get('/portfolio/')

    @task(2)
    def reference_data_workflow(self):
        """Reference data checks"""
        self.client.get('/reference-data/currency/')

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
        print(f"⚠️  SLOW REQUEST: {name} took {response_time}ms")


# ===========================
# Custom Test Scenarios
# ===========================

class StressTestUser(AuthenticationMixin, HttpUser):
    """
    Stress test scenario - rapid-fire requests
    Use this to test system limits

    Usage: locust --host=http://localhost:8000 StressTestUser
    """
    wait_time = between(0.5, 1)  # Very short wait time

    @task
    def rapid_portfolio_list(self):
        """Rapid portfolio list requests"""
        self.client.get('/portfolio/')


class SoakTestUser(AuthenticationMixin, HttpUser):
    """
    Soak test scenario - sustained load over time
    Use this to test memory leaks and resource exhaustion

    Usage: locust --host=http://localhost:8000 --users 200 --spawn-rate 5 --run-time 2h SoakTestUser
    """
    wait_time = between(10, 30)  # Realistic wait times

    @task(3)
    def normal_operations(self):
        """Mix of normal operations"""
        endpoints = ['/portfolio/', '/reference-data/currency/', '/udf/', '/dashboard/']
        self.client.get(random.choice(endpoints))

    @task(1)
    def export_operations(self):
        """Occasional exports"""
        endpoints = [
            '/portfolio/?export=csv',
            '/reference-data/currency/?export=csv',
            '/reference-data/counterparty/?export=csv'
        ]
        self.client.get(random.choice(endpoints))
