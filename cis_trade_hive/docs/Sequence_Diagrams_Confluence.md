# CIS Trade Hive - Sequence Diagrams for Confluence

Copy and paste these diagrams into Confluence using the **Mermaid macro** or **Mermaid plugin**.

---

## 1. Trade Creation Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Django UI
    participant View as Trade View
    participant Service as Trade Service
    participant Repo as Trade Repository
    participant Impala as Impala/Kudu
    participant Audit as Audit Service

    User->>UI: Click "Create Trade"
    UI->>View: GET /trade/create/
    View->>Service: get_dropdowns()
    Service->>Repo: get_portfolios()
    Repo->>Impala: SELECT * FROM cis_portfolio
    Impala-->>Repo: Portfolio list
    Repo-->>Service: Portfolio data
    Service-->>View: Dropdown data
    View-->>UI: Render form

    User->>UI: Fill form & Submit
    UI->>View: POST /trade/create/
    View->>Service: validate_trade(data)
    Service->>Repo: validate_portfolio(id)
    Repo->>Impala: SELECT FROM cis_portfolio
    Impala-->>Repo: Portfolio exists
    Service->>Repo: validate_security(id)
    Repo->>Impala: SELECT FROM cis_security
    Impala-->>Repo: Security exists

    Service->>Repo: create_trade(data)
    Repo->>Impala: UPSERT INTO cis_trade
    Impala-->>Repo: Success

    Service->>Audit: log_action(CREATE, trade_id)
    Audit->>Impala: UPSERT INTO cis_audit_log

    Repo-->>Service: trade_id
    Service-->>View: Success
    View-->>UI: Redirect to trade detail
    UI-->>User: Show success message
```

---

## 2. Maker-Checker Workflow (Four-Eyes Principle)

```mermaid
sequenceDiagram
    autonumber
    actor Maker
    actor Checker
    participant UI as Django UI
    participant Service as Portfolio Service
    participant Repo as Portfolio Repository
    participant DB as Impala/Kudu
    participant Audit as Audit Log

    Note over Maker,Audit: PHASE 1: Maker Creates Portfolio

    Maker->>UI: Create Portfolio
    UI->>Service: create_portfolio(data)
    Service->>Repo: save(status=DRAFT)
    Repo->>DB: UPSERT INTO cis_portfolio
    DB-->>Repo: Success
    Service->>Audit: log(CREATE, portfolio_id)
    UI-->>Maker: Portfolio created (DRAFT)

    Note over Maker,Audit: PHASE 2: Maker Submits for Approval

    Maker->>UI: Submit for Approval
    UI->>Service: submit_for_approval(id)
    Service->>Repo: update(status=PENDING_APPROVAL)
    Repo->>DB: UPSERT SET status='PENDING_APPROVAL'
    DB-->>Repo: Success
    Service->>Audit: log(SUBMIT, portfolio_id)
    UI-->>Maker: Submitted for approval

    Note over Maker,Audit: PHASE 3: Checker Reviews & Approves

    Checker->>UI: View Pending Approvals
    UI->>Service: get_pending_approvals()
    Service->>Repo: find_by_status(PENDING_APPROVAL)
    Repo->>DB: SELECT WHERE status='PENDING_APPROVAL'
    DB-->>Repo: Pending list
    UI-->>Checker: Show pending items

    Checker->>UI: Approve Portfolio
    UI->>Service: approve(id, checker_id)
    Service->>Service: Validate checker != maker
    Service->>Repo: update(status=APPROVED)
    Repo->>DB: UPSERT SET status='APPROVED'
    Service->>Repo: update(status=ACTIVE)
    Repo->>DB: UPSERT SET status='ACTIVE'
    DB-->>Repo: Success
    Service->>Audit: log(APPROVE, portfolio_id)
    UI-->>Checker: Portfolio approved & activated
