"""
Security Models

NOTE: This module does NOT use Django ORM.
All data is stored in Kudu tables and accessed via Impala queries.

Data Tables (in Kudu):
- gmp_cis.cis_security - Main security master data
- gmp_cis.cis_security_history - Security change history

See:
- sql/ddl/cis_security_kudu_v2.sql
- sql/ddl/cis_security_history_kudu.sql
"""

# No Django models - all data in Kudu tables
