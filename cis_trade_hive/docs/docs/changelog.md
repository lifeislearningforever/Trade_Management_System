# Change Log

All notable changes to CisTrade will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-12-27

### Added
- Initial documentation structure
- Portfolio Management module with Four-Eyes workflow
- UDF Management module
- Market Data (FX Rates) module
- Comprehensive audit logging to Kudu
- Repository pattern for data access
- Service layer for business logic
- Portfolio close/reactivate functionality
- Search and filter capabilities
- CSV export functionality

### Technical
- Django 5.2.9 framework
- Apache Kudu/Impala integration
- Direct SQL via repository pattern (no Django ORM)
- Bootstrap 5 UI
- Development mode with bypassed permissions

### Documentation
- Business user guides
- Technical architecture documentation
- Database schema documentation
- Four-Eyes workflow guide
- MkDocs with Material theme

---

## [Unreleased]

### Planned
- Redis caching for performance
- In-app help system with Kudu storage
- REST API endpoints
- Advanced search with filters
- Bulk operations
- Report generation
- Dashboard analytics
- Mobile-responsive improvements

---

## Version History

| Version | Release Date | Major Changes |
|---------|--------------|---------------|
| 1.0.0 | 2025-12-27 | Initial release with core modules |

---

**Note**: This changelog will be updated with each release.
