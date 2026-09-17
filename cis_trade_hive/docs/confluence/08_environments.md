# Environments & Configuration

> **Audience:** Developer, Support, New Joiner (technical)
> **Read time:** ~10 minutes

---

## Environments at a Glance

| Environment | Purpose | Database host | Auth |
|-------------|---------|---------------|------|
| **LOCAL** | Developer laptop | `localhost:21050` (Docker) | NOSASL (no auth) |
| **SIT** | System Integration Testing | Cloudera CML cluster | GSSAPI (Kerberos) |
| **UAT** | User Acceptance Testing | Cloudera CML cluster | GSSAPI (Kerberos) |
| **PROD** | Production | Cloudera CML cluster | GSSAPI (Kerberos) |
| **DR** | Disaster Recovery failover | Separate cluster | GSSAPI (Kerberos) |

---

## Local Development Setup

### Prerequisites
- Python 3.12
- Docker (for local Kudu/Impala)

### Steps
```bash
# 1. Clone repo and set up virtual environment
cd cis_trade_hive
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Start Docker Kudu/Impala container
docker start kudu-impala

# 3. Create .env file (copy from .env.example)
cp .env.example .env
# Edit .env — LOCAL settings are pre-filled

# 4. Create Kudu tables
impala-shell -i localhost:21050 -f sql/ddl/00_all_kudu_tables_docker.sql

# 5. Test connection
python manage.py test_hive

# 6. Run dev server
python manage.py runserver 0.0.0.0:8000

# Open: http://localhost:8000
```

### Environment Variables (.env) — Local

```ini
CIS_ENV=LOCAL
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=your-dev-secret-key

# Impala/Kudu — Local Docker
IMPALA_HOST=localhost
IMPALA_PORT=21050
IMPALA_DB=gmp_cis
IMPALA_AUTH=NOSASL
IMPALA_TIMEOUT=60
IMPALA_POOL_SIZE=10

# Django DB (for sessions) — Local SQLite
DB_ENGINE=django.db.backends.sqlite3
DB_NAME=db.sqlite3

# RBAC
RBAC_VERSION=v2
SKIP_PERMISSION_CHECKS=False

# Audit
AUDIT_ASYNC_ENABLED=True
AUDIT_ONLY_WRITES=False
AUDIT_LOGGER_TYPE=console
```

---

## SIT / UAT / PROD Configuration

These run on Cloudera CML (Cloudera Machine Learning). Kerberos authentication is required.

### Environment Variables — SIT/UAT/PROD

```ini
CIS_ENV=SIT   # or UAT, PROD

# Impala/Kudu — Cloudera CML
IMPALA_HOST=<cloudera-impala-coordinator>
IMPALA_PORT=21050
IMPALA_DB=gmp_cis
IMPALA_AUTH=GSSAPI
IMPALA_TIMEOUT=60
IMPALA_POOL_SIZE=35

# Hive (for managed tables)
HIVE_HOST=<cloudera-hiveserver2>
HIVE_PORT=10000
HIVE_DB=mrw_ima
HIVE_AUTH=GSSAPI

# Kerberos
KRB_PRINCIPAL=cis_svc@YOURDOMAIN.COM
KRB_KEYTAB=/etc/security/cis_svc.keytab
KRB_CCNAME=/tmp/krb_ccache_cis

# Django DB — MySQL on CML
DB_ENGINE=django.db.backends.mysql
DB_HOST=<mysql-host>
DB_NAME=cis_db
DB_USER=cis_app
DB_PASSWORD=<password>

# RBAC
RBAC_VERSION=v2
SKIP_PERMISSION_CHECKS=False

# Audit
AUDIT_ASYNC_ENABLED=True
AUDIT_ONLY_WRITES=True
AUDIT_LOGGER_TYPE=impala
AUDIT_ASYNC_WORKERS=4
```

---

## Key Management Commands

| Command | What it does |
|---------|-------------|
| `python manage.py test_hive` | Test Impala connection — prints "OK" or error |
| `python manage.py create_hive_db` | Create all Kudu tables (dev only) |
| `python manage.py process_settlements` | EOD: settle validated trades |
| `python manage.py refresh_positions` | Recalculate AVP positions |
| `python manage.py run_trade_event_worker` | Start async event queue worker |
| `python manage.py process_corporate_actions` | EOD: process CA cash flows |
| `python manage.py collectstatic --noinput` | Gather static files for production |

