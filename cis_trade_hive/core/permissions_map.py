"""
URL Permission Map
==================
Central declaration of which permission each named URL requires.

Format:
    'app_namespace:url_name': (permission_name, mode, allowed_methods)

    - permission_name : string matching cis_permission_info.permission_name
    - mode            : 'READ' or 'WRITE'
    - allowed_methods : tuple of HTTP methods that need this check,
                        or None to apply to ALL methods.
                        Use per-method dict for GET/POST split:
                        {'GET': ('perm', 'READ'), 'POST': ('perm', 'WRITE')}

Rules enforced by PermissionMiddleware:
    1. URL in EXEMPT_URL_NAMES  → always pass through (login, logout, health, etc.)
    2. User not logged in        → redirect to login
    3. URL not in map            → DEFAULT_DENY blocks with 403 (forces explicit opt-in)
    4. URL in map                → check permission + mode from session
    5. SKIP_PERMISSION_CHECKS    → bypass all checks (dev mode only)

Adding a new module:
    - Add URL patterns to your app's urls.py (no change needed here for that)
    - Add entries below for each new URL name
    - Add permission names to cis_permission_info via RBAC Admin UI
    - Assign permissions to groups via RBAC Admin → Groups → Permissions

Removing a module:
    - Remove the URL patterns from urls.py
    - Remove entries below
    - Optionally soft-delete permissions in RBAC Admin (audit trail preserved)
"""

# ---------------------------------------------------------------------------
# URLs that NEVER require a permission check (always pass through)
# Includes: auth pages, health checks, system APIs, static assets
# ---------------------------------------------------------------------------
EXEMPT_URL_NAMES = frozenset([
    # Auth
    'login',
    'logout',
    'auto_login',
    'home',

    # Health / ops (monitoring tools call these without a session)
    'core:health_check',
    'core:pool_stats',
    'core:reset_stats',
    'core:system_date_api',

    # Dashboard (permission checked inside the view itself via context)
    'dashboard',
    'global_search',
])

# ---------------------------------------------------------------------------
# Default deny
# If a URL is not in EXEMPT_URL_NAMES and not in URL_PERMISSION_MAP,
# the middleware BLOCKS it with 403.
# This forces every new URL to explicitly declare its permission requirement.
# Set to False only during initial development of a new module.
# ---------------------------------------------------------------------------
DEFAULT_DENY = True


