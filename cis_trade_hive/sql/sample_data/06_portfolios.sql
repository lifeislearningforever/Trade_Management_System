-- =====================================================
-- Sample Portfolio Data for CisTrade
-- Demonstrates Four-Eyes Principle workflow states
-- =====================================================

-- Note: created_by_id should reference actual user IDs
-- These are sample scripts, adjust IDs based on your user setup

-- Portfolio 1: Active Portfolio (Approved)
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, created_at)
VALUES (
    'PORT-USD-001',
    'US Equity Portfolio',
    'Large cap US equity portfolio focused on technology and healthcare sectors',
    'USD',
    'John Doe',
    5000000.00,
    'ACTIVE',
    TRUE,
    CURRENT_TIMESTAMP
);

-- Portfolio 2: Pending Approval (Maker submitted, waiting for Checker)
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, submitted_for_approval_at, created_at)
VALUES (
    'PORT-EUR-001',
    'European Bond Portfolio',
    'Investment grade European corporate bonds',
    'EUR',
    'Jane Smith',
    3000000.00,
    'PENDING_APPROVAL',
    FALSE,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Portfolio 3: Draft (Being prepared by Maker)
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, created_at)
VALUES (
    'PORT-SGD-001',
    'Singapore REIT Portfolio',
    'Singapore Real Estate Investment Trusts',
    'SGD',
    'Mike Johnson',
    2500000.00,
    'DRAFT',
    FALSE,
    CURRENT_TIMESTAMP
);

-- Portfolio 4: Rejected (Checker rejected, needs revision)
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, review_comments, created_at)
VALUES (
    'PORT-JPY-001',
    'Japan Small Cap',
    'Japanese small cap equity portfolio',
    'JPY',
    'Sarah Williams',
    500000000.00,
    'REJECTED',
    FALSE,
    'Cash balance needs verification. Please resubmit with updated figures.',
    CURRENT_TIMESTAMP
);

-- Portfolio 5: Active Multi-Currency Portfolio
INSERT INTO portfolio (
    code, name, description, currency, manager, portfolio_client,
    cash_balance, cost_centre_code, corp_code, account_group,
    portfolio_group, report_group, entity_group,
    status, is_active, created_at
)
VALUES (
    'PORT-MULTI-001',
    'Global Balanced Portfolio',
    'Diversified global portfolio with equity, fixed income, and alternatives',
    'USD',
    'Portfolio Management Team',
    'Institutional Client A',
    10000000.00,
    'CC-001',
    'CORP-A',
    'Balanced',
    'Global',
    'Monthly',
    'Singapore Entity',
    'ACTIVE',
    TRUE,
    CURRENT_TIMESTAMP
);

-- Portfolio 6: Active Fixed Income
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, created_at)
VALUES (
    'PORT-GBP-001',
    'UK Gilt Portfolio',
    'UK government bonds and gilts',
    'GBP',
    'Bob Brown',
    4000000.00,
    'ACTIVE',
    TRUE,
    CURRENT_TIMESTAMP
);

-- Portfolio 7: Pending Approval (Complex Portfolio)
INSERT INTO portfolio (
    code, name, description, currency, manager, portfolio_client,
    cash_balance, account_group, portfolio_group,
    status, is_active, submitted_for_approval_at, created_at
)
VALUES (
    'PORT-HKD-001',
    'Hong Kong Tech Portfolio',
    'Hong Kong listed technology stocks',
    'HKD',
    'Investment Team Asia',
    'Corporate Client B',
    50000000.00,
    'Tech Growth',
    'Asia Pacific',
    'PENDING_APPROVAL',
    FALSE,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);

-- Portfolio 8: Inactive (Closed)
INSERT INTO portfolio (code, name, description, currency, manager, cash_balance, status, is_active, created_at)
VALUES (
    'PORT-AUD-001',
    'Australia Resources',
    'Australian mining and resources sector (CLOSED)',
    'AUD',
    'Legacy Manager',
    0.00,
    'CLOSED',
    FALSE,
    CURRENT_TIMESTAMP
);
