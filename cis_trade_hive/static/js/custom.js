/**
 * CisTrade - Enhanced Custom JavaScript
 * Version: 3.0 - Ultra Premium Edition
 * Next-Generation UI Interactions and Animations
 *
 * Features:
 * - Advanced form validation with floating labels
 * - Smooth animations and transitions
 * - Toast notifications
 * - Table enhancements
 * - Search optimization
 * - Accessibility improvements
 */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all enhancements
    initStatCounters();
    initFormValidation();
    initSearchEnhancements();
    initTableEnhancements();
    initAnimations();
    initTooltips();
    initThemeToggle();
});

/**
 * Animated Counter for Stat Cards
 */
function initStatCounters() {
    const statValues = document.querySelectorAll('.stat-value[data-count]');

    statValues.forEach(stat => {
        const target = parseInt(stat.getAttribute('data-count'));
        const duration = 2000; // 2 seconds
        const increment = target / (duration / 16); // 60fps
        let current = 0;

        const timer = setInterval(() => {
            current += increment;
            if (current >= target) {
                stat.textContent = target;
                clearInterval(timer);
            } else {
                stat.textContent = Math.floor(current);
            }
        }, 16);
    });
}

/**
 * Enhanced Form Validation with Real-time Feedback
 */
function initFormValidation() {
    const forms = document.querySelectorAll('form');

    forms.forEach(form => {
        const inputs = form.querySelectorAll('input[required], textarea[required], select[required]');

        inputs.forEach(input => {
            // Add validation on blur
            input.addEventListener('blur', function() {
                validateField(this);
            });

            // Add validation on input for immediate feedback
            input.addEventListener('input', function() {
                if (this.classList.contains('is-invalid')) {
                    validateField(this);
                }
            });
        });

        // Form submission validation
        form.addEventListener('submit', function(e) {
            let isValid = true;

            inputs.forEach(input => {
                if (!validateField(input)) {
                    isValid = false;
                }
            });

            if (!isValid) {
                e.preventDefault();
                // Scroll to first error
                const firstError = form.querySelector('.is-invalid');
                if (firstError) {
                    firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    firstError.focus();
                }
            }
        });
    });
}

/**
 * Validate Individual Form Field
 */
function validateField(field) {
    const value = field.value.trim();
    const isRequired = field.hasAttribute('required');
    const type = field.getAttribute('type');
    const maxLength = field.getAttribute('maxlength');

    let isValid = true;
    let errorMessage = '';

    // Required field validation
    if (isRequired && !value) {
        isValid = false;
        errorMessage = 'This field is required.';
    }

    // Email validation
    if (type === 'email' && value) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        if (!emailRegex.test(value)) {
            isValid = false;
            errorMessage = 'Please enter a valid email address.';
        }
    }

    // Number validation
    if (type === 'number' && value) {
        const min = parseFloat(field.getAttribute('min'));
        const max = parseFloat(field.getAttribute('max'));
        const numValue = parseFloat(value);

        if (isNaN(numValue)) {
            isValid = false;
            errorMessage = 'Please enter a valid number.';
        } else if (!isNaN(min) && numValue < min) {
            isValid = false;
            errorMessage = `Value must be at least ${min}.`;
        } else if (!isNaN(max) && numValue > max) {
            isValid = false;
            errorMessage = `Value must not exceed ${max}.`;
        }
    }

    // Max length validation
    if (maxLength && value.length > maxLength) {
        isValid = false;
        errorMessage = `Maximum ${maxLength} characters allowed.`;
    }

    // Update field state
    if (isValid) {
        field.classList.remove('is-invalid');
        field.classList.add('is-valid');
        removeFieldError(field);
    } else {
        field.classList.remove('is-valid');
        field.classList.add('is-invalid');
        showFieldError(field, errorMessage);
    }

    return isValid;
}

/**
 * Show Field Error Message
 */
function showFieldError(field, message) {
    removeFieldError(field);

    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = message;

    field.parentNode.appendChild(errorDiv);
}

/**
 * Remove Field Error Message
 */
function removeFieldError(field) {
    const existingError = field.parentNode.querySelector('.invalid-feedback');
    if (existingError) {
        existingError.remove();
    }
}

/**
 * Enhanced Search with Debouncing
 */
