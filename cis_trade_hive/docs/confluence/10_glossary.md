# Glossary

> **Audience:** Everyone — User, BA, SA, Developer, Support, New Joiner
> **Reference document — search for the term you need**

---

| Term | Plain English Meaning |
|------|-----------------------|
| **AVP** | Average Price Position. The weighted average cost of a portfolio's holding in a security. Recalculated automatically every time a trade settles. |
| **Audit Log** | A permanent record of everything that happened in CIS — who did what, when, with before/after values. Stored in `cis_audit_log`. |
| **BA** | Business Analyst. Writes requirements and works between business and tech. |
| **Backdated trade** | A trade entered in CIS with a trade date in the past. Triggers recalculation of all positions from that date forward. |
| **Basis (position)** | TRADED or SETTLED — the date basis on which a position is calculated. CIS tracks both. |
| **BUY** | Trade type — purchase of securities. Increases position quantity and recalculates average cost. |
| **CA** | Corporate Action. An event by a company affecting its securities (dividend, split, rights issue, etc.). |
| **Cash Flow** | A money movement linked to a portfolio — from dividends, trade settlements, corporate actions, etc. |
| **CDH** | Cloudera Data Hub / Cloudera Distribution of Hadoop. The enterprise platform where SIT/UAT/PROD runs. |
| **Checker** | The second person in the Four-Eyes workflow who reviews and approves or rejects a maker's work. |
| **CIS** | Capital & Investment Services. The name of this system. |
| **CML** | Cloudera Machine Learning. The execution environment on the Cloudera platform. |
| **Confluence** | The wiki tool where this documentation lives. |
| **Control-M** | Job scheduler used to run ETL jobs on a schedule (e.g. daily at 6 AM). |
| **Counterparty** | The other party in a trade — typically a broker or bank. Managed in `cis_counterparty_kudu`. |
| **DECIMAL(20,8)** | Numeric precision used for AVP calculations — 20 total digits, 8 decimal places. |
| **Django** | The Python web framework CIS is built on. Handles routing, templates, sessions, middleware. |
| **EOD** | End of Day. The batch jobs that run after market close — settlement, CA processing, position refresh. |
| **ETL** | Extract, Transform, Load. The process of moving data from one system to another. GMP → CIS is an ETL process. |
| **External Table** | A Hive table that points to files already on HDFS. CIS doesn't own these — GMP does. Read-only in CIS. |
| **FC** | Foreign Currency. The currency in which a security trades. |
| **Four-Eyes** | The rule that no one can approve their own work. Two people's eyes must see every critical action. |
| **FX Rate** | Foreign Exchange Rate. The conversion rate between two currencies. Comes from GMP daily. |
| **gmp_cis** | The Impala/Hive database name where all CIS and GMP tables live. |
| **GMP** | Global Market Platform. The upstream system that feeds CIS with market data, reference data, and some trades. |
| **GSSAPI** | Authentication method used on Cloudera clusters (Kerberos-based). |
| **HDFS** | Hadoop Distributed File System. The storage layer where Hive external table files live. |
| **Hive** | A data warehouse layer on top of HDFS. Used for both external (GMP data) and managed (internal) tables. |
| **Idempotent** | A property of an operation: running it multiple times produces the same result as running it once. CIS UPSERTs are idempotent. |
| **Impala** | The SQL query engine for Kudu and Hive tables. CIS connects to it on port 21050. |
| **ISIN** | International Securities Identification Number. A 12-character code uniquely identifying a security globally. |
| **Kerberos** | A network authentication protocol. Required to connect to Cloudera on SIT/UAT/PROD. |
| **Kudu** | Apache Kudu. The fast columnar database that backs CIS's own tables. Supports UPSERT and fast scans. |
| **LC** | Local Currency. The portfolio's base currency. |
| **Maker** | The person who creates a record (trade, portfolio) and submits it for approval. |
| **Maker-Checker** | See Four-Eyes. |
| **NOSASL** | Authentication mode — no security. Used only on LOCAL Docker development. Never on production. |
| **ORC** | A columnar file format used by Hive managed tables. |
| **Parquet** | A columnar file format. Used by CIS backup scripts to store table data as files. |
| **Portfolio** | An investment account or fund that holds positions in securities. All trades belong to a portfolio. |
| **Position** | How many units of a security a portfolio currently holds, at what average cost. |
| **P&L** | Profit & Loss. Realised P&L = profit/loss from sold positions. Unrealised P&L = current gain/loss on open positions. |
| **RBAC** | Role-Based Access Control. Who can do what in CIS, controlled by user groups and permissions. |
| **Repository** | A code class that handles all SQL queries for one entity type. Only place where SQL is written. |
| **SA** | Solution Architect or System Analyst. Designs the system and translates requirements into technical specs. |
| **Security** | A tradeable financial instrument — shares, bonds, ETFs, etc. Must exist and be approved before trading. |
| **SELL** | Trade type — sale of securities. Decreases position quantity; average cost unchanged; realised P&L calculated. |
| **Service** | A code class that holds business rules. Calls repositories. Called by views. |
| **SIT** | System Integration Testing. The environment where developers test integrated systems. |
| **SETTLED** | Final status of a trade. Position has been updated. Cannot be edited. |
| **Soft Delete** | Marking a record as `is_active = false` or `is_deleted = true` instead of physically removing it. Keeps audit history. |
| **Spark** | Apache Spark. Used for large-scale data processing — backup/restore scripts, ETL. |
| **src_system** | A column on `cis_trade` indicating whether the trade came from CIS (`'CIS'`) or GMP (`'GMP'`). |
| **T+0, T+1, T+2** | Settlement timing. T = trade date. T+2 = trade date plus 2 business days. |
| **UAT** | User Acceptance Testing. The environment where business users test before production. |
| **UDF** | User-Defined Field. A custom field added to trades, portfolios, or securities without schema changes. |
| **UPSERT** | Insert if new, update if exists. Kudu's native write operation — idempotent by primary key. |
| **View** | A Django code function that handles one URL. Calls services and renders HTML templates. |
| **Yarn** | The Hadoop resource manager. Spark jobs on Cloudera are submitted with `--master yarn`. |
