/**
 * CIS Trade Hive - Select2 Global Initialization
 *
 * This file provides uniform Select2 dropdown functionality across all forms.
 * Include this file after jQuery and Select2 are loaded.
 *
 * Usage:
 *   1. Add class "select2-searchable" to any <select> element for searchable dropdown
 *   2. Add class "select2-basic" for basic Select2 styling without search
 *   3. Or call CISSelect2.init() to initialize all .form-select elements
 *   4. Use CISSelect2.initElement(selector) for specific elements
 *
 * Data attributes:
 *   data-placeholder="Select Option"  - Custom placeholder text
 *   data-allow-clear="true"           - Allow clearing selection
 *   data-minimum-results="5"          - Show search only if more than N options
 */

var CISSelect2 = (function() {
    'use strict';

    // Default configuration
    var defaultConfig = {
        theme: 'bootstrap-5',
        allowClear: true,
        width: '100%',
        minimumResultsForSearch: 0,  // Always show search box (set to Infinity to hide)
        delay: 0,  // Instant search, no debounce delay
        closeOnSelect: true,
        language: {
            noResults: function() {
                return 'No results found';
            },
            searching: function() {
                return 'Searching...';
            }
        }
    };

    /**
     * Custom matcher for fast case-insensitive search
     * Matches anywhere in the text, not just at the beginning
     */
    function customMatcher(params, data) {
        // If there are no search terms, return all data
        if ($.trim(params.term) === '') {
            return data;
        }

        // Skip if there is no 'text' property
        if (typeof data.text === 'undefined') {
            return null;
        }

        // Fast case-insensitive search
        var term = params.term.toLowerCase();
        var text = data.text.toLowerCase();

        // Check if the text contains the search term
        if (text.indexOf(term) > -1) {
            return data;
        }

        // Return null if the term does not match
        return null;
    }

    /**
     * Get configuration from data attributes
     */
    function getDataConfig($element) {
        var config = {};

        if ($element.data('placeholder')) {
            config.placeholder = $element.data('placeholder');
        } else {
            // Try to get placeholder from first option if it's empty value
            var firstOption = $element.find('option:first');
            if (firstOption.val() === '' && firstOption.text()) {
                config.placeholder = firstOption.text();
            }
        }

        if ($element.data('allow-clear') !== undefined) {
            config.allowClear = $element.data('allow-clear');
        }

        if ($element.data('minimum-results') !== undefined) {
            config.minimumResultsForSearch = parseInt($element.data('minimum-results'));
        }

        return config;
    }

    /**
     * Initialize Select2 on a specific element
     */
    function initElement(selector, customConfig) {
        var $elements = $(selector);

        $elements.each(function() {
            var $el = $(this);

            // Skip if already initialized
            if ($el.hasClass('select2-hidden-accessible')) {
                return;
            }

            // Skip if disabled
            if ($el.prop('disabled')) {
                return;
            }

            // Merge configurations: default < data attributes < custom
            var dataConfig = getDataConfig($el);
            var config = $.extend({}, defaultConfig, dataConfig, customConfig || {});

            // Always use custom matcher for searchable dropdowns
            config.matcher = customMatcher;

            // Initialize Select2
            $el.select2(config);

            // Trigger native change event on selection for compatibility with validation
            $el.on('select2:select select2:clear', function(e) {
                this.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
    }

    /**
     * Initialize Select2 on all form-select elements in a container
     */
    function initAll(container) {
        var $container = container ? $(container) : $(document);

        // Initialize elements with explicit class
        initElement($container.find('.select2-searchable'));

        // Initialize elements with basic class (no search)
        initElement($container.find('.select2-basic'), {
            minimumResultsForSearch: Infinity
        });
    }

    /**
     * Initialize Select2 on specific form selects by ID
     */
    function initByIds(ids, customConfig) {
        ids.forEach(function(id) {
            initElement('#' + id, customConfig);
        });
    }

    /**
     * Destroy Select2 on specific elements
     */
    function destroy(selector) {
        var $elements = $(selector);
        $elements.each(function() {
            if ($(this).hasClass('select2-hidden-accessible')) {
                $(this).select2('destroy');
            }
        });
    }

    /**
     * Refresh/reinitialize Select2 on specific elements
     */
    function refresh(selector, customConfig) {
        destroy(selector);
        initElement(selector, customConfig);
    }

    // Public API
    return {
        init: initAll,
        initElement: initElement,
        initByIds: initByIds,
        destroy: destroy,
        refresh: refresh,
        defaultConfig: defaultConfig,
        customMatcher: customMatcher
    };
})();

// Auto-initialize on document ready if jQuery is available
if (typeof jQuery !== 'undefined') {
    jQuery(document).ready(function() {
        // Auto-initialize elements with select2-searchable or select2-basic class
        CISSelect2.init();
    });
}