function initSearchEnhancements() {
    const searchInputs = document.querySelectorAll('input[type="search"], input[name="search"]');

    searchInputs.forEach(input => {
        let timeout;

        input.addEventListener('input', function() {
            clearTimeout(timeout);

            // Add loading indicator
            this.style.backgroundImage = 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'20\' height=\'20\' viewBox=\'0 0 20 20\'%3E%3Ccircle cx=\'10\' cy=\'10\' r=\'8\' fill=\'none\' stroke=\'%233b82f6\' stroke-width=\'2\'/%3E%3C/svg%3E")';
            this.style.backgroundRepeat = 'no-repeat';
            this.style.backgroundPosition = 'right 12px center';

            // Debounce search (500ms delay)
            timeout = setTimeout(() => {
                this.style.backgroundImage = 'none';
                // Auto-submit search form after typing stops
                const form = this.closest('form');
                if (form && this.value.length >= 2) {
                    // form.submit(); // Uncomment to enable auto-submit
                }
            }, 500);
        });
    });
}

/**
 * Enhanced Table Interactions
 */
function initTableEnhancements() {
    // Highlight selected row
    const tableRows = document.querySelectorAll('.table tbody tr');

    tableRows.forEach(row => {
        row.addEventListener('click', function(e) {
            // Don't highlight if clicking on button/link
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' ||
                e.target.closest('button') || e.target.closest('a')) {
                return;
            }

            // Remove previous selection
            tableRows.forEach(r => r.classList.remove('table-row-selected'));

            // Add selection
            this.classList.add('table-row-selected');
        });
    });

    // Add sorting capability
    const tableHeaders = document.querySelectorAll('.table th[data-sortable]');

    tableHeaders.forEach(header => {
        header.style.cursor = 'pointer';
        header.innerHTML += ' <i class="bi bi-arrow-down-up" style="font-size: 0.75rem; opacity: 0.5;"></i>';

        header.addEventListener('click', function() {
            // Sorting logic would go here
            console.log('Sort by:', this.textContent);
        });
    });
}

/**
 * Initialize Animations and Transitions
 */
function initAnimations() {
    // Fade in elements on scroll
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '0';
                entry.target.style.transform = 'translateY(20px)';

                setTimeout(() => {
                    entry.target.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }, 100);

                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    // Observe cards
    const cards = document.querySelectorAll('.card');
    cards.forEach(card => observer.observe(card));
}

/**
 * Initialize Bootstrap Tooltips
 */
function initTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl, {
            trigger: 'hover',
            delay: { show: 500, hide: 100 }
        });
    });

    // Add tooltips to truncated text
    const truncatedElements = document.querySelectorAll('[title]');
    truncatedElements.forEach(el => {
        if (el.scrollWidth > el.clientWidth) {
            new bootstrap.Tooltip(el);
        }
    });
}

/**
 * Theme Toggle (Light/Dark Mode)
 */
function initThemeToggle() {
    const themeToggle = document.getElementById('theme-toggle');

    if (themeToggle) {
        // Check for saved theme preference
        const currentTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', currentTheme);

        themeToggle.addEventListener('click', function() {
            const theme = document.documentElement.getAttribute('data-theme');
            const newTheme = theme === 'light' ? 'dark' : 'light';

            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);

            // Animate transition
            document.body.style.transition = 'background-color 0.3s ease, color 0.3s ease';
        });
    }
}

/**
 * Show Loading State
 */
function showLoadingState(element, message = 'Loading...') {
    const originalContent = element.innerHTML;
    element.setAttribute('data-original-content', originalContent);
    element.disabled = true;

    element.innerHTML = `
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        ${message}
    `;
}

/**
 * Hide Loading State
 */
function hideLoadingState(element) {
    const originalContent = element.getAttribute('data-original-content');
    if (originalContent) {
        element.innerHTML = originalContent;
        element.disabled = false;
        element.removeAttribute('data-original-content');
    }
}

/**
 * Show Toast Notification
 */
function showToast(message, type = 'info', duration = 3000) {
    const toastContainer = document.getElementById('toast-container') || createToastContainer();

    const toastId = 'toast-' + Date.now();
    const iconMap = {
        success: 'bi-check-circle-fill',
        error: 'bi-exclamation-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        info: 'bi-info-circle-fill'
    };

    const toast = document.createElement('div');
    toast.id = toastId;
    toast.className = `alert alert-${type} alert-dismissible fade show`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <i class="bi ${iconMap[type] || iconMap.info}"></i>
        <div>${message}</div>
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;

    toastContainer.appendChild(toast);

    // Auto-dismiss
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

/**
 * Create Toast Container
 */
function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'messages-container';
    document.body.appendChild(container);
    return container;
}

/**
 * Confirm Dialog with Better UX
 */
