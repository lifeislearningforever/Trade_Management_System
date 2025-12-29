# CisTrade - Database Setup Guide

## Overview

This directory contains DDL (Data Definition Language) files and sample data for the CisTrade application.

## Directory Structure

```
sql/
├── ddl/                          # Table definitions
│   ├── 01_core_tables.sql       # Core infrastructure (AuditLog)
│   ├── 02_portfolio_tables.sql  # Portfolio with Four-Eyes
│   ├── 03_reference_data_tables.sql  # Reference data
│   ├── 04_udf_tables.sql        # User-Defined Fields
│   └── 05_acl_tables_kudu.sql   # ACL for Kudu/Impala
└── sample_data/                  # Sample data
    ├── 01_users.sql             # Users and groups
    ├── 02_currencies.sql        # 25 major currencies
    ├── 03_countries.sql         # 30 countries
    ├── 04_calendars.sql         # SGX, NYSE, LSE holidays 2025
    ├── 05_counterparties.sql    # Banks, brokers, institutions
    ├── 06_portfolios.sql        # 8 sample portfolios (various states)
    └── 07_acl_permissions_kudu.sql  # Role-based permissions
```

## Database Setup

### Option 1: Using Django Migrations (Recommended for Development)

Django automatically creates tables from models:

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade
source venv/bin/activate

# Create migrations
python manage.py makemigrations core
python manage.py makemigrations reference_data
python manage.py makemigrations portfolio

# Apply migrations
python manage.py migrate
```

### Option 2: Using SQL Files Directly

For production or if you need to create tables manually:

**SQLite (Development):**
```bash
cd sql/ddl
sqlite3 ../../db.sqlite3 < 01_core_tables.sql
sqlite3 ../../db.sqlite3 < 02_portfolio_tables.sql
sqlite3 ../../db.sqlite3 < 03_reference_data_tables.sql
sqlite3 ../../db.sqlite3 < 04_udf_tables.sql
```

**MySQL (Production):**
```bash
mysql -u root -p trade_management < ddl/01_core_tables.sql
mysql -u root -p trade_management < ddl/02_portfolio_tables.sql
mysql -u root -p trade_management < ddl/03_reference_data_tables.sql
mysql -u root -p trade_management < ddl/04_udf_tables.sql
```

**Kudu/Impala (ACL Tables):**
```bash
# Connect to Impala
impala-shell -i lxmrwtsgv0d1.sg.uobnet.com:21050 -d gmp_cis

# Execute ACL DDL
[localhost:21050] > USE gmp_cis;
[localhost:21050] > source sql/ddl/05_acl_tables_kudu.sql;
```

## Loading Sample Data

### Step 1: Create Users

```bash
python manage.py shell << 'EOF'
from django.contrib.auth.models import User, Group

# Superuser
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@cistrade.com', 'admin@2025')

# Makers
maker1 = User.objects.create_user('maker1', 'maker1@cistrade.com', 'maker@2025')
maker1.first_name, maker1.last_name = 'John', 'Doe'
maker1.save()

maker2 = User.objects.create_user('maker2', 'maker2@cistrade.com', 'maker@2025')
maker2.first_name, maker2.last_name = 'Jane', 'Smith'
maker2.save()

# Checkers
checker1 = User.objects.create_user('checker1', 'checker1@cistrade.com', 'checker@2025')
checker1.first_name, checker1.last_name = 'Mike', 'Johnson'
checker1.save()

checker2 = User.objects.create_user('checker2', 'checker2@cistrade.com', 'checker@2025')
checker2.first_name, checker2.last_name = 'Sarah', 'Williams'
checker2.save()

# Viewer
viewer1 = User.objects.create_user('viewer1', 'viewer1@cistrade.com', 'viewer@2025')
viewer1.first_name, viewer1.last_name = 'Bob', 'Brown'
viewer1.save()

# Groups
makers_group, _ = Group.objects.get_or_create(name='Makers')
checkers_group, _ = Group.objects.get_or_create(name='Checkers')
viewers_group, _ = Group.objects.get_or_create(name='Viewers')

# Assign to groups
maker1.groups.add(makers_group)
maker2.groups.add(makers_group)
checker1.groups.add(checkers_group)
checker2.groups.add(checkers_group)
viewer1.groups.add(viewers_group)

print("✓ Users created successfully!")
EOF
```

### Step 2: Load Reference Data

```bash
cd sql/sample_data

# SQLite
sqlite3 ../../db.sqlite3 < 02_currencies.sql
sqlite3 ../../db.sqlite3 < 03_countries.sql
sqlite3 ../../db.sqlite3 < 04_calendars.sql
sqlite3 ../../db.sqlite3 < 05_counterparties.sql

# MySQL
mysql -u root -p trade_management < 02_currencies.sql
mysql -u root -p trade_management < 03_countries.sql
mysql -u root -p trade_management < 04_calendars.sql
mysql -u root -p trade_management < 05_counterparties.sql
```

### Step 3: Load Portfolio Data

```bash
# SQLite
sqlite3 ../../db.sqlite3 < 06_portfolios.sql