# ---------------------------------------------------------------------------
# Central Permission Map
# 'namespace:url_name' → (permission_name, mode)
#   OR for GET/POST split:
# 'namespace:url_name' → {'GET': (perm, mode), 'POST': (perm, mode)}
# ---------------------------------------------------------------------------
URL_PERMISSION_MAP = {

    # =========================================================================
    # CORE — Audit & RBAC Admin
    # =========================================================================
    'core:audit_log':               ('audit-logs-read', 'READ'),

    # RBAC Admin (all routes require rbac-admin WRITE)
    'core:rbac_dashboard':          ('rbac-admin', 'WRITE'),
    'core:rbac_user_list':          ('rbac-admin', 'READ'),
    'core:rbac_user_create':        ('rbac-admin', 'WRITE'),
    'core:rbac_user_edit':          ('rbac-admin', 'WRITE'),
    'core:rbac_user_deactivate':    ('rbac-admin', 'WRITE'),
    'core:rbac_user_groups':        ('rbac-admin', 'WRITE'),
    'core:rbac_group_list':         ('rbac-admin', 'READ'),
    'core:rbac_group_create':       ('rbac-admin', 'WRITE'),
    'core:rbac_group_edit':         ('rbac-admin', 'WRITE'),
    'core:rbac_group_permissions':  ('rbac-admin', 'WRITE'),
    'core:rbac_permission_list':    ('rbac-admin', 'READ'),
    'core:rbac_permission_create':  ('rbac-admin', 'WRITE'),
    'core:rbac_audit':              ('rbac-admin', 'READ'),

    # =========================================================================
    # PORTFOLIO
    # =========================================================================
    'portfolio:list':               ('portfolio-list', 'READ'),
    'portfolio:dashboard':          ('portfolio-list', 'READ'),
    'portfolio:detail':             ('portfolio-view', 'READ'),
    'portfolio:create':             {
                                        'GET':  ('portfolio-create', 'READ'),
                                        'POST': ('portfolio-create', 'WRITE'),
                                    },
    'portfolio:edit':               {
                                        'GET':  ('portfolio-edit', 'READ'),
                                        'POST': ('portfolio-edit', 'WRITE'),
                                    },
    'portfolio:submit':             ('portfolio-edit', 'WRITE'),
    'portfolio:cancel':             ('portfolio-edit', 'WRITE'),
    'portfolio:reactivate':         ('portfolio-edit', 'WRITE'),
    'portfolio:validate':           ('portfolio-approval', 'WRITE'),
    'portfolio:settle':             ('portfolio-approval', 'WRITE'),
    'portfolio:approve':            ('portfolio-approval', 'WRITE'),
    'portfolio:reject':             ('portfolio-approval', 'WRITE'),
    'portfolio:close':              ('portfolio-approval', 'WRITE'),
    'portfolio:pending_validation': ('portfolio-approval', 'READ'),
    'portfolio:pending_settlement': ('portfolio-approval', 'READ'),
    'portfolio:pending_approvals':  ('portfolio-approval', 'READ'),

    # =========================================================================
    # TRADE
    # =========================================================================
    'trade:list':                   ('trade-list', 'READ'),
    'trade:dashboard':              ('trade-list', 'READ'),
    'trade:detail':                 ('trade-view', 'READ'),
    'trade:history':                ('trade-view', 'READ'),
    'trade:create':                 {
                                        'GET':  ('trade-create', 'READ'),
                                        'POST': ('trade-create', 'WRITE'),
                                    },
    'trade:create_type':            {
                                        'GET':  ('trade-create', 'READ'),
                                        'POST': ('trade-create', 'WRITE'),
                                    },
    'trade:edit':                   {
                                        'GET':  ('trade-edit', 'READ'),
                                        'POST': ('trade-edit', 'WRITE'),
                                    },
    'trade:delete':                 ('trade-edit', 'WRITE'),
    'trade:submit':                 ('trade-edit', 'WRITE'),
    'trade:validate':               ('trade-approval', 'WRITE'),
    'trade:settle':                 ('trade-approval', 'WRITE'),
    'trade:cancel':                 ('trade-approval', 'WRITE'),
    'trade:reactivate':             ('trade-approval', 'WRITE'),
    'trade:pending_validation':     ('trade-approval', 'READ'),
    'trade:pending_settlement':     ('trade-approval', 'READ'),

    # Positions
    'trade:position_list':          ('position-list', 'READ'),

    # Cash Flows
    'trade:cash_flow_list':         ('cash-flow-list', 'READ'),
    'trade:cash_flow_detail':       ('cash-flow-list', 'READ'),
    'trade:cash_flow_create':       {
                                        'GET':  ('cash-flow-create', 'READ'),
                                        'POST': ('cash-flow-create', 'WRITE'),
                                    },
    'trade:cash_flow_edit':         {
                                        'GET':  ('cash-flow-list', 'READ'),
                                        'POST': ('cash-flow-create', 'WRITE'),
                                    },
    'trade:cash_flow_delete':       ('cash-flow-create', 'WRITE'),
    'trade:cash_flow_restore':      ('cash-flow-create', 'WRITE'),
    'trade:cash_flow_approve':      ('cash-flow-approval', 'WRITE'),
    'trade:cash_flow_pending_approvals': ('cash-flow-approval', 'READ'),

    # Trade AJAX APIs (called from within already-gated pages — READ is enough)
    'trade:api_validate_portfolio':         ('trade-list', 'READ'),
    'trade:api_validate_security':          ('trade-list', 'READ'),
    'trade:api_validate_counterparty':      ('trade-list', 'READ'),
    'trade:api_validate_settlement_date':   ('trade-list', 'READ'),
    'trade:api_portfolios':                 ('trade-list', 'READ'),
    'trade:api_securities':                 ('trade-list', 'READ'),
    'trade:api_counterparties':             ('trade-list', 'READ'),
    'trade:api_get_position':               ('trade-list', 'READ'),
    'trade:api_portfolios_detailed':        ('trade-list', 'READ'),
    'trade:api_securities_detailed':        ('trade-list', 'READ'),
    'trade:api_currencies':                 ('trade-list', 'READ'),
    'trade:api_securities_by_currency':     ('trade-list', 'READ'),
    'trade:api_get_equity_price':           ('trade-list', 'READ'),
    'trade:api_get_fx_rate':                ('trade-list', 'READ'),
    'trade:api_get_broker_charges':         ('trade-list', 'READ'),
    'trade:api_calculate_charges':          ('trade-list', 'READ'),
    'trade:api_get_exchanges':              ('trade-list', 'READ'),
    'trade:api_debug_charge_lut':           ('trade-list', 'READ'),
    'trade:api_validate_cf_portfolio':      ('cash-flow-list', 'READ'),
    'trade:api_validate_cf_security':       ('cash-flow-list', 'READ'),

    # Event queue management (ops/admin — reuse rbac-admin or trade-approval)
    'trade:api_worker_health':                      ('trade-list', 'READ'),
    'trade:api_trade_event_queue_health':           ('trade-approval', 'READ'),
    'trade:api_trade_event_queue_failed':           ('trade-approval', 'READ'),
    'trade:api_trade_event_reprocess':              ('trade-approval', 'WRITE'),
    'trade:api_trade_event_reprocess_all_failed':   ('trade-approval', 'WRITE'),
    'trade:api_trade_event_worker_start':           ('trade-approval', 'WRITE'),
    'trade:api_trade_event_worker_stop':            ('trade-approval', 'WRITE'),

    # =========================================================================
    # MARKET DATA
    # =========================================================================
    'market_data:market_data_dashboard': ('market-data-dashboard', 'READ'),
    'market_data:fx_rate_list':          ('fx-rates-list', 'READ'),
    'market_data:fx_dashboard':          ('fx-rates-list', 'READ'),
    'market_data:fx_rate_detail':        ('fx-rates-list', 'READ'),
    'market_data:equity_price_list':     ('equity-prices-list', 'READ'),
    'market_data:equity_price_create':   {
                                             'GET':  ('equity-prices-create', 'READ'),
                                             'POST': ('equity-prices-create', 'WRITE'),
                                         },
    'market_data:equity_price_detail':   ('equity-prices-list', 'READ'),
    'market_data:equity_price_edit':     {
                                             'GET':  ('equity-prices-list', 'READ'),
                                             'POST': ('equity-prices-create', 'WRITE'),
                                         },

    # =========================================================================
    # REFERENCE DATA
    # =========================================================================
    'reference_data:currency_list':     ('currencies-list', 'READ'),
    'reference_data:country_list':      ('countries-list', 'READ'),
    'reference_data:calendar_list':     ('calendars-list', 'READ'),

    # Counterparties
    'reference_data:counterparty_list':     ('parties-list', 'READ'),
    'reference_data:counterparty_detail':   ('parties-list', 'READ'),
    'reference_data:counterparty_create':   {
                                                'GET':  ('parties-create', 'READ'),
                                                'POST': ('parties-create', 'WRITE'),
                                            },
    'reference_data:counterparty_edit':     {
                                                'GET':  ('parties-list', 'READ'),
                                                'POST': ('parties-create', 'WRITE'),
                                            },
    'reference_data:counterparty_delete':   ('parties-create', 'WRITE'),
    'reference_data:counterparty_restore':  ('parties-create', 'WRITE'),
    'reference_data:counterparty_cif_list':   ('parties-list', 'READ'),
    'reference_data:counterparty_cif_create': ('parties-create', 'WRITE'),
    'reference_data:counterparty_cif_update': ('parties-create', 'WRITE'),
    'reference_data:counterparty_cif_delete': ('parties-create', 'WRITE'),

    # Parties
    'reference_data:party_list':            ('parties-list', 'READ'),
    'reference_data:party_detail':          ('parties-list', 'READ'),
    'reference_data:party_create':          {
                                                'GET':  ('parties-create', 'READ'),
                                                'POST': ('parties-create', 'WRITE'),
                                            },
    'reference_data:party_edit':            {
                                                'GET':  ('parties-list', 'READ'),
                                                'POST': ('parties-create', 'WRITE'),
                                            },
    'reference_data:party_delete':          ('parties-create', 'WRITE'),
    'reference_data:party_restore':         ('parties-create', 'WRITE'),
    'reference_data:party_validate':        ('parties-create', 'WRITE'),
    'reference_data:party_pending_approvals': ('parties-create', 'READ'),
    'reference_data:party_cif_list':        ('parties-list', 'READ'),
    'reference_data:party_cif_create':      ('parties-create', 'WRITE'),
    'reference_data:party_cif_update':      ('parties-create', 'WRITE'),
    'reference_data:party_cif_delete':      ('parties-create', 'WRITE'),

    # Corporate Actions
    'reference_data:corporate_action_list':             ('corp-action-list', 'READ'),
    'reference_data:corporate_action_detail':           ('corp-action-list', 'READ'),
    'reference_data:corporate_action_create':           {
                                                            'GET':  ('corp-action-create', 'READ'),
                                                            'POST': ('corp-action-create', 'WRITE'),
                                                        },
    'reference_data:corporate_action_edit':             {
                                                            'GET':  ('corp-action-list', 'READ'),
                                                            'POST': ('corp-action-create', 'WRITE'),
                                                        },
    'reference_data:corporate_action_delete':           ('corp-action-create', 'WRITE'),
    'reference_data:corporate_action_restore':          ('corp-action-create', 'WRITE'),
    'reference_data:corporate_action_validate':         ('corp-action-create', 'WRITE'),
    'reference_data:corporate_action_pending_approvals': ('corp-action-create', 'READ'),

    # =========================================================================
    # SECURITY MASTER
    # =========================================================================
    'security:list':            ('securities-list', 'READ'),
    'security:dashboard':       ('securities-list', 'READ'),
    'security:detail':          ('securities-list', 'READ'),
    'security:create':          {
                                    'GET':  ('securities-create', 'READ'),
                                    'POST': ('securities-create', 'WRITE'),
                                },
    'security:edit':            {
                                    'GET':  ('securities-list', 'READ'),
                                    'POST': ('securities-create', 'WRITE'),
                                },
    'security:validate':        ('securities-create', 'WRITE'),
    'security:pending_approvals': ('securities-create', 'READ'),

    # =========================================================================
    # UDF (User Defined Fields)
    # =========================================================================
    'udf:dashboard':            ('udf-list', 'READ'),
    'udf:list':                 ('udf-list', 'READ'),
    'udf:create':               {
                                    'GET':  ('udf-create', 'READ'),
                                    'POST': ('udf-create', 'WRITE'),
                                },
    'udf:edit':                 {
                                    'GET':  ('udf-list', 'READ'),
                                    'POST': ('udf-create', 'WRITE'),
                                },
    'udf:delete':               ('udf-create', 'WRITE'),
    'udf:restore':              ('udf-create', 'WRITE'),
    # UDF AJAX APIs
    'udf:api_object_types':         ('udf-list', 'READ'),
    'udf:api_fields_by_object_new': ('udf-list', 'READ'),
    'udf:api_fields_by_object':     ('udf-list', 'READ'),

    # =========================================================================
    # FILE UPLOAD
    # =========================================================================
    'upload:list':          ('upload-list', 'READ'),
    'upload:dashboard':     ('upload-list', 'READ'),
    'upload:detail':        ('upload-list', 'READ'),
    'upload:create':        {
                                'GET':  ('upload-list', 'READ'),
                                'POST': ('upload-list', 'WRITE'),
                            },
    'upload:preview':       ('upload-list', 'READ'),
    'upload:update_schema': ('upload-list', 'WRITE'),
    'upload:ingest':        ('upload-list', 'WRITE'),
    'upload:delete':        ('upload-list', 'WRITE'),
    # Upload AJAX APIs
    'upload:api_validate':      ('upload-list', 'READ'),
    'upload:api_status':        ('upload-list', 'READ'),
    'upload:api_preview':       ('upload-list', 'READ'),
    'upload:api_reconciliation': ('upload-list', 'READ'),

    # =========================================================================
    # LOOKUP TABLES
    # =========================================================================
    'lookup:table_list':    ('lookup-tables-list', 'READ'),
    'lookup:table_detail':  ('lookup-tables-list', 'READ'),
    'lookup:row_create':    ('lookup-tables-edit', 'WRITE'),
    'lookup:row_edit':      ('lookup-tables-edit', 'WRITE'),
    'lookup:row_delete':    ('lookup-tables-edit', 'WRITE'),
    # Lookup AJAX APIs
    'lookup:api_table':     ('lookup-tables-list', 'READ'),
    'lookup:api_dropdown':  ('lookup-tables-list', 'READ'),

    # =========================================================================
    # QUERY BUILDER
    # =========================================================================
    'query_builder:builder':        ('query-builder-run', 'READ'),
    'query_builder:run_query':      ('query-builder-run', 'READ'),
    'query_builder:export':         ('query-builder-run', 'READ'),
    'query_builder:saved_reports':  ('query-builder-run', 'READ'),
    'query_builder:save_template':  ('query-builder-manage', 'WRITE'),
    'query_builder:delete_template':('query-builder-manage', 'WRITE'),
    'query_builder:sql_editor':     ('query-builder-admin', 'WRITE'),
    'query_builder:run_raw_sql':    ('query-builder-admin', 'WRITE'),
    'query_builder:api_schema':     ('query-builder-run', 'READ'),
    'query_builder:api_join_options':('query-builder-run', 'READ'),
}