function confirmAction(message, title = 'Confirm Action') {
    return new Promise((resolve) => {
        // Create modal backdrop
        const backdrop = document.createElement('div');
        backdrop.className = 'modal-backdrop fade show';
        backdrop.style.zIndex = '1050';

        // Create modal
        const modal = document.createElement('div');
        modal.className = 'modal fade show';
        modal.style.display = 'block';
        modal.style.zIndex = '1051';
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${title}</h5>
                        <button type="button" class="btn-close" data-dismiss="modal"></button>
                    </div>
                    <div class="modal-body">
                        <p>${message}</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-secondary" data-dismiss="modal">Cancel</button>
                        <button type="button" class="btn btn-primary" data-confirm="true">Confirm</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(backdrop);
        document.body.appendChild(modal);

        // Handle button clicks
        modal.querySelector('[data-confirm="true"]').addEventListener('click', () => {
            cleanup();
            resolve(true);
        });

        modal.querySelectorAll('[data-dismiss="modal"]').forEach(btn => {
            btn.addEventListener('click', () => {
                cleanup();
                resolve(false);
            });
        });

        function cleanup() {
            modal.classList.remove('show');
            backdrop.classList.remove('show');
            setTimeout(() => {
                modal.remove();
                backdrop.remove();
            }, 300);
        }
    });
}

/**
 * Format Currency
 */
function formatCurrency(amount, currency = 'USD', locale = 'en-US') {
    return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    }).format(amount);
}

/**
 * Format Number
 */
