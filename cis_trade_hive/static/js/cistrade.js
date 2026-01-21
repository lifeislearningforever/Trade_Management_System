/**
 * CisTrade - Custom JavaScript
 * Professional Trade Management System
 */

document.addEventListener('DOMContentLoaded', function() {
    // Sidebar Toggle for Mobile
    const sidebarToggleMobile = document.getElementById('sidebar-toggle');
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.querySelector('.main-content');

    if (sidebarToggleMobile && sidebar) {
        sidebarToggleMobile.addEventListener('click', function() {
            sidebar.classList.toggle('show');
        });

        // Close sidebar when clicking outside on mobile
        document.addEventListener('click', function(event) {
            if (window.innerWidth < 768) {
                if (!sidebar.contains(event.target) && !sidebarToggleMobile.contains(event.target)) {
                    sidebar.classList.remove('show');
                }
            }
        });
    }

    // Note: Sidebar Collapse/Expand Toggle is handled by sidebar-toggle.js
    // This prevents duplicate event handlers and conflicts

    // User Menu Dropdown
    const userMenu = document.getElementById('user-menu');
    const userDropdown = document.getElementById('user-dropdown');

    if (userMenu && userDropdown) {
        userMenu.addEventListener('click', function(event) {
            event.stopPropagation();
            const isVisible = userDropdown.style.display === 'block';
            userDropdown.style.display = isVisible ? 'none' : 'block';

            // Position dropdown
            const rect = userMenu.getBoundingClientRect();
            userDropdown.style.position = 'absolute';
            userDropdown.style.top = (rect.bottom + 5) + 'px';
            userDropdown.style.right = '2rem';
            userDropdown.style.zIndex = '1050';
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', function() {
            userDropdown.style.display = 'none';
        });
    }

    // Global Search
    const globalSearch = document.getElementById('global-search');
    if (globalSearch) {
        globalSearch.addEventListener('keyup', function(event) {
            if (event.key === 'Enter') {
                const searchTerm = this.value.trim();
                if (searchTerm) {
                    window.location.href = `/search/?q=${encodeURIComponent(searchTerm)}`;
                }
            }
        });
    }

    // Auto-hide alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Confirm Delete Actions
    const deleteButtons = document.querySelectorAll('[data-confirm-delete]');
    deleteButtons.forEach(function(button) {
        button.addEventListener('click', function(event) {
            const message = this.getAttribute('data-confirm-delete') || 'Are you sure you want to delete this item?';
            if (!confirm(message)) {
                event.preventDefault();
            }
        });
    });

    // Form Validation Enhancement
    const forms = document.querySelectorAll('form[data-validate]');
    forms.forEach(function(form) {
        form.addEventListener('submit', function(event) {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Table Row Click (for list pages)
    const clickableRows = document.querySelectorAll('tr[data-href]');
    clickableRows.forEach(function(row) {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function(event) {
            // Don't trigger if clicking on a button or link
            if (event.target.tagName !== 'BUTTON' && event.target.tagName !== 'A' && !event.target.closest('button') && !event.target.closest('a')) {
                window.location.href = this.getAttribute('data-href');
            }
        });
    });

    // CSV Export Button
    const exportButtons = document.querySelectorAll('[data-export-csv]');
    exportButtons.forEach(function(button) {
        button.addEventListener('click', function() {
            const url = this.getAttribute('data-export-csv');
            if (url) {
                window.location.href = url;
            }
        });
    });

    // Notification Button (Placeholder)
    const notificationsBtn = document.getElementById('notifications-btn');
    if (notificationsBtn) {
        notificationsBtn.addEventListener('click', function() {
            // TODO: Implement notifications panel
            alert('Notifications feature coming soon!');
        });
    }

    // Initialize Tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize Popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Server Status Check (Simulated)
    const serverStatus = document.getElementById('server-status');
    if (serverStatus) {
        setInterval(function() {
            // In production, this would ping an API endpoint
            serverStatus.textContent = 'Online';
            serverStatus.style.color = 'var(--success-color)';
        }, 30000); // Check every 30 seconds
    }

    // Active Nav Link Highlighting
    const currentPath = window.location.pathname;
    const navLinks = document.querySelectorAll('.nav-link');
    navLinks.forEach(function(link) {
        const href = link.getAttribute('href');
        if (href && currentPath.startsWith(href) && href !== '/') {
            link.classList.add('active');
        }
    });
});

/**
 * Utility function to format currency
 */
function formatCurrency(amount, currency = 'USD') {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: currency
    }).format(amount);
}

/**
 * Utility function to format date
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    }).format(date);
}

/**
 * Utility function to format date and time
 */
function formatDateTime(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

/**
 * Show loading spinner
 */
function showLoading(message = 'Loading...') {
    const loader = document.createElement('div');
    loader.id = 'global-loader';
    loader.innerHTML = `
        <div style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5);
                    display: flex; align-items: center; justify-content: center; z-index: 9999;">
            <div style="background: white; padding: 2rem; border-radius: 0.5rem; text-align: center;">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-2 mb-0">${message}</p>
            </div>
        </div>
    `;
    document.body.appendChild(loader);
}

/**
 * Hide loading spinner
 */
function hideLoading() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.remove();
    }
}