```

---

## 3. Hive REST Proxy Flow (CML Environment)

```mermaid
sequenceDiagram
    autonumber
    participant CML as CML Application
    participant Django as Django App
    participant Hybrid as HybridConnectionManager
    participant Impala as Impala (Reads)
    participant Proxy as REST Proxy (Edge Node)
    participant Beeline as Beeline CLI
    participant Hive as HiveServer2

    Note over CML,Hive: READ OPERATION (Fast Path)

    CML->>Django: GET /portfolio/
    Django->>Hybrid: execute_query(SELECT)
    Hybrid->>Impala: SELECT * FROM cis_portfolio
    Impala-->>Hybrid: Results (sub-second)
    Hybrid-->>Django: Portfolio list
    Django-->>CML: JSON response

    Note over CML,Hive: WRITE OPERATION (REST Proxy Path)

    CML->>Django: POST /portfolio/create/
    Django->>Hybrid: execute_write(INSERT)
    Hybrid->>Proxy: POST /insert/cis_portfolio
    Note over Proxy: API Key validation
    Proxy->>Proxy: Build INSERT query
    Proxy->>Beeline: Execute via subprocess
    Beeline->>Hive: JDBC + Kerberos
    Hive->>Hive: INSERT INTO (ACID)
    Hive-->>Beeline: Success
    Beeline-->>Proxy: Exit code 0
    Proxy-->>Hybrid: {"success": true, "elapsed_ms": 8500}
    Hybrid-->>Django: True
    Django-->>CML: Created successfully
```

---

## 4. User Authentication & ACL Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Login Page
    participant View as Auth View
    participant ACL as ACL Service
    participant Cache as Query Cache
    participant Repo as ACL Repository
    participant DB as Impala/Kudu

    User->>UI: Enter username
    UI->>View: POST /login/
    View->>ACL: authenticate(username)

    ACL->>Cache: get(user:{username})
    alt Cache Hit
        Cache-->>ACL: User data (cached)
    else Cache Miss
        ACL->>Repo: find_user(username)
        Repo->>DB: SELECT FROM cis_user WHERE username=?
        DB-->>Repo: User record
        Repo-->>ACL: User data
        ACL->>Cache: set(user:{username}, data, TTL=300s)
    end

    ACL->>Repo: get_user_permissions(user_id)
    Repo->>DB: SELECT FROM cis_group_permissions
    DB-->>Repo: Permissions list
    Repo-->>ACL: Permissions

    ACL-->>View: User authenticated
    View->>View: Create session
    View-->>UI: Redirect to dashboard
    UI-->>User: Dashboard view
```

---

## 5. Audit Logging Flow (Async)

```mermaid
sequenceDiagram
    autonumber
    participant Service as Business Service
    participant Audit as Audit Service
    participant Queue as Async Queue
    participant Executor as ThreadPoolExecutor
    participant Repo as Audit Repository
    participant DB as Impala/Kudu

    Service->>Audit: log_action(entity, action, old, new)
    Audit->>Audit: Build audit record
    Audit->>Queue: submit(audit_record)
    Queue-->>Audit: Future object
    Audit-->>Service: Return immediately (non-blocking)

    Note over Service,DB: Service continues without waiting

    par Async Execution
        Executor->>Repo: create_audit_log(record)
        Repo->>DB: UPSERT INTO cis_audit_log
        DB-->>Repo: Success
        Repo-->>Executor: Logged
    end
```

---

## 6. Trade Position Calculation Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Trade UI
    participant Service as Trade Service
    participant PosService as Position Service
    participant TradeRepo as Trade Repository
    participant PosRepo as Position Repository
    participant DB as Impala/Kudu

    User->>UI: Settle Trade
    UI->>Service: settle_trade(trade_id)

    Service->>TradeRepo: get_trade(trade_id)
    TradeRepo->>DB: SELECT FROM cis_trade
    DB-->>TradeRepo: Trade data

    Service->>TradeRepo: update_status(SETTLED)
    TradeRepo->>DB: UPSERT SET status='SETTLED'

    Service->>PosService: update_position(trade)
    PosService->>PosRepo: get_position(portfolio, security)
    PosRepo->>DB: SELECT FROM cis_trade_position
    DB-->>PosRepo: Current position

    PosService->>PosService: Calculate new position
    Note over PosService: quantity += trade.quantity<br/>cost += trade.amount

    PosService->>PosRepo: upsert_position(new_position)
    PosRepo->>DB: UPSERT INTO cis_trade_position
    DB-->>PosRepo: Success

    PosService-->>Service: Position updated
    Service-->>UI: Trade settled
    UI-->>User: Success message
