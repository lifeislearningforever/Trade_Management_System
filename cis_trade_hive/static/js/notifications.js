/**
 * CIS Trade Hive — Real-time WebSocket notifications client
 *
 * Handles:
 *  - WebSocket lifecycle (connect / reconnect with exponential backoff)
 *  - Heartbeat ping/pong to detect stale connections
 *  - Per-message toast notifications (auto-dismiss)
 *  - Notification panel: badge count, list, mark-read, clear-all
 *  - Session-expiry redirect (close code 4001)
 *  - Tab visibility API: suppress toasts when tab is active & panel is open
 *  - Graceful degradation when WebSocket is unavailable
 */
(function () {
    'use strict';

    /* ------------------------------------------------------------------ */
    /* Config                                                               */
    /* ------------------------------------------------------------------ */
    var WS_URL         = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
                         window.location.host + '/ws/notifications/';
    var MAX_RETRIES    = 5;
    var BASE_DELAY_MS  = 1000;   // doubles each retry, max ~32 s
    var PING_INTERVAL  = 25000;  // 25 s — server heartbeat interval is 30 s
    var TOAST_DURATION = 5000;   // ms before auto-dismiss
    var MAX_LIST_SIZE  = 50;     // max notifications kept in panel

    // close codes
    var CLOSE_SESSION_EXPIRED = 4001;
    var CLOSE_FORBIDDEN       = 4003;

    /* ------------------------------------------------------------------ */
    /* State                                                                */
    /* ------------------------------------------------------------------ */
    var ws           = null;
    var retryCount   = 0;
    var retryTimer   = null;
    var pingTimer    = null;
    var pongReceived = true;  // assume alive until first ping cycle
    var panelOpen    = false;
    var notifications = [];   // [{id, type, severity, title, body, ts, read}]
    var unreadCount  = 0;
    var disabled     = false; // set true on 4001/4003 — stop reconnecting

    /* ------------------------------------------------------------------ */
    /* DOM refs (resolved after DOMContentLoaded)                          */
    /* ------------------------------------------------------------------ */
    var elBtn, elBadge, elPanel, elList, elEmpty,
        elMarkAll, elClearAll, elConnStatus, elToastContainer;

    /* ------------------------------------------------------------------ */
    /* Severity → Bootstrap colour map                                     */
    /* ------------------------------------------------------------------ */
    var SEV_CLASS = {
        info:    'text-info',
        success: 'text-success',
        warning: 'text-warning',
        error:   'text-danger'
    };
    var SEV_ICON = {
        info:    'bi-info-circle-fill',
        success: 'bi-check-circle-fill',
        warning: 'bi-exclamation-triangle-fill',
        error:   'bi-x-circle-fill'
    };
    var SEV_BG = {
        info:    'border-info',
        success: 'border-success',
        warning: 'border-warning',
        error:   'border-danger'
    };

    /* ================================================================== */
    /* WebSocket lifecycle                                                  */
    /* ================================================================== */
    function connect() {
        if (disabled || !('WebSocket' in window)) return;

        try {
            ws = new WebSocket(WS_URL);
        } catch (e) {
            scheduleReconnect();
            return;
        }

        ws.onopen    = onOpen;
        ws.onmessage = onMessage;
        ws.onclose   = onClose;
        ws.onerror   = onError;
    }

    function onOpen() {
        retryCount   = 0;
        pongReceived = true;
        setConnStatus('connected');
        startPing();
    }

    function onMessage(evt) {
        var msg;
        try {
            msg = JSON.parse(evt.data);
        } catch (e) {
            return;
        }

        if (msg.type === 'pong' || msg.event_type === 'EVT_PONG') {
            pongReceived = true;
            return;
        }

        handleNotification(msg);
    }

    function onClose(evt) {
        stopPing();
        setConnStatus('disconnected');

        if (evt.code === CLOSE_SESSION_EXPIRED) {
            disabled = true;
            redirectLogin();
            return;
        }
        if (evt.code === CLOSE_FORBIDDEN) {
            disabled = true;
            showSystemToast('Access denied — notification stream unavailable.', 'error');
            return;
        }

        scheduleReconnect();
    }

    function onError() {
        // onClose fires immediately after, which handles reconnect
    }

    function scheduleReconnect() {
        if (disabled || retryCount >= MAX_RETRIES) {
            setConnStatus('failed');
            return;
        }
        var delay = Math.min(BASE_DELAY_MS * Math.pow(2, retryCount), 32000);
        retryCount++;
        setConnStatus('reconnecting');
        retryTimer = setTimeout(connect, delay);
    }

    /* ------------------------------------------------------------------ */
    /* Heartbeat                                                            */
    /* ------------------------------------------------------------------ */
    function startPing() {
        stopPing();
        pingTimer = setInterval(function () {
            if (!ws || ws.readyState !== WebSocket.OPEN) return;

            if (!pongReceived) {
                // server didn't reply to last ping — connection is stale
                ws.close(1001, 'pong timeout');
                return;
            }
            pongReceived = false;
            try {
                ws.send(JSON.stringify({type: 'ping'}));
            } catch (e) { /* ignore */ }
        }, PING_INTERVAL);
    }

    function stopPing() {
        if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
    }

    /* ------------------------------------------------------------------ */
    /* Connection status indicator                                          */
    /* ------------------------------------------------------------------ */
    function setConnStatus(state) {
        if (!elConnStatus) return;
        var dot = elConnStatus.querySelector('i');
        if (!dot) return;
        dot.className = 'bi bi-circle-fill';
        var titles = {
            connected:    'Connected',
            disconnected: 'Disconnected — retrying…',
            reconnecting: 'Reconnecting…',
            failed:       'Connection failed'
        };
        var colours = {
            connected:    'text-success',
            disconnected: 'text-warning',
            reconnecting: 'text-warning',
            failed:       'text-danger'
        };
        dot.classList.add(colours[state] || 'text-secondary');
        elConnStatus.title = titles[state] || state;
    }

    /* ================================================================== */
    /* Message handling                                                     */
    /* ================================================================== */
    function handleNotification(msg) {
        var severity = msg.severity || 'info';
        var title    = msg.title    || eventLabel(msg.event_type);
        var body     = msg.message  || msg.body || '';

        var notif = {
            id:       msg.id || generateId(),
            type:     msg.event_type || 'EVT_UNKNOWN',
            severity: severity,
            title:    title,
            body:     body,
            ts:       msg.timestamp ? new Date(msg.timestamp) : new Date(),
            read:     false
        };

        // prepend, cap list
        notifications.unshift(notif);
        if (notifications.length > MAX_LIST_SIZE) {
            notifications = notifications.slice(0, MAX_LIST_SIZE);
        }

        unreadCount++;
        renderBadge();
        renderList();

        // show toast unless panel is open and tab is visible
        if (!(panelOpen && !document.hidden)) {
            showToast(notif);
        }
    }

    /* ================================================================== */
    /* Badge                                                                */
    /* ================================================================== */
    function renderBadge() {
        if (!elBadge) return;
        if (unreadCount <= 0) {
            elBadge.style.display = 'none';
            elBadge.textContent   = '0';
        } else {
            elBadge.textContent   = unreadCount > 99 ? '99+' : String(unreadCount);
            elBadge.style.display = '';
        }
    }

    /* ================================================================== */
    /* Notification list                                                    */
    /* ================================================================== */
    function renderList() {
        if (!elList || !elEmpty) return;

        if (notifications.length === 0) {
            elEmpty.style.display = '';
            // remove all <li> except empty placeholder
            Array.prototype.forEach.call(elList.querySelectorAll('li.notif-item'), function (el) {
                el.parentNode.removeChild(el);
            });
            return;
        }

        elEmpty.style.display = 'none';

        // rebuild list from scratch (max 50 items, fast enough)
        Array.prototype.forEach.call(elList.querySelectorAll('li.notif-item'), function (el) {
            el.parentNode.removeChild(el);
        });

        notifications.forEach(function (n) {
            var li = buildListItem(n);
            elList.appendChild(li);
        });
    }

    function buildListItem(n) {
        var li = document.createElement('li');
        li.className = 'notif-item' + (n.read ? ' notif-read' : ' notif-unread');
        li.dataset.id = n.id;

        var icon = '<i class="bi ' + (SEV_ICON[n.severity] || 'bi-bell') + ' ' +
                   (SEV_CLASS[n.severity] || '') + ' notif-icon"></i>';

        var timeStr = formatTime(n.ts);

        li.innerHTML =
            '<div class="notif-item-inner">' +
                icon +
                '<div class="notif-content">' +
                    '<div class="notif-title">' + escHtml(n.title) + '</div>' +
                    (n.body ? '<div class="notif-body">' + escHtml(n.body) + '</div>' : '') +
                    '<div class="notif-time">' + timeStr + '</div>' +
                '</div>' +
                '<button class="notif-dismiss" data-id="' + n.id + '" title="Dismiss">' +
                    '<i class="bi bi-x"></i>' +
                '</button>' +
            '</div>';

        li.querySelector('.notif-dismiss').addEventListener('click', function (e) {
            e.stopPropagation();
            dismissNotif(n.id);
        });

        li.addEventListener('click', function () {
            markRead(n.id);
        });

        return li;
    }

    function markRead(id) {
        var n = findNotif(id);
        if (!n || n.read) return;
        n.read = true;
        unreadCount = Math.max(0, unreadCount - 1);
        renderBadge();
        var li = elList && elList.querySelector('[data-id="' + id + '"]');
        if (li) {
            li.classList.remove('notif-unread');
            li.classList.add('notif-read');
        }
    }

    function markAllRead() {
        notifications.forEach(function (n) { n.read = true; });
        unreadCount = 0;
        renderBadge();
        Array.prototype.forEach.call(
            elList ? elList.querySelectorAll('.notif-unread') : [],
            function (el) {
                el.classList.remove('notif-unread');
                el.classList.add('notif-read');
            }
        );
    }

    function dismissNotif(id) {
        var n = findNotif(id);
        if (n && !n.read) {
            unreadCount = Math.max(0, unreadCount - 1);
        }
        notifications = notifications.filter(function (x) { return x.id !== id; });
        renderBadge();
        renderList();
    }

    function clearAll() {
        notifications = [];
        unreadCount   = 0;
        renderBadge();
        renderList();
    }

    function findNotif(id) {
        for (var i = 0; i < notifications.length; i++) {
            if (notifications[i].id === id) return notifications[i];
        }
        return null;
    }

    /* ================================================================== */
    /* Panel toggle                                                         */
    /* ================================================================== */
    function openPanel() {
        if (!elPanel || !elBtn) return;
        panelOpen = true;
        elPanel.style.display = '';
        elBtn.setAttribute('aria-expanded', 'true');
        // mark all read when opening
        markAllRead();
    }

    function closePanel() {
        if (!elPanel || !elBtn) return;
        panelOpen = false;
        elPanel.style.display = 'none';
        elBtn.setAttribute('aria-expanded', 'false');
    }

    function togglePanel() {
        if (panelOpen) { closePanel(); } else { openPanel(); }
    }

    /* ================================================================== */
    /* Toast notifications                                                  */
    /* ================================================================== */
    function ensureToastContainer() {
        if (!elToastContainer) {
            elToastContainer = document.createElement('div');
            elToastContainer.id        = 'notif-toast-container';
            elToastContainer.className = 'notif-toast-container';
            elToastContainer.setAttribute('aria-live', 'polite');
            elToastContainer.setAttribute('aria-atomic', 'false');
            document.body.appendChild(elToastContainer);
        }
        return elToastContainer;
    }

    function showToast(n) {
        var container = ensureToastContainer();
        var div = document.createElement('div');
        div.className = 'notif-toast ' + (SEV_BG[n.severity] || 'border-secondary');
        div.setAttribute('role', 'alert');

        div.innerHTML =
            '<div class="notif-toast-header">' +
                '<i class="bi ' + (SEV_ICON[n.severity] || 'bi-bell') + ' ' +
                    (SEV_CLASS[n.severity] || '') + ' me-2"></i>' +
                '<strong class="me-auto">' + escHtml(n.title) + '</strong>' +
                '<button class="notif-toast-close" title="Close">' +
                    '<i class="bi bi-x-lg"></i>' +
                '</button>' +
            '</div>' +
            (n.body ? '<div class="notif-toast-body">' + escHtml(n.body) + '</div>' : '');

        div.querySelector('.notif-toast-close').addEventListener('click', function () {
            removeToast(div);
        });

        container.appendChild(div);

        // trigger slide-in
        requestAnimationFrame(function () {
            div.classList.add('notif-toast-show');
        });

        var timer = setTimeout(function () { removeToast(div); }, TOAST_DURATION);
        div._dismissTimer = timer;
    }

    function removeToast(div) {
        if (div._dismissTimer) { clearTimeout(div._dismissTimer); }
        div.classList.remove('notif-toast-show');
        div.classList.add('notif-toast-hide');
        setTimeout(function () {
            if (div.parentNode) { div.parentNode.removeChild(div); }
        }, 300);
    }

    function showSystemToast(msg, severity) {
        showToast({
            id:       generateId(),
            type:     'EVT_SYSTEM',
            severity: severity || 'info',
            title:    'System',
            body:     msg,
            ts:       new Date(),
            read:     false
        });
    }

    /* ================================================================== */
    /* Helpers                                                              */
    /* ================================================================== */
    function redirectLogin() {
        showSystemToast('Your session has expired. Redirecting to login…', 'warning');
        setTimeout(function () {
            window.location.href = '/login/?next=' + encodeURIComponent(window.location.pathname);
        }, 2000);
    }

    function eventLabel(evtType) {
        var labels = {
            EVT_AVP_QUEUED:      'Position queued',
            EVT_AVP_PROCESSING:  'Processing position',
            EVT_AVP_COMPLETED:   'Position calculated',
            EVT_AVP_FAILED:      'Position failed',
            EVT_AVP_DEAD_LETTER: 'Position error',
            EVT_AVP_SLA_BREACH:  'SLA breach',
            EVT_UPLOAD_STARTED:  'Upload started',
            EVT_UPLOAD_STEP:     'Upload progress',
            EVT_UPLOAD_COMPLETED:'Upload complete',
            EVT_UPLOAD_FAILED:   'Upload failed',
            EVT_TRADE_CREATED:   'Trade created',
            EVT_TRADE_APPROVED:  'Trade approved',
            EVT_TRADE_REJECTED:  'Trade rejected',
            EVT_TRADE_SETTLED:   'Trade settled',
            EVT_SYSTEM_ERROR:    'System error',
            EVT_PING:            'Ping',
            EVT_PONG:            'Pong'
        };
        return evtType && labels[evtType] ? labels[evtType] : 'Notification';
    }

    function formatTime(date) {
        if (!date) return '';
        var now   = new Date();
        var diffS = Math.floor((now - date) / 1000);
        if (diffS < 60)  return 'just now';
        if (diffS < 3600) return Math.floor(diffS / 60) + 'm ago';
        if (diffS < 86400) return Math.floor(diffS / 3600) + 'h ago';
        return date.toLocaleDateString();
    }

    function escHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function generateId() {
        return 'n_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
    }

    /* ================================================================== */
    /* Tab visibility: reconnect when tab becomes visible                  */
    /* ================================================================== */
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && !disabled) {
            if (!ws || ws.readyState === WebSocket.CLOSED ||
                       ws.readyState === WebSocket.CLOSING) {
                retryCount = 0;
                connect();
            }
        }
    });

    /* ================================================================== */
    /* Bootstrap                                                            */
    /* ================================================================== */
    document.addEventListener('DOMContentLoaded', function () {
        elBtn        = document.getElementById('notifications-btn');
        elBadge      = document.getElementById('notification-badge');
        elPanel      = document.getElementById('notification-panel');
        elList       = document.getElementById('notification-list');
        elEmpty      = document.getElementById('notification-empty');
        elMarkAll    = document.getElementById('notif-mark-all-read');
        elClearAll   = document.getElementById('notif-clear-all');
        elConnStatus = document.getElementById('notification-conn-status');

        if (elBtn) {
            elBtn.addEventListener('click', function (e) {
                e.stopPropagation();
                togglePanel();
            });
        }

        if (elMarkAll) {
            elMarkAll.addEventListener('click', function (e) {
                e.stopPropagation();
                markAllRead();
            });
        }

        if (elClearAll) {
            elClearAll.addEventListener('click', function (e) {
                e.stopPropagation();
                clearAll();
            });
        }

        // close panel when clicking outside
        document.addEventListener('click', function (e) {
            if (!panelOpen) return;
            var wrapper = document.getElementById('notification-wrapper');
            if (wrapper && !wrapper.contains(e.target)) {
                closePanel();
            }
        });

        // close panel on Escape
        document.addEventListener('keydown', function (e) {
            if ((e.key === 'Escape' || e.keyCode === 27) && panelOpen) {
                closePanel();
            }
        });

        setConnStatus('disconnected');
        connect();
    });

    /* ================================================================== */
    /* Public API (for other scripts / testing)                            */
    /* ================================================================== */
    window.CISNotifications = {
        // Inject a test notification (dev/testing only)
        inject: function (msg) { handleNotification(msg); },
        // Force reconnect
        reconnect: function () { if (ws) { ws.close(); } else { connect(); } },
        // Current state
        getState: function () {
            return {
                connected:  ws ? ws.readyState === WebSocket.OPEN : false,
                unread:     unreadCount,
                count:      notifications.length,
                retryCount: retryCount
            };
        }
    };

}());
