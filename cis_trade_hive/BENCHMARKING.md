# CisTrade - Performance Benchmarking Guide

**Last Updated:** 2025-12-27
**Target:** 500 Concurrent Users
**Framework:** Locust

---

## Table of Contents

- [Quick Start](#quick-start)
- [Understanding User Scenarios](#understanding-user-scenarios)
- [Running Benchmarks](#running-benchmarks)
- [Interpreting Results](#interpreting-results)
- [Performance Targets](#performance-targets)
- [Optimization Guide](#optimization-guide)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

### Prerequisites

```bash
# Install benchmarking tools
pip install -r requirements-dev.txt

# Verify installation
locust --version
```

### Run Your First Benchmark

```bash
# Terminal 1: Start Django server
python manage.py runserver 0.0.0.0:8000

# Terminal 2: Run quick smoke test (50 users, 2 minutes)
chmod +x run_benchmark.sh
./run_benchmark.sh quick
```

Results will be saved to `benchmark_results/quick_50users_[timestamp]/`

---

## Understanding User Scenarios

### User Behavior Profiles

Locust simulates realistic user behavior with 5 user types:

#### 1. PortfolioUser (40% of users)
**Behavior:** Traders managing portfolios

**Actions:**
- View portfolio list (most common)
- Search portfolios by name, currency, status
- Filter by status
- View portfolio details
- Export portfolios to CSV
- Create new portfolios (makers only)

**Wait Time:** 2-5 seconds between actions

**Example Flow:**
```
Login → Portfolio List → Search "USD" → View Detail → Export CSV → Logout
```

#### 2. ReferenceDataUser (30% of users)
**Behavior:** Operations team checking reference data

**Actions:**
- View currencies, countries, calendars, counterparties
- Search counterparties
- Export reference data to CSV

**Wait Time:** 3-8 seconds between actions

**Example Flow:**
```
Login → Currency List → Counterparty List → Search "Bank" → Export CSV
```

#### 3. UDFUser (15% of users)
**Behavior:** Admins configuring custom fields

**Actions:**
- View UDF definitions
- Filter by entity type (PORTFOLIO, TRADE, etc.)
- View UDF details

**Wait Time:** 5-10 seconds between actions

**Example Flow:**
```
Login → UDF List → Filter "PORTFOLIO" → View Detail → Edit UDF
```

#### 4. DashboardUser (15% of users)
**Behavior:** Managers monitoring system

**Actions:**
- View dashboard
- Check audit logs
- Monitor recent activity

**Wait Time:** 10-20 seconds between actions

**Example Flow:**
```
Login → Dashboard → Audit Log → Review Activity
```

#### 5. MixedUser (Power Users)
**Behavior:** Users navigating across all modules

**Task Distribution:**
- 50% Portfolio operations
- 30% Reference data checks
- 10% UDF configuration
- 10% Dashboard monitoring

---

## Running Benchmarks

### Using the Benchmark Script

The `run_benchmark.sh` script provides preset scenarios:

#### 1. Quick Smoke Test
```bash
./run_benchmark.sh quick
```
- **Users:** 50
- **Duration:** 2 minutes
- **Use Case:** Post-deployment sanity check
- **Expected Time:** ~2.5 minutes

#### 2. Standard Benchmark (500 Users)
```bash
./run_benchmark.sh standard
```
- **Users:** 500 concurrent
- **Spawn Rate:** 10 users/second
- **Duration:** 10 minutes
- **Use Case:** Regular performance validation
- **Expected Time:** ~11 minutes

#### 3. Stress Test
```bash
./run_benchmark.sh stress
```
- **Users:** 1000+ concurrent
- **Spawn Rate:** 50 users/second
- **Duration:** 5 minutes
- **Use Case:** Find breaking point
- **Expected Time:** ~6 minutes

#### 4. Soak Test
```bash
./run_benchmark.sh soak
```
- **Users:** 200 concurrent
- **Duration:** 2 hours
- **Use Case:** Detect memory leaks
- **Expected Time:** ~2 hours

### Using Locust Web UI (Recommended)

The web UI provides real-time monitoring and control:

```bash
# Start Locust
locust --host=http://localhost:8000

# Open browser
open http://localhost:8089

# Configure test:
# - Number of users: 500
# - Spawn rate: 10
# - Host: http://localhost:8000

# Click "Start Swarming"
```

**Benefits:**
- ✅ Real-time charts
- ✅ Live statistics
- ✅ Adjust users on the fly
- ✅ Stop/start anytime
- ✅ Download results

### Custom Scenarios

#### Test Specific User Type

```bash
# Test only Portfolio users
locust --host=http://localhost:8000 --users 200 PortfolioUser

# Test only Reference Data users
locust --host=http://localhost:8000 --users 100 ReferenceDataUser
```

#### Headless with Custom Parameters

```bash
locust \
  --host=http://localhost:8000 \
  --users 300 \
  --spawn-rate 15 \
  --run-time 15m \
  --headless \
  --html=my_report.html \
  --csv=my_stats
```

### Distributed Load Testing

For testing beyond single machine capacity:

```bash
# Terminal 1: Start master
locust --host=http://localhost:8000 --master

# Terminal 2-N: Start workers
locust --host=http://localhost:8000 --worker --master-host=localhost
locust --host=http://localhost:8000 --worker --master-host=localhost
locust --host=http://localhost:8000 --worker --master-host=localhost

# Access web UI at http://localhost:8089
```

---

## Interpreting Results

### HTML Report Structure

After each benchmark, open `benchmark_results/[scenario]/report.html`:

#### 1. Statistics Table

| Column | Meaning | Good Value | Investigate If |
|--------|---------|------------|----------------|
| **Type** | Request method | GET/POST | - |
| **Name** | Endpoint | Portfolio List | - |
| **# Requests** | Total count | >1000 | <100 (low traffic) |
| **# Fails** | Failed requests | 0 | >0 |
| **Median (ms)** | 50th percentile | <300 | >1000 |
| **95%ile (ms)** | 95th percentile | <2000 | >3000 |
| **Average (ms)** | Mean response time | <1000 | >2000 |
| **Min (ms)** | Fastest request | <50 | >500 |
| **Max (ms)** | Slowest request | <5000 | >10000 |
| **RPS** | Requests/second | >2 | <0.5 |

#### 2. Response Time Charts

**Charts to Analyze:**

- **Total Requests per Second:** Should be steady, not declining
- **Response Times (ms):** Should be flat, not increasing
- **Number of Users:** Ramp-up visualization
- **Total Requests:** Should increase linearly

**Red Flags:**
- 📈 Response times increasing over time (memory leak?)
- 📉 RPS decreasing over time (resource exhaustion?)
- 🔺 Spike in response times (database timeout?)
- ⚠️ High failure rate (errors under load?)

#### 3. Failure Analysis

If failures occur, check `benchmark_results/[scenario]/stats_failures.csv`:

```csv
Method,Name,Error,Occurrences
GET,/portfolio/,ConnectionError: Connection refused,15
POST,/portfolio/create/,500 Internal Server Error,3
```

**Common Failures:**

| Error | Likely Cause | Fix |
|-------|-------------|-----|
| **ConnectionError** | Server crashed | Check server logs, increase resources |
| **500 Internal Server Error** | Application error | Check Django logs |
| **502 Bad Gateway** | Server overloaded | Add more servers |
| **Timeout** | Slow query | Optimize database queries |
| **Too Many Connections** | DB pool exhausted | Increase connection pool |

### CSV Statistics Files

Three CSV files are generated:

#### 1. `stats_stats.csv` - Request Statistics

```csv
Type,Name,Request Count,Failure Count,Median Response Time,Average Response Time...
GET,/portfolio/,5420,0,245,287...
GET,/reference-data/currency/,3210,0,156,178...
```

#### 2. `stats_failures.csv` - Failure Details

```csv
Method,Name,Error,Occurrences
GET,/portfolio/123/,404 Not Found,25
```

#### 3. `stats_history.csv` - Time-Series Data

```csv
Timestamp,User Count,Type,Name,Requests/s,Failures/s,50%,95%...
1640000000,100,GET,/portfolio/,15.3,0,250,890...
```

Use this for creating custom charts in Excel/Pandas.

---

## Performance Targets

### Response Time Targets (500 Users)

| Operation | Median | 95th %ile | 99th %ile | Status |
|-----------|--------|-----------|-----------|--------|
| **Portfolio List** | <300ms | <800ms | <1500ms | ✅ Target |
| **Portfolio Detail** | <200ms | <500ms | <1000ms | ✅ Target |
| **Search** | <500ms | <1200ms | <2000ms | ⚠️ Monitor |
| **Create/Edit** | <800ms | <1500ms | <2500ms | ⚠️ Monitor |
| **CSV Export** | <2000ms | <5000ms | <8000ms | ⚠️ Monitor |
| **Dashboard** | <400ms | <1000ms | <1800ms | ✅ Target |

### Throughput Targets

- **Minimum Acceptable:** 100 requests/second
- **Target:** 250 requests/second
- **Excellent:** 500+ requests/second

### Error Rate Targets

- **Normal Load (500 users):** 0% errors
- **Peak Load (800 users):** <0.5% errors
- **Stress Test (1000+ users):** <5% errors

### Resource Utilization

| Resource | Normal | Warning | Critical |
|----------|--------|---------|----------|
| **CPU** | <60% | 60-80% | >80% |
| **Memory** | <70% | 70-85% | >85% |
| **DB Connections** | <50% pool | 50-80% | >80% |
| **Disk I/O** | <30% | 30-50% | >50% |

---

## Optimization Guide

### If Response Times Are Slow

#### 1. Identify Slow Endpoints

Look at the statistics table, sort by "Average" column:

```
Name                              Average (ms)
Portfolio List                    1250          ← SLOW
Portfolio Detail                  450
Create Portfolio                  2100          ← VERY SLOW
```

#### 2. Profile the Slow Endpoint

```bash
# Install django-silk
pip install django-silk

# Add to INSTALLED_APPS and MIDDLEWARE
# Access /silk/ to see query breakdown
```

#### 3. Common Fixes

**Database Queries:**
```python
# Bad: N+1 queries
portfolios = Portfolio.objects.all()
for p in portfolios:
    print(p.manager.name)  # Query for each!

# Good: Use select_related
portfolios = Portfolio.objects.select_related('manager').all()
for p in portfolios:
    print(p.manager.name)  # No extra queries
```

**Caching:**
```python
from django.core.cache import cache

def get_currencies():
    result = cache.get('currencies')
    if result is None:
        result = currency_repository.list_all()
        cache.set('currencies', result, timeout=3600)
    return result
```

**Pagination:**
```python
# Always limit queries
portfolios = portfolio_hive_repository.get_all_portfolios(limit=100)
```

### If Throughput Is Low

#### Symptoms:
- Low requests/second (<50 RPS)
- Server CPU at 100%
- Long request queues

#### Fixes:

**1. Enable Database Connection Pooling**

```python
# config/settings.py
DATABASES = {
    'default': {
        'CONN_MAX_AGE': 600,  # Keep connections for 10 minutes
    }
}
```

**2. Use Gunicorn with Multiple Workers**

```bash
# Install gunicorn
pip install gunicorn

# Run with 4 workers (2-4x CPU cores)
gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000
```

**3. Enable Query Result Caching in Impala**

```sql
-- Enable result caching
SET QUERY_RESULTS_CACHE=true;
```

### If Memory Usage Is High

#### Symptoms:
- Memory increasing over time
- Server OOM (Out of Memory) errors
- Slow garbage collection

#### Fixes:

**1. Fix Query Memory Leaks**

```python
# Bad: Loads entire table into memory
all_portfolios = portfolio_hive_repository.get_all_portfolios()  # Could be 100k rows!

# Good: Use pagination
portfolios = portfolio_hive_repository.get_all_portfolios(limit=100, offset=page*100)
```

**2. Use Generators for Large Exports**

```python
# Bad: Loads all data at once
def export_csv(request):
    data = get_all_portfolios()  # 10 MB in memory
    return csv_response(data)

# Good: Stream with generator
def export_csv(request):
    def data_generator():
        for row in get_portfolios_batch():  # Batch of 1000
            yield row

    return StreamingHttpResponse(data_generator(), content_type='text/csv')
```

**3. Monitor Memory with Soak Test**

```bash
# Run 2-hour soak test
./run_benchmark.sh soak 200 2h

# Monitor memory
watch -n 5 'ps aux | grep python'
```

---

## Troubleshooting

### Server Won't Start

```bash
# Check if port is already in use
lsof -i :8000

# Kill existing process
kill -9 <PID>

# Restart server
python manage.py runserver 0.0.0.0:8000
```

### Locust Can't Connect

```bash
# Test server manually
curl -v http://localhost:8000/dashboard/

# Check firewall
sudo ufw status

# Check Django ALLOWED_HOSTS
# config/settings.py
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
```

### High Error Rate

```bash
# Check Django logs
tail -f logs/cistrade.log

# Check for specific errors
grep ERROR logs/cistrade.log | tail -20

# Check database connectivity
python manage.py shell
>>> from core.repositories.impala_connection import impala_manager
>>> impala_manager.execute_query("SELECT 1")
```

### Results Look Strange

**Symptom:** Response times are 0ms or extremely low

**Cause:** Not actually hitting the server (cached responses, wrong host)

**Fix:**
```bash
# Verify host in locustfile.py or command line
locust --host=http://localhost:8000  # Must match running server

# Check server logs to confirm requests
tail -f logs/cistrade.log  # Should see GET/POST requests
```

### Database Timeouts

```bash
# Check Impala query timeouts
# Increase timeout in settings
IMPALA_QUERY_TIMEOUT = 120  # seconds

# Check for long-running queries
# See PROJECT_MANAGEMENT.md for Impala monitoring queries
```

---

## Benchmark Checklist

Before running a production benchmark:

### Pre-Benchmark

- [ ] Server is running and healthy
- [ ] Database is accessible (test with `python manage.py shell`)
- [ ] No other load on the server (close other apps)
- [ ] Disk space available (>10GB free)
- [ ] Monitoring tools ready (htop, vmstat)
- [ ] Baseline metrics recorded (CPU, memory at rest)

### During Benchmark

- [ ] Monitor server resources (CPU, memory, disk I/O)
- [ ] Watch for errors in Django logs
- [ ] Check database connection pool usage
- [ ] Note any warnings or unusual behavior

### Post-Benchmark

- [ ] Save results to benchmark_results/
- [ ] Review HTML report
- [ ] Check for failures in CSV
- [ ] Compare with previous benchmarks
- [ ] Document findings
- [ ] Create tickets for performance issues

---

## Continuous Benchmarking

### Weekly Benchmarks

Run every Monday before sprint planning:

```bash
# Automated weekly benchmark
./run_benchmark.sh standard 500 10m

# Compare with baseline
python scripts/compare_benchmarks.py \
  benchmark_results/baseline/ \
  benchmark_results/latest/
```

### Pre-Release Benchmarks

Before every production deployment:

```bash
# 1. Quick smoke test
./run_benchmark.sh quick

# 2. If smoke test passes, standard benchmark
./run_benchmark.sh standard

# 3. Document results in release notes
```

### Regression Detection

Track performance over time:

```python
# scripts/benchmark_tracker.py
import pandas as pd

baseline = pd.read_csv('benchmark_results/baseline/stats_stats.csv')
current = pd.read_csv('benchmark_results/latest/stats_stats.csv')

# Compare average response times
baseline_avg = baseline.groupby('Name')['Average Response Time'].mean()
current_avg = current.groupby('Name')['Average Response Time'].mean()

regression = current_avg / baseline_avg > 1.2  # >20% slower
if regression.any():
    print("PERFORMANCE REGRESSION DETECTED:")
    print(regression[regression == True])
```

---

## Best Practices

1. **Run on Isolated Environment**
   - Don't benchmark on your development machine
   - Use dedicated test server
   - No other processes running

2. **Warm Up First**
   - Run 1-2 minute warm-up before official benchmark
   - Allows connection pools to fill, caches to warm

3. **Consistent Data Set**
   - Use same database state for each benchmark
   - Reset between runs if needed
   - Document data size (number of portfolios, etc.)

4. **Multiple Runs**
   - Run benchmark 3 times, take median
   - Discard outliers (network hiccups, etc.)

5. **Document Everything**
   - Server specs (CPU, RAM)
   - Database size
   - Code version (git commit hash)
   - Environment variables

6. **Incremental Load**
   - Don't jump from 0 to 500 users instantly
   - Use spawn rate of 10-20 users/second
   - Allows system to adjust

---

## Appendix: Benchmark Data Sheet

Copy this template for each benchmark run:

```
BENCHMARK DATA SHEET
====================

Date: _______________
Tester: ______________
Scenario: ____________

## Environment
- Django Version: ___________
- Python Version: ___________
- Server CPU: ___________
- Server RAM: ___________
- Database: Kudu/Impala (version: _______)

## Configuration
- Users: ___________
- Spawn Rate: ___________
- Duration: ___________
- Test Data Size: _____ portfolios, _____ UDFs, _____ counterparties

## Results
- Total Requests: ___________
- Failed Requests: ___________
- Requests/Second: ___________
- Average Response Time: _____ms
- 95th Percentile: _____ms
- Error Rate: _____%

## Resource Usage (Peak)
- CPU: _____%
- Memory: _____%
- Disk I/O: _____%
- DB Connections: _____

## Issues Found
1. ___________
2. ___________

## Action Items
1. ___________
2. ___________
```

---

**CisTrade Benchmarking** © 2025
