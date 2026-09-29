# Development Guide

Setup and development workflow for CisTrade contributors.

## Prerequisites

- Python 3.10+
- Virtual environment (venv)
- Access to Impala cluster
- Git
- IDE (VS Code recommended)

## Initial Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourcompany/cistrade.git
cd cistrade
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

Create `.env` file:

```env
DJANGO_DEBUG=true
DJANGO_SECRET_KEY=your-secret-key
IMPALA_HOST=your-impala-host
IMPALA_PORT=21050
```

### 5. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create superuser (optional)
python manage.py createsuperuser
```

### 6. Load Reference Data

```bash
# Load ACL data
impala-shell -f sql/hive_ddl/02_acl_tables.sql

# Load reference data (external tables)
impala-shell -f sql/hive_ddl/03_reference_external_tables.sql
```

## Development Workflow

### Running Development Server

```bash
python manage.py runserver 0.0.0.0:8000
```

Access at: http://localhost:8000

### Auto-Login for Development

Navigate to: http://localhost:8000/auto-login/

Logs in as TMP3RC user automatically.

### Code Changes

1. Create feature branch
```bash
git checkout -b feature/my-feature
```

2. Make changes
3. Test locally
4. Commit and push
```bash
git add .
git commit -m "feat: add new feature"
git push origin feature/my-feature
```

5. Create pull request

## Project Structure

See [Code Structure](code-structure.md) for detailed layout.

## Common Tasks

### Add New View

1. Create view function in `{app}/views.py`
2. Add URL pattern in `{app}/urls.py`
3. Create template in `{app}/templates/{app}/`
4. Add permission decorator if needed

### Add New Service Method

1. Add method to `{app}/services/{service}.py`
2. Add unit tests
3. Update API documentation

### Add New Repository Method

1. Add method to `{app}/repositories/{repository}.py`
2. Write SQL query
3. Test with sample data

## Testing

### Run All Tests

```bash
python manage.py test
```

### Run Specific App Tests

```bash
python manage.py test portfolio
```

### Run Single Test

```bash
python manage.py test portfolio.tests.test_service.PortfolioServiceTest.test_create_portfolio
```

## Database

### Access Impala Shell

```bash
impala-shell -i your-impala-host
```

### Common Queries

```sql
-- Check portfolio count
SELECT COUNT(*) FROM gmp_cis.cis_portfolio;

-- View sample portfolios
SELECT * FROM gmp_cis.cis_portfolio LIMIT 10;

-- Check audit logs
SELECT * FROM gmp_cis.cis_audit_log 
ORDER BY created_at DESC LIMIT 20;
```

## Debugging

### Enable Debug Mode

In `.env`:
```env
DJANGO_DEBUG=true
```

### View Logs

```bash
tail -f logs/cistrade.log
```

### Django Shell

```bash
python manage.py shell
```

Test queries:
```python
from portfolio.repositories import portfolio_hive_repository
portfolios = portfolio_hive_repository.get_all_portfolios(limit=5)
print(portfolios)
```

## Code Quality

### Run Linter

```bash
flake8 .
```

### Format Code

```bash
black .
```

### Type Checking

```bash
mypy .
```

## Documentation

### Build Docs

```bash
cd docs
mkdocs build
```

### Serve Docs Locally

```bash
cd docs
mkdocs serve
```

Access at: http://localhost:8001

## Deployment

See [Deployment Guide](deployment.md) for production deployment.

## Troubleshooting

### Impala Connection Fails

1. Check `IMPALA_HOST` and `IMPALA_PORT` in `.env`
2. Verify network connectivity
3. Check firewall rules
4. Verify Impala cluster is running

### Migration Errors

```bash
# Reset migrations (dev only!)
python manage.py migrate --fake-initial
```

### Static Files Not Loading

```bash
python manage.py collectstatic
```

## Contributing

1. Follow code style guide
2. Write tests for new features
3. Update documentation
4. Submit pull request with clear description

## Related Documentation

- [Code Structure](code-structure.md)
- [Architecture](architecture.md)
- [Testing](testing.md)
- [Deployment](deployment.md)
