# CisTrade - Project Management Documentation

**Last Updated:** 2025-12-27
**Project Manager:** Development Team
**Target Release:** Q1 2026

---

## Table of Contents

1. [Benchmarking Strategy](#benchmarking-strategy)
2. [Performance Targets](#performance-targets)
3. [Housekeeping & Technical Debt](#housekeeping--technical-debt)
4. [Database Optimization](#database-optimization)
5. [Monitoring & Observability](#monitoring--observability)
6. [Quality Gates](#quality-gates)
7. [Project Roadmap](#project-roadmap)
8. [Risk Management](#risk-management)
9. [Capacity Planning](#capacity-planning)
10. [Deployment Strategy](#deployment-strategy)

---

## Benchmarking Strategy

### Overview

CisTrade must support **500 concurrent users** with acceptable performance under normal and peak load conditions.

### Load Testing Framework: Locust

**Why Locust?**
- ✅ Python-based (matches our tech stack)
- ✅ Distributed load generation
- ✅ Real-time web UI for monitoring
- ✅ Easy to define realistic user behavior
- ✅ Excellent reporting capabilities

### User Behavior Profiles

Based on real-world usage analysis:

| User Type | % of Users | Wait Time | Primary Actions |
|-----------|------------|-----------|-----------------|
| **Portfolio Traders** | 40% | 2-5s | CRUD portfolios, search, export |
| **Reference Data Ops** | 30% | 3-8s | View ref data, search, export CSV |
| **UDF Admins** | 15% | 5-10s | Configure UDFs, manage options |
| **Dashboard Monitors** | 15% | 10-20s | View dashboard, audit logs |

### Test Scenarios

#### 1. Quick Smoke Test
```bash
./run_benchmark.sh quick 50 2m
```
- **Users:** 50
- **Duration:** 2 minutes
- **Purpose:** Rapid sanity check after deployments
- **Success Criteria:** 0% errors, <500ms avg response time

#### 2. Standard Benchmark (Target: 500 Users)
```bash
./run_benchmark.sh standard 500 10m
```
- **Users:** 500 concurrent
- **Spawn Rate:** 10 users/second
- **Duration:** 10 minutes
- **Success Criteria:**
  - ✅ 0% error rate
  - ✅ Avg response time <1000ms
  - ✅ 95th percentile <2000ms
  - ✅ Requests/sec >100

#### 3. Stress Test
```bash
./run_benchmark.sh stress 1000 5m
```
- **Users:** 1000+ concurrent
- **Purpose:** Find breaking point
- **Success Criteria:**
  - Identify max capacity before degradation
  - Graceful degradation (no crashes)
  - Error rate <5% at peak

#### 4. Soak Test
```bash
./run_benchmark.sh soak 200 2h
```
- **Users:** 200 concurrent
- **Duration:** 2-4 hours
- **Purpose:** Detect memory leaks, resource exhaustion
- **Success Criteria:**
  - Stable memory usage over time
  - No degradation in response times
  - No database connection leaks

### Key Performance Metrics

#### Response Time Targets

| Operation Type | Median | 95th %ile | 99th %ile | Max Acceptable |
|----------------|--------|-----------|-----------|----------------|
| **List Views** | <300ms | <800ms | <1500ms | 2000ms |
| **Detail Views** | <200ms | <500ms | <1000ms | 1500ms |
| **Search** | <500ms | <1200ms | <2000ms | 3000ms |
| **Create/Update** | <800ms | <1500ms | <2500ms | 4000ms |
| **CSV Export** | <2000ms | <5000ms | <8000ms | 10000ms |
| **Dashboard** | <400ms | <1000ms | <1800ms | 2500ms |

#### Throughput Targets

- **Minimum:** 100 requests/second
- **Target:** 250 requests/second
- **Peak:** 500 requests/second

#### Error Rate Targets

- **Normal Load:** 0% error rate
- **Peak Load:** <0.5% error rate
- **Stress Test:** <5% error rate

### Running Benchmarks

#### Prerequisites

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Ensure server is running
python manage.py runserver 0.0.0.0:8000

# (In another terminal) Run benchmark
chmod +x run_benchmark.sh
./run_benchmark.sh standard 500 10m
```

#### Using Locust Web UI (Recommended)

```bash
# Start Locust web interface
locust --host=http://localhost:8000

# Open browser at http://localhost:8089
# Configure users, spawn rate, and start test
# Monitor real-time charts and statistics
```

#### Headless Mode (CI/CD)

```bash
locust \
  --host=http://localhost:8000 \
  --users 500 \
  --spawn-rate 10 \
  --run-time 10m \
  --headless \
  --html=report.html \
  --csv=stats
```

### Benchmark Reporting

After each benchmark, results are saved to:

```
benchmark_results/
├── standard_500users_20251227_143022/
│   ├── report.html          # Visual report with charts
│   ├── stats_stats.csv      # Request statistics
│   ├── stats_failures.csv   # Failure details
│   ├── locust.log          # Execution log
│   └── system_stats.log    # System resource usage
```

**Key sections in HTML report:**
- Request statistics table
- Response time charts (median, 95th percentile)
- Requests per second over time
- Number of users over time
- Failure rate analysis

---

## Performance Targets

### Production Targets (500 Users)

| Metric | Target | Alert Threshold | Critical Threshold |
|--------|--------|-----------------|-------------------|
| **Response Time (avg)** | <1000ms | >1500ms | >2000ms |
| **Response Time (p95)** | <2000ms | >3000ms | >4000ms |
| **Error Rate** | 0% | >0.1% | >1% |
| **CPU Usage** | <60% | >75% | >90% |
| **Memory Usage** | <70% | >80% | >90% |
| **Database Connections** | <80% pool | >90% pool | Pool exhausted |
| **Disk I/O Wait** | <5% | >15% | >25% |

### Database Query Performance

| Query Type | Target | Action Required If Exceeded |
|------------|--------|----------------------------|
| **Portfolio List** | <100ms | Add index, optimize query |
| **Reference Data** | <50ms | Cache result |
| **Search Queries** | <200ms | Full-text search index |
| **Joins** | <150ms | Denormalize or cache |
| **Aggregations** | <300ms | Pre-compute or materialize |

---

## Housekeeping & Technical Debt

### Code Quality Tasks

#### Immediate (Sprint 1-2)

- [ ] **Fix Flake8 violations** - Current: 47 issues
  - `flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics`
  - Target: 0 critical issues

- [ ] **Add type hints to remaining modules**
  - Core: 85% done ✅
  - Portfolio: 60% done
  - UDF: 45% done
  - Reference Data: 70% done
  - Target: 95% coverage

- [ ] **Remove unused imports and dead code**
  - Use: `autoflake --remove-all-unused-imports --recursive --in-place .`
  - Estimate: 2-3 hours

#### Short Term (Sprint 3-4)

- [ ] **Refactor long functions (>50 lines)**
  - `portfolio/views.py::portfolio_approve()` - 78 lines
  - `udf/services/udf_service.py::save_udf_values()` - 65 lines
  - Target: Max 40 lines per function

- [ ] **Extract magic numbers to constants**
  - Database query limits (currently hardcoded 1000)
  - Pagination sizes (currently hardcoded 25)
  - Session timeouts

- [ ] **Add docstrings to all public methods**
  - Current coverage: ~60%
  - Target: 95%
  - Use: Google or NumPy style

- [ ] **Consolidate duplicate code**
  - CSV export logic (appears 6 times)
  - Audit logging setup (appears 8 times)
  - Create utility functions

#### Medium Term (Sprint 5-8)

- [ ] **Increase test coverage from 39% to 75%**
  - Service layer tests (priority 1)
  - Dashboard views (priority 2)
  - Edge cases and error paths (priority 3)

- [ ] **Security audit**
  - Run: `bandit -r . -f json -o security_report.json`
  - Fix all HIGH and MEDIUM issues
  - SQL injection review (Impala queries)
  - XSS vulnerability scan

- [ ] **Dependency audit**
  - Run: `safety check --json`
  - Update vulnerable packages
  - Remove unused dependencies

- [ ] **Code complexity analysis**
  - Run: `radon cc . -a -nb`
  - Refactor functions with cyclomatic complexity >10

### Documentation Debt

- [ ] **API documentation with OpenAPI/Swagger**
  - Install: `drf-spectacular`
  - Document all API endpoints
  - Add request/response examples

- [ ] **Architecture Decision Records (ADRs)**
  - Document why Kudu/Impala was chosen
  - Document session-based auth vs JWT
  - Document Four-Eyes workflow design

- [ ] **Database schema documentation**
  - Document all Kudu tables
  - Add ER diagrams
  - Document column meanings and constraints

- [ ] **Runbook for operations**
  - Deployment procedures
  - Rollback procedures
  - Common issues and fixes
  - Monitoring and alerting setup

### Maintenance Tasks

#### Weekly

- [ ] Review and close stale PRs/issues
- [ ] Check for security updates
- [ ] Review error logs and exceptions
- [ ] Monitor slow query log

#### Monthly

- [ ] Dependency updates
- [ ] Database query optimization review
- [ ] Disk space and log rotation
- [ ] Backup verification

#### Quarterly

- [ ] Full security audit
- [ ] Performance benchmark (regression check)
- [ ] Code quality metrics review
- [ ] Technical debt assessment

---

## Database Optimization

### Impala/Kudu Query Optimization

#### Current Issues

1. **Full table scans on portfolio searches**
   - Query: `SELECT * FROM cis_portfolio WHERE name LIKE '%search%'`
   - Execution time: ~800ms for 10k rows
   - **Fix:** Add Kudu hash partition on `name` prefix

2. **Counterparty queries missing index**
   - Query: `SELECT * FROM cis_counterparty WHERE counterparty_type = 'BANK'`
   - Execution time: ~450ms
   - **Fix:** Add range partition on `counterparty_type`

3. **Audit log queries unbounded**
   - Query: `SELECT * FROM cis_audit_log ORDER BY timestamp DESC`
   - Execution time: >2000ms
   - **Fix:** Add date range filter, limit to 90 days

#### Optimization Strategies

**1. Kudu Table Partitioning**

```sql
-- Portfolio table with hash + range partitioning
CREATE TABLE cis_portfolio (
  portfolio_id BIGINT,
  name STRING,
  status STRING,
  created_date TIMESTAMP,
  PRIMARY KEY (portfolio_id, created_date)
)
PARTITION BY
  HASH (portfolio_id) PARTITIONS 8,
  RANGE (created_date) (
    PARTITION VALUES < '2024-01-01',
    PARTITION '2024-01-01' <= VALUES < '2025-01-01',
    PARTITION '2025-01-01' <= VALUES
  )
STORED AS KUDU;
```

**2. Bloom Filters for String Columns**

```sql
ALTER TABLE cis_portfolio
SET TBLPROPERTIES ('kudu.table_hash_schema' = 'name:bloom');
```

**3. Query Result Caching**

```python
# Django caching for reference data (changes infrequently)
from django.core.cache import cache

def get_all_currencies():
    cache_key = 'currencies_list'
    result = cache.get(cache_key)

    if result is None:
        result = currency_repository.list_all()
        cache.set(cache_key, result, timeout=3600)  # 1 hour

    return result
```

**4. Connection Pooling**

```python
# config/settings.py
IMPALA_CONNECTION_POOL = {
    'max_connections': 20,
    'min_connections': 5,
    'connection_timeout': 30,
    'query_timeout': 60,
}
```

### Database Monitoring

**Queries to Monitor:**

```sql
-- Long-running queries
SELECT query_id, user, default_db,
       state, query_state,
       UNIX_TIMESTAMP() - UNIX_TIMESTAMP(start_time) as duration_sec
FROM sys.queries
WHERE state = 'RUNNING'
  AND UNIX_TIMESTAMP() - UNIX_TIMESTAMP(start_time) > 10
ORDER BY duration_sec DESC;

-- Table statistics
SHOW TABLE STATS cis_portfolio;
SHOW COLUMN STATS cis_portfolio;

-- Refresh statistics after bulk loads
COMPUTE STATS cis_portfolio;
```

### Index Strategy

| Table | Current Indexes | Recommended Indexes |
|-------|----------------|---------------------|
| cis_portfolio | PRIMARY KEY (portfolio_id) | + INDEX(name), INDEX(status, is_active) |
| cis_counterparty | PRIMARY KEY (counterparty_id) | + INDEX(counterparty_type), INDEX(name) |
| cis_audit_log | PRIMARY KEY (audit_id) | + INDEX(timestamp, user_id) |
| cis_udf_definition | PRIMARY KEY (udf_id) | + INDEX(entity_type, is_active) |

---

## Monitoring & Observability

### Application Performance Monitoring (APM)

#### Django Debug Toolbar (Development)

```python
# config/settings.py
if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = ['debug_toolbar.middleware.DebugToolbarMiddleware'] + MIDDLEWARE
    INTERNAL_IPS = ['127.0.0.1']
```

**Features:**
- ✅ SQL query analysis
- ✅ Template rendering time
- ✅ Cache performance
- ✅ Request/response inspection

#### Django Silk (Production Profiling)

```python
# config/settings.py
INSTALLED_APPS += ['silk']
MIDDLEWARE += ['silk.middleware.SilkyMiddleware']

SILKY_PYTHON_PROFILER = True
SILKY_PYTHON_PROFILER_BINARY = True
```

**Access:** `/silk/` - View request profiles, SQL queries, slow endpoints

### Logging Strategy

#### Log Levels

```python
# config/settings.py
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{levelname}] {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': 'logs/cistrade.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
        'portfolio': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
        },
        'core.audit': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
        },
    },
}
```

#### Structured Logging

```python
import logging
import json

logger = logging.getLogger(__name__)

def log_action(action, user, entity, status, **kwargs):
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'user': user,
        'entity': entity,
        'status': status,
        **kwargs
    }
    logger.info(json.dumps(log_data))
```

### Metrics Collection

#### System Metrics

```bash
# Install psutil for system monitoring
pip install psutil

# Monitor CPU, memory, disk
python manage.py monitor_system
```

#### Custom Metrics

```python
# Track business metrics
class PortfolioMetrics:
    @staticmethod
    def record_creation(portfolio_code, user, duration_ms):
        # Send to monitoring system (Prometheus, Grafana, etc.)
        metrics.counter('portfolio.created', tags={'user': user})
        metrics.histogram('portfolio.creation_time', duration_ms)
```

### Health Checks

```python
# core/views/health_views.py
from django.http import JsonResponse
from django.db import connection

def health_check(request):
    """Health check endpoint for load balancer"""
    try:
        # Check database
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Check Kudu/Impala
        from core.repositories.impala_connection import impala_manager
        impala_manager.execute_query("SELECT 1")

        return JsonResponse({
            'status': 'healthy',
            'database': 'ok',
            'impala': 'ok',
        })
    except Exception as e:
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e)
        }, status=503)
```

---

## Quality Gates

### Pre-Commit Checks

```bash
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.10.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/flake8
    rev: 7.1.1
    hooks:
      - id: flake8
        args: ['--max-line-length=100', '--ignore=E203,W503']

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

### CI/CD Pipeline Gates

#### Stage 1: Code Quality
- ✅ Black formatting check
- ✅ Flake8 linting (0 errors)
- ✅ Type checking with mypy
- ✅ Security scan with bandit

#### Stage 2: Testing
- ✅ Unit tests (90+ tests passing)
- ✅ Coverage >75% (or improvement over previous)
- ✅ Integration tests
- ✅ No regression in test count

#### Stage 3: Performance
- ✅ Quick smoke test (50 users, 2min)
- ✅ Response time <500ms avg
- ✅ 0% error rate

#### Stage 4: Security
- ✅ Dependency vulnerability scan (safety)
- ✅ No HIGH or CRITICAL vulnerabilities
- ✅ OWASP ZAP scan (if web deployment)

### Definition of Done (DoD)

For a feature to be considered complete:

- [ ] Code written and peer-reviewed
- [ ] Unit tests written (coverage >80% for new code)
- [ ] Integration tests if applicable
- [ ] Documentation updated
- [ ] Benchmark run shows no performance degradation
- [ ] Security review completed
- [ ] Code quality checks pass
- [ ] Accepted by Product Owner
- [ ] Deployed to staging and tested
- [ ] Release notes updated

---

## Project Roadmap

### Q1 2026 - Production Readiness

**Sprint 1-2 (Weeks 1-4): Stability & Performance**
- [ ] Complete benchmark testing (500 users)
- [ ] Fix all HIGH priority bugs
- [ ] Database optimization (Kudu partitioning, indexes)
- [ ] Implement connection pooling
- [ ] Add caching layer for reference data

**Sprint 3-4 (Weeks 5-8): Observability**
- [ ] Set up Django Silk for production profiling
- [ ] Implement structured logging
- [ ] Create monitoring dashboard (Grafana)
- [ ] Set up alerting (PagerDuty/Slack)
- [ ] Health check endpoints

**Sprint 5-6 (Weeks 9-12): Quality & Security**
- [ ] Increase test coverage to 75%
- [ ] Complete security audit
- [ ] Fix all security vulnerabilities
- [ ] API documentation (OpenAPI/Swagger)
- [ ] Load balancer configuration

### Q2 2026 - Feature Enhancements

**Sprint 7-8: Advanced Portfolio Features**
- [ ] Portfolio analytics dashboard
- [ ] Batch operations
- [ ] Portfolio hierarchy (parent/child)
- [ ] Advanced search with saved filters

**Sprint 9-10: Workflow Improvements**
- [ ] Email notifications
- [ ] Approval queue dashboard
- [ ] Bulk approval/rejection
- [ ] Workflow audit trail visualization

**Sprint 11-12: Integration & API**
- [ ] REST API v2 with versioning
- [ ] Webhook support
- [ ] External system integrations
- [ ] API rate limiting

### Q3 2026 - Advanced Features

**Sprint 13-14: Reporting**
- [ ] Custom report builder
- [ ] Scheduled reports
- [ ] PDF export
- [ ] Excel export with formatting

**Sprint 15-16: Analytics**
- [ ] Real-time dashboards
- [ ] Trend analysis
- [ ] Forecasting
- [ ] Data visualization library

### Q4 2026 - Scale & Optimize

**Sprint 17-18: Horizontal Scaling**
- [ ] Multi-region deployment
- [ ] Read replicas
- [ ] CDN integration
- [ ] Cache clustering (Redis)

**Sprint 19-20: Advanced Monitoring**
- [ ] Machine learning anomaly detection
- [ ] Predictive alerting
- [ ] Capacity planning automation
- [ ] Cost optimization

---

## Risk Management

### Technical Risks

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **Kudu/Impala performance under load** | HIGH | HIGH | • Early benchmarking<br>• Database optimization<br>• Caching layer<br>• Connection pooling |
| **Memory leaks in long-running processes** | MEDIUM | HIGH | • Soak testing<br>• Memory profiling<br>• Process restart automation |
| **Database connection exhaustion** | MEDIUM | CRITICAL | • Connection pooling<br>• Connection monitoring<br>• Auto-scaling |
| **Third-party dependency vulnerabilities** | MEDIUM | MEDIUM | • Weekly security scans<br>• Automated updates<br>• Dependency pinning |
| **Data loss during Kudu writes** | LOW | CRITICAL | • Transaction logging<br>• Backup strategy<br>• Write acknowledgment |

### Operational Risks

| Risk | Probability | Impact | Mitigation Strategy |
|------|-------------|--------|---------------------|
| **Insufficient server capacity** | MEDIUM | HIGH | • Capacity planning<br>• Auto-scaling<br>• Load testing |
| **Network latency to Kudu cluster** | MEDIUM | MEDIUM | • Co-location<br>• Connection keep-alive<br>• Query optimization |
| **Deployment failures** | MEDIUM | MEDIUM | • Blue-green deployment<br>• Automated rollback<br>• Canary releases |
| **Knowledge gaps in team** | LOW | MEDIUM | • Documentation<br>• Knowledge sharing<br>• Cross-training |

---

## Capacity Planning

### Current Capacity (Estimated)

**Single Application Server:**
- **CPU:** 4 cores
- **RAM:** 16GB
- **Expected Capacity:** ~200 concurrent users
- **Bottleneck:** Database connections, CPU during searches

### Target Capacity (500 Users)

**Recommended Setup:**

```
Load Balancer (HAProxy/Nginx)
    ↓
App Server 1 (4 CPU, 16GB RAM) - 200 users
App Server 2 (4 CPU, 16GB RAM) - 200 users
App Server 3 (4 CPU, 16GB RAM) - 100 users (buffer)
    ↓
Kudu/Impala Cluster (existing)
```

**Resource Requirements:**
- **Total CPUs:** 12 cores
- **Total RAM:** 48GB
- **Estimated Cost:** $500-800/month (AWS/Azure)

### Scaling Strategy

#### Vertical Scaling (Phase 1)
- Increase single server to 8 CPU, 32GB RAM
- Capacity: ~400 users
- **Pros:** Simple, no code changes
- **Cons:** Single point of failure, limited ceiling

#### Horizontal Scaling (Phase 2)
- Add 2-3 application servers
- Session sharing (Redis/Memcached)
- Capacity: 500+ users
- **Pros:** High availability, unlimited scaling
- **Cons:** More complex, session management needed

---

## Deployment Strategy

### Environments

| Environment | Purpose | Users | Deployment Frequency |
|-------------|---------|-------|---------------------|
| **Development** | Developer testing | 1-5 | Continuous |
| **Testing** | QA testing | 10-20 | Daily |
| **Staging** | Pre-production validation | 50 | Weekly |
| **Production** | Live system | 500+ | Bi-weekly |

### Deployment Process

#### Blue-Green Deployment

```
1. Deploy to "Green" environment (inactive)
2. Run smoke tests on Green
3. Switch traffic from Blue to Green (load balancer)
4. Monitor Green for 30 minutes
5. If issues: Instant rollback to Blue
6. If stable: Blue becomes next Green
```

#### Rollback Plan

```bash
# Automatic rollback if health checks fail
if ! curl -f http://green/health/; then
    echo "Health check failed, rolling back..."
    lb-switch blue
    exit 1
fi
```

### Deployment Checklist

**Pre-Deployment:**
- [ ] All tests passing (CI/CD)
- [ ] Code review approved
- [ ] Database migrations tested
- [ ] Benchmark run completed
- [ ] Rollback plan documented
- [ ] Stakeholders notified

**During Deployment:**
- [ ] Backup current database
- [ ] Run database migrations
- [ ] Deploy application code
- [ ] Restart application servers
- [ ] Run smoke tests
- [ ] Monitor error rates

**Post-Deployment:**
- [ ] Verify all critical flows
- [ ] Monitor for 1 hour
- [ ] Check error logs
- [ ] Review performance metrics
- [ ] Update deployment log

---

## Conclusion

This document provides a comprehensive framework for managing CisTrade from a Project Manager perspective. Regular review and updates are essential as the project evolves.

**Next Review Date:** 2026-01-27

---

**CisTrade Project Management** © 2025
