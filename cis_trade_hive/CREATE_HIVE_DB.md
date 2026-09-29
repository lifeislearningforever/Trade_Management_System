# Create Hive Database "cis"

This guide provides multiple methods to create the Hive database.

## Method 1: Using Beeline (Recommended)

Beeline is the command-line tool for Hive.

```bash
# Connect to Hive
beeline -u jdbc:hive2://localhost:10000

# Once connected, run:
CREATE DATABASE IF NOT EXISTS cis;

# Verify
SHOW DATABASES;

# Use the database
USE cis;

# Exit
!quit
```

## Method 2: Using Beeline with SQL File

```bash
beeline -u jdbc:hive2://localhost:10000 -f sql/create_database.sql
```

## Method 3: Using Hive CLI (Deprecated but still works)

```bash
hive -e "CREATE DATABASE IF NOT EXISTS cis;"
```

## Method 4: Using Django Management Command (After installation)

First, install dependencies:

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive
pip install -r requirements.txt
```

Then run:

```bash
python manage.py create_hive_db
```

## Method 5: Direct Python Script

Create a file `create_db.py`:

```python
from pyhive import hive

# Connect to Hive
conn = hive.Connection(
    host='localhost',
    port=10000,
    auth='NOSASL'
)

cursor = conn.cursor()

# Create database
cursor.execute("CREATE DATABASE IF NOT EXISTS cis")
print("Database 'cis' created successfully!")

# Show databases
cursor.execute("SHOW DATABASES")
databases = cursor.fetchall()
print("\nAvailable databases:")
for db in databases:
    print(f"  - {db[0]}")

cursor.close()
conn.close()
```

Run it:
```bash
python create_db.py
```

## Verification

After creating the database, verify it exists:

```bash
beeline -u jdbc:hive2://localhost:10000 -e "SHOW DATABASES;"
```

You should see 'cis' in the list.

## Troubleshooting

### Connection Issues

If you can't connect to Hive:

1. **Check if HiveServer2 is running:**
   ```bash
   jps | grep HiveServer2
   ```

2. **Start HiveServer2 if not running:**
   ```bash
   hive --service hiveserver2 &
   ```

3. **Check if port 10000 is open:**
   ```bash
   netstat -an | grep 10000
   ```

### Permission Issues

If you get permission errors:

```bash
# Connect as superuser or with proper credentials
beeline -u jdbc:hive2://localhost:10000 -n yourusername
```

## Next Steps

After creating the database:

1. Test connection using Django command:
   ```bash
   python manage.py test_hive
   ```

2. Create tables in the database using the DDL scripts in `sql/ddl/` directory
