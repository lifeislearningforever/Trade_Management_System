-- ============================================================================
-- CIS Cash Flow UDF Field Definitions
-- ============================================================================
-- Description: UDF field definitions for Cash Flow dropdowns
-- Database: gmp_cis
-- Table: cis_udf_field
--
-- UDF Fields Created:
--   1. CASH_FLOW_TYPE - Types of cash flows (Dividend, Interest, Fee, etc.)
--   2. SEND_RECEIVE - Direction of cash flow (Send/Receive)
--   3. CASH_FLOW_STATUS - Status of cash flow settlement
-- ============================================================================

-- ============================================================================
-- 1. CASH_FLOW_TYPE UDF
-- ============================================================================
-- Description: Types of cash flows for portfolio income/expense tracking

UPSERT INTO gmp_cis.cis_udf_field (
    field_id, field_name, field_label, field_type, entity_type,
    dropdown_values, is_required, is_active, display_order,
    description, created_by, created_at, updated_by, updated_at
) VALUES (
    301,
    'CASH_FLOW_TYPE',
    'Cash Flow Type',
    'dropdown',
    'CASH_FLOW',
    '[{"value": "DIVIDEND", "label": "Dividend"}, {"value": "INTEREST", "label": "Interest"}, {"value": "COUPON", "label": "Coupon"}, {"value": "MANAGEMENT_FEE", "label": "Management Fee"}, {"value": "CUSTODY_FEE", "label": "Custody Fee"}, {"value": "TRANSACTION_FEE", "label": "Transaction Fee"}, {"value": "TAX_WITHHOLDING", "label": "Tax Withholding"}, {"value": "TAX_RECLAIM", "label": "Tax Reclaim"}, {"value": "CAPITAL_GAIN", "label": "Capital Gain Distribution"}, {"value": "RETURN_OF_CAPITAL", "label": "Return of Capital"}, {"value": "SUBSCRIPTION", "label": "Subscription"}, {"value": "REDEMPTION", "label": "Redemption"}, {"value": "DEPOSIT", "label": "Deposit"}, {"value": "WITHDRAWAL", "label": "Withdrawal"}, {"value": "FX_SETTLEMENT", "label": "FX Settlement"}, {"value": "OTHER", "label": "Other"}]',
    TRUE,
    TRUE,
    1,
    'Type of cash flow transaction for portfolio income/expense tracking',
    'system',
    CAST(NOW() AS STRING),
    'system',
    CAST(NOW() AS STRING)
);

-- ============================================================================
-- 2. SEND_RECEIVE UDF
-- ============================================================================
-- Description: Direction of cash flow - sending money out or receiving money in

UPSERT INTO gmp_cis.cis_udf_field (
    field_id, field_name, field_label, field_type, entity_type,
    dropdown_values, is_required, is_active, display_order,
    description, created_by, created_at, updated_by, updated_at
) VALUES (
    302,
    'SEND_RECEIVE',
    'Send/Receive',
    'dropdown',
    'CASH_FLOW',
    '[{"value": "SEND", "label": "Send"}, {"value": "RECEIVE", "label": "Receive"}]',
    TRUE,
    TRUE,
    2,
    'Direction of the cash flow - sending money out (expense) or receiving money in (income)',
    'system',
    CAST(NOW() AS STRING),
    'system',
    CAST(NOW() AS STRING)
);

-- ============================================================================
-- 3. CASH_FLOW_STATUS UDF
-- ============================================================================
-- Description: Settlement/processing status of the cash flow

UPSERT INTO gmp_cis.cis_udf_field (
    field_id, field_name, field_label, field_type, entity_type,
    dropdown_values, is_required, is_active, display_order,
    description, created_by, created_at, updated_by, updated_at
) VALUES (
    303,
    'CASH_FLOW_STATUS',
    'Cash Flow Status',
    'dropdown',
    'CASH_FLOW',
    '[{"value": "PENDING", "label": "Pending"}, {"value": "CONFIRMED", "label": "Confirmed"}, {"value": "SETTLED", "label": "Settled"}, {"value": "FAILED", "label": "Failed"}, {"value": "CANCELLED", "label": "Cancelled"}, {"value": "ON_HOLD", "label": "On Hold"}]',
    FALSE,
    TRUE,
    3,
    'Settlement/processing status of the cash flow transaction',
    'system',
    CAST(NOW() AS STRING),
    'system',
    CAST(NOW() AS STRING)
);

-- ============================================================================
-- Verification Queries
-- ============================================================================
-- SELECT field_id, field_name, field_label, entity_type, is_active
-- FROM gmp_cis.cis_udf_field
-- WHERE entity_type = 'CASH_FLOW'
-- ORDER BY display_order;

-- Check dropdown values:
-- SELECT field_name, dropdown_values
-- FROM gmp_cis.cis_udf_field
-- WHERE entity_type = 'CASH_FLOW' AND field_name = 'CASH_FLOW_TYPE';
