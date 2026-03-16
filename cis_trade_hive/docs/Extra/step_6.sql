INSERT INTO gmp_cis.cis_trade_position

(version_id, position_id, position_date, portfolio_short_name, security_label,

quantity, average_cost, total_cost, realized_pnl, current_price, market_value,

unrealized_pnl, trade_id, trade_type, lots_held, custodian, sub_custodian,

security_currency, portfolio_currency, fx_rate, average_cost_base,

total_cost_base, realized_pnl_base, status, is_active, is_latest,

created_by, created_at, updated_by, updated_at)

WITH base AS (

  SELECT

      sq.*,

      cp.position_id            AS cp_position_id,

      cp.quantity               AS cp_quantity_raw,

      cp.average_cost           AS cp_average_cost_raw,

      cp.total_cost             AS cp_total_cost_raw,

      cp.realized_pnl           AS cp_realized_pnl_raw,

      cp.lots_held              AS cp_lots_held,

      ROW_NUMBER() OVER (ORDER BY sq.settle_date, sq.queue_id) AS rn

  FROM gmp_cis.cis_settlement_queue sq

  LEFT JOIN gmp_cis.tmp_current_positions_eod cp

         ON sq.queue_id = cp.queue_id

  WHERE sq.settle_date <= '2026-03-22'

    AND sq.status = 'PROCESSING'

    -- Exclude error cases: SELL without position or insufficient quantity

    AND NOT (

      sq.trade_type = 'SELL'

      AND (

           cp.position_id IS NULL

        OR CAST(COALESCE(cp.quantity, 0) AS DECIMAL(38,8))

           < CAST(sq.quantity AS DECIMAL(38,8))

      )

    )

),

typed AS (

  -- Normalize all numeric inputs to DECIMAL(38,8)

  SELECT

      base.*,

      CAST(COALESCE(base.cp_quantity_raw,     0) AS DECIMAL(38,8)) AS q_prev,

     CAST(COALESCE(base.cp_average_cost_raw, 0) AS DECIMAL(38,8)) AS ac_prev,

      CAST(COALESCE(base.cp_total_cost_raw,   0) AS DECIMAL(38,8)) AS tc_prev,

      CAST(COALESCE(base.cp_realized_pnl_raw, 0) AS DECIMAL(38,8)) AS rp_prev,

      CAST(base.quantity AS DECIMAL(38,8))                             AS q_trd,

      CAST(base.price    AS DECIMAL(38,8))                             AS p_trd,

      CAST(COALESCE(base.charges, 0) AS DECIMAL(38,8))                 AS chg_trd

  FROM base

),

calc1 AS (

  -- Compute items that are reused by later calculations

  SELECT

      typed.*,

      CAST(typed.q_trd * typed.p_trd AS DECIMAL(38,8)) AS buy_notional

  FROM typed

),