```

---

## 7. Market Data Update Flow (FX Rate)

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Market Data UI
    participant View as FX Rate View
    participant Service as FX Rate Service
    participant Repo as FX Rate Repository
    participant HistRepo as FX Rate History Repository
    participant DB as Impala/Kudu

    User->>UI: Update FX Rate
    UI->>View: POST /market-data/fx-rates/{id}/edit/
    View->>Service: update_rate(id, new_data)

    Service->>Repo: get_rate(id)
    Repo->>DB: SELECT FROM cis_fx_rate
    DB-->>Repo: Current rate
    Repo-->>Service: Old rate data

    Service->>HistRepo: save_history(old_rate)
    HistRepo->>DB: INSERT INTO cis_fx_rate_history
    DB-->>HistRepo: Success

    Service->>Repo: update(id, new_data)
    Repo->>DB: UPSERT INTO cis_fx_rate
    DB-->>Repo: Success

    Service-->>View: Rate updated
    View-->>UI: Redirect to detail
    UI-->>User: Show updated rate
```

---

## 8. Connection Pool Management

```mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant Pool as Connection Pool
    participant Validator as Connection Validator
    participant Impala as Impala Server

    App->>Pool: get_connection()

    alt Pool has available connection
        Pool->>Pool: Get from queue
        Pool->>Validator: validate(connection)
        Validator->>Impala: SELECT 1
        alt Connection valid
            Impala-->>Validator: OK
            Validator-->>Pool: Valid
            Pool-->>App: Return connection
        else Connection stale
            Impala-->>Validator: Error/Timeout
            Validator-->>Pool: Invalid
            Pool->>Pool: Close stale connection
            Pool->>Pool: Decrement count
            Pool->>Impala: Create new connection
            Impala-->>Pool: New connection
            Pool-->>App: Return new connection
        end
    else Pool empty
        alt Under max connections
            Pool->>Impala: Create new connection
            Impala-->>Pool: New connection
            Pool->>Pool: Increment count
            Pool-->>App: Return connection
        else At max connections
            Pool->>Pool: Wait for available (30s timeout)
            Pool-->>App: Return connection or timeout error
        end
    end

    Note over App,Impala: After use
    App->>Pool: return_connection(conn)
    Pool->>Validator: validate(connection)
    alt Valid
        Pool->>Pool: Put back in queue
    else Invalid
        Pool->>Pool: Close and decrement
    end
```

---

## How to Use in Confluence

