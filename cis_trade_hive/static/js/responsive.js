/**
 * CisTrade - Responsive Display Controller
 * Handles dynamic font scaling and user preferences
 */

(function() {
    'use strict';

    // Configuration
    const STORAGE_KEY = 'cistrade_display_scale';
    const SCALE_OPTIONS = {
        'small': { class: 'font-scale-small', percent: '85%', scale: 0.85 },
        'default': { class: 'font-scale-default', percent: '100%', scale: 1.0 },
        'large': { class: 'font-scale-large', percent: '115%', scale: 1.15 },
        'xlarge': { class: 'font-scale-xlarge', percent: '130%', scale: 1.3 }
    };

    /**
     * Display Scale Controller
     */
    const DisplayController = {
        currentScale: 'default',

        /**
         * Initialize the display controller
         */
        init: function() {
            // Load saved preference
            this.loadPreference();

            // Apply saved scale immediately
            this.applyScale(this.currentScale, false);

            // Set up event listeners when DOM is ready
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', () => this.setupListeners());
            } else {
                this.setupListeners();
            }

            // Listen for storage changes from other tabs
            window.addEventListener('storage', (e) => {
                if (e.key === STORAGE_KEY && e.newValue) {
                    this.applyScale(e.newValue, false);
                    this.updateUI();
                }
            });

            // Detect screen size changes
            this.setupMediaQueryListeners();
        },

        /**
         * Load user preference from localStorage
         */
        loadPreference: function() {
            try {
                const saved = localStorage.getItem(STORAGE_KEY);
                if (saved && SCALE_OPTIONS[saved]) {
                    this.currentScale = saved;
                }
            } catch (e) {
                console.warn('Could not load display preference:', e);
            }
        },

        /**
         * Save user preference to localStorage
         */
        savePreference: function(scale) {
            try {
                localStorage.setItem(STORAGE_KEY, scale);
            } catch (e) {
                console.warn('Could not save display preference:', e);
            }
        },

        /**
         * Apply a font scale
         * @param {string} scale - Scale key (small, default, large, xlarge)
         * @param {boolean} save - Whether to save the preference
         */
        applyScale: function(scale, save = true) {
            if (!SCALE_OPTIONS[scale]) {
                console.warn('Invalid scale:', scale);
                return;
            }

            const html = document.documentElement;

            // Remove all scale classes
            Object.values(SCALE_OPTIONS).forEach(option => {
                html.classList.remove(option.class);
            });

            // Add the new scale class
            html.classList.add(SCALE_OPTIONS[scale].class);

            // Update CSS custom property as backup
            html.style.setProperty('--font-scale', SCALE_OPTIONS[scale].scale);

            this.currentScale = scale;

            if (save) {
                this.savePreference(scale);
            }

            // Update UI
            this.updateUI();

            // Dispatch event for any components that need to react
            window.dispatchEvent(new CustomEvent('displayScaleChanged', {
                detail: { scale: scale, percent: SCALE_OPTIONS[scale].percent }
            }));
        },

        /**
         * Set up click listeners for scale buttons
         */
        setupListeners: function() {
            const control = document.getElementById('font-size-control');
            if (!control) return;

            const buttons = control.querySelectorAll('.font-size-btn');
            buttons.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    const scale = btn.dataset.scale;
                    if (scale) {
                        this.applyScale(scale);
                    }
                });
            });

            // Initial UI update
            this.updateUI();
        },

        /**
         * Update the UI to reflect current scale
         */
        updateUI: function() {
            // Update button active states
            const buttons = document.querySelectorAll('.font-size-btn');
            buttons.forEach(btn => {
                const isActive = btn.dataset.scale === this.currentScale;
                btn.classList.toggle('active', isActive);
            });

            // Update indicator
            const indicator = document.getElementById('font-size-indicator');
            if (indicator && SCALE_OPTIONS[this.currentScale]) {
                indicator.textContent = SCALE_OPTIONS[this.currentScale].percent;
            }
        },

        /**
         * Set up media query listeners for automatic adjustments
         */
        setupMediaQueryListeners: function() {
            // Detect very large screens (4K+)
            const ultraWideQuery = window.matchMedia('(min-width: 2560px)');
            // Detect small laptops
            const smallScreenQuery = window.matchMedia('(max-width: 1279px)');

            // Log screen info for debugging (only in development)
            if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
                console.log('CisTrade Display Controller initialized');
                console.log('Screen width:', window.innerWidth);
                console.log('Screen height:', window.innerHeight);
                console.log('Device pixel ratio:', window.devicePixelRatio);
                console.log('Current scale:', this.currentScale);
            }
        },

        /**
         * Get current scale info
         */
        getScaleInfo: function() {
            return {
                scale: this.currentScale,
                ...SCALE_OPTIONS[this.currentScale]
            };
        },

        /**
         * Reset to default scale
         */
        reset: function() {
            this.applyScale('default');
        }
    };

    // Initialize immediately to prevent FOUC (Flash of Unstyled Content)
    DisplayController.init();

    // Expose to global scope for debugging and external access
    window.CisTradeDisplay = DisplayController;

})();


/**
 * Keyboard shortcuts for accessibility
 */
document.addEventListener('keydown', function(e) {
    // Ctrl/Cmd + Plus: Increase font size
    if ((e.ctrlKey || e.metaKey) && (e.key === '+' || e.key === '=')) {
        e.preventDefault();
        const scales = ['small', 'default', 'large', 'xlarge'];
        const currentIndex = scales.indexOf(window.CisTradeDisplay.currentScale);
        if (currentIndex < scales.length - 1) {
            window.CisTradeDisplay.applyScale(scales[currentIndex + 1]);
        }
    }

    // Ctrl/Cmd + Minus: Decrease font size
    if ((e.ctrlKey || e.metaKey) && e.key === '-') {
        e.preventDefault();
        const scales = ['small', 'default', 'large', 'xlarge'];
        const currentIndex = scales.indexOf(window.CisTradeDisplay.currentScale);
        if (currentIndex > 0) {
            window.CisTradeDisplay.applyScale(scales[currentIndex - 1]);
        }
    }

    // Ctrl/Cmd + 0: Reset to default
    if ((e.ctrlKey || e.metaKey) && e.key === '0') {
        e.preventDefault();
        window.CisTradeDisplay.reset();
    }
});
