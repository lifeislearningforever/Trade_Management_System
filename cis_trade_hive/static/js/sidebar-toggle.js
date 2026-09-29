/**
 * Sidebar Toggle Functionality
 * CIS Trade Hive - Sidebar collapse/expand with state persistence
 */

(function() {
    'use strict';

    // Define toggleSidebar as a global function
    window.toggleSidebar = function() {
        var sidebar = document.getElementById('sidebar');
        var mainContent = document.querySelector('.main-content');
        var toggleIcon = document.getElementById('toggleIcon');

        console.log('Toggle clicked - sidebar:', sidebar, 'mainContent:', mainContent, 'toggleIcon:', toggleIcon);

        if (sidebar) {
            sidebar.classList.toggle('collapsed');

            if (mainContent) {
                mainContent.classList.toggle('sidebar-collapsed');
            }

            // Check if collapsed
            var isCollapsed = sidebar.classList.contains('collapsed');
            console.log('Sidebar collapsed:', isCollapsed);

            // Update toggle icon
            if (toggleIcon) {
                if (isCollapsed) {
                    toggleIcon.classList.remove('bi-chevron-double-left');
                    toggleIcon.classList.add('bi-chevron-double-right');
                } else {
                    toggleIcon.classList.remove('bi-chevron-double-right');
                    toggleIcon.classList.add('bi-chevron-double-left');
                }
            }

            // Save state to localStorage
            try {
                localStorage.setItem('sidebarCollapsed', isCollapsed);
                console.log('Saved to localStorage:', isCollapsed);
            } catch (e) {
                console.warn('Could not save to localStorage:', e);
            }
        } else {
            console.error('Sidebar element not found!');
        }
    };

    // Restore sidebar state on page load
    function restoreSidebarState() {
        var sidebar = document.getElementById('sidebar');
        var mainContent = document.querySelector('.main-content');
        var toggleIcon = document.getElementById('toggleIcon');

        try {
            var isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
            console.log('Restoring sidebar state:', isCollapsed);

            if (isCollapsed && sidebar) {
                sidebar.classList.add('collapsed');

                if (mainContent) {
                    mainContent.classList.add('sidebar-collapsed');
                }

                // Update icon on load
                if (toggleIcon) {
                    toggleIcon.classList.remove('bi-chevron-double-left');
                    toggleIcon.classList.add('bi-chevron-double-right');
                }
            }
        } catch (e) {
            console.warn('Could not restore from localStorage:', e);
        }
    }

    // Initialize on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', restoreSidebarState);
    } else {
        // DOM already loaded
        restoreSidebarState();
    }

    console.log('Sidebar toggle script loaded successfully');
})();
