# CisTrade UI/UX Quick Reference Guide

## Quick Start

The CisTrade application now features a modern, professional design system with:
- **Modern color palette** optimized for financial trading
- **Enhanced animations** and micro-interactions
- **Responsive design** that works on all devices
- **Accessibility** compliant with WCAG AA standards
- **Professional polish** with consistent spacing and typography

## Files Added/Modified

### New Files
- `/static/css/custom.css` - Enhanced design system CSS
- `/static/js/custom.js` - Modern UI interactions
- `/static/design_system.md` - Complete design documentation
- `/static/QUICK_REFERENCE.md` - This file

### Modified Files
- `/templates/base.html` - Includes custom CSS and JS
- `/templates/dashboard.html` - Enhanced stat cards
- `/templates/portfolio/portfolio_form.html` - Modern form design

## Common Patterns

### 1. Creating a Page Header

```html
<div class="content-header">
    <h1 class="content-title">
        <i class="bi bi-icon-name text-primary"></i> Page Title
    </h1>
    <p class="content-subtitle">Description of the page</p>
</div>
```

### 2. Adding a Stat Card

```html
<div class="stat-card" style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);">
    <div class="stat-icon">
        <i class="bi bi-briefcase-fill"></i>
    </div>
    <div class="stat-value" data-count="125">125</div>
    <div class="stat-label">Label Text</div>
    <div class="stat-change">
        <i class="bi bi-arrow-up"></i>
        <span>+12% from last month</span>
    </div>
</div>
```

**Available Gradients:**
- Blue: `linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)`
- Green: `linear-gradient(135deg, #059669 0%, #10b981 100%)`
- Orange: `linear-gradient(135deg, #d97706 0%, #f59e0b 100%)`
- Purple: `linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%)`

### 3. Creating a Card with Header

```html
<div class="card">
    <div class="card-header">
        <h5 class="card-title">
            <i class="bi bi-icon"></i> Card Title
        </h5>
        <button class="btn btn-sm btn-outline-primary">Action</button>
    </div>
    <div class="card-body">
        <!-- Content here -->
    </div>
</div>
```

### 4. Form Fields

#### Standard Input
```html
<div class="form-group">
    <label for="field-id" class="form-label required">Field Name</label>
    <input type="text" class="form-control" id="field-id"
           placeholder="Enter value" required>
    <div class="form-text">
        <i class="bi bi-info-circle"></i> Helper text
    </div>
</div>
```

#### Input with Icon
```html
<div class="input-group">
    <span class="input-group-text">
        <i class="bi bi-currency-dollar"></i>
    </span>
    <input type="number" class="form-control" placeholder="0.00">
</div>
```

#### Search Input
```html
<div class="input-group">
    <span class="input-group-text">
        <i class="bi bi-search"></i>
    </span>
    <input type="search" class="form-control" placeholder="Search...">
</div>
```

### 5. Buttons

```html
<!-- Primary Button -->
<button class="btn btn-primary">
    <i class="bi bi-plus-circle"></i> Create
</button>

<!-- Secondary Button -->
<button class="btn btn-outline-secondary">
    <i class="bi bi-x-circle"></i> Cancel
</button>

<!-- Success Button -->
<button class="btn btn-success">
    <i class="bi bi-check-circle"></i> Save
</button>

<!-- Button Sizes -->
<button class="btn btn-primary btn-sm">Small</button>
<button class="btn btn-primary">Default</button>
<button class="btn btn-primary btn-lg">Large</button>
```

### 6. Badges

```html
<span class="badge badge-success">Active</span>
<span class="badge badge-warning">Pending</span>
<span class="badge badge-danger">Rejected</span>
<span class="badge badge-info">Info</span>
<span class="badge badge-secondary">Draft</span>
```

### 7. Alerts

```html
<div class="alert alert-success alert-dismissible fade show">
    <i class="bi bi-check-circle"></i>
    <div>Success message</div>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
</div>
```

### 8. Tables

```html
<div class="card">
    <div class="card-header">
        <h5 class="card-title">Table Title</h5>
    </div>
    <div class="card-body p-0">
        <div class="table-responsive">
            <table class="table">
                <thead>
                    <tr>
                        <th>Column 1</th>
                        <th>Column 2</th>
                    </tr>
                </thead>
                <tbody>
                    <tr data-href="/detail/1">
                        <td>Data 1</td>
                        <td>Data 2</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
</div>
```

