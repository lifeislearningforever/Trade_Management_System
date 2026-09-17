# CIS Trade Hive — EOD & CORR Process Flow Diagrams

**Version:** 1.0  
**Updated:** 2026-07-07  
**Audience:** Business Analysts / System Analysts / Operations  
**Render with:** GitHub, Confluence Mermaid plugin, draw.io (import `.mmd`), or [mermaid.live](https://mermaid.live)

---

## Diagram 1 — EOD Sequence (Full Pipeline)

Shows the complete nightly EOD run from GMP ETL completion through to SOD snapshot.  
Each actor represents a system component. Arrows show data flow and dependencies.

```mermaid
sequenceDiagram
    autonumber

    participant GMP as GMP ETL
    participant ALT as alldatesinfo
    participant CAT as cis_corporate_actions
    participant CAQ as ca_cash_flow_queue
    participant CF as cis_cash_flow
    participant SQ as cis_settlement_queue
    participant CTP as cis_trade_position
    participant CP as cis_position
    participant PRC as Price and FX

    Note over GMP,PRC: WAVE 0 - Pre-flight 17:45
    GMP->>ALT: ETL done, prev_day=T-1, contextual_today=T
    Note over GMP,PRC: CIS_PREFLIGHT_CHECK - verify Impala connection
    Note over PRC: CIS_VERIFY_PRICES - assert prices and FX loaded for T-1

    Note over GMP,PRC: WAVE 1 - GMP CA Sync 18:00
    GMP->>CAT: UPSERT corporate actions (src=GMP, status=VALIDATED)
    CAT->>CAQ: INSERT PENDING entries for DIVIDEND, INTEREST, COUPON, ROC, SPLIT

    Note over GMP,PRC: WAVE 2 - CA Cash Flow Processing 18:15
    CAQ->>CAQ: PENDING to PROCESSING
    CAQ->>CP: lookup portfolios holding security on ex-date
    CP-->>CAQ: portfolio list and quantities
    CAQ->>CF: INSERT one cash_flow row per portfolio (amount = qty x price_per_share)
    CAQ->>CAQ: PROCESSING to COMPLETED (FAILED retried up to 3x)

    Note over GMP,PRC: WAVE 3a - Cash Flow Application 18:30
    CF->>CF: SELECT APPROVED where payment_date <= T-1 and position_updated=false
    CF->>CTP: lookup open SETTLED position (is_latest=true)
    CTP-->>CF: current qty, avg_cost, accumulated fields
    CF->>CTP: mark old version is_latest=false
    CF->>CTP: UPSERT new version, accumulate dividend, uncall, pipeline, provision
    CF->>CP: UPSERT INT row (basis=SETTLED, position_date=payment_date)
    CF->>CF: UPDATE position_updated=true

    Note over GMP,PRC: WAVE 3b - Settlement Processing 18:30 parallel
    SQ->>SQ: SELECT PENDING where settle_date = contextual_today
    SQ->>CTP: UPSERT settled position versions
    SQ->>SQ: UPDATE status to COMPLETED

    Note over GMP,PRC: WAVE 4 - EOD Position Revaluation 18:45
    CP->>CP: SELECT latest INT row per portfolio and security and basis
    PRC-->>CP: latest closing price from cis_equity_price
    PRC-->>CP: FX spot rate FC to LC

    alt Case A - REVALUED portfolio, normal security
        CP->>CP: market_value_fc = qty x price, cost_lc = cost_fc x fx_rate MTM override
    else Case B - NON-REVALUED portfolio
        CP->>CP: market_value_fc = qty x price, cost_lc carried forward unchanged
    else Case C - Equity-method ASSOC or SUBSI
        CP->>CP: market_value_fc = qty x price, unrealized_pnl = 0
    else Case D - No price available
        CP->>CP: market_value_fc carried forward, market_value_lc = fc x fx_rate
    end

    CP->>CP: DELETE old EOD row, INSERT new EOD row (position_type=EOD, position_date=T-1)
    Note right of CP: dividend, uncall, pipeline, provision, realized_pnl carried forward

    Note over GMP,PRC: WAVE 5 - SOD Snapshot 19:00
    CP->>CP: SELECT all EOD rows where position_date = T-1
    SQ->>CP: SELECT PENDING settlement entries where settle_date = today

    alt BUY settles today
        CP->>CP: new_qty = old + trade_qty, new_avg_cost recalculated
    else SELL partial settles today
        CP->>CP: new_qty = old - trade_qty, realized_pnl accumulated
    else SELL full close settles today
        CP->>CP: qty to 0, cost to 0, realized_pnl accumulated
    end

    CP->>CP: INSERT SOD rows (position_type=SOD, position_date=today)
    SQ->>SQ: UPDATE processed entries to COMPLETED
```

---

## Diagram 2 — CORR (Month-End Correction) Sequence

Runs D+1 to D+5 after month-end. Replays cash flow application and revaluation for `last_month_end`.

```mermaid
sequenceDiagram
    autonumber

    participant ALT as alldatesinfo
    participant CF as cis_cash_flow
    participant CTP as cis_trade_position
    participant CP as cis_position
    participant PRC as Price and FX

    Note over ALT,PRC: CORR Wave C1 - Cash Flow Application 18:30
    ALT-->>CF: Read contextual_today and reporting_date as YYYYMMDD integers

    alt contextual_today month differs from reporting_date month
        Note over CF: last_month_end = reporting_date (it IS the month-end)
    else same month
        Note over CF: last_month_end = first_of_ref_month minus 1 day
    end

    CF->>CF: SELECT APPROVED where payment_date <= last_month_end and position_updated=false
    CF->>CTP: lookup open SETTLED position for last_month_end
    CTP-->>CF: current qty, avg_cost, accumulated fields
    CF->>CTP: mark old version is_latest=false
    CF->>CTP: UPSERT new version with accumulated CF fields
    CF->>CP: UPSERT INT row (position_type=INT, position_date=last_month_end)
    CF->>CF: UPDATE position_updated=true

    Note over ALT,PRC: CORR Wave C2 - Position Revaluation 18:45
    CP->>CP: SELECT latest INT rows for position_date = last_month_end
    PRC-->>CP: closing price for last_month_end
    PRC-->>CP: FX spot rate for last_month_end
    CP->>CP: Apply revaluation Cases A, B, C, D (same logic as EOD Wave 4)
    CP->>CP: DELETE existing CORR row for same portfolio and security and basis and date
    CP->>CP: INSERT new CORR row (position_type=CORR, position_date=last_month_end)
    Note right of CP: CORR and EOD rows coexist for the same date
```

---

## Diagram 3 — Position Lifecycle (Full Day)

Shows how a single position evolves from trade entry through the full intraday and overnight cycle.

```mermaid
flowchart TD
    subgraph INTRADAY["☀️  Intraday — During Trading Day"]
        direction TB

        T1["Trade booked via CIS UI\nor backdated entry"]
        TD_INT["cis_position\nposition_type = INT\nposition_basis = TRADED\nposition_date = trade_date"]
        SD_Q{"settle_date\nvs today?"}

        SD_TODAY["cis_position\nposition_type = INT\nposition_basis = SETTLED\nposition_date = settle_date\n(immediate)"]
        SD_QUEUE["cis_settlement_queue\nstatus = PENDING\n(held until settle_date)"]

        UPL["Position Upload\n(USER_UPLOAD / AMSICEQ)"]
        UPL_INT["cis_position\nposition_type = INT\nposition_date = reporting_date\nsrc_system = USER_UPLOAD"]

        CA["Corporate Action queued\n(GMP sync or CIS UI)"]
        CF_ROW["cis_cash_flow\n(one per portfolio holding)"]
        INT_UPDATE["INT position updated\ndividend / uncall / pipeline\navg_cost reduction (ROC)"]

        T1 --> TD_INT
        T1 --> SD_Q
        SD_Q -->|"settle_date == today\nor backdated"| SD_TODAY
        SD_Q -->|"T+1 / T+2"| SD_QUEUE
        UPL --> UPL_INT
        CA --> CF_ROW --> INT_UPDATE
    end

    subgraph EOD["🌙  EOD Batch — ~18:30–19:00"]
        direction TB

        W3["Wave 3a\nprocess_approved_cashflows\n--run-type EOD"]
        W3b["Wave 3b\nprocess_settlements\n(settle_date = today)"]
        W4["Wave 4\nrefresh_positions\n--run-type EOD"]
        W5["Wave 5\ncreate_sod_snapshot"]

        EOD_CF["INT rows updated\nwith CF accumulation"]
        EOD_SETTLE["Settlement queue\nentries applied → COMPLETED"]
        EOD_POS["cis_position\nposition_type = EOD\nposition_date = T-1\n(market_value + PnL recalculated)"]
        SOD_POS["cis_position\nposition_type = SOD\nposition_date = T\n(prev EOD + today's settlements)"]

        W3 --> EOD_CF
        W3b --> EOD_SETTLE
        EOD_CF --> W4
        EOD_SETTLE --> W4
        W4 --> EOD_POS
        EOD_POS --> W5
        W5 --> SOD_POS
    end

    subgraph CORR["📅  Month-End CORR (D+1 to D+5)"]
        direction TB

        C1["Wave C1\nprocess_approved_cashflows\n--run-type CORR"]
        C2["Wave C2\nrefresh_positions\n--run-type CORR"]

        CORR_INT["INT position for last_month_end\n(late CF catch-up)"]
        CORR_POS["cis_position\nposition_type = CORR\nposition_date = last_month_end\n(corrected month-end revaluation)"]

        C1 --> CORR_INT --> C2 --> CORR_POS
    end

    subgraph TYPES["📊  Position Type Summary"]
        direction LR
        PT_INT["INT\nIntraday working\nposition"]
        PT_EOD["EOD\nNightly revalued\nsnapshot"]
        PT_SOD["SOD\nOpening position\n(next day)"]
        PT_CORR["CORR\nMonth-end\ncorrection"]
    end

    INTRADAY --> EOD
    SOD_POS -->|"next morning: SOD is\nstarting point for new day"| INTRADAY
    INTRADAY -.->|"month-end +1 to +5"| CORR

    EOD_POS --> PT_EOD
    SOD_POS --> PT_SOD
    TD_INT --> PT_INT
    SD_TODAY --> PT_INT
    UPL_INT --> PT_INT
    CORR_POS --> PT_CORR

    style INTRADAY fill:#e8f4fd,stroke:#2196F3,stroke-width:2px
    style EOD fill:#fff8e1,stroke:#FFA000,stroke-width:2px
    style CORR fill:#f3e5f5,stroke:#9C27B0,stroke-width:2px
    style TYPES fill:#e8f5e9,stroke:#4CAF50,stroke-width:2px

    style PT_INT  fill:#2196F3,color:#fff,stroke:none
    style PT_EOD  fill:#FFA000,color:#fff,stroke:none
    style PT_SOD  fill:#4CAF50,color:#fff,stroke:none
    style PT_CORR fill:#9C27B0,color:#fff,stroke:none
```

---

## Diagram 4 — Data Flow (Tables)

Shows which management command reads/writes each Kudu table. Flow is top-to-bottom by EOD wave.

```mermaid
flowchart TB
    subgraph EXT["External Feeds"]
        direction LR
        GMP_ETL["GMP ETL\n(corporate_action, alldatesinfo, fx_rates)"]
        PRICE_FEED["Market Data ETL\n(cis_equity_price)"]
    end

    subgraph W1["Wave 1 — GMP CA Sync"]
        direction LR
        SYNC["sync_gmp_corporate_actions"]
        CAT["cis_corporate_actions"]
        CAQ["cis_ca_cash_flow_queue"]
        SYNC -->|UPSERT| CAT
        SYNC -->|INSERT PENDING| CAQ
    end

    subgraph W2["Wave 2 — CA Processing"]
        direction LR
        PCA["process_corporate_actions"]
        CFT["cis_cash_flow"]
        PCA -->|INSERT| CFT
        PCA -->|UPDATE COMPLETED| CAQ2["ca_cash_flow_queue"]
    end

    subgraph W3["Wave 3 — Cash Flow and Settlement"]
        direction LR
        PAC["process_approved_cashflows"]
        PS["process_settlements"]
        CTP["cis_trade_position"]
        SQT["cis_settlement_queue"]
        PAC -->|UPSERT new version| CTP
        PS  -->|UPSERT settled| CTP
        PS  -->|UPDATE COMPLETED| SQT
    end

    subgraph W4["Wave 4 — EOD Revaluation"]
        direction LR
        RP["refresh_positions"]
        CPW4["cis_position"]
        RP -->|DELETE old EOD, INSERT new EOD| CPW4
    end

    subgraph W5["Wave 5 — SOD Snapshot"]
        direction LR
        SOD["create_sod_snapshot"]
        CPW5["cis_position"]
        SOD -->|INSERT SOD rows| CPW5
        SOD -->|UPDATE COMPLETED| SQT2["cis_settlement_queue"]
    end

    GMP_ETL  -->|READ CA source| SYNC
    CAQ      -->|READ PENDING| PCA
    CFT      -->|READ APPROVED| PAC
    SQT      -->|READ PENDING settle_date=today| PS
    PAC      -->|UPSERT INT| CPW4
    CPW4     -->|READ latest INT rows| RP
    PRICE_FEED -->|READ latest price| RP
    GMP_ETL  -->|READ FX rates| RP
    CPW4     -->|READ EOD rows| SOD
    SQT      -->|READ PENDING settle_date=today| SOD

    style EXT fill:#fce4ec,stroke:#E91E63,stroke-width:2px
    style W1  fill:#e8f5e9,stroke:#2E7D32,stroke-width:2px
    style W2  fill:#fff8e1,stroke:#FFA000,stroke-width:2px
    style W3  fill:#fce4ec,stroke:#c62828,stroke-width:2px
    style W4  fill:#ede7f6,stroke:#6A1B9A,stroke-width:2px
    style W5  fill:#e3f2fd,stroke:#1565C0,stroke-width:2px
```

---

## Position Type Reference (Quick Card)

| `position_type` | Written by | `position_date` | Description |
|---|---|---|---|
| `INT` | `position_service` (trades), `upload_service`, `process_approved_cashflows` | trade_date / settle_date / reporting_date / payment_date | Intraday working position — accumulates all CF/CA updates |
| `EOD` | `refresh_positions --run-type EOD` | T-1 (`reporting_date`) | Nightly revalued snapshot — market_value + PnL recalculated |
| `SOD` | `create_sod_snapshot` | T (`contextual_today`) | Opening snapshot = prev EOD + settled T+1/T+2 trades applied |
| `CORR` | `refresh_positions --run-type CORR` | `last_month_end` | Month-end corrected revaluation (D+1 to D+5) |

---

## EOD Job Schedule Reference

| Time | Job (Control-M) | Wave | Command |
|---|---|---|---|
| 17:30 | GMP_ETL_COMPLETE | — | External dependency |
| 17:45 | CIS_PREFLIGHT_CHECK | 0 | `python manage.py test_hive` |
| 17:50 | CIS_VERIFY_PRICES | 0 | impala-shell price/FX count checks |
| 18:00 | CIS_SYNC_GMP_CA | 1 | `sync_gmp_corporate_actions` |
| 18:15 | CIS_PROCESS_CA | 2 | `process_corporate_actions` |
| 18:30 | CIS_PROCESS_CASHFLOWS | 3 | `process_approved_cashflows --run-type EOD` |
| 18:30 | CIS_PROCESS_SETTLEMENTS | 3 ‖ | `process_settlements` (parallel) |
| 18:45 | CIS_REFRESH_POSITIONS | 4 | `refresh_positions --run-type EOD` |
| 19:00 | CIS_CREATE_SOD_SNAPSHOT | 5 | `create_sod_snapshot` |

**CORR (month-end D+1 to D+5):**

| Time | Job | Wave | Command |
|---|---|---|---|
| 18:30 | CIS_CORR_PROCESS_CASHFLOWS | C1 | `process_approved_cashflows --run-type CORR` |
| 18:45 | CIS_CORR_REFRESH_POSITIONS | C2 | `refresh_positions --run-type CORR` |
