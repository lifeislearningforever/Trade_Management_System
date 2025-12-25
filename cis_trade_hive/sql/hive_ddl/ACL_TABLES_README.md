# ACL Tables - Hive Implementation

## Overview
This document describes the ACL (Access Control List) tables implementation in the Hive database `cis`.

## Tables Created

### 1. cis_user_group
- **Purpose**: Stores user groups
- **Format**: TEXT (pipe-delimited)
- **Rows**: 1
- **Columns**:
  - cis_user_group_id (INT)
  - name (STRING)
  - entity (STRING)
  - description (STRING)
  - is_deleted (BOOLEAN)
  - updated_on (TIMESTAMP)
  - updated_by (STRING)

### 2. cis_user
- **Purpose**: Stores user information
- **Format**: TEXT (pipe-delimited)
- **Rows**: 3
- **Columns**:
  - cis_user_id (INT)
  - login (STRING)
  - name (STRING)
  - entity (STRING)
  - email (STRING)
  - domain (STRING)
  - cis_user_group_id (INT)
  - is_deleted (BOOLEAN)
  - enabled (BOOLEAN)
  - last_login (TIMESTAMP)
  - created_on (TIMESTAMP)
  - created_by (STRING)
  - updated_on (TIMESTAMP)
  - updated_by (STRING)

### 3. cis_permission
- **Purpose**: Stores available permissions
- **Format**: TEXT (pipe-delimited)
- **Rows**: 7
- **Columns**:
  - cis_permission_id (INT)
  - permission (STRING)
  - description (STRING)
  - is_deleted (BOOLEAN)
  - updated_on (TIMESTAMP)
  - updated_by (STRING)

**Permissions Include**:
- cis-report
- cis-trade
- cis-currency
- cis-audit
- cis-udf
- cis-udflist
- cis-portfolio

### 4. cis_group_permissions
- **Purpose**: Maps permissions to user groups with read/write access
- **Format**: TEXT (pipe-delimited)
- **Rows**: 30
- **Columns**:
  - cis_group_permissions_id (INT)
  - cis_user_group_id (INT)
  - permission (STRING)
  - read_write (STRING) - Values: READ, WRITE, READ_WRITE
  - is_deleted (BOOLEAN)
  - updated_on (TIMESTAMP)
  - updated_by (STRING)

## Data Source
- **Original File**: `cis_trade_hive/kudu_ddl/ACL_TABLES.xlsx`
- **Sheets**: cis_user, cis_user_group, cis_permission, cis_group_permissions
- **Total Rows**: 41 (1 + 3 + 7 + 30)

## Loading Process

### Step 1: Export Excel to CSV
```bash
python3 export_acl_to_csv.py
```
This creates pipe-delimited CSV files in the `acl_csv/` directory.

### Step 2: Create Staging Tables
Created TEXT format tables with pipe delimiter to match CSV format:
```sql
CREATE TABLE cis_user_group_stage (...)
ROW FORMAT DELIMITED
FIELDS TERMINATED BY '|'
STORED AS TEXTFILE;
```

### Step 3: Load CSV Data
```sql
LOAD DATA LOCAL INPATH '.../acl_csv/cis_user_group.csv'
OVERWRITE INTO TABLE cis_user_group_stage;
```

### Step 4: Rename to Production Tables
```sql
ALTER TABLE cis_user_group_stage RENAME TO cis_user_group;
```

## Table Format Decision
**Format**: TEXT with pipe delimiter
**Reason**:
- ORC format encountered persistent INSERT/CTAS errors in local Hive environment
- Dataset is small (41 rows total)
- TEXT format is perfectly adequate for this data volume
- Can be converted to ORC later if needed for larger datasets

## Files Generated

### DDL and Data Loading
- `02_acl_tables_nobucket.sql` - Table creation DDL (TEXT format)
- `03_load_acl_data_staging.sql` - Staging table approach
- `06_finalize_tables.sql` - Final table renaming

### Data Export
- `export_acl_to_csv.py` - Python script to export Excel to CSV
- `generate_acl_inserts.py` - Python script to generate INSERT statements
- `02_acl_data_inserts.sql` - Generated INSERT statements (not used due to errors)
- `load_acl_data.py` - PyHive loader script (not used due to connection issues)

### CSV Data Files
- `acl_csv/cis_user_group.csv`
- `acl_csv/cis_user.csv`
- `acl_csv/cis_permission.csv`
- `acl_csv/cis_group_permissions.csv`

## Verification

### Check Tables Exist
```sql
SHOW TABLES;
```

### View Data
```sql
SELECT * FROM cis_user_group;
SELECT * FROM cis_user;
SELECT * FROM cis_permission;
SELECT * FROM cis_group_permissions;
```

### Sample Queries
```sql
-- Get all users in a group
SELECT u.*
FROM cis_user u
JOIN cis_user_group g ON u.cis_user_group_id = g.cis_user_group_id
WHERE g.name = 'CIS-DEV';

-- Get permissions for a group
SELECT p.permission, gp.read_write
FROM cis_group_permissions gp
JOIN cis_permission p ON gp.permission = p.permission
WHERE gp.cis_user_group_id = 1;
```

## Known Issues

### Issue 1: ORC Table INSERT/CTAS Failures
- **Error**: Generic "Error running query" when inserting into ORC tables
- **Workaround**: Used TEXT format instead of ORC
- **Impact**: None for current dataset size
- **Future**: Can convert to ORC if needed for larger datasets

### Issue 2: COUNT() Aggregation Errors
- **Error**: Aggregation queries (COUNT, SUM, etc.) fail with generic errors
- **Likely Cause**: MapReduce/Tez execution engine configuration issue
- **Workaround**: Use SELECT without aggregation
- **Impact**: Minimal - can count rows manually or use external tools

## Next Steps
1. Test ACL integration with Django application
2. Implement ACL middleware to check permissions
3. Add more user groups and permissions as needed
4. Consider converting to ORC format when dataset grows larger

## Maintenance

### Adding New Data
To add new ACL data:
1. Update `ACL_TABLES.xlsx` with new rows
2. Re-export to CSV: `python3 export_acl_to_csv.py`
3. Load into Hive:
   ```sql
   LOAD DATA LOCAL INPATH '.../acl_csv/table_name.csv'
   OVERWRITE INTO TABLE table_name;
   ```

### Converting to ORC (Future)
If ORC format becomes necessary:
1. Create ORC tables with same schema
2. Use CTAS or INSERT SELECT from TEXT tables
3. Investigate and resolve ORC insertion errors
4. Update documentation

---
**Created**: 2025-12-24
**Status**: ✓ Complete - All ACL data successfully loaded
**Total Rows**: 41 across 4 tables
