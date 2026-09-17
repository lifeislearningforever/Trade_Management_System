# CisTrade UI v3.0 - Quick Start Guide

## 5-Minute Setup

The enhanced UI system is **already integrated** into your application. All files are in place and ready to use!

---

## What's Already Working

### Automatic Features (No Setup Required):
- Page load progress bar
- Smooth scroll animations
- Table row navigation
- Keyboard shortcuts
- Lazy image loading
- Form validation
- Ripple effects on buttons

---

## How to Use New Features

### 1. Floating Label Forms

**Before:**
```html
<div class="form-group">
    <label for="email">Email</label>
    <input type="email" class="form-control" id="email">
</div>
```

**After:**
```html
<div class="form-group-floating">
    <input type="email" id="email" placeholder=" " required>
    <label for="email">Email Address</label>
</div>
```

**Note:** The `placeholder=" "` is required for the floating effect to work!

---

### 2. Show Toast Notifications

**Instead of Django messages:**
```javascript
// In your template or JavaScript
CisTrade.createAdvancedToast(
    'Success!',
    'Portfolio created successfully.',
    'success',
    5000  // Duration in ms
);

// Types: 'success', 'error', 'warning', 'info'
```

---

### 3. Enhanced Tables

**Add one class:**
```html
<table class="table table-advanced">
    <!-- Your existing table code -->
</table>
```

**Benefits:**
- Sticky headers
- Animated hover effects
- Better visual feedback

---

### 4. Metric Cards (Dashboard Stats)

**Replace standard stat cards:**
```html
<div class="metric-card">
    <div class="metric-value">$2.5M</div>
    <div class="metric-label">Total Portfolio Value</div>
    <div class="metric-trend trend-up">
        <i class="bi bi-arrow-up"></i> +12.5%
    </div>
</div>
```

---

### 5. Status Pills

**Replace badges:**
```html
<!-- Before -->
<span class="badge badge-success">Active</span>

<!-- After -->
<span class="status-pill status-active">Active</span>
```

**Available:** `status-active`, `status-pending`, `status-inactive`

---

### 6. Auto-Save Forms

**Enable auto-save with one line:**
```html
<form id="portfolio-form" method="post">
    <!-- Your form fields -->
</form>

<script>
    // Auto-save every 5 seconds
    CisTrade.initAutoSave('portfolio-form', 5000);
</script>
```

**Benefits:**
- Saves to localStorage automatically
- Restores on page reload
- Shows notification when restored

---

### 7. Glassmorphism Cards

**Add glass effect:**
```html
<div class="card glass-card">
    <div class="card-body">
        Premium frosted glass effect
    </div>
</div>
```

---

### 8. Advanced Loading States

**Show skeleton while loading:**
```javascript
const container = document.getElementById('content');

// Show loading
CisTrade.showSkeleton(container);

// After data loads
fetch('/api/data')
    .then(response => response.json())
    .then(data => {
        const html = renderData(data);
        CisTrade.hideSkeleton(container, html);
    });
```

---

## Keyboard Shortcuts (Power Users)

Your users can now use:
- `Ctrl/Cmd + K` - Jump to search
- `Ctrl/Cmd + /` - Show all shortcuts
- `ESC` - Close modals/dropdowns
- `Tab` - Navigate through elements

---

## CSS Utility Classes

### Hover Effects:
```html
<div class="card hover-lift">Lifts on hover</div>
<div class="card card-hover-glow">Glows on hover</div>
```

### Scrollbars:
```html
<div class="custom-scrollbar" style="overflow: auto;">
    Content with themed scrollbar
</div>
```

### Tooltips:
```html
<span class="tooltip-custom" data-tooltip="This is helpful info">
    Hover me
</span>
```

---

## JavaScript API Quick Reference

```javascript
// Available globally via window.CisTrade

// Notifications
CisTrade.createAdvancedToast(title, message, type, duration)
CisTrade.showToast(message, type, duration)

// Confirmation
const confirmed = await CisTrade.confirmAction('Delete this?', 'Confirm');
if (confirmed) {
    // User clicked confirm
}

// Smooth Scrolling
CisTrade.smoothScrollTo('#section-id', 80);

// Number Animation
const element = document.getElementById('counter');
CisTrade.animateValue(element, 0, 1000, 2000);

// Formatting
const price = CisTrade.formatCurrency(2500, 'USD');  // "$2,500.00"
const number = CisTrade.formatNumber(1234.567, 2);   // "1,234.57"
const date = CisTrade.formatDate('2025-12-25', 'long'); // "December 25, 2025"

// Copy to Clipboard
CisTrade.copyToClipboard('Text to copy');

// Loading States
CisTrade.showLoadingState(button, 'Saving...');
// After operation
CisTrade.hideLoadingState(button);
```

---

## Common Patterns

### Clickable Table Rows

```html
<tr data-href="{% url 'portfolio:detail' portfolio.id %}">
    <td>{{ portfolio.code }}</td>
    <td>{{ portfolio.name }}</td>
</tr>
```

**Automatically works!** Clicking the row navigates to the URL.

