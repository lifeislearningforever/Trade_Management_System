# CisTrade Documentation Implementation Plan

**Last Updated**: 2025-12-27
**Status**: Planning Phase
**Owner**: Development Team

---

## Overview

This document outlines the comprehensive documentation strategy for CisTrade application, targeting three key audiences:
1. **Business Users** - Non-technical users who use the system daily
2. **Business Analysts (BAs)** - Need process flows and business logic
3. **Developers** - Need technical architecture and implementation details

## Goals

- Create user-friendly documentation for business users
- Provide technical reference for developers and BAs
- Integrate documentation into Confluence
- Embed contextual help within the application
- Ensure high performance with Kudu/Impala integration

---

## Documentation Stack

### Tools Selected

| Tool | Purpose | Audience | Status |
|------|---------|----------|--------|
| MkDocs + Material | Technical docs | Developers, BAs | ⏳ Pending |
| Confluence | Business user guides | Business Users, BAs | ⏳ Pending |
| In-App Help Modals | Contextual help | All Users | ⏳ Pending |
| Kudu Help Tables | Dynamic help content | All Users | ⏳ Pending |
| Redis Cache | Performance optimization | N/A | ⏳ Pending |
| Loom/Screenshots | Visual guides | Business Users | ⏳ Pending |

**Legend**: ✅ Complete | 🚧 In Progress | ⏳ Pending | ❌ Blocked

---

## Task Breakdown

### Phase 1: Foundation (Week 1)

#### 1.1 MkDocs Setup
- [ ] Install MkDocs and Material theme
  ```bash
  pip install mkdocs mkdocs-material
  mkdocs new docs
  ```
- [ ] Create documentation folder structure:
  ```
  docs/
  ├── business/          # Business user guides
  ├── technical/         # Developer documentation
  └── integration/       # BA documentation
  ```
- [ ] Configure `mkdocs.yml` with theme and plugins
- [ ] Set up local preview: `mkdocs serve`

**Owner**: Developer
**Estimated Effort**: 2 hours
**Status**: ⏳ Pending

---

#### 1.2 Documentation Structure
- [ ] Create folder structure
- [ ] Create template pages for each section
- [ ] Set up navigation in mkdocs.yml

**Owner**: Developer
**Estimated Effort**: 1 hour
**Status**: ⏳ Pending

---

### Phase 2: Business User Documentation (Week 1-2)

#### 2.1 User Guides
- [ ] Portfolio Management Guide
  - Creating portfolios
  - Editing portfolios
  - Portfolio lifecycle
  - Search and filtering
- [ ] Four-Eyes Workflow Guide
  - Maker role explained
  - Checker role explained
  - Approval process
  - Rejection process
- [ ] UDF Management Guide
- [ ] Market Data Guide
- [ ] Reports Guide

**Owner**: BA + Developer
**Estimated Effort**: 8 hours
**Status**: ⏳ Pending

---

#### 2.2 Visual Content
- [ ] Create screenshots for all major screens
- [ ] Record video tutorials (5-10 min each):
  - Portfolio creation walkthrough
  - Four-eyes approval demo
  - Search and filter demo
- [ ] Create Quick Reference Cards (1-page PDFs)

**Owner**: BA
**Estimated Effort**: 6 hours
**Status**: ⏳ Pending

---

### Phase 3: Technical Documentation (Week 2)

#### 3.1 Architecture Documentation
- [ ] System architecture overview
- [ ] Technology stack documentation
- [ ] Design patterns used:
  - Repository pattern
  - Service layer
  - Four-Eyes workflow
  - Soft delete pattern
- [ ] Data flow diagrams

**Owner**: Developer
**Estimated Effort**: 4 hours
**Status**: ⏳ Pending

---

#### 3.2 Database Documentation
- [ ] Document all Kudu/Impala tables:
  - cis_portfolio
  - cis_portfolio_history
  - cis_audit_log
  - cis_udf_master
  - cis_fx_rate
  - etc.
- [ ] Create ER diagrams
- [ ] Document data types and constraints
- [ ] Document partitioning strategy

**Owner**: Developer
**Estimated Effort**: 4 hours
**Status**: ⏳ Pending

---

#### 3.3 API/Code Reference
- [ ] Document repository pattern
- [ ] Document service layer methods
- [ ] Document view functions
- [ ] Create code examples
- [ ] Document URL routing

**Owner**: Developer
**Estimated Effort**: 3 hours
**Status**: ⏳ Pending

---

### Phase 4: In-App Help Integration (Week 3)

#### 4.1 Kudu Help Tables
- [ ] Create `cis_help_content` table in Kudu:
  ```sql
  CREATE TABLE gmp_cis.cis_help_content (
      id STRING,
      module STRING,
      page STRING,
      section STRING,
      title STRING,
      content STRING,
      user_type STRING,
      is_active BOOLEAN,
      created_at TIMESTAMP,
      updated_at TIMESTAMP,
      PRIMARY KEY (id)
  )
  PARTITION BY HASH(id) PARTITIONS 4
  STORED AS KUDU;
  ```
