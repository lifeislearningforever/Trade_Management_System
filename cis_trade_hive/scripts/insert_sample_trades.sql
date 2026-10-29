-- Sample Trades Insert Script for CIS Trade Hive
-- Run via: docker exec kudu-impala-new impala-shell -f /path/to/insert_sample_trades.sql
-- Or copy-paste into impala-shell

-- Trade 1: BUY - INITIAL status
UPSERT INTO gmp_cis.cis_trade (
    trade_id, trade_type, deal_number,
    portfolio_short_name, portfolio_full_name,
    security_label, security_full_name, security_type,
    trade_date, settle_date, quantity, price, total_amount,
    status, is_active, is_deleted, src_system,
    created_by, created_at, updated_by, updated_at, remarks, counterparty
) VALUES (
    1736800001, 'BUY', 'DEAL-20260113-001',
    'ASFINCO SPORE', 'ASFINCO SPORE',
    'Thomas, Bruce and Williams', 'Thomas, Bruce and Williams', 'EQUITY',
    '2026-01-10', '2026-01-12', 1000, 25.50, 25500.00,
    'INITIAL', false, false, 'CIS',
    'admin', '2026-01-13 10:00:00', 'admin', '2026-01-13 10:00:00',
    'Sample BUY trade 1', 'BROKER001'
);

-- Trade 2: BUY - PENDING_VALIDATION status
UPSERT INTO gmp_cis.cis_trade (
    trade_id, trade_type, deal_number,
    portfolio_short_name, portfolio_full_name,
    security_label, security_full_name, security_type,
    trade_date, settle_date, quantity, price, total_amount,
    status, is_active, is_deleted, src_system,
    created_by, created_at, updated_by, updated_at, remarks, counterparty
) VALUES (
    1736800002, 'BUY', 'DEAL-20260113-002',
    'AVATEC', 'AVATEC',
    'Cooke-Garcia', 'Cooke-Garcia', 'EQUITY',
    '2026-01-11', '2026-01-13', 500, 42.75, 21375.00,
    'PENDING_VALIDATION', false, false, 'CIS',
    'admin', '2026-01-13 10:05:00', 'admin', '2026-01-13 10:05:00',
    'Sample BUY trade 2', 'BROKER002'
);

-- Trade 3: SELL - VALIDATED status
UPSERT INTO gmp_cis.cis_trade (
    trade_id, trade_type, deal_number,
    portfolio_short_name, portfolio_full_name,
    security_label, security_full_name, security_type,
    trade_date, settle_date, quantity, price, total_amount,
    status, is_active, is_deleted, src_system,
    created_by, created_at, updated_by, updated_at, remarks, counterparty
) VALUES (
    1736800003, 'SELL', 'DEAL-20260113-003',
    'CEDAR CONS LLC', 'CEDAR CONS LLC',
    'Reyes, Torres and Bishop', 'Reyes, Torres and Bishop', 'BOND',
    '2026-01-12', '2026-01-14', 200, 88.25, 17650.00,
    'VALIDATED', false, false, 'CIS',
    'admin', '2026-01-13 10:10:00', 'admin', '2026-01-13 10:10:00',
    'Sample SELL trade 3', 'BROKER003'
);

-- Trade 4: BUY - SETTLED status
UPSERT INTO gmp_cis.cis_trade (
    trade_id, trade_type, deal_number,
    portfolio_short_name, portfolio_full_name,
    security_label, security_full_name, security_type,
    trade_date, settle_date, quantity, price, total_amount,
    status, is_active, is_deleted, src_system,
    created_by, created_at, updated_by, updated_at, remarks, counterparty
) VALUES (
    1736800004, 'BUY', 'DEAL-20260113-004',
    'EUCALYPTUS JS', 'EUCALYPTUS JS',
    'Rose, Winters and Morrison', 'Rose, Winters and Morrison', 'ETF',
    '2026-01-13', '2026-01-15', 750, 15.30, 11475.00,
    'SETTLED', false, false, 'CIS',
    'admin', '2026-01-13 10:15:00', 'admin', '2026-01-13 10:15:00',
    'Sample BUY trade 4', 'BROKER004'
);

-- Trade 5: BUY - CANCELLED status
UPSERT INTO gmp_cis.cis_trade (
    trade_id, trade_type, deal_number,
    portfolio_short_name, portfolio_full_name,
    security_label, security_full_name, security_type,
    trade_date, settle_date, quantity, price, total_amount,
    status, is_active, is_deleted, src_system,
    created_by, created_at, updated_by, updated_at, remarks, counterparty
) VALUES (
    1736800005, 'BUY', 'DEAL-20260113-005',
    'GC F&B (HK)', 'GC F&B (HK)',
    'Thomas, Bruce and Williams', 'Thomas, Bruce and Williams', 'EQUITY',
    '2026-01-13', '2026-01-15', 1500, 8.90, 13350.00,
    'CANCELLED', false, false, 'CIS',
    'admin', '2026-01-13 10:20:00', 'admin', '2026-01-13 10:20:00',
    'Sample BUY trade 5 - cancelled', 'BROKER005'
);

-- Verify trades inserted
SELECT trade_id, deal_number, portfolio_short_name, security_label, trade_type, status, total_amount
FROM gmp_cis.cis_trade
ORDER BY trade_id
LIMIT 10;