### 9. Empty State

```html
<div class="empty-state">
    <i class="bi bi-inbox"></i>
    <h3>No items found</h3>
    <p>Try adjusting your filters or create a new item</p>
    <button class="btn btn-primary">
        <i class="bi bi-plus-circle"></i> Create Item
    </button>
</div>
```

### 10. Loading State

```html
<!-- On a button -->
<button class="btn btn-primary" disabled>
    <span class="spinner-border spinner-border-sm me-2"></span>
    Loading...
</button>

<!-- Full page loader -->
<div style="text-align: center; padding: 3rem;">
    <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">Loading...</span>
    </div>
    <p class="mt-3">Loading data...</p>
</div>
```

## JavaScript Functions

Access via `window.CisTrade` object:

### Show Toast Notification
```javascript
CisTrade.showToast('Operation successful!', 'success');
CisTrade.showToast('Something went wrong', 'error');
CisTrade.showToast('Please wait...', 'info');
CisTrade.showToast('Action required', 'warning');
```

### Confirm Action
```javascript
const confirmed = await CisTrade.confirmAction(
    'Are you sure you want to delete this item?',
    'Confirm Delete'
);
if (confirmed) {
    // Proceed with deletion
}
```

### Format Currency
```javascript
const formatted = CisTrade.formatCurrency(1234.56, 'USD');
// Returns: "$1,234.56"
```

### Format Number
```javascript
const formatted = CisTrade.formatNumber(1234.567, 2);
// Returns: "1,234.57"
```

### Format Date
```javascript
const formatted = CisTrade.formatDate('2025-12-25', 'short');
// Returns: "Dec 25, 2025"

const formatted = CisTrade.formatDate('2025-12-25', 'long');
// Returns: "Thursday, December 25, 2025"

const formatted = CisTrade.formatDate('2025-12-25T10:30:00', 'full');
// Returns: "Dec 25, 2025, 10:30 AM"
```

### Show/Hide Loading State
```javascript
const button = document.getElementById('submit-btn');

// Show loading
CisTrade.showLoadingState(button, 'Processing...');

// After async operation
CisTrade.hideLoadingState(button);
```

### Copy to Clipboard
```javascript
await CisTrade.copyToClipboard('Text to copy');
// Shows success toast automatically
```

## Bootstrap Icons

Common icons used in the application:

```html
<!-- Navigation -->
<i class="bi bi-speedometer2"></i>     <!-- Dashboard -->
<i class="bi bi-briefcase"></i>        <!-- Portfolio -->
<i class="bi bi-currency-exchange"></i><!-- Currency -->
<i class="bi bi-building"></i>         <!-- Counterparty -->
<i class="bi bi-file-text"></i>        <!-- Audit Log -->

<!-- Actions -->
<i class="bi bi-plus-circle"></i>      <!-- Add/Create -->
<i class="bi bi-pencil"></i>           <!-- Edit -->
<i class="bi bi-trash"></i>            <!-- Delete -->
<i class="bi bi-check-circle"></i>     <!-- Approve/Success -->
<i class="bi bi-x-circle"></i>         <!-- Cancel/Reject -->
<i class="bi bi-save"></i>             <!-- Save -->
<i class="bi bi-download"></i>         <!-- Download -->
<i class="bi bi-upload"></i>           <!-- Upload -->

<!-- Status -->
<i class="bi bi-check-circle-fill"></i>    <!-- Active/Success -->
<i class="bi bi-clock-history"></i>        <!-- Pending -->
<i class="bi bi-exclamation-circle"></i>   <!-- Warning -->
<i class="bi bi-exclamation-triangle"></i> <!-- Error -->
<i class="bi bi-info-circle"></i>          <!-- Info -->

<!-- Other -->
<i class="bi bi-search"></i>           <!-- Search -->
<i class="bi bi-filter"></i>           <!-- Filter -->
<i class="bi bi-three-dots-vertical"></i> <!-- More options -->
<i class="bi bi-arrow-up"></i>         <!-- Increase -->
<i class="bi bi-arrow-down"></i>       <!-- Decrease -->
```

Find more icons at: https://icons.getbootstrap.com/

## Color Classes

### Text Colors
```html
<span class="text-primary">Primary text</span>
<span class="text-success">Success text</span>
<span class="text-danger">Danger text</span>
<span class="text-warning">Warning text</span>
<span class="text-info">Info text</span>
<span class="text-muted">Muted text</span>
```

