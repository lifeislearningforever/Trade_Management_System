# UOB Project Summary

---

## Project Name
**CIS Trade Hive** - Trade Management System

---

## Project Description
Enterprise-grade Trade Management System for managing trade portfolios, market data, security master data, and reference data with comprehensive audit logging, role-based access control (ACL), and maker-checker workflow (Four-Eyes principle) for regulatory compliance.

---

## Role in the Project
**Full Stack Developer / Technical Lead**

---

## Tasks & Work Responsibilities

### Database Architecture
- Designed and implemented migration from Apache Kudu to Hive Managed Tables with ORC format and ACID transaction support
- Created 24 database tables with proper bucketing, partitioning, and compression strategies
- Implemented soft delete pattern with audit trail for regulatory compliance

### Backend Development
- Built Django 5.2.9 application with Repository pattern, Service layer, and SOLID architecture principles
- Developed 10 Django apps: Core, Portfolio, Trade, Security, Market Data, Reference Data, UDF, Lookup, Audit, Hive POC
- Implemented 50+ REST API endpoints for CRUD operations

### Connection Management
- Developed HybridConnectionManager for optimized read/write operations
- Implemented Impala for fast reads (sub-second) and Hive for ACID writes
- Built connection pooling with 35 connections supporting concurrent users

### REST Proxy Solution
- Architected and implemented Flask-based REST Proxy for CML (Cloudera Machine Learning) environments
- Solved critical glibc/SASL connectivity issues preventing direct HiveServer2 connections from Docker containers
- Deployed on edge nodes with Gunicorn, Kerberos authentication, and auto-renewal

### Performance Optimization
- Created PyHive connection pooling with Tez execution engine
- Reduced write latency from ~38 seconds to ~3-8 seconds (10x improvement)
- Implemented query caching with TTL for dropdown and reference data

### Workflow Implementation
- Implemented maker-checker (Four-Eyes) workflow for Portfolio, Trade, and Security modules
- Status flow: DRAFT → PENDING_APPROVAL → APPROVED/REJECTED → ACTIVE → SETTLED/CLOSED
- Role-based permissions: Maker (create, edit, submit), Checker (approve, reject)

### Audit & Compliance
- Built comprehensive audit logging system with async write support
- Tracked all changes with old/new values as JSON
- Captured user, IP address, timestamp, and action type for every operation

### Testing & Benchmarking
- Developed Locust load testing framework supporting 500 concurrent users
- Created direct Kudu database benchmark scripts for realistic performance measurement
- Achieved target response times: <500ms median, <2s for 95th percentile

### Documentation
- Created technical documentation including CLAUDE.md, migration guides, and API documentation
- Prepared Jira stories for Kudu to Hive migration (31 stories across 6 sprints)
- Documented operational runbooks for production maintenance

---

## Achievements

### 1. Kudu to Hive Migration
Successfully migrated 24 database tables from Kudu to Hive ACID tables, enabling true INSERT/UPDATE/DELETE operations with full transaction support.

### 2. CML Connectivity Solution
Solved critical CML Docker container connectivity issue using REST Proxy architecture, enabling production deployment in Cloudera Machine Learning environment.

### 3. 10x Write Performance Improvement
Reduced Hive write latency from ~38 seconds to ~3-8 seconds using PyHive connection pooling and Tez execution engine configuration.

### 4. Full CRUD Implementation
Delivered complete CRUD operations across 10 Django apps covering all business entities: Portfolio, Trade, Security, Market Data (FX Rates, Equity Prices), Reference Data (Currency, Country, Counterparty), and User-Defined Fields.

### 5. Scalable Architecture
Implemented connection pooling (35 connections), async write queues, and query caching supporting 500+ concurrent users with sub-second read performance.

### 6. Compliance Ready
Built maker-checker workflow ensuring Four-Eyes principle compliance for financial operations, with complete audit trail for regulatory requirements.

### 7. Comprehensive Test Coverage
Created benchmarking framework with realistic load testing scenarios, including quick (50 users), standard (500 users), and stress (1000 users) test profiles.

---

## Tech Stack

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Django | 5.2.9 | Web framework |
| Django REST Framework | 3.16.1 | REST API |
| Python | 3.10+ | Programming language |
| Flask | Latest | REST Proxy |
| Gunicorn | Latest | WSGI server |

### Database & Big Data
| Technology | Purpose |
|------------|---------|
| Apache Hive | ACID transactions, ORC storage |
| Apache Kudu | Original database (migrated from) |
| Apache Impala | Fast SQL queries |
| ORC + SNAPPY | Storage format with compression |
| Cloudera Data Platform | Enterprise data platform |
| Cloudera Machine Learning | Application deployment |

### Connection Libraries
| Library | Purpose |
|---------|---------|
| PyHive 0.7.0 | Hive connection |
| impyla | Impala connection |
| thrift | Protocol |
| thrift-sasl | SASL authentication |

### Authentication
| Technology | Purpose |
|------------|---------|
| Kerberos (GSSAPI) | Production authentication |
| LDAP | User directory |

### Frontend
| Technology | Version | Purpose |
|------------|---------|---------|
| Bootstrap | 5.3.3 | UI framework |
| jQuery | Latest | JavaScript library |
| Select2 | Latest | Enhanced dropdowns |

### DevOps & Testing
| Technology | Purpose |
|------------|---------|
| Docker | Containerization |
| Docker Compose | Local development environment |
| pytest | Unit testing |
| pytest-cov | Code coverage |
| Locust | Load testing |
| Git/GitHub | Version control |

---

## Total Experience at UOB
*(Fill in your actual tenure)*

---

## Training Requirements

### High Priority

**1. Apache Spark**
- Large-scale data processing and ETL pipelines
- Integration with Cloudera Data Platform
- PySpark for Python developers

**2. Cloudera Data Platform (CDP) Administration**
- Deeper understanding of CDP ecosystem
- Production cluster management and optimization
- Security and governance features

### Medium Priority

**3. Apache Kafka**
- Real-time data streaming
- Event-driven architecture
- Integration with existing data pipelines

**4. Kubernetes/OpenShift**
- Container orchestration
- Scaling CML applications
- Production deployment strategies

**5. Advanced Python Performance**
- Async programming (asyncio)
- Profiling and optimization techniques
- Memory management

**6. Financial Domain Knowledge**
- Trade lifecycle and settlement processes
- Regulatory compliance (MAS guidelines)
- Risk management concepts

### Low Priority

**7. Cloudera Data Engineering (CDE)**
- Advanced ETL workflows
- Airflow integration
- Job orchestration

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Database Tables | 24 |
| Django Apps | 10 |
| API Endpoints | 50+ |
| Concurrent Users Supported | 500+ |
| Write Latency (Optimized) | 3-8 seconds |
| Read Latency | <500ms |
| Test Coverage Target | 80%+ |
| Migration Stories | 31 |
| Sprint Duration | 9 weeks |

---

## Project Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Infrastructure Setup | 2 weeks | Completed |
| Repository Migration | 2 weeks | Completed |
| Data Migration | 1 week | Completed |
| Integration Testing | 2 weeks | Completed |
| Deployment | 1 week | Completed |
| Documentation | 1 week | Completed |

---

*Document prepared for UOB Project Review*
*Date: February 2026*