### Option 1: Mermaid Macro (if installed)
1. Edit your Confluence page
2. Type `/mermaid` or insert "Mermaid" macro
3. Paste the diagram code (without the ```mermaid wrapper)
4. Save

### Option 2: Mermaid Plugin
1. Install "Mermaid Diagrams for Confluence" from Atlassian Marketplace
2. Add Mermaid macro to page
3. Paste diagram code

### Option 3: Export as Image
1. Go to https://mermaid.live/
2. Paste the diagram code
3. Download as PNG/SVG
4. Upload image to Confluence

### Option 4: Draw.io Integration
1. Use Confluence's built-in Draw.io integration
2. Create diagrams manually based on the flows above

---

## 9. Portfolio CRUD Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Portfolio UI
    participant View as Portfolio View
    participant Service as Portfolio Service
    participant Repo as Portfolio Repository
    participant HistRepo as Portfolio History Repo
    participant DB as Impala/Kudu
    participant Audit as Audit Service

    Note over User,Audit: CREATE PORTFOLIO

    User->>UI: Click "Create Portfolio"
    UI->>View: GET /portfolio/create/
    View->>Service: get_currencies()
    Service->>DB: SELECT FROM cis_currency
    DB-->>Service: Currency list
    View-->>UI: Render form with dropdowns

    User->>UI: Fill form & Submit
    UI->>View: POST /portfolio/create/
    View->>Service: create_portfolio(data)
    Service->>Service: Generate portfolio_id
    Service->>Service: Set status = DRAFT
    Service->>Repo: save(portfolio_data)
    Repo->>DB: UPSERT INTO cis_portfolio
    DB-->>Repo: Success
    Service->>Audit: log(CREATE, portfolio_id, new_values)
    Audit->>DB: UPSERT INTO cis_audit_log
    Service-->>View: portfolio_id
    View-->>UI: Redirect to detail page
    UI-->>User: Portfolio created successfully

    Note over User,Audit: UPDATE PORTFOLIO

    User->>UI: Click "Edit Portfolio"
    UI->>View: GET /portfolio/{id}/edit/
    View->>Service: get_portfolio(id)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT FROM cis_portfolio WHERE portfolio_id=?
    DB-->>Repo: Portfolio data
    Repo-->>Service: Portfolio
    View-->>UI: Render form with data

    User->>UI: Modify & Submit
    UI->>View: POST /portfolio/{id}/edit/
    View->>Service: update_portfolio(id, data)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT (get old values)
    DB-->>Repo: Old portfolio data

    Service->>HistRepo: save_history(old_data, UPDATED)
    HistRepo->>DB: UPSERT INTO cis_portfolio_history
    DB-->>HistRepo: Success

    Service->>Repo: update(id, new_data)
    Repo->>DB: UPSERT INTO cis_portfolio
    DB-->>Repo: Success
    Service->>Audit: log(UPDATE, id, old, new)
    Service-->>View: Success
    View-->>UI: Redirect to detail
    UI-->>User: Portfolio updated

    Note over User,Audit: DELETE PORTFOLIO (Soft Delete)

    User->>UI: Click "Delete Portfolio"
    UI->>View: POST /portfolio/{id}/delete/
    View->>Service: delete_portfolio(id)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT FROM cis_portfolio
    DB-->>Repo: Portfolio data

    Service->>HistRepo: save_history(data, DELETED)
    HistRepo->>DB: UPSERT INTO cis_portfolio_history

    Service->>Repo: soft_delete(id)
    Repo->>DB: UPSERT SET deleted_at = NOW()
    DB-->>Repo: Success
    Service->>Audit: log(DELETE, id)
    Service-->>View: Success
    View-->>UI: Redirect to list
    UI-->>User: Portfolio deleted
```

---

## 10. Security Master CRUD Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Security UI
    participant View as Security View
    participant Service as Security Service
    participant Repo as Security Repository
    participant HistRepo as Security History Repo
    participant DB as Impala/Kudu
    participant Audit as Audit Service

    Note over User,Audit: CREATE SECURITY

    User->>UI: Click "Create Security"
    UI->>View: GET /security/create/
    View->>Service: get_dropdowns()
    Service->>DB: SELECT currencies, countries, exchanges
    DB-->>Service: Dropdown data
    View-->>UI: Render form

    User->>UI: Fill ISIN, Ticker, Name, Type & Submit
    UI->>View: POST /security/create/
    View->>Service: create_security(data)

    Service->>Service: Validate ISIN format
    Service->>Repo: check_duplicate_isin(isin)
    Repo->>DB: SELECT FROM cis_security WHERE isin=?
    DB-->>Repo: No duplicate

    Service->>Service: Generate security_id
    Service->>Service: Set status = DRAFT
    Service->>Repo: save(security_data)
    Repo->>DB: UPSERT INTO cis_security
    DB-->>Repo: Success

    Service->>Audit: log(CREATE, security_id)
    Audit->>DB: UPSERT INTO cis_audit_log
    Service-->>View: security_id
    View-->>UI: Redirect to detail
    UI-->>User: Security created

    Note over User,Audit: UPDATE SECURITY

    User->>UI: Click "Edit Security"
    UI->>View: GET /security/{id}/edit/
    View->>Service: get_security(id)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT FROM cis_security
    DB-->>Repo: Security data
    View-->>UI: Render form with data

    User->>UI: Modify & Submit
    UI->>View: POST /security/{id}/edit/
    View->>Service: update_security(id, data)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT (old values)
    DB-->>Repo: Old data

    Service->>HistRepo: save_history(old_data)
    HistRepo->>DB: UPSERT INTO cis_security_history
    DB-->>HistRepo: Success

    Service->>Repo: update(id, new_data)
    Repo->>DB: UPSERT INTO cis_security
    DB-->>Repo: Success
    Service->>Audit: log(UPDATE, id, old, new)
    Service-->>View: Success
    View-->>UI: Redirect to detail
    UI-->>User: Security updated

    Note over User,Audit: SECURITY LOOKUP BY IDENTIFIERS

    User->>UI: Search by ISIN/CUSIP/SEDOL
    UI->>View: GET /security/?isin=US0378331005
    View->>Service: search_by_identifier(isin)
    Service->>Repo: find_by_isin(isin)
    Repo->>DB: SELECT FROM cis_security WHERE isin=?
    DB-->>Repo: Security record
    Repo-->>Service: Security
    Service-->>View: Search results
    View-->>UI: Display security
    UI-->>User: Show security details
```

---

## 11. Counterparty (Party) CRUD Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Counterparty UI
    participant View as Counterparty View
    participant Service as Reference Data Service
    participant Repo as Counterparty Repository
    participant DB as Impala/Kudu
    participant Audit as Audit Service
    participant Cache as Query Cache

    Note over User,Cache: CREATE COUNTERPARTY

    User->>UI: Click "Create Counterparty"
    UI->>View: GET /reference-data/counterparty/create/
    View->>Service: get_party_types()
    Service->>DB: SELECT DISTINCT party_type
    DB-->>Service: Party types
    View->>Service: get_countries()
    Service->>Cache: get(countries)
    alt Cache Hit
        Cache-->>Service: Countries (cached)
    else Cache Miss
        Service->>DB: SELECT FROM cis_country
        DB-->>Service: Countries
        Service->>Cache: set(countries, TTL=3600)
    end
    View-->>UI: Render form

    User->>UI: Fill Party Name, Type, Country & Submit
    UI->>View: POST /reference-data/counterparty/create/
    View->>Service: create_counterparty(data)

    Service->>Service: Validate party_short_name unique
    Service->>Repo: check_duplicate(short_name)
    Repo->>DB: SELECT FROM cis_counterparty WHERE party_short_name=?
    DB-->>Repo: No duplicate

    Service->>Service: Generate counterparty_id
    Service->>Repo: save(counterparty_data)
    Repo->>DB: UPSERT INTO cis_counterparty
    DB-->>Repo: Success

    Service->>Cache: invalidate(counterparties)
    Service->>Audit: log(CREATE, counterparty_id)
    Audit->>DB: UPSERT INTO cis_audit_log

    Service-->>View: counterparty_id
    View-->>UI: Redirect to detail
    UI-->>User: Counterparty created

    Note over User,Cache: UPDATE COUNTERPARTY

    User->>UI: Click "Edit Counterparty"
    UI->>View: GET /reference-data/counterparty/{id}/edit/
    View->>Service: get_counterparty(id)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT FROM cis_counterparty
    DB-->>Repo: Counterparty data
    View-->>UI: Render form with data

    User->>UI: Modify & Submit
    UI->>View: POST /reference-data/counterparty/{id}/edit/
    View->>Service: update_counterparty(id, data)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT (old values)
    DB-->>Repo: Old data

    Service->>Repo: update(id, new_data)
    Repo->>DB: UPSERT INTO cis_counterparty
    DB-->>Repo: Success

    Service->>Cache: invalidate(counterparties)
    Service->>Audit: log(UPDATE, id, old, new)
    Service-->>View: Success
    View-->>UI: Redirect to detail
    UI-->>User: Counterparty updated

    Note over User,Cache: FILTER BY PARTY TYPE

    User->>UI: Filter by Type = BROKER
    UI->>View: GET /reference-data/counterparty/?party_type=BROKER
    View->>Service: filter_by_type(BROKER)
    Service->>Repo: find_by_type(BROKER)
    Repo->>DB: SELECT FROM cis_counterparty WHERE party_type='BROKER'
    DB-->>Repo: Filtered list
    Repo-->>Service: Brokers list
    Service-->>View: Results
    View-->>UI: Display brokers
    UI-->>User: Show filtered counterparties

    Note over User,Cache: DELETE COUNTERPARTY (Soft Delete)

    User->>UI: Click "Delete"
    UI->>View: POST /reference-data/counterparty/{id}/delete/
    View->>Service: delete_counterparty(id)
    Service->>Service: Check if used in trades
    Service->>DB: SELECT FROM cis_trade WHERE counterparty_id=?
    DB-->>Service: Usage count

    alt Has active trades
        Service-->>View: Cannot delete - in use
        View-->>UI: Show error
        UI-->>User: Cannot delete counterparty
    else No active trades
        Service->>Repo: soft_delete(id)
        Repo->>DB: UPSERT SET deleted_at = NOW()
        DB-->>Repo: Success
        Service->>Cache: invalidate(counterparties)
        Service->>Audit: log(DELETE, id)
        Service-->>View: Success
        View-->>UI: Redirect to list
        UI-->>User: Counterparty deleted
    end
```

---

## 12. Equity Price CRUD Flow

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Equity Price UI
    participant View as Equity Price View
    participant Service as Equity Price Service
    participant Repo as Equity Price Repository
    participant HistRepo as Price History Repo
    participant SecRepo as Security Repository
    participant DB as Impala/Kudu
    participant Audit as Audit Service

    Note over User,Audit: CREATE EQUITY PRICE

    User->>UI: Click "Add Price"
    UI->>View: GET /market-data/equity-prices/create/
    View->>Service: get_securities_dropdown()
    Service->>SecRepo: find_active_securities()
    SecRepo->>DB: SELECT FROM cis_security WHERE is_active=true
    DB-->>SecRepo: Securities list
    SecRepo-->>Service: Securities
    View-->>UI: Render form with security dropdown

    User->>UI: Select Security, Enter Price, Date & Submit
    UI->>View: POST /market-data/equity-prices/create/
    View->>Service: create_price(data)

    Service->>Service: Validate price > 0
    Service->>Repo: check_duplicate(security_id, price_date)
    Repo->>DB: SELECT WHERE security_id=? AND price_date=?
    DB-->>Repo: Check result

    alt Duplicate exists
        Service-->>View: Price already exists for this date
        View-->>UI: Show error
        UI-->>User: Duplicate price error
    else No duplicate
        Service->>Service: Generate price_id
        Service->>Repo: save(price_data)
        Repo->>DB: UPSERT INTO cis_equity_price
        DB-->>Repo: Success

        Service->>Audit: log(CREATE, price_id)
        Service-->>View: price_id
        View-->>UI: Redirect to detail
        UI-->>User: Price created
    end

    Note over User,Audit: UPDATE EQUITY PRICE (With History)

    User->>UI: Click "Edit Price"
    UI->>View: GET /market-data/equity-prices/{id}/edit/
    View->>Service: get_price(id)
    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT FROM cis_equity_price
    DB-->>Repo: Price data
    View-->>UI: Render form

    User->>UI: Modify price & Submit
    UI->>View: POST /market-data/equity-prices/{id}/edit/
    View->>Service: update_price(id, new_data)

    Service->>Repo: find_by_id(id)
    Repo->>DB: SELECT (old values)
    DB-->>Repo: Old price

    Service->>HistRepo: save_to_history(old_price, change_type=UPDATE)
    HistRepo->>DB: UPSERT INTO cis_equity_price_history
    DB-->>HistRepo: Success

    Service->>Repo: update(id, new_data)
    Repo->>DB: UPSERT INTO cis_equity_price
    DB-->>Repo: Success

    Service->>Audit: log(UPDATE, id, old_price, new_price)
    Service-->>View: Success
    View-->>UI: Redirect to detail
    UI-->>User: Price updated

    Note over User,Audit: GET LATEST PRICE (API for Trade Form)

    User->>UI: Select Security in Trade Form
    UI->>View: GET /trade/api/equity-price/?security_id=SEC001
    View->>Service: get_latest_price(security_id)
    Service->>Repo: find_latest_by_security(security_id)
    Repo->>DB: SELECT FROM cis_equity_price WHERE security_id=? ORDER BY price_date DESC LIMIT 1
    DB-->>Repo: Latest price
    Repo-->>Service: Price data
    Service-->>View: {"price": 150.25, "currency": "USD", "date": "2026-02-22"}
    View-->>UI: JSON response
    UI-->>User: Auto-fill price field
```

---

*Created for CIS Trade Hive Project*
*Date: February 2026*
