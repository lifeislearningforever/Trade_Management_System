# Django Silk Profiler - Setup & Usage Guide

**Last Updated:** 2025-12-27

---

## What is Django Silk?

**Django Silk** is a live profiling and inspection tool for Django applications. It acts as a "performance microscope" that shows you exactly what's happening inside your application during request processing.

Think of it as **Developer Tools for Django** - but much more powerful!

---

## Why Use Django Silk?

### Problem: "My page is slow - but why?"

Without Silk, you're guessing:
- Maybe it's the database?
- Maybe it's a slow API call?
- Maybe it's Python code?
- Maybe it's the template rendering?

### Solution: Silk Shows You Exactly Where Time is Spent

```
Request: GET /portfolio/
Total Time: 1,245ms

Breakdown:
- View Code: 45ms
- SQL Queries: 1,150ms ← THE PROBLEM!
  - Query 1: SELECT * FROM cis_portfolio... (234ms)
  - Query 2: SELECT * FROM cis_audit_log... (189ms)
  - Query 3: SELECT * FROM cis_portfolio... (234ms) ← DUPLICATE!
  ...8 more duplicate queries
- Template Rendering: 50ms
```

Now you know: **Fix those SQL queries!**

---

## Key Features

### 1. Request Profiling
- **Every HTTP request** is recorded
- Exact execution time down to milliseconds
- Full request/response headers
- Request body and response content
- Filter and search requests

### 2. SQL Query Analysis
Shows ALL database queries for each request:
```
GET /portfolio/ executed 15 SQL queries (8 duplicates!)

Slow Queries:
1. SELECT * FROM cis_portfolio WHERE status='ACTIVE' - 234ms ⚠️
2. SELECT * FROM cis_audit_log ORDER BY... - 189ms ⚠️

Duplicate Queries (N+1 Problem):
3. SELECT * FROM cis_portfolio WHERE id=1 - 45ms
4. SELECT * FROM cis_portfolio WHERE id=2 - 45ms
5. SELECT * FROM cis_portfolio WHERE id=3 - 45ms
   ↓
   SOLUTION: Use select_related() or prefetch_related()
```

### 3. Python Line-by-Line Profiling
Shows which Python functions are slow:
```
portfolio/views.py::portfolio_list()
Total: 1200ms

Hotspots:
- Line 45: portfolio_hive_repository.get_all() - 950ms ⚠️
- Line 67: [p.to_dict() for p in portfolios] - 180ms
- Line 89: render(request, ...) - 70ms
```

### 4. Live Dashboard
- Real-time request monitoring
- Filter by URL, status code, time
- Sort by response time
- Search by user, method, etc.

---

## Installation

### Step 1: Install Django Silk

```bash
pip install django-silk
```

### Step 2: Add to Django Settings

**File:** `config/settings.py`

```python
# INSTALLED_APPS
INSTALLED_APPS = [
    ...
    'silk',  # Add this
]

# MIDDLEWARE - Add Silk middleware near the TOP
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'silk.middleware.SilkyMiddleware',  # Add here (early in the list)
    'django.contrib.sessions.middleware.SessionMiddleware',
    ...
]

# Silk Configuration
SILKY_PYTHON_PROFILER = True  # Enable Python profiling
SILKY_PYTHON_PROFILER_BINARY = True  # Binary profiling (faster)
SILKY_AUTHENTICATION = True  # Require login to view Silk
SILKY_AUTHORISATION = True  # Check user permissions

# Only enable in development/staging - NOT production
if not DEBUG:
    SILKY_INTERCEPT_PERCENT = 10  # Only profile 10% of requests in production
```

### Step 3: Add Silk URLs

**File:** `config/urls.py`

```python
from django.urls import path, include

urlpatterns = [
    ...
    path('silk/', include('silk.urls', namespace='silk')),  # Add this
]
```

### Step 4: Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

Silk creates its own database tables to store profiling data.

### Step 5: Restart Server

```bash
python manage.py runserver
```

---

## Usage

### Access Silk Dashboard

Visit: **http://localhost:8000/silk/**

You'll see:
- List of all requests
- Response times
- SQL query counts
- Filter and search options

### Analyzing a Slow Request

