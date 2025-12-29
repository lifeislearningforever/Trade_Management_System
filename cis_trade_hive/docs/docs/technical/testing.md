# Testing Guide

Comprehensive testing strategy for CisTrade application.

## Testing Philosophy

- **Test Early**: Write tests during development
- **Test Often**: Run tests before every commit
- **Test Everything**: Unit, integration, and end-to-end tests
- **Maintain Coverage**: Target 80%+ code coverage

## Test Types

### Unit Tests

Test individual functions/methods in isolation.

**Example** (`portfolio/tests/test_service.py`):
```python
from django.test import TestCase
from portfolio.services import PortfolioService

class PortfolioServiceTest(TestCase):
    def test_create_portfolio_valid_data(self):
        data = {
            'code': 'TEST001',
            'name': 'Test Portfolio',
            'currency': 'SGD'
        }
        portfolio = PortfolioService.create_portfolio(user, data)
        self.assertEqual(portfolio.code, 'TEST001')
        self.assertEqual(portfolio.status, 'DRAFT')
```

### Integration Tests

Test multiple components working together.

**Example** (`portfolio/tests/test_integration.py`):
```python
class PortfolioIntegrationTest(TestCase):
    def test_create_and_approve_portfolio(self):
        # Create as maker
        portfolio = PortfolioService.create_portfolio(maker, data)

        # Submit for approval
        PortfolioService.submit_for_approval(portfolio, maker)

        # Approve as checker
        approved = PortfolioService.approve_portfolio(portfolio, checker, "Approved")

        self.assertEqual(approved.status, 'ACTIVE')
```

### View Tests

Test HTTP requests and responses.

**Example** (`portfolio/tests/test_views.py`):
```python
class PortfolioViewTest(TestCase):
    def test_portfolio_list_requires_login(self):
        response = self.client.get('/portfolio/')
        self.assertRedirects(response, '/login/')

    def test_portfolio_list_authenticated(self):
        self.client.login(username='test', password='pass')
        response = self.client.get('/portfolio/')
        self.assertEqual(response.status_code, 200)
```

## Running Tests

### All Tests

```bash
python manage.py test
```

### Specific App

```bash
python manage.py test portfolio
```

### Specific Test File

```bash
python manage.py test portfolio.tests.test_service
```

### Single Test Method

```bash
python manage.py test portfolio.tests.test_service.PortfolioServiceTest.test_create_portfolio
```

### With Coverage

```bash
coverage run --source='.' manage.py test
coverage report
coverage html  # Generate HTML report
```

## Test Organization

```
{app}/tests/
├── __init__.py
├── test_models.py        # Model tests
├── test_views.py         # View tests
├── test_services.py      # Service layer tests
├── test_repositories.py  # Repository tests
└── test_integration.py   # Integration tests
```

## Test Fixtures

### Using Factories

**Install**:
```bash
pip install factory-boy
```

**Define Factory** (`portfolio/tests/factories.py`):
```python
import factory
from portfolio.models import Portfolio

class PortfolioFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Portfolio

    code = factory.Sequence(lambda n: f'PORT{n:03d}')
    name = factory.Faker('company')
    currency = 'SGD'
    status = 'DRAFT'
```

**Use in Tests**:
```python
def test_with_factory(self):
    portfolio = PortfolioFactory.create()
    self.assertIsNotNone(portfolio.code)
```

### Using Fixtures

**Define Fixture** (`portfolio/fixtures/test_portfolios.json`):
```json
[
  {
    "model": "portfolio.portfolio",
    "pk": 1,
    "fields": {
      "code": "TEST001",
      "name": "Test Portfolio",
      "currency": "SGD",
      "status": "DRAFT"
    }
  }
]
```

**Load in Test**:
```python
class PortfolioTest(TestCase):
    fixtures = ['test_portfolios.json']

    def test_portfolio_exists(self):
        portfolio = Portfolio.objects.get(code='TEST001')
        self.assertEqual(portfolio.name, 'Test Portfolio')
```

## Mocking

### Mock External Services

**Mock Impala Connection**:
```python
from unittest.mock import patch, MagicMock

class TestPortfolioRepository(TestCase):
    @patch('core.repositories.impala_connection.impala_manager')
    def test_get_all_portfolios(self, mock_impala):
        # Setup mock
        mock_impala.execute_query.return_value = [
            {'code': 'TEST001', 'name': 'Test Portfolio'}
        ]

        # Call method
        portfolios = portfolio_repository.get_all_portfolios()

        # Assertions
        self.assertEqual(len(portfolios), 1)
        mock_impala.execute_query.assert_called_once()
```

### Mock User

```python
from django.contrib.auth.models import User

def create_test_user(username='testuser', is_staff=False):
    user = User.objects.create_user(
        username=username,
        password='testpass123'
    )
    user.is_staff = is_staff
    return user
```

## Best Practices

### 1. Test Names

✅ **Good**:
```python
def test_create_portfolio_with_valid_data_returns_portfolio(self):
def test_submit_for_approval_without_draft_status_raises_error(self):
```

❌ **Avoid**:
```python
def test_portfolio(self):
def test1(self):
```

### 2. AAA Pattern

```python
def test_approve_portfolio(self):
    # Arrange
    portfolio = PortfolioFactory.create(status='PENDING_APPROVAL')
    checker = create_test_user('checker')

    # Act
    result = PortfolioService.approve_portfolio(portfolio, checker, "OK")

    # Assert
    self.assertEqual(result.status, 'ACTIVE')
```

### 3. One Assertion Per Test (when practical)

```python
def test_portfolio_created_with_draft_status(self):
    portfolio = PortfolioService.create_portfolio(user, data)
    self.assertEqual(portfolio.status, 'DRAFT')

def test_portfolio_created_with_maker_as_creator(self):
    portfolio = PortfolioService.create_portfolio(user, data)
    self.assertEqual(portfolio.created_by, user)
```

### 4. Test Edge Cases

```python
def test_create_portfolio_with_empty_code_raises_error(self):
def test_create_portfolio_with_duplicate_code_raises_error(self):
def test_create_portfolio_with_invalid_currency_raises_error(self):
```

## Continuous Integration

### GitHub Actions

`.github/workflows/tests.yml`:
```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.10
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install coverage
      - name: Run tests
        run: |
          coverage run --source='.' manage.py test
          coverage report --fail-under=80
```

## Performance Testing

### Load Testing with Locust

**Install**:
```bash
pip install locust
```

**Define Test** (`locustfile.py`):
```python
from locust import HttpUser, task, between

class CisTradeUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post("/login/", {
            "username": "test",
            "password": "pass"
        })

    @task(3)
    def view_portfolio_list(self):
        self.client.get("/portfolio/")

    @task(1)
    def view_portfolio_detail(self):
        self.client.get("/portfolio/TEST001/")
```

**Run**:
```bash
locust -f locustfile.py --host=http://localhost:8000
```

## Debugging Tests

### Verbose Output

```bash
python manage.py test --verbose=2
```

### Keep Database

```bash
python manage.py test --keepdb
```

### Run Failed Tests Only

```bash
python manage.py test --failed
```

### PDB Debugging

```python
def test_something(self):
    import pdb; pdb.set_trace()
    # Test code here
```

## Related Documentation

- [Development Guide](development-guide.md)
- [Code Structure](code-structure.md)
- [API Reference](api-reference.md)