---

## Impala Connection Details

The connection pool is managed by `core/repositories/impala_connection.py` (singleton).

| Setting | Local | SIT/UAT/PROD |
|---------|-------|-------------|
| Host | localhost | Cloudera coordinator |
| Port | 21050 | 21050 |
| Auth | NOSASL | GSSAPI |
| Pool size | 10 | 35 |
| Connection TTL | 30 min | 30 min |
| Timeout | 60s | 60s |
| Hard limit | 64 total | 64 total per worker |

### Testing the Connection
```bash
# Via management command
python manage.py test_hive

# Via impala-shell directly
impala-shell -i localhost:21050 -q "SHOW DATABASES"          # Local
impala-shell -i <host>:21050 --kerberos -q "SHOW DATABASES"  # SIT/UAT/PROD
```

---

## DDL Files (Creating Tables)

SQL DDL scripts are in `sql/ddl/`, numbered in dependency order.

| File | What it creates |
|------|----------------|
| `00_all_kudu_tables_docker.sql` | All tables for local Docker setup (single file) |
| `00_all_kudu_tables_sit.sql` | All tables for SIT (single file, SIT-specific config) |
| `01_core_tables.sql` | `cis_audit_log`, `cis_sequence`, `cis_system_date` |
| `02_portfolio_tables.sql` | `cis_portfolio`, `cis_portfolio_history` |
| `03_reference_data_tables.sql` | Currencies, countries, calendars |
| `04_udf_tables.sql` | UDF definitions and values |
| `05_acl_tables_kudu.sql` | RBAC V1 tables |
| `06_trade_tables_kudu.sql` | `cis_trade`, `cis_trade_history` |
| `50_rbac_tables_kudu.sql` | RBAC V2 tables |
| `99_sit_clean_gmp_cis.sql` | DROP all tables (SIT cleanup before migration) |

---

## Spark Configuration (Cloudera CML)

Used by migration/backup scripts:

```python
SparkSession.builder
    .master("yarn")
    .config("spark.submit.deployMode", "client")
    .config("spark.sql.extensions",
            "com.qubole.spark.hiveacid.HiveAcidAutoConvertExtension")
    .config("spark.sql.hive.hwc.execution.mode", "spark")
    .config("spark.datasource.hive.warehouse.read.jdbc.mode", "cluster")
    .config("spark.kryo.registrator",
            "com.qubole.spark.hiveacid.util.HiveAcidKryoRegistrator")
    .config("spark.kudu.master", "<kudu-master>:7051")
    .enableHiveSupport()
```

JAR paths on Cloudera:
```
/app/cloudera/parcels/SPARK3/lib/spark3/hue_for_spark3/hive-warehouse-connector-spark3-assembly-*.jar
/app/cloudera/parcels/CDH/jars/kudu-spark3_2.12-1.17.0.7.1.9.1054-4.jar
/app/cloudera/parcels/CDH/jars/kudu-client-3.17.0.7.1.9.1054-4.jar
```

---

## Production Server

```bash
# Start production server (Gunicorn)
gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 4 \
    --threads 4 \
    --timeout 120

# Startup script for CML
scripts/cml_startup.sh
```

Performance targets:
- 500 concurrent users
- < 1000ms average response time
- Impala pool: 35 connections per worker

---

## For New Joiners: Day 1 Checklist

```
□ Clone repo from GitHub
□ Set up Python 3.12 virtual environment
□ Install requirements: pip install -r requirements.txt
□ Start Docker: docker start kudu-impala
□ Copy .env.example → .env (LOCAL settings work out of the box)
□ Create tables: impala-shell -i localhost:21050 -f sql/ddl/00_all_kudu_tables_docker.sql
□ Test connection: python manage.py test_hive
□ Run server: python manage.py runserver 0.0.0.0:8000
□ Open http://localhost:8000
□ Read: 01_what_is_cis.md (this wiki)
□ Read: 02_architecture.md
□ Read: 03_kudu_vs_hive.md
□ Browse: sql/ddl/ to understand the tables
```