1. **Find the slow request** in the list
   - Sort by "Time" column
   - Look for requests taking >1000ms

2. **Click on the request** to see details:
   ```
   Request Details
   ===============
   URL: /portfolio/
   Method: GET
   Time: 1,245ms
   Status: 200 OK

   SQL Queries: 15 queries (1,150ms total)
   Python Time: 45ms
   Template Rendering: 50ms
   ```

3. **Click "SQL Queries"** tab:
   ```
   Query 1: 234ms ⚠️ SLOW
   SELECT * FROM gmp_cis.cis_portfolio
   WHERE status = 'ACTIVE'
   ORDER BY created_date DESC
   LIMIT 1000

   Executed in: portfolio/repositories/portfolio_hive_repository.py:45

   [EXPLAIN] button shows query execution plan
   [Raw SQL] shows the actual SQL
   ```

4. **Click "Profiling"** tab (if enabled):
   ```
   Python Function Call Graph:

   portfolio_list() - 1200ms
   ├─ portfolio_hive_repository.get_all() - 950ms
   │  └─ impala_manager.execute_query() - 945ms
   ├─ [list comprehension] - 180ms
   └─ render() - 70ms
   ```

### Common Use Cases

#### 1. Finding N+1 Query Problems

**Symptom:** Many identical queries (just different IDs)

```
Queries (50 total):
1. SELECT * FROM portfolio WHERE id=1
2. SELECT * FROM portfolio WHERE id=2
3. SELECT * FROM portfolio WHERE id=3
...
50. SELECT * FROM portfolio WHERE id=50
```

**Solution:**
```python
# Bad
portfolios = Portfolio.objects.all()
for p in portfolios:
    print(p.manager.name)  # Queries for each!

# Good
portfolios = Portfolio.objects.select_related('manager').all()
for p in portfolios:
    print(p.manager.name)  # No extra queries!
```

#### 2. Finding Slow Queries

**Symptom:** One query takes >500ms

```
Query: 945ms ⚠️
SELECT * FROM gmp_cis.cis_portfolio
WHERE LOWER(name) LIKE '%search%'  ← No index!
```

**Solution:** Add database index or change query
```sql
-- Add index
CREATE INDEX idx_portfolio_name ON cis_portfolio(name);

-- Or use better query
SELECT * FROM cis_portfolio
WHERE name = 'EXACT_MATCH'  -- Uses index
```

#### 3. Finding Memory-Heavy Operations

**Symptom:** Request uses too much memory

Silk shows:
```
Memory Usage:
- Before request: 45MB
- After request: 245MB
- Leaked: 200MB! ⚠️
```

**Common causes:**
- Loading entire tables into memory
- Not using pagination
- Large list comprehensions

**Solution:**
```python
# Bad
all_portfolios = list(Portfolio.objects.all())  # 100k rows in memory!

# Good
portfolios = Portfolio.objects.all()[:100]  # Only 100 rows
# Or use pagination
```

---

## Best Practices

### 1. Use in Development Only

```python
# config/settings.py
if DEBUG:
    INSTALLED_APPS += ['silk']
    MIDDLEWARE = ['silk.middleware.SilkyMiddleware'] + MIDDLEWARE
```

**Why?** Silk adds overhead - not for production!

### 2. Clean Up Old Data

Silk stores all requests in the database - it grows fast!

```bash
# Delete requests older than 7 days
python manage.py silk_clear_request_log

# Or manually via SQL
DELETE FROM silk_request WHERE start_time < DATE_SUB(NOW(), INTERVAL 7 DAY);
```

### 3. Profile Specific Views

Instead of profiling everything, use decorators:

```python
from silk.profiling.profiler import silk_profile

@silk_profile(name='Portfolio List - Heavy Operation')
def get_all_portfolios():
    # This specific function will be profiled
    return portfolio_hive_repository.get_all_portfolios(limit=1000)
```

### 4. Use with Load Testing

Run Locust benchmark → Check Silk for slow requests:

```bash
# Terminal 1: Run benchmark
locust --host=http://localhost:8000 --users 50

# Terminal 2: Monitor Silk dashboard
# Visit http://localhost:8000/silk/
# Sort by "Time" to see slowest requests
```

### 5. Filter Noise

Silk records EVERYTHING - including static files!

