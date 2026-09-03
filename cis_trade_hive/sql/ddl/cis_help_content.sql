-- CisTrade In-App Help Content Table
-- Purpose: Store contextual help content for in-app help system

CREATE TABLE IF NOT EXISTS gmp_cis.cis_help_content (
    -- Identity
    id STRING NOT NULL,

    -- Location
    module STRING,              -- 'portfolio', 'udf', 'market_data', 'core'
    page STRING,                -- 'list', 'detail', 'create', 'edit'
    section STRING,             -- 'header', 'search', 'form', 'actions'

    -- Content
    title STRING,               -- Help topic title
    content STRING,             -- HTML content

    -- Targeting
    user_type STRING,           -- 'business', 'technical', 'all'

    -- Status
    is_active BOOLEAN DEFAULT true,
    display_order INT DEFAULT 0,

    -- Audit
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by STRING,
    updated_by STRING,

    PRIMARY KEY (id)
)
PARTITION BY HASH(id) PARTITIONS 4
STORED AS KUDU;

-- Sample help content for Portfolio module
INSERT INTO gmp_cis.cis_help_content VALUES (
    'help_portfolio_list_001',
    'portfolio',
    'list',
    'overview',
    'Portfolio List Overview',
    '<p>This page displays all portfolios in the system. Use filters to find specific portfolios.</p><ul><li>Search by code, name, or manager</li><li>Filter by status or currency</li><li>Click <strong>View</strong> to see details</li><li>Click <strong>Edit</strong> for Draft/Rejected portfolios</li></ul>',
    'business',
    true,
    1,
    NOW(),
    NOW(),
    'system',
    'system'
);

INSERT INTO gmp_cis.cis_help_content VALUES (
    'help_portfolio_create_001',
    'portfolio',
    'create',
    'form',
    'Creating a Portfolio',
    '<p>Fill in all required fields marked with *.</p><p><strong>Required:</strong> Code, Name, Currency, Manager</p><p>After creation, the portfolio will be in <strong>Draft</strong> status. Submit for approval to activate.</p>',
    'business',
    true,
    1,
    NOW(),
    NOW(),
    'system',
    'system'
);

INSERT INTO gmp_cis.cis_help_content VALUES (
    'help_portfolio_detail_001',
    'portfolio',
    'detail',
    'actions',
    'Portfolio Actions',
    '<ul><li><strong>Draft:</strong> Edit and Submit for Approval</li><li><strong>Pending Approval:</strong> Approve or Reject (Checker only)</li><li><strong>Active:</strong> Close Portfolio</li><li><strong>Inactive:</strong> Reactivate Portfolio</li></ul>',
    'business',
    true,
    1,
    NOW(),
    NOW(),
    'system',
    'system'
);