- [ ] Create help repository (`core/repositories/help_repository.py`)
- [ ] Create help service (`core/services/help_service.py`)
- [ ] Insert sample help content for Portfolio module

**Owner**: Developer
**Estimated Effort**: 3 hours
**Status**: ⏳ Pending

---

#### 4.2 UI Integration
- [ ] Add help button to base template navigation
- [ ] Create help modal component
- [ ] Add page-specific help content blocks:
  - Portfolio List
  - Portfolio Detail
  - Portfolio Create/Edit
  - UDF List
  - Market Data List
  - etc.
- [ ] Add tooltips/popovers for form fields
- [ ] Test help modal on all pages

**Owner**: Developer
**Estimated Effort**: 4 hours
**Status**: ⏳ Pending

---

### Phase 5: Performance Optimization (Week 3)

#### 5.1 Redis Caching
- [ ] Install Redis: `pip install django-redis`
- [ ] Configure Django cache settings
- [ ] Implement help content caching
- [ ] Create cache warming script
- [ ] Test cache hit rates

**Owner**: Developer
**Estimated Effort**: 2 hours
**Status**: ⏳ Pending

---

#### 5.2 Performance Testing
- [ ] Test help modal load times
- [ ] Test page load with help content
- [ ] Optimize database queries
- [ ] Monitor cache effectiveness

**Owner**: Developer
**Estimated Effort**: 2 hours
**Status**: ⏳ Pending

---

### Phase 6: Confluence Integration (Week 4)

#### 6.1 Confluence Setup
- [ ] Create Confluence space for CisTrade
- [ ] Create parent pages:
  - User Guides
  - Technical Documentation
  - Business Analyst Documentation
  - FAQ
- [ ] Set up permissions

**Owner**: BA
**Estimated Effort**: 1 hour
**Status**: ⏳ Pending

---

#### 6.2 Content Migration
- [ ] Export MkDocs to HTML/PDF
- [ ] Upload business user guides to Confluence
- [ ] Upload technical docs to Confluence
- [ ] Add screenshots and videos
- [ ] Create table of contents
- [ ] Link to in-app help

**Owner**: BA + Developer
**Estimated Effort**: 4 hours
**Status**: ⏳ Pending

---

## Implementation Details

### Kudu Help Content Schema

```sql
-- Table structure
CREATE TABLE gmp_cis.cis_help_content (
    id STRING,                  -- Unique ID (e.g., 'help_001')
    module STRING,              -- 'portfolio', 'udf', 'market_data', 'core'
    page STRING,                -- 'list', 'detail', 'create', 'edit'
    section STRING,             -- 'header', 'search', 'form', 'actions'
    title STRING,               -- Help topic title
    content STRING,             -- HTML content
    user_type STRING,           -- 'business', 'technical', 'all'
    is_active BOOLEAN,          -- Active flag
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    PRIMARY KEY (id)
)
PARTITION BY HASH(id) PARTITIONS 4
STORED AS KUDU;

-- Sample data
INSERT INTO gmp_cis.cis_help_content VALUES (
    'help_portfolio_list_001',
    'portfolio',
    'list',
    'search_filter',
    'How to Search and Filter Portfolios',
    '<h6>Search</h6><p>Enter portfolio code, name, or manager in the search box...</p>',
    'business',
    true,
    NOW(),
    NOW()
);
```

### Help Repository Pattern

```python
# core/repositories/help_repository.py
class HelpRepository:
    """Repository for help content from Kudu."""

    def get_help_content(self, module: str, page: str, section: str = None) -> List[Dict]:
        """Get help content for a specific page."""
        query = f"""
            SELECT id, title, content, user_type
            FROM gmp_cis.cis_help_content
            WHERE module = '{module}'
              AND page = '{page}'
              AND is_active = true
        """
        if section:
            query += f" AND section = '{section}'"

        return self.execute_query(query)
```

### Cache Implementation

```python
# core/services/help_service.py
from django.core.cache import cache

class HelpService:
    """Service for help content with caching."""

    @staticmethod
    def get_page_help(module: str, page: str) -> Dict:
        """Get help content with caching."""
        cache_key = f'help_{module}_{page}'
        content = cache.get(cache_key)

        if not content:
            content = help_repository.get_help_content(module, page)
            cache.set(cache_key, content, timeout=3600)  # 1 hour

        return content
```

### Template Integration

```html
<!-- templates/base.html -->
<!-- Help Button in Navbar -->
<li class="nav-item">
    <a class="nav-link" href="#" data-bs-toggle="modal" data-bs-target="#helpModal">
        <i class="bi bi-question-circle"></i> Help
    </a>
</li>

<!-- Help Modal -->
<div class="modal fade" id="helpModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header">
                <h5 class="modal-title">
                    <i class="bi bi-question-circle text-primary"></i> Help
                </h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
                {% block help_content %}
                    <p>No help content available for this page.</p>
                {% endblock %}
            </div>
            <div class="modal-footer">
                <a href="/docs/" target="_blank" class="btn btn-primary">
                    <i class="bi bi-book"></i> Full Documentation
                </a>
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
            </div>
        </div>
    </div>
</div>
```

