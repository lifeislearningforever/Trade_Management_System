# Kudu to Hive DDL Conversion Notes

## Overview

This document explains how Kudu DDL has been converted to Hive DDL for the CIS Trade Management System.

## Key Conversion Principles

### 1. Storage Format
- **Kudu**: `STORED AS KUDU`
- **Hive**: `STORED AS ORC`
- **Reason**: ORC provides excellent compression, columnar storage, ACID support, and is native to Hive

### 2. Primary Keys
- **Kudu**: Enforced `PRIMARY KEY (col1, col2)`
- **Hive**: Documented in table COMMENT, enforced at application layer
- **Note**: Hive doesn't enforce primary key constraints. Application must ensure uniqueness.

### 3. Partitioning Strategy
- **Kudu**: `PARTITION BY HASH (columns) PARTITIONS N`
- **Hive**: `CLUSTERED BY (columns) INTO N BUCKETS`
- **Conversion**: Same columns and bucket count as Kudu partitions

Example:
```sql
-- Kudu
PARTITION BY HASH (entity_type, entity_id) PARTITIONS 16

-- Hive
CLUSTERED BY (entity_type, entity_id) INTO 16 BUCKETS
```

### 4. NOT NULL Constraints
- **Kudu**: Enforced `NOT NULL`
- **Hive**: Removed (not reliably enforced)
- **Alternative**: Validate at application layer (Django model validation)

### 5. DEFAULT Values
- **Kudu**: `DEFAULT TRUE`, `DEFAULT CURRENT_TIMESTAMP()`
- **Hive**: Removed (limited support)
- **Alternative**: Set defaults in INSERT statements or application layer

### 6. Transactional Support
- **Added**: ORC with transactional properties for UPDATE/DELETE support
```sql
TBLPROPERTIES (
  'transactional'='true',
  'transactional_properties'='default'
)
```

### 7. Compression and Optimization
- **ORC Compression**: SNAPPY (good balance of speed vs compression ratio)
- **ORC Indexes**: Enabled for better query performance
```sql
TBLPROPERTIES (
  'orc.compress'='SNAPPY',
  'orc.create.index'='true'
)
```

## UDF Tables Converted

### 1. cis_udf_value
- **Purpose**: Single-value UDF storage
- **PK**: (entity_type, entity_id, field_name)
- **Buckets**: 16 (hash on entity_type, entity_id)

### 2. cis_udf_value_multi
- **Purpose**: Multi-select UDF storage
- **PK**: (entity_type, entity_id, field_name, option_value)
- **Buckets**: 16 (hash on entity_type, entity_id)

### 3. cis_udf_option
- **Purpose**: UDF dropdown options
- **PK**: (udf_id, option_value)
- **Buckets**: 8 (hash on udf_id)

### 4. cis_udf_definition
- **Purpose**: UDF field definitions
- **PK**: (udf_id)
- **Buckets**: 8 (hash on udf_id)

## Data Type Mapping

| Kudu Type | Hive Type | Notes |
|-----------|-----------|-------|
| STRING | STRING | Direct mapping |
| BIGINT | BIGINT | Direct mapping |
| INT | INT | Direct mapping |
| BOOLEAN | BOOLEAN | Direct mapping |
| TIMESTAMP | TIMESTAMP | Direct mapping |
| DECIMAL(38,10) | DECIMAL(38,10) | Direct mapping |

## Application Layer Responsibilities

Since Hive doesn't enforce all constraints, the application must:

1. **Primary Key Uniqueness**: Check before INSERT/UPDATE
2. **NOT NULL Validation**: Validate required fields
3. **Default Values**: Set in code before INSERT
4. **Timestamps**: Set created_at/updated_at explicitly
5. **Referential Integrity**: Validate foreign key relationships

## Django Model Recommendations

```python
class UDFValue(models.Model):
    entity_type = models.CharField(max_length=100)  # NOT NULL at model level
    entity_id = models.BigIntegerField()
    field_name = models.CharField(max_length=100)
    # ... other fields ...

    class Meta:
        db_table = 'cis_udf_value'
        unique_together = ('entity_type', 'entity_id', 'field_name')  # Enforce PK
        managed = False  # Don't let Django manage the table
```

## Query Performance Tips

1. **Use Bucketing**: Query with bucket columns for better performance
```sql
SELECT * FROM cis_udf_value
WHERE entity_type = 'PORTFOLIO' AND entity_id = 123;
```

2. **Predicate Pushdown**: ORC format supports efficient filtering
3. **Vectorized Execution**: Enable for better performance
```sql
SET hive.vectorized.execution.enabled = true;
```

## Migration Strategy

When migrating data from Kudu to Hive:

1. **Export from Kudu**: Use Impala or Kudu API
2. **Transform**: Ensure data meets constraints
3. **Load to Hive**: Use `INSERT INTO` or `LOAD DATA`
4. **Verify**: Check row counts and sample data

## Future Considerations

- **Partitioning**: May add time-based partitioning for large tables
- **Indexing**: Consider creating materialized views for common queries
- **Compaction**: Schedule regular compaction for transactional tables
- **Statistics**: Compute statistics after data loads for query optimization
