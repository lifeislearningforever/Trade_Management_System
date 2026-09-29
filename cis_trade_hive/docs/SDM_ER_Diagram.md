# CIS Trade Hive — Entity Relationship Diagram

System Design Document (SDM) artifact. Reflects the Kudu/Impala data model
(see `sql/ddl/*.sql`). Kudu does not enforce foreign keys — relationships
below are logical, enforced at the application layer.

```mermaid
erDiagram
    CIS_PORTFOLIO ||--o{ CIS_TRADE : "books trades"
    CIS_PORTFOLIO ||--o{ CIS_TRADE_POSITION : "holds"
    CIS_PORTFOLIO ||--o{ CIS_POSITION : "holds (golden copy)"
    CIS_PORTFOLIO ||--o{ CIS_CASH_FLOW : "receives"

    CIS_SECURITY ||--o{ CIS_TRADE : "traded as"
    CIS_SECURITY ||--o{ CIS_TRADE_POSITION : "held as"
    CIS_SECURITY ||--o{ CIS_POSITION : "held as"
    CIS_SECURITY ||--o{ CIS_CASH_FLOW : "generates"
    CIS_SECURITY ||--o{ CIS_CORPORATE_ACTIONS : "subject of"

    CIS_PARTY ||--o{ CIS_TRADE : "counterparty for"
    CIS_PARTY ||--o{ CIS_PARTY_CIF : "has CIF codes"

    CIS_TRADE ||--o{ CIS_TRADE_HISTORY : "audit trail"
    CIS_TRADE ||--o{ CIS_TRADE_NOTE : "annotated by"
    CIS_TRADE ||--o| CIS_TRADE_POSITION : "drives version"
    CIS_TRADE ||--o{ CIS_POSITION_QUEUE : "queues AVP calc"
    CIS_TRADE ||--o{ CIS_SETTLEMENT_QUEUE : "queues future settle"
    CIS_TRADE ||--o{ CIS_TRADE_EVENT_QUEUE : "queues async events"

    CIS_CORPORATE_ACTIONS ||--o{ CIS_CASH_FLOW : "generates"
    CIS_CORPORATE_ACTIONS ||--o{ CIS_CA_CASH_FLOW_QUEUE : "fans out per holding"

    CIS_USER ||--o{ CIS_USER_GROUP : "assigned to"
    CIS_GROUP ||--o{ CIS_USER_GROUP : "contains"
    CIS_GROUP ||--o{ CIS_GROUP_PERMISSIONS : "grants"

    CIS_UDF_FIELD ||..o{ CIS_PORTFOLIO : "extends (by object_type)"
    CIS_UDF_FIELD ||..o{ CIS_TRADE : "extends (by object_type)"
    CIS_UDF_FIELD ||..o{ CIS_SECURITY : "extends (by object_type)"

    CIS_USER ||--o{ CIS_NOTIFICATION : "receives"

    CIS_PORTFOLIO {
        string name PK
        string description
        string currency
        string manager
        string portfolio_client
        decimal cash_balance
        string revaluation_status "REVALUED / NON-REVALUED"
        string entity_group
        string status "Four-Eyes: INITIAL..SETTLED"
        boolean is_active
        string created_by
        timestamp created_at
    }

    CIS_SECURITY {
        bigint security_id PK
        string security_name "business key, used as security_label FK"
        string isin
        string security_description
        string issuer
        string ticker
        string industry
        string security_type
        string investment_type
        string country_of_exchange
        string currency_code
        decimal price
        decimal shares_outstanding
    }

    CIS_PARTY {
        string party_short_name PK
        string party_full_name
        boolean is_broker
        boolean is_custodian
        boolean is_issuer
        boolean is_bank
        boolean is_subsidiary
        string country
        string status "Four-Eyes"
        string validated_by
    }

    CIS_PARTY_CIF {
        string party_name PK_FK
        string m_label PK "CIF number"
        string country PK
        string isin
    }

    CIS_TRADE {
        bigint trade_id PK
        string deal_number
        string trade_type "BUY/SELL/ADD_LONG/..."
        string portfolio_short_name FK
        string security_label FK
        string counterparty FK
        string currency_code
        string portfolio_currency
        date trade_date
        date settle_date
        decimal quantity
        decimal price
        decimal commission
        decimal sec_fee
        decimal other_charges
        decimal gross_amount_fc
        decimal gross_amount_lc
        decimal total_amount_fc
        decimal total_amount_lc
        string trade_status
        string status "Four-Eyes: INITIAL..SETTLED"
        string src_system "CIS/GMP"
        boolean is_deleted
        string created_by
        timestamp created_at
    }

    CIS_TRADE_HISTORY {
        bigint history_id PK
        bigint trade_id FK
        string deal_number
        string action "CREATE/UPDATE/VALIDATE/..."
        string old_status
        string new_status
        string changes "JSON diff"
        string performed_by
        timestamp performed_at
    }

    CIS_TRADE_NOTE {
        bigint note_id PK
        bigint trade_id FK
        string note_text
        string created_by
        timestamp created_at
    }

    CIS_TRADE_POSITION {
        bigint version_id PK
        bigint position_id "natural key (portfolio+sec+basis+date)"
        string position_basis "TRADED / SETTLED"
        date position_date
        string portfolio_short_name FK
        string security_label FK
        bigint trade_id FK
        decimal quantity
        decimal average_cost_fc
        decimal average_cost_lc
        decimal total_cost_fc
        decimal total_cost_lc
        decimal realized_pnl_fc
        decimal unrealized_pnl_fc
        decimal market_value_fc
        decimal market_value_lc
        decimal fx_rate
        string status
        boolean is_latest
    }

    CIS_POSITION {
        bigint position_id PK "golden/consolidated copy"
        bigint version_id
        string portfolio FK
        string security_label FK
        string position_basis
        date position_date
        string src_system "CIS/GMP/AMS_STREET/USER_UPLOAD"
        string position_type "EOD/SOD/INT/CORR"
        decimal quantity
        decimal average_cost_fc
        decimal cost_fc
        decimal market_value_fc
        decimal net_book_value_fc
        decimal unrealized_pnl_fc
        decimal provision_fc
        decimal dividend_fc
        string isin
        boolean is_latest
    }

    CIS_POSITION_QUEUE {
        bigint queue_id PK
        bigint trade_id FK
        string portfolio_id
        string security_id
        string trade_type
        decimal quantity
        decimal price
        decimal charges
        string status "PENDING/PROCESSING/COMPLETED/FAILED/DEAD_LETTER"
        int retry_count
        timestamp queued_at
        string queued_by
    }

    CIS_SETTLEMENT_QUEUE {
        bigint queue_id PK
        bigint trade_id FK
        string portfolio_id
        string security_id
        date settle_date
        string status "PENDING/PROCESSING/COMPLETED/FAILED"
        int retry_count
    }

    CIS_TRADE_EVENT_QUEUE {
        bigint event_id PK
        bigint trade_id FK
        string deal_number
        string event_type "HISTORY/SETTLEMENT"
        string event_data "JSON payload"
        string status
    }

    CIS_CASH_FLOW {
        bigint cash_flow_id PK
        string cash_flow_number
        string portfolio_short_name FK
        string security_label FK
        bigint ca_id FK "nullable, set when src_system=CA"
        string cash_flow_type "DIVIDEND/ROC/COUPON/..."
        string send_receive "SEND/RECEIVE or INCREASE/DECREASE"
        boolean cf_processed
        decimal foreign_ccy_amt
        decimal local_ccy_amt
        decimal fx_rate
        string src_system "CIS/CA"
        string status "Four-Eyes"
        date payment_date
        date ex_date
        date record_date
    }

    CIS_CORPORATE_ACTIONS {
        bigint ca_id PK
        string ca_number
        string ca_type "CASH_DIVIDEND/BONUS_ISSUE/SPLIT/..."
        string security_name FK
        date announcement_date
        date ex_date
        date record_date
        date payment_date
        decimal price "ratio or amount per share"
        string status "Four-Eyes"
        boolean cash_flow_queued
        boolean ca_processed
    }

    CIS_CA_CASH_FLOW_QUEUE {
        bigint queue_id PK
        bigint ca_id FK
        string portfolio_short_name
        string security_name
        string status
        int retry_count
    }

    CIS_UDF_FIELD {
        bigint udf_id PK
        string object_type "PORTFOLIO/TRADE/SECURITY/..."
        string field_name
        string field_value
        boolean is_active
    }

    CIS_USER {
        bigint user_id PK
        string username
        string full_name
        boolean is_active
    }

    CIS_GROUP {
        bigint group_id PK
        string group_name
    }

    CIS_USER_GROUP {
        bigint user_id PK_FK
        bigint group_id PK_FK
    }

    CIS_GROUP_PERMISSIONS {
        bigint group_id PK_FK
        string module
        boolean can_view
        boolean can_create
        boolean can_edit
        boolean can_delete
        boolean can_approve
    }

    CIS_NOTIFICATION {
        bigint notif_id PK
        string username FK
        string event_type
        string severity
        string title
        string message
        boolean is_read
    }
```

## Notes for reviewers

- **Versioned tables** (`cis_trade_position`, `cis_trade_history`): Kudu is
  append/upsert-only, so these tables model change-over-time via a
  `version_id`/`is_latest` pattern rather than in-place `UPDATE`.
- **Dual-write pattern**: every CIS-originated position change lands in both
  `cis_trade_position` (versioned working ledger, CIS-only) and `cis_position`
  (golden/consolidated copy merging CIS, GMP, AMS_STREET and USER_UPLOAD
  sources) — the two are kept in sync by the service layer, not by the
  database.
- **Four-Eyes status** appears on `cis_portfolio`, `cis_trade`,
  `cis_cash_flow`, and `cis_corporate_actions`: `INITIAL → MODIFIED →
  PENDING_VALIDATION → VALIDATED/CANCELLED → SETTLED`.
- **UDF (User-Defined Fields)** is a generic key/value extension table keyed
  by `object_type`, not a physical foreign key — it can extend Portfolio,
  Trade, or Security records without schema changes.