```html
<!-- templates/portfolio/portfolio_list.html -->
{% block help_content %}
<div class="help-section">
    <h6><i class="bi bi-briefcase"></i> Portfolio List</h6>
    <p>This page displays all portfolios in the CisTrade system.</p>

    <h6 class="mt-3">Search & Filter</h6>
    <ul>
        <li><strong>Search:</strong> Enter portfolio code, name, or manager name</li>
        <li><strong>Status Filter:</strong> Filter by Draft, Pending Approval, Approved, Rejected, or Inactive</li>
        <li><strong>Currency Filter:</strong> Filter by currency code (e.g., USD, EUR)</li>
    </ul>

    <h6 class="mt-3">Actions</h6>
    <ul>
        <li><strong>View (Eye icon):</strong> View portfolio details</li>
        <li><strong>Edit (Pencil icon):</strong> Edit portfolio (only for Draft/Rejected status)</li>
        <li><strong>Create New:</strong> Create a new portfolio (starts in Draft status)</li>
        <li><strong>Pending Approvals:</strong> View portfolios awaiting approval</li>
    </ul>

    <h6 class="mt-3">Four-Eyes Principle</h6>
    <p>All portfolio changes follow the Maker-Checker workflow:</p>
    <ol>
        <li>Maker creates/edits portfolio (Draft status)</li>
        <li>Maker submits for approval (Pending Approval status)</li>
        <li>Checker approves or rejects (different user)</li>
        <li>Approved portfolios become Active</li>
    </ol>
</div>
{% endblock %}
```

---

## Documentation Content Outline

### Business User Documentation

#### 1. Portfolio Management Guide
- Introduction to portfolios
- Creating a new portfolio
- Editing a portfolio
- Portfolio statuses explained
- Closing a portfolio
- Reactivating a portfolio
- Searching and filtering
- Exporting to CSV

#### 2. Four-Eyes Workflow Guide
- What is Four-Eyes principle?
- Maker role and responsibilities
- Checker role and responsibilities
- Submitting for approval
- Approving changes
- Rejecting changes
- Common scenarios

#### 3. UDF Management Guide
- What are User Defined Fields?
- Creating UDF definitions
- Managing UDF values
- UDF history tracking

#### 4. Market Data Guide
- FX rates management
- Uploading market data
- Data validation

### Technical Documentation

#### 1. Architecture
- System overview
- Technology stack (Django, Kudu, Impala)
- Design patterns
- Security model

#### 2. Database Schema
- Kudu/Impala tables
- Table relationships
- Partitioning strategy
- Data types

#### 3. Code Structure
- Repository pattern
- Service layer
- View layer
- URL routing

#### 4. Development Guide
- Setting up development environment
- Running the application
- Testing
- Deployment

### BA Documentation

#### 1. Business Processes
- Portfolio lifecycle
- Approval workflows
- Data flow diagrams
- Integration points

#### 2. Business Rules
- Validation rules
- Status transitions
- Permission model

---

## Performance Considerations

### Caching Strategy
- **Help Content**: Cache for 1 hour (3600 seconds)
- **Static Documentation**: Serve via CDN if possible
- **Kudu Queries**: Use Redis cache for frequently accessed help

### Load Time Targets
- Help modal open: < 200ms
- Page load with help: < 500ms
- Documentation search: < 1s

---

## Maintenance Plan

### Regular Updates
- **Monthly**: Review and update user guides
- **Quarterly**: Update technical documentation
- **After Each Release**: Update changelog and new features

### Ownership
- **Business Guides**: BA Team
- **Technical Docs**: Development Team
- **In-App Help**: Development Team
- **Confluence**: BA Team (primary), Dev Team (technical sections)

---

## Success Metrics

### User Adoption
- Track help modal usage (via audit logs)
- Track Confluence page views
- Collect user feedback

### Documentation Quality
- Completeness: 100% of features documented
- Accuracy: < 5% error reports
- User satisfaction: > 80% positive feedback

---

## Next Steps

1. **Immediate** (This Week):
   - [ ] Review and approve this plan
   - [ ] Set up MkDocs
   - [ ] Create initial folder structure

2. **Short Term** (Next 2 Weeks):
   - [ ] Write business user guides
   - [ ] Create Kudu help tables
   - [ ] Add in-app help modals

3. **Medium Term** (Next Month):
   - [ ] Complete technical documentation
   - [ ] Migrate to Confluence
   - [ ] Record video tutorials

---

## Resources

### Tools & Libraries
- MkDocs: https://www.mkdocs.org/
- Material Theme: https://squidfunk.github.io/mkdocs-material/
- Django Redis: https://github.com/jazzband/django-redis
- Loom: https://www.loom.com/

### Documentation Examples
- Django Docs: https://docs.djangoproject.com/
- Stripe Docs: https://stripe.com/docs

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-27 | Initial documentation plan created | Development Team |

---

**End of Documentation Plan**