```python
# config/settings.py
SILKY_IGNORE_PATHS = [
    '/static/',
    '/media/',
    '/favicon.ico',
    '/health/',  # Health check endpoints
]
```

---

## Integration with CisTrade Benchmark

### Workflow

1. **Run Benchmark** (already done!):
   ```bash
   locust --host=http://localhost:8000 --users 50 --run-time 1m
   ```

2. **Open Silk Dashboard**:
   ```
   Visit: http://localhost:8000/silk/
   ```

3. **Filter Recent Requests**:
   - Click "Requests" tab
   - Filter by last 5 minutes
   - Sort by "Time" (descending)

4. **Identify Slow Endpoints**:
   ```
   Slow Requests Found:
   1. GET /portfolio/?export=csv - 4,791ms ⚠️
   2. GET /reference-data/calendar/ - 7,201ms ⚠️
   3. GET /portfolio/?search=USD - 3,659ms ⚠️
   ```

5. **Click Each Request** to see:
   - SQL queries (is Impala slow?)
   - Python profiling (is data transformation slow?)
   - Template rendering (is HTML generation slow?)

6. **Fix Issues**:
   - Add indexes
   - Optimize queries
   - Add caching
   - Use pagination

7. **Re-run Benchmark** to verify improvement!

---

## Example: Debugging Your Slow Calendar List

From your benchmark, we saw:
```
⚠️  SLOW REQUEST: Calendar List took 7,200ms
```

**Steps with Silk:**

1. **Open Silk**, find the Calendar List request

2. **Check SQL Queries**:
   ```
   Query 1: 6,850ms ⚠️
   SELECT * FROM gmp_cis.cis_calendar
   ORDER BY calendar_date DESC
   LIMIT 1000
   ```

3. **Identify Problem**: Full table scan, no index

4. **Solution**:
   ```sql
   -- Add index on calendar_date
   CREATE INDEX idx_calendar_date ON cis_calendar(calendar_date);
   ```

5. **Re-test**: Now takes 250ms ✅ (96% improvement!)

---

## Silk vs. Other Tools

| Tool | Purpose | Best For |
|------|---------|----------|
| **Django Silk** | Request profiling, SQL analysis | Finding slow queries, N+1 problems |
| **Django Debug Toolbar** | Per-request debugging | Development debugging |
| **cProfile** | Python code profiling | CPU-intensive Python code |
| **py-spy** | Production profiling | Live production systems |
| **Locust** | Load testing | Finding performance under load |

**Use together:**
1. Locust → Find slow endpoints
2. Silk → Diagnose why they're slow
3. Fix → Re-run Locust to verify

---

## Troubleshooting

### "Silk not showing any requests"

**Check:**
1. Did you run `python manage.py migrate`?
2. Is `silk` in `INSTALLED_APPS`?
3. Is `SilkyMiddleware` in `MIDDLEWARE`?
4. Are you accessing the correct URL (`/silk/`)?

### "Silk slowing down my application"

**Solutions:**
1. Only enable in development:
   ```python
   if DEBUG:
       INSTALLED_APPS += ['silk']
   ```

2. Reduce profiling:
   ```python
   SILKY_PYTHON_PROFILER = False  # Disable Python profiling
   ```

3. Sample requests:
   ```python
   SILKY_INTERCEPT_PERCENT = 10  # Only profile 10% of requests
   ```

### "Silk database is huge!"

**Solution:** Clean up old data regularly:
```bash
# Delete data older than 7 days
python manage.py silk_clear_request_log

# Or schedule with cron
0 0 * * * cd /path/to/project && python manage.py silk_clear_request_log
```

---

## Next Steps

1. **Install Silk** (follow steps above)
2. **Browse Silk Dashboard** - get familiar with the UI
3. **Find your slowest request** from the benchmark
4. **Analyze with Silk** - see SQL queries and Python profiling
5. **Fix the issue** - add indexes, optimize queries
6. **Re-run benchmark** - verify improvement

---

## Resources

- **Documentation:** https://github.com/jazzband/django-silk
- **Tutorial:** https://www.youtube.com/watch?v=...
- **Best Practices:** https://silk.readthedocs.io/

---

**Django Silk Profiler Guide** © 2025