/**
 * Show toast notification
 */
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    toastContainer.appendChild(toast);

    setTimeout(function() {
        const bsAlert = new bootstrap.Alert(toast);
        bsAlert.close();
    }, 3000);
}

/**
 * Create toast container if it doesn't exist
 */
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.style.position = 'fixed';
    container.style.top = '5rem';
    container.style.right = '1rem';
    container.style.zIndex = '1060';
    container.style.minWidth = '300px';
    document.body.appendChild(container);
    return container;
}

/**
 * =====================================================
 * Sortable Tables Functionality
 * =====================================================
 * Initialize sortable tables by adding class 'sortable-table' to the table
 * and class 'sortable' to the th elements that should be sortable.
 *
 * Usage:
 * <table class="table sortable-table">
 *   <thead>
 *     <tr>
 *       <th class="sortable" data-sort-type="text">Name</th>
 *       <th class="sortable" data-sort-type="number">Amount</th>
 *       <th class="sortable" data-sort-type="date">Date</th>
 *       <th class="sticky-action-column">Actions</th>
 *     </tr>
 *   </thead>
 *   ...
 * </table>
 */

/**
 * Initialize sortable tables
 */
function initSortableTables() {
    const tables = document.querySelectorAll('.sortable-table');

    tables.forEach(function(table) {
        const headers = table.querySelectorAll('th.sortable');

        headers.forEach(function(header, columnIndex) {
            header.addEventListener('click', function() {
                sortTable(table, columnIndex, header);
            });
        });
    });
}

/**
 * Sort table by column
 */
function sortTable(table, columnIndex, header) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;

    const rows = Array.from(tbody.querySelectorAll('tr'));
    const sortType = header.getAttribute('data-sort-type') || 'text';

    // Determine sort direction
    let ascending = true;
    if (header.classList.contains('sort-asc')) {
        ascending = false;
    }

    // Remove sort classes from all headers
    table.querySelectorAll('th.sortable').forEach(function(th) {
        th.classList.remove('sort-asc', 'sort-desc');
    });

    // Add appropriate sort class
    header.classList.add(ascending ? 'sort-asc' : 'sort-desc');

    // Sort rows
    rows.sort(function(rowA, rowB) {
        const cellA = rowA.cells[columnIndex];
        const cellB = rowB.cells[columnIndex];

        if (!cellA || !cellB) return 0;

        let valueA = getCellValue(cellA, sortType);
        let valueB = getCellValue(cellB, sortType);

        let comparison = 0;

        switch (sortType) {
            case 'number':
                comparison = valueA - valueB;
                break;
            case 'date':
                comparison = valueA - valueB;
                break;
            case 'text':
            default:
                comparison = valueA.localeCompare(valueB, undefined, {numeric: true, sensitivity: 'base'});
                break;
        }

        return ascending ? comparison : -comparison;
    });

    // Re-append sorted rows
    rows.forEach(function(row) {
        tbody.appendChild(row);
    });
}

/**
 * Get cell value for sorting
 */
function getCellValue(cell, sortType) {
    // Get text content, handling badges and other elements
    let text = cell.textContent.trim();

    // Also check for data-sort-value attribute for custom sort values
    if (cell.hasAttribute('data-sort-value')) {
        text = cell.getAttribute('data-sort-value');
    }

    switch (sortType) {
        case 'number':
            // Remove currency symbols, commas, and parse as float
            const numStr = text.replace(/[^0-9.-]/g, '');
            return parseFloat(numStr) || 0;

        case 'date':
            // Parse date string
            const date = new Date(text);
            return isNaN(date.getTime()) ? 0 : date.getTime();

        case 'text':
        default:
            return text.toLowerCase();
    }
}

// Initialize sortable tables when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    initSortableTables();
});
