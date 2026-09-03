# CisTrade Documentation - Access Guide

## ✅ Documentation Now Integrated into CisTrade!

Your comprehensive documentation is now fully integrated and accessible from within the CisTrade application.

---

## 🚀 How to Access Documentation

### 1. From Within the Application

**Option A: Help Button (Top Navbar)**
- Click the **?** (question mark) icon in the top right corner of any page
- Opens documentation in a new tab

**Option B: Sidebar Navigation**
- Look in the left sidebar under **System** section
- Click on **Documentation** (has a book icon with external link indicator)
- Opens documentation in a new tab

Both options open: `/static/docs/index.html`

---

### 2. Direct URL Access

When your Django server is running at `http://localhost:8000`:

- **Main Documentation**: http://localhost:8000/static/docs/index.html

**Direct Section Links**:
- Business User Guides: http://localhost:8000/static/docs/business/
- Technical Docs: http://localhost:8000/static/docs/technical/
- BA Documentation: http://localhost:8000/static/docs/integration/

---

### 3. Local Development Server (MkDocs)

For live preview with auto-reload during documentation editing:

```bash
cd /Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/docs
mkdocs serve
```

Then open: http://127.0.0.1:8000

---

## 📚 What's Available

### Business User Guides
✅ **Portfolio Management** (3,000+ words)
  - Creating portfolios
  - Editing and submitting
  - Search and filter
  - Close/Reactivate workflows
  - Troubleshooting and FAQs

✅ **Four-Eyes Workflow** (3,500+ words)
  - Maker vs Checker roles
  - Approval process
  - Best practices
  - Compliance requirements
  - Complete workflow diagrams

### Technical Documentation
✅ **Architecture** (4,000+ words)
  - System architecture
  - Design patterns (Repository, Service, Four-Eyes, Soft Delete)
  - Layered architecture
  - Security model
  - Performance optimization

✅ **Database Schema** (3,500+ words)
  - All 6 Kudu tables documented
  - ER diagrams
  - CREATE statements
  - Sample queries
  - Partitioning strategy

### Features
- 📊 Mermaid diagrams (workflow, sequence, ER diagrams)
- 🔍 Full-text search
- 🌓 Dark/light mode toggle
- 📱 Mobile responsive
- 🎨 Professional Material theme
- 📑 Expandable FAQ sections
- 💻 Code syntax highlighting
- 📋 Copy-to-clipboard for code examples

---

## 🛠️ For Developers: Building Documentation

### Rebuild Static Documentation

When you make changes to documentation source files:

```bash
cd docs
mkdocs build
cp -r site /Users/prakashhosalli/Personal_Data/Code/Django_projects/cis_trade_hive/Trade_Management_System/cis_trade_hive/static/docs
```

### Documentation Source Location

- **Source Files**: `docs/docs/` (Markdown files)
- **Configuration**: `docs/mkdocs.yml`
- **Built Site**: `docs/site/` (generated HTML)
- **Django Static**: `static/docs/` (served by Django)

### File Structure

```
docs/
├── docs/
│   ├── index.md                    # Homepage
│   ├── business/
│   │   ├── index.md
│   │   ├── portfolio-management.md ✅
│   │   └── four-eyes-workflow.md  ✅
│   ├── technical/
│   │   ├── index.md
│   │   ├── architecture.md         ✅
│   │   └── database-schema.md      ✅
│   ├── integration/
│   │   └── index.md
│   └── changelog.md
├── mkdocs.yml                      # Configuration
└── site/                           # Built HTML (→ static/docs/)
```

---

## 📤 Sharing with Team

### For Business Users
Send them:
1. Application URL: http://your-server:8000
2. Tell them to click the **?** help icon in the top navbar
3. Or navigate to **System → Documentation** in the sidebar

### For Developers
Send them:
1. Link to Architecture docs
2. Link to Database Schema docs
3. Clone the repo and run `mkdocs serve` for local viewing

### For Confluence Integration
1. Build documentation: `mkdocs build`
2. Export to PDF: `mkdocs build` then use browser Print → PDF on key pages
3. Or use `mkdocs-with-pdf` plugin (install separately)
4. Upload PDFs to Confluence

---

## 🎯 What's Completed

✅ **Tasks 1-7 Complete:**

1. ✅ Set up MkDocs with Material theme
2. ✅ Created documentation folder structure
3. ✅ Portfolio Management guide (complete)
4. ✅ Four-Eyes Workflow guide (complete)
5. ✅ Architecture documentation (complete)
6. ✅ Database Schema documentation (complete)
7. ✅ **Documentation integrated into Django app**

**Total Documentation**: ~18,000 words across 10 pages

---

## 🔜 Next Steps (Optional)

Remaining tasks from original plan:

- Task 8: API Reference documentation
- Task 9-14: In-app help system with Kudu storage
- Task 15-17: Confluence integration
- Task 18-21: Additional materials (videos, PDFs, diagrams)

---

## 📧 Support

If you have questions or need help with the documentation:

- **Email**: cistrade-support@yourcompany.com
- **In-App**: Click the **?** help button
- **Slack**: #cistrade-support (if available)

---

**Last Updated**: 2025-12-27
**Documentation Version**: 1.0.0
**Django Server**: http://localhost:8000