calc AS (

  -- All CASE branches explicitly return DECIMAL(38,8)

  SELECT

      c1.*,



     -- Quantity after trade

      CASE

        WHEN c1.trade_type = 'BUY'

          THEN CAST(c1.q_prev + c1.q_trd AS DECIMAL(38,8))

        WHEN c1.trade_type = 'SELL'

          THEN CAST(c1.q_prev - c1.q_trd AS DECIMAL(38,8))

        ELSE CAST(c1.q_prev AS DECIMAL(38,8))

      END AS qty_after,



      -- Average cost after trade

      CASE

        WHEN c1.trade_type = 'BUY' THEN

          CASE

            WHEN CAST(c1.q_prev + c1.q_trd AS DECIMAL(38,8)) > CAST(0 AS DECIMAL(38,8)) THEN

              CAST(

                (c1.tc_prev + CAST(c1.buy_notional + c1.chg_trd AS DECIMAL(38,8)))

                / CAST(c1.q_prev + c1.q_trd AS DECIMAL(38,8))

                AS DECIMAL(38,8)

              )

            ELSE CAST(0 AS DECIMAL(38,8))

          END

        ELSE CAST(c1.ac_prev AS DECIMAL(38,8))

      END AS ac_after,



      -- Total cost after trade

      CASE

        WHEN c1.trade_type = 'BUY' THEN

          CAST(c1.tc_prev + CAST(c1.buy_notional + c1.chg_trd AS DECIMAL(38,8)) AS DECIMAL(38,8))

        WHEN c1.trade_type = 'SELL' THEN

          CASE

            WHEN c1.q_prev > CAST(0 AS DECIMAL(38,8)) THEN

              CAST(

                CAST(c1.tc_prev * CAST(c1.q_prev - c1.q_trd AS DECIMAL(38,8)) AS DECIMAL(38,8))

                / c1.q_prev

                AS DECIMAL(38,8)

              )

            ELSE CAST(0 AS DECIMAL(38,8))

          END

        ELSE CAST(c1.tc_prev AS DECIMAL(38,8))

      END AS tc_after,



      -- Realized P&L after trade

      CASE

        WHEN c1.trade_type = 'SELL' THEN

          CAST(c1.rp_prev + CAST(c1.q_trd * (c1.p_trd - c1.ac_prev) AS DECIMAL(38,8)) AS DECIMAL(38,8))

        ELSE CAST(c1.rp_prev AS DECIMAL(38,8))

      END AS rp_after,



      -- Lots after trade

      CAST(

        CASE

          WHEN c1.trade_type = 'BUY' THEN COALESCE(c1.cp_lots_held, 0) + 1

          ELSE COALESCE(c1.cp_lots_held, 0)

        END AS INT

      ) AS lots_after

  FROM calc1 c1

)



SELECT

  -- version_id: unique per record

  CAST(1741788000000 * 1000 + calc.rn AS BIGINT) AS version_id,



  -- position_id: reuse existing or generate new

  CAST(COALESCE(calc.cp_position_id, 1741788000000 * 100 + calc.rn) AS BIGINT) AS position_id,



  calc.settle_date                      AS position_date,

  calc.portfolio_id                     AS portfolio_short_name,

  calc.security_id                      AS security_label,



  -- Final downcasts to DECIMAL(20,8)

  CAST(calc.qty_after AS DECIMAL(20,8)) AS quantity,

  CAST(calc.ac_after  AS DECIMAL(20,8)) AS average_cost,

  CAST(calc.tc_after  AS DECIMAL(20,8)) AS total_cost,

  CAST(calc.rp_after  AS DECIMAL(20,8)) AS realized_pnl,



  CAST(calc.p_trd AS DECIMAL(20,8))     AS current_price,

  CAST(NULL AS DECIMAL(20,8))           AS market_value,      -- calculated later

  CAST(NULL AS DECIMAL(20,8))           AS unrealized_pnl,    -- calculated later



  calc.trade_id,

  calc.trade_type,

  calc.lots_after                       AS lots_held,

 calc.custodian,

  calc.sub_custodian,

  calc.security_currency,

  calc.portfolio_currency,



  CAST(NULL AS DECIMAL(20,8))           AS fx_rate,

  CAST(NULL AS DECIMAL(20,8))           AS average_cost_base,

  CAST(NULL AS DECIMAL(20,8))           AS total_cost_base,

  CAST(NULL AS DECIMAL(20,8))           AS realized_pnl_base,



  -- Status uses computed qty_after

  CASE

    WHEN calc.trade_type = 'BUY' THEN 'OPEN'

    WHEN calc.trade_type = 'SELL' AND calc.qty_after <= CAST(0 AS DECIMAL(38,8)) THEN 'CLOSED'

    ELSE 'OPEN'

  END AS status,



  CAST(true AS BOOLEAN)                 AS is_active,

  CAST(true AS BOOLEAN)                 AS is_latest,



  'EOD_SYSTEM'                          AS created_by,

  FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS created_at,

  'EOD_SYSTEM'                          AS updated_by,

  FROM_UNIXTIME(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS updated_at

FROM calc;