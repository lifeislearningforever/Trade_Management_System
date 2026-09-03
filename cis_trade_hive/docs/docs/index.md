# Welcome to CisTrade Documentation

![CisTrade Logo](assets/images/logo.png){ width="200" }

## Overview

**CisTrade** is a comprehensive Trade Management System designed for managing portfolios, user-defined fields (UDFs), market data, and trade operations with robust audit trails and a Four-Eyes approval workflow.

## Key Features

:material-check-circle:{ .success } **Portfolio Management** - Create, edit, and manage portfolios with maker-checker workflow

:material-check-circle:{ .success } **Four-Eyes Principle** - Enforced maker-checker approval for all critical operations

:material-check-circle:{ .success } **Apache Kudu/Impala Integration** - High-performance data storage and querying

:material-check-circle:{ .success } **Comprehensive Audit Trail** - All actions logged to Kudu audit tables

:material-check-circle:{ .success } **UDF Management** - Define and manage custom fields for business entities

:material-check-circle:{ .success } **Market Data** - FX rates and market data management

:material-check-circle:{ .success } **Real-time Search & Filtering** - Fast search across all modules

## Documentation Sections

### :material-account-group: For Business Users

If you're a day-to-day user of CisTrade, start here:

<div class="grid cards" markdown>

-   :material-briefcase:{ .lg .middle } __Portfolio Management__

    ---

    Learn how to create, edit, and manage portfolios

    [:octicons-arrow-right-24: Portfolio Guide](business/portfolio-management.md)

-   :material-account-check:{ .lg .middle } __Four-Eyes Workflow__

    ---

    Understand the maker-checker approval process

    [:octicons-arrow-right-24: Workflow Guide](business/four-eyes-workflow.md)

-   :material-database:{ .lg .middle } __UDF Management__

    ---

    Manage user-defined fields for custom data

    [:octicons-arrow-right-24: UDF Guide](business/udf-management.md)

-   :material-chart-line:{ .lg .middle } __Market Data__

    ---

    Work with FX rates and market data

    [:octicons-arrow-right-24: Market Data Guide](business/market-data.md)

</div>

### :material-code-braces: For Developers

Technical documentation for developers and architects:

<div class="grid cards" markdown>

-   :material-architecture:{ .lg .middle } __Architecture__

    ---

    System architecture and design patterns

    [:octicons-arrow-right-24: Architecture](technical/architecture.md)

-   :material-database-cog:{ .lg .middle } __Database Schema__

    ---

    Kudu/Impala table structures and relationships

    [:octicons-arrow-right-24: Schema Docs](technical/database-schema.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Service and repository layer documentation

    [:octicons-arrow-right-24: API Docs](technical/api-reference.md)

-   :material-wrench:{ .lg .middle } __Development Guide__

    ---

    Setup and development workflow

    [:octicons-arrow-right-24: Dev Guide](technical/development-guide.md)

</div>

### :material-chart-timeline: For Business Analysts

Process flows and business logic documentation:

<div class="grid cards" markdown>

-   :material-sitemap:{ .lg .middle } __Business Processes__

    ---

    End-to-end business process documentation

    [:octicons-arrow-right-24: Processes](integration/business-processes.md)

-   :material-swap-horizontal:{ .lg .middle } __Data Flow__

    ---

    How data moves through the system

    [:octicons-arrow-right-24: Data Flow](integration/data-flow.md)

-   :material-book-open:{ .lg .middle } __Business Rules__

    ---

    Business logic and validation rules

    [:octicons-arrow-right-24: Rules](integration/business-rules.md)

-   :material-connection:{ .lg .middle } __Integrations__

    ---

    External system integrations

    [:octicons-arrow-right-24: Integrations](integration/integrations.md)

</div>

## Quick Links

- :material-help-circle: [FAQ](business/faq.md) - Frequently Asked Questions
- :material-file-document: [Change Log](changelog.md) - Release notes and changes
- :material-email: [Support](mailto:cistrade-support@yourcompany.com) - Get help from the team

## Technology Stack

=== "Backend"
    - **Framework**: Django 5.2.9
    - **Language**: Python 3.12
    - **Architecture**: Repository + Service Layer Pattern

=== "Database"
    - **Primary**: Apache Kudu (via Impala)
    - **No Django ORM**: Direct SQL for all data operations
    - **Audit**: All actions logged to Kudu audit tables

=== "Frontend"
    - **Framework**: Bootstrap 5
    - **Icons**: Bootstrap Icons
    - **Templates**: Django Templates (Jinja2 syntax)

## System Status

!!! success "Production Ready"
    CisTrade is currently in production with the following modules:

    - ✅ Portfolio Management
    - ✅ UDF Management
    - ✅ Market Data (FX Rates)
    - ✅ Audit Logging
    - ✅ Four-Eyes Workflow

!!! warning "Development Mode"
    The system is currently in **DEV MODE** with:

    - All permissions bypassed for testing
    - Four-eyes checks disabled for development
    - See `DEV_MODE_SETUP.md` for details

## Getting Started

### For Business Users
1. Read the [Portfolio Management Guide](business/portfolio-management.md)
2. Understand the [Four-Eyes Workflow](business/four-eyes-workflow.md)
3. Check the [FAQ](business/faq.md) for common questions

### For Developers
1. Review the [Architecture](technical/architecture.md)
2. Set up your environment with the [Development Guide](technical/development-guide.md)
3. Understand the [Database Schema](technical/database-schema.md)

### For Business Analysts
1. Study [Business Processes](integration/business-processes.md)
2. Review [Data Flow](integration/data-flow.md) diagrams
3. Check [Business Rules](integration/business-rules.md)

## Need Help?

!!! question "Questions or Issues?"
    - **Email**: [cistrade-support@yourcompany.com](mailto:cistrade-support@yourcompany.com)
    - **In-App Help**: Click the Help (?) button in the application
    - **Documentation**: Browse this site for detailed guides

---

**Last Updated**: 2025-12-27 | **Version**: 1.0.0
