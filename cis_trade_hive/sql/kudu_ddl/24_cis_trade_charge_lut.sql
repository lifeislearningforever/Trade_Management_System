-- ============================================================
-- DDL: cis_trade_charge_lut
-- Database:   gmp_cis
-- Storage:    Kudu
-- Purpose:    Broker / exchange fee lookup table.
--             Drives automatic charge calculation on every trade.
--
-- How values are used in trade calculation
-- =========================================
-- trade_value  = quantity × price
--
-- Pass 1 — non-GST fees (fee_rule):
--   'Percent' → calculated_fee = trade_value × (fee_value / 100)
--   'Flat'    → calculated_fee = fee_value
--   Each calculated_fee is then rounded per its rounding_method (below) at
--   currency precision (2dp) before being added to subtotal_fees.
--
-- Pass 2 — GST only (applied on subtotal of Pass-1 fees, NOT on trade_value):
--   'Percent' → calculated_fee = subtotal_fees × (fee_value / 100)
--   'Flat'    → calculated_fee = fee_value
--   Rounded the same way as Pass 1.
--
-- rounding_method (applied to each fee, at 2dp, before summation):
--   'Rounding Nearest' → standard round-half-up
--   'Round down'        → truncate towards zero
--   'Round up'           → away from zero
--
-- total_charges = sum(all rounded calculated_fees)
-- grand_total   = trade_value + total_charges  (BUY)
--               = trade_value - total_charges  (SELL)
--
-- Fee types stored
-- ================
--   'Brokerage Fee'  → commission paid to broker     (Percent of trade_value)
--   'Clearing Fee'   → clearing / settlement fee     (Percent of trade_value)
--   'Trading Fee'    → exchange trading fee          (Percent of trade_value)
--   'GST'            → tax on subtotal of other fees (Percent of subtotal_fees)
--   'FFP/SGX SI FEE' → flat exchange-specific fee   (Flat amount)
--
-- Broker matching (wildcard support in application layer)
--   broker = 'UOB KAY HIAN PL*'  → LIKE 'UOB KAY HIAN PL%'
--
-- Created:  2026-03-02
-- ============================================================

CREATE TABLE IF NOT EXISTS gmp_cis.cis_trade_charge_lut
(
    lut_id              BIGINT         NOT NULL COMMENT 'Surrogate primary key',

    -- Fee definition
    fee_type            STRING         NOT NULL COMMENT 'Brokerage Fee | Clearing Fee | Trading Fee | GST | FFP/SGX SI FEE',
    fee_rule            STRING         NOT NULL COMMENT 'Percent | Flat',
    fee_value           DECIMAL(20, 8) NOT NULL COMMENT 'Rate (e.g. 0.28 = 0.28%) or flat amount',

    -- Scope
    broker              STRING         NOT NULL COMMENT 'Broker name; wildcard suffix * supported in app layer',
    exchange            STRING                  COMMENT 'Exchange code e.g. SGX, BURSA',
    country_of_exchange STRING                  COMMENT 'ISO country code e.g. SG, MY',

    -- Rounding
    rounding_method     STRING                  COMMENT 'Rounding Nearest | Round down | Round up -- applied at currency precision (2dp) before summing into total_charges',

    -- Audit
    created_by          STRING                  COMMENT 'User who created the record',
    created_at          STRING                  COMMENT 'Creation timestamp (YYYY-MM-DD HH:MM:SS)',
    updated_by          STRING                  COMMENT 'User who last updated the record',
    updated_at          STRING                  COMMENT 'Last update timestamp (YYYY-MM-DD HH:MM:SS)',
    is_active           BOOLEAN                 COMMENT 'Soft-delete flag; FALSE = inactive row',

    PRIMARY KEY (lut_id)
)
STORED AS KUDU
TBLPROPERTIES (
    'kudu.master_addresses' = 'localhost:7051',
    'kudu.num_tablet_replicas' = '1'
);


-- ============================================================
-- Seed data — UOB KAY HIAN PL* / SGX / SG
-- ============================================================

INSERT INTO gmp_cis.cis_trade_charge_lut
    (lut_id, fee_type,        broker,               exchange, country_of_exchange, fee_rule,  fee_value,  rounding_method,     is_active)
VALUES
    (1,  'Brokerage Fee',  'UOB KAY HIAN PL*',  'SGX',    'SG',                'Percent',  0.28000000, 'Rounding Nearest',  true),
    (2,  'Clearing Fee',   'UOB KAY HIAN PL*',  'SGX',    'SG',                'Percent',  0.03250000, 'Round down',        true),
    (3,  'Trading Fee',    'UOB KAY HIAN PL*',  'SGX',    'SG',                'Percent',  0.00750000, 'Round up',          true),
    (4,  'GST',            'UOB KAY HIAN PL*',  'SGX',    'SG',                'Percent',  9.00000000, 'Rounding Nearest',  true),
    (5,  'FFP/SGX SI FEE', 'UOB KAY HIAN PL*',  'SGX',    'SG',                'Flat',     0.75000000, 'Round up',          true);


-- ============================================================
-- Verify
-- ============================================================
-- SELECT lut_id, fee_type, fee_rule, fee_value, broker, exchange, country_of_exchange
-- FROM gmp_cis.cis_trade_charge_lut
-- ORDER BY broker, fee_type;