function formatNumber(number, decimals = 0, locale = 'en-US') {
    return new Intl.NumberFormat(locale, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(number);
}

/**
 * Format Date
 */
function formatDate(dateString, format = 'short') {
    const date = new Date(dateString);
    const options = {
        short: { year: 'numeric', month: 'short', day: 'numeric' },
        long: { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' },
        time: { hour: '2-digit', minute: '2-digit' },
        full: { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    };

    return new Intl.DateTimeFormat('en-US', options[format] || options.short).format(date);
}

/**
 * Debounce Function
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Copy to Clipboard
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success', 2000);
        return true;
    } catch (err) {
        showToast('Failed to copy to clipboard', 'error', 2000);
        return false;
    }
}

/**
 * Export Functions for Global Use
 */
window.CisTrade = {
    showToast,
    confirmAction,
    formatCurrency,
    formatNumber,
    formatDate,
    debounce,
    copyToClipboard,
    showLoadingState,
    hideLoadingState
};

/* =====================================================
   ULTRA PREMIUM JAVASCRIPT ENHANCEMENTS - Version 3.0
   ===================================================== */

/**
 * Initialize Floating Label Forms
 */
function initFloatingLabels() {
    const floatingGroups = document.querySelectorAll('.form-group-floating');

    floatingGroups.forEach(group => {
        const input = group.querySelector('input, textarea, select');
        const label = group.querySelector('label');

        if (!input || !label) return;

        // Handle autofill
        const checkAutofill = () => {
            if (input.matches(':-webkit-autofill') || input.value) {
                label.classList.add('active');
            }
        };

        // Check on load
        checkAutofill();

        // Check on animation (for autofill)
        input.addEventListener('animationstart', checkAutofill);

        // Real-time validation for floating labels
        input.addEventListener('blur', function() {
            validateFloatingField(group, this);
        });

        input.addEventListener('input', function() {
            if (group.classList.contains('has-error')) {
                validateFloatingField(group, this);
            }
        });
    });
}

/**
 * Validate Floating Label Field
 */
function validateFloatingField(group, input) {
    const value = input.value.trim();
    const isRequired = input.hasAttribute('required');

    group.classList.remove('has-success', 'has-error');

    if (isRequired && !value) {
        group.classList.add('has-error');
        return false;
    } else if (value) {
        // Additional validation based on type
        const type = input.getAttribute('type');
        if (type === 'email') {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(value)) {
                group.classList.add('has-error');
                return false;
            }
        }
        group.classList.add('has-success');
        return true;
    }

    return true;
}

/**
 * Enhanced Toast Notification System
 */
function createAdvancedToast(title, message, type = 'info', duration = 5000) {
    const toastContainer = document.getElementById('toast-container') || createAdvancedToastContainer();

    const icons = {
        success: 'bi-check-circle-fill',
        error: 'bi-exclamation-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        info: 'bi-info-circle-fill'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon">
            <i class="bi ${icons[type]}"></i>
        </div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-message">${message}</div>
        </div>
        <button type="button" class="toast-close" aria-label="Close">
            <i class="bi bi-x"></i>
        </button>
    `;

    toastContainer.appendChild(toast);

    // Close button
    toast.querySelector('.toast-close').addEventListener('click', () => {
        removeToast(toast);
    });

    // Auto-remove
    setTimeout(() => {
        removeToast(toast);
    }, duration);

    // Animate in
    setTimeout(() => toast.style.opacity = '1', 10);
}

function createAdvancedToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function removeToast(toast) {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
}

/**
 * Ripple Effect on Buttons
 */
function initRippleEffect() {
    const rippleButtons = document.querySelectorAll('.btn, .ripple');

    rippleButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const ripple = document.createElement('span');
            const rect = this.getBoundingClientRect();
            const size = Math.max(rect.width, rect.height);
            const x = e.clientX - rect.left - size / 2;
            const y = e.clientY - rect.top - size / 2;

            ripple.style.width = ripple.style.height = size + 'px';
            ripple.style.left = x + 'px';
            ripple.style.top = y + 'px';
            ripple.classList.add('ripple-effect');

            this.appendChild(ripple);

            setTimeout(() => ripple.remove(), 600);
        });
    });
}

/**
 * Skeleton Loading States
 */
function showSkeleton(container) {
    const skeleton = `
        <div class="skeleton-card">
            <div class="skeleton-loader skeleton-text-lg" style="width: 60%;"></div>
            <div class="skeleton-loader skeleton-text" style="width: 100%;"></div>
            <div class="skeleton-loader skeleton-text" style="width: 85%;"></div>
            <div class="skeleton-loader skeleton-text" style="width: 90%;"></div>
        </div>
    `;
    container.innerHTML = skeleton;
}

function hideSkeleton(container, content) {
    container.innerHTML = content;
}

/**
 * Smooth Scroll with Offset
 */
function smoothScrollTo(target, offset = 80) {
    const element = typeof target === 'string' ? document.querySelector(target) : target;
    if (!element) return;

    const elementPosition = element.getBoundingClientRect().top;
    const offsetPosition = elementPosition + window.pageYOffset - offset;

    window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
    });
}

/**
 * Table Row Click Navigation
 */
function initTableNavigation() {
    const clickableRows = document.querySelectorAll('tr[data-href]');

    clickableRows.forEach(row => {
        row.style.cursor = 'pointer';

        row.addEventListener('click', function(e) {
            // Don't navigate if clicking on action buttons
            if (e.target.closest('button, a, input, select')) return;

            const href = this.getAttribute('data-href');
            if (href) {
                window.location.href = href;
            }
        });
    });
}

/**
 * Auto-save Form Data to LocalStorage
 */
function initAutoSave(formId, interval = 5000) {
    const form = document.getElementById(formId);
    if (!form) return;

    const storageKey = `autosave_${formId}`;

    // Restore saved data
    const savedData = localStorage.getItem(storageKey);
    if (savedData) {
        const data = JSON.parse(savedData);
        Object.keys(data).forEach(key => {
            const input = form.querySelector(`[name="${key}"]`);
            if (input) input.value = data[key];
        });

        // Show restore notification
        createAdvancedToast(
            'Form Restored',
            'Your previous work has been restored.',
            'info',
            3000
        );
    }

    // Auto-save periodically
    const saveInterval = setInterval(() => {
        const formData = new FormData(form);
        const data = {};
        formData.forEach((value, key) => {
            data[key] = value;
        });
        localStorage.setItem(storageKey, JSON.stringify(data));
    }, interval);

    // Clear on successful submit
    form.addEventListener('submit', () => {
        localStorage.removeItem(storageKey);
        clearInterval(saveInterval);
    });
}

/**
 * Number Counter Animation
 */
function animateValue(element, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        const value = Math.floor(progress * (end - start) + start);
        element.textContent = value.toLocaleString();
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

/**
 * Image Lazy Loading
 */
function initLazyLoading() {
    const images = document.querySelectorAll('img[data-src]');

    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.removeAttribute('data-src');
                observer.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
}

/**
 * Keyboard Shortcuts
 */
function initKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + K: Focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const search = document.querySelector('input[type="search"], input[name="search"]');
            if (search) search.focus();
        }

        // Ctrl/Cmd + /: Show keyboard shortcuts
        if ((e.ctrlKey || e.metaKey) && e.key === '/') {
            e.preventDefault();
            showKeyboardShortcuts();
        }

        // Escape: Close modals/dropdowns
        if (e.key === 'Escape') {
            const modals = document.querySelectorAll('.modal.show');
            modals.forEach(modal => {
                const closeBtn = modal.querySelector('.btn-close, [data-dismiss="modal"]');
                if (closeBtn) closeBtn.click();
            });
        }
    });
}

function showKeyboardShortcuts() {
    const shortcuts = [
        { key: 'Ctrl/Cmd + K', action: 'Focus search' },
        { key: 'Ctrl/Cmd + /', action: 'Show shortcuts' },
        { key: 'Esc', action: 'Close modals' }
    ];

    let shortcutsHTML = '<div style="padding: 1rem;"><h4>Keyboard Shortcuts</h4><ul style="list-style: none; padding: 0;">';
    shortcuts.forEach(sc => {
        shortcutsHTML += `<li style="padding: 0.5rem 0;"><kbd style="background: var(--gray-200); padding: 0.25rem 0.5rem; border-radius: 4px; font-family: monospace;">${sc.key}</kbd> - ${sc.action}</li>`;
    });
    shortcutsHTML += '</ul></div>';

    createAdvancedToast('Keyboard Shortcuts', shortcutsHTML, 'info', 8000);
}

/**
 * Enhanced Data Tables
 */
function initAdvancedTable(tableSelector) {
    const table = document.querySelector(tableSelector);
    if (!table) return;

    // Add search
    const searchInput = document.createElement('input');
    searchInput.type = 'search';
    searchInput.className = 'form-control mb-3';
    searchInput.placeholder = 'Search in table...';
    table.parentElement.insertBefore(searchInput, table);

    searchInput.addEventListener('input', debounce(function() {
        const searchTerm = this.value.toLowerCase();
        const rows = table.querySelectorAll('tbody tr');

        rows.forEach(row => {
            const text = row.textContent.toLowerCase();
            row.style.display = text.includes(searchTerm) ? '' : 'none';
        });
    }, 300));

    // Add column sorting
    const headers = table.querySelectorAll('thead th');
    headers.forEach((header, index) => {
        header.style.cursor = 'pointer';
        header.innerHTML += ' <i class="bi bi-arrow-down-up ms-1" style="font-size: 0.75rem; opacity: 0.5;"></i>';

        header.addEventListener('click', function() {
            sortTable(table, index);
        });
    });
}

function sortTable(table, columnIndex) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const isAscending = table.dataset.sortOrder !== 'asc';

    rows.sort((a, b) => {
        const aText = a.cells[columnIndex].textContent.trim();
        const bText = b.cells[columnIndex].textContent.trim();

        // Try numeric sort first
        const aNum = parseFloat(aText.replace(/[^0-9.-]/g, ''));
        const bNum = parseFloat(bText.replace(/[^0-9.-]/g, ''));

        if (!isNaN(aNum) && !isNaN(bNum)) {
            return isAscending ? aNum - bNum : bNum - aNum;
        }

        // Fallback to string sort
        return isAscending ? aText.localeCompare(bText) : bText.localeCompare(aText);
    });

    rows.forEach(row => tbody.appendChild(row));
    table.dataset.sortOrder = isAscending ? 'asc' : 'desc';
}

/**
 * Progress Indicator for Page Load
 */
function initPageLoadProgress() {
    const progressBar = document.createElement('div');
    progressBar.id = 'page-load-progress';
    progressBar.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 0;
        height: 3px;
        background: linear-gradient(90deg, var(--primary-600), var(--accent-purple));
        z-index: 9999;
        transition: width 0.3s ease;
    `;
    document.body.appendChild(progressBar);

    let progress = 0;
    const interval = setInterval(() => {
        progress += Math.random() * 30;
        if (progress > 90) progress = 90;
        progressBar.style.width = progress + '%';
    }, 200);

    window.addEventListener('load', () => {
        clearInterval(interval);
        progressBar.style.width = '100%';
        setTimeout(() => {
            progressBar.style.opacity = '0';
            setTimeout(() => progressBar.remove(), 300);
        }, 200);
    });
}

// Initialize page load progress
initPageLoadProgress();

// Initialize additional features on DOM load
document.addEventListener('DOMContentLoaded', function() {
    initFloatingLabels();
    initRippleEffect();
    initTableNavigation();
    initLazyLoading();
    initKeyboardShortcuts();
});

// Export additional functions
window.CisTrade = {
    ...window.CisTrade,
    createAdvancedToast,
    smoothScrollTo,
    animateValue,
    showSkeleton,
    hideSkeleton,
    initAdvancedTable,
    initAutoSave
};