---

### Confirming Deletions

```html
<button onclick="handleDelete({{ portfolio.id }})">Delete</button>

<script>
async function handleDelete(id) {
    const confirmed = await CisTrade.confirmAction(
        'Are you sure you want to delete this portfolio?',
        'Confirm Deletion'
    );

    if (confirmed) {
        // Proceed with deletion
        CisTrade.showLoadingState(event.target, 'Deleting...');
        // Make API call...
    }
}
</script>
```

---

### Form Validation Feedback

```html
<div class="form-group-floating has-error">
    <input type="email" id="email" placeholder=" " required>
    <label for="email">Email Address</label>
</div>

<!-- Add 'has-success' for valid state -->
<!-- Add 'has-error' for error state -->
<!-- Validation happens automatically on blur -->
```

---

## Color Variables Reference

Use these in your custom styles:

```css
/* Primary colors */
var(--primary)       /* Main blue */
var(--primary-600)   /* Default shade */
var(--primary-50)    /* Lightest */

/* Semantic colors */
var(--success)       /* Green */
var(--danger)        /* Red */
var(--warning)       /* Amber */
var(--info)          /* Cyan */

/* Grays */
var(--gray-50) to var(--gray-900)

/* Spacing */
var(--space-1) to var(--space-12)

/* Shadows */
var(--shadow-sm) to var(--shadow-2xl)

/* Borders */
var(--radius-sm) to var(--radius-full)

/* Transitions */
var(--transition-fast)  /* 150ms */
var(--transition-base)  /* 200ms */
var(--transition-slow)  /* 300ms */
```

---

## Example: Complete Form with Modern UI

```html
<div class="card glass-card">
    <div class="card-header">
        <h5 class="card-title">
            <i class="bi bi-plus-circle text-primary"></i>
            Create Portfolio
        </h5>
    </div>
    <div class="card-body">
        <form id="create-portfolio-form" method="post">
            {% csrf_token %}

            <!-- Floating label input -->
            <div class="form-group-floating">
                <input type="text" id="code" name="code" placeholder=" " required>
                <label for="code">Portfolio Code</label>
            </div>

            <!-- Floating label input -->
            <div class="form-group-floating">
                <input type="text" id="name" name="name" placeholder=" " required>
                <label for="name">Portfolio Name</label>
            </div>

            <!-- Floating label textarea -->
            <div class="form-group-floating">
                <textarea id="description" name="description" placeholder=" " rows="4"></textarea>
                <label for="description">Description</label>
            </div>

            <!-- Buttons -->
            <div class="d-flex gap-3 justify-content-end">
                <a href="{% url 'portfolio:list' %}" class="btn btn-outline-secondary">
                    <i class="bi bi-x-circle"></i> Cancel
                </a>
                <button type="submit" class="btn btn-primary ripple">
                    <i class="bi bi-save"></i> Create Portfolio
                </button>
            </div>
        </form>
    </div>
</div>

<script>
    // Enable auto-save
    CisTrade.initAutoSave('create-portfolio-form', 5000);

    // Success handler
    document.getElementById('create-portfolio-form').addEventListener('submit', function(e) {
        e.preventDefault();

        // Show loading state
        const submitBtn = this.querySelector('[type="submit"]');
        CisTrade.showLoadingState(submitBtn, 'Creating...');

        // Simulate API call
        setTimeout(() => {
            CisTrade.createAdvancedToast(
                'Success!',
                'Portfolio created successfully.',
                'success'
            );
            CisTrade.hideLoadingState(submitBtn);
        }, 2000);
    });
</script>
```

---

## Troubleshooting

### Floating labels not working?
- Ensure `placeholder=" "` is present (with a space)
- Label must come AFTER the input in HTML

### Auto-save not working?
- Check that form has an ID
- Ensure localStorage is enabled in browser
- Check browser console for errors

### Ripple effect not showing?
- Add `.ripple` class to button
- Effects initialize automatically on page load

### Tooltips not appearing?
- Use `data-tooltip` attribute, not `title`
- Or use `.tooltip-custom` class

---

## Need Help?

### Documentation:
- `/static/design_system.md` - Complete design system
- `/static/UI_REDESIGN_SUMMARY.md` - Full redesign details
- `/static/QUICK_START_GUIDE.md` - This document

### JavaScript Console:
```javascript
// All functions available in browser console
CisTrade.createAdvancedToast('Test', 'Testing toast', 'info');
```

### CSS Variables:
```javascript
// View all CSS variables in DevTools
getComputedStyle(document.documentElement).getPropertyValue('--primary');
```

---

## What's Next?

The system is ready to use! Start by:

1. Converting existing forms to floating labels
2. Replacing Django messages with toast notifications
3. Adding `.table-advanced` to tables
4. Using metric cards on dashboards
5. Enabling auto-save on complex forms

**Remember:** All features are already working. You're just choosing which ones to use!

---

**Created:** December 25, 2025
**Version:** 3.0 - Ultra Premium Edition
**Need more help?** Check the full documentation in `/static/design_system.md`