### Background Colors
```html
<div class="bg-primary text-white">Primary background</div>
<div class="bg-success text-white">Success background</div>
<div class="bg-danger text-white">Danger background</div>
```

## Spacing Utilities

### Margin
```html
<div class="mt-4">Margin top</div>
<div class="mb-3">Margin bottom</div>
<div class="my-5">Margin top and bottom</div>
<div class="mx-auto">Margin left and right auto (center)</div>
```

### Padding
```html
<div class="p-4">Padding all sides</div>
<div class="px-3">Padding left and right</div>
<div class="py-2">Padding top and bottom</div>
```

### Gap (for flexbox/grid)
```html
<div class="d-flex gap-2">Items with 8px gap</div>
<div class="d-flex gap-3">Items with 12px gap</div>
<div class="d-flex gap-4">Items with 16px gap</div>
```

## Layout Utilities

### Flexbox
```html
<div class="d-flex align-items-center justify-content-between">
    <div>Left content</div>
    <div>Right content</div>
</div>
```

### Grid
```html
<div class="row g-4">
    <div class="col-md-6">Column 1</div>
    <div class="col-md-6">Column 2</div>
</div>
```

## Responsive Classes

### Display
```html
<div class="d-none d-md-block">Hidden on mobile, visible on tablet+</div>
<div class="d-md-none">Visible on mobile, hidden on tablet+</div>
```

### Grid Columns
```html
<div class="col-12 col-md-6 col-lg-4 col-xl-3">
    <!-- 12 cols mobile, 6 tablet, 4 desktop, 3 large desktop -->
</div>
```

## Best Practices

### Do's ✓
- Use semantic HTML elements
- Include icons with buttons and labels
- Provide loading states for async operations
- Show validation feedback inline
- Use the design system variables
- Test on mobile devices
- Ensure keyboard navigation works
- Add proper ARIA labels

### Don'ts ✗
- Don't use inline styles (use classes)
- Don't create custom colors (use palette)
- Don't hardcode spacing (use utilities)
- Don't ignore empty states
- Don't forget error handling
- Don't rely on color alone for information
- Don't make buttons too small (<44px)

## Performance Tips

1. **Images:** Use appropriate sizes, lazy load images
2. **Animations:** Keep under 300ms, use CSS transforms
3. **Tables:** Use pagination for large datasets
4. **Forms:** Debounce search inputs
5. **Loading:** Show skeleton screens during load

## Accessibility Checklist

- [ ] All images have alt text
- [ ] Forms have labels
- [ ] Buttons have descriptive text
- [ ] Color contrast meets WCAG AA
- [ ] Keyboard navigation works
- [ ] Focus states are visible
- [ ] Error messages are clear
- [ ] Screen reader tested

## Common Issues & Solutions

### Issue: Button not showing icon
**Solution:** Make sure Bootstrap Icons CSS is loaded
```html
<link rel="stylesheet" href="{% static 'bootstrap-icons/bootstrap-icons-1.11.3/font/bootstrap-icons.min.css' %}">
```

### Issue: Custom CSS not loading
**Solution:** Check static files are collected and path is correct
```bash
python manage.py collectstatic
```

### Issue: Animations not working
**Solution:** Ensure custom.js is loaded after bootstrap.bundle.js
```html
<script src="{% static 'js/bootstrap.bundle.min.js' %}"></script>
<script src="{% static 'js/cistrade.js' %}"></script>
<script src="{% static 'js/custom.js' %}"></script>
```

### Issue: Form validation not triggering
**Solution:** Make sure the form fields have `required` attribute
```html
<input type="text" class="form-control" required>
```

### Issue: Table not responsive on mobile
**Solution:** Wrap table in `.table-responsive` div
```html
<div class="table-responsive">
    <table class="table">...</table>
</div>
```

## Resources

- **Design System Documentation:** `/static/design_system.md`
- **Bootstrap 5 Docs:** https://getbootstrap.com/docs/5.0/
- **Bootstrap Icons:** https://icons.getbootstrap.com/
- **Color Palette Tool:** https://coolors.co/
- **Accessibility Checker:** https://wave.webaim.org/

## Support

For issues or questions:
1. Check this quick reference
2. Review the design system documentation
3. Inspect existing components in the templates
4. Test in browser dev tools

---

**Version:** 2.0
**Last Updated:** 2025-12-25
**Maintained By:** CisTrade Development Team