# MySQL
mysql -u root -p trade_management < 06_portfolios.sql
```

### Step 4: Load ACL Data (Kudu/Impala)

```bash
impala-shell -i lxmrwtsgv0d1.sg.uobnet.com:21050 -d gmp_cis -f 07_acl_permissions_kudu.sql
```

## Sample Data Overview

### Users (6 users)
| Username  | Role      | Password      | Description                           |
|-----------|-----------|---------------|---------------------------------------|
| admin     | Admin     | admin@2025    | Full system access                    |
| maker1    | Maker     | maker@2025    | Can create/edit portfolios            |
| maker2    | Maker     | maker@2025    | Can create/edit portfolios            |
| checker1  | Checker   | checker@2025  | Can approve/reject                    |
| checker2  | Checker   | checker@2025  | Can approve/reject                    |
| viewer1   | Viewer    | viewer@2025   | Read-only access                      |

### Currencies (25 major currencies)
- USD, EUR, GBP, JPY, SGD, AUD, CAD, CHF
- CNY, HKD, NZD, SEK, NOK, DKK, INR, MYR
- THB, KRW, PHP, IDR, ZAR, BRL, MXN, TRY, RUB

### Countries (30 countries)
- Major economies and trading partners
- Includes region, continent, and currency mapping

### Calendars (40+ holidays for 2025)
- SGX (Singapore Exchange) - 11 holidays
- NYSE (New York Stock Exchange) - 10 holidays
- LSE (London Stock Exchange) - 8 holidays

### Counterparties (20 entities)
- 5 Banks: HSBC, DBS, UOB, OCBC, Citi
- 5 Brokers: Goldman Sachs, Morgan Stanley, JP Morgan, BAML, UBS
- 5 Corporates: Apple, Microsoft, Google, Amazon, Tesla
- 5 Institutional: BlackRock, Vanguard, Fidelity, State Street, PIMCO

### Portfolios (8 portfolios with various states)
1. **PORT-USD-001** - ACTIVE (Approved and operational)
2. **PORT-EUR-001** - PENDING_APPROVAL (Awaiting checker review)
3. **PORT-SGD-001** - DRAFT (Being prepared)
4. **PORT-JPY-001** - REJECTED (Needs revision)
5. **PORT-MULTI-001** - ACTIVE (Global balanced)
6. **PORT-GBP-001** - ACTIVE (UK Gilts)
7. **PORT-HKD-001** - PENDING_APPROVAL (Hong Kong Tech)
8. **PORT-AUD-001** - CLOSED (Inactive)

### ACL Permissions (Kudu/Impala)
- **Administrators**: Full access to everything
- **Makers**: Create/edit permissions, no approve
- **Checkers**: Approve/reject permissions, no create/edit
- **Viewers**: Read-only access

## Testing Four-Eyes Workflow

### Create a Portfolio (Maker)
```python
from portfolio.models import Portfolio
from django.contrib.auth.models import User

maker = User.objects.get(username='maker1')

portfolio = Portfolio.objects.create(
    code='TEST-001',
    name='Test Portfolio',
    currency='USD',
    manager='Test Manager',
    cash_balance=1000000,
    status='DRAFT',
    created_by=maker
)

# Submit for approval
portfolio.submit_for_approval(maker)
print(f"Portfolio status: {portfolio.status}")  # PENDING_APPROVAL
```

### Approve Portfolio (Checker)
```python
checker = User.objects.get(username='checker1')

# Approve
portfolio.approve(checker, 'Approved after review')
print(f"Portfolio status: {portfolio.status}")  # APPROVED
print(f"Is active: {portfolio.is_active}")  # True
```

### Test Four-Eyes Enforcement
```python
# Try to approve own portfolio (should fail)
try:
    portfolio.approve(maker, 'Self approval')
except ValidationError as e:
    print(f"Error: {e}")  # Four-Eyes principle violation
```

## Verifying Data

### Check Record Counts
```sql
-- SQLite / MySQL
SELECT 'Currencies' as entity, COUNT(*) as count FROM reference_currency
UNION ALL
SELECT 'Countries', COUNT(*) FROM reference_country
UNION ALL
SELECT 'Calendars', COUNT(*) FROM reference_calendar
UNION ALL
SELECT 'Counterparties', COUNT(*) FROM reference_counterparty
UNION ALL
SELECT 'Portfolios', COUNT(*) FROM portfolio
UNION ALL
SELECT 'Audit Logs', COUNT(*) FROM core_audit_log;
```

Expected results:
- Currencies: 25
- Countries: 30
- Calendars: 40+
- Counterparties: 20
- Portfolios: 8
- Audit Logs: (varies based on activity)

## Backup and Restore

### Backup
```bash
# SQLite
sqlite3 db.sqlite3 .dump > backup_$(date +%Y%m%d).sql

# MySQL
mysqldump -u root -p trade_management > backup_$(date +%Y%m%d).sql
```

### Restore
```bash
# SQLite
sqlite3 db.sqlite3 < backup_20251217.sql

# MySQL
mysql -u root -p trade_management < backup_20251217.sql
```

## Notes

1. **Production Setup**: For production, use MySQL with proper backup procedures
2. **Kudu Integration**: ACL tables should be in Kudu for enterprise deployment
3. **Data Sync**: Reference data is cached from Kudu; use ETL jobs to sync
4. **Security**: Change all default passwords in production
5. **Testing**: Use SQLite for development, MySQL for staging/production

## Support

For database issues or questions:
- Check Django migrations: `python manage.py showmigrations`
- Verify connections: `python manage.py dbshell`
- Review logs: Check `logs/cistrade.log`

---

**CisTrade Database Setup** © 2025
