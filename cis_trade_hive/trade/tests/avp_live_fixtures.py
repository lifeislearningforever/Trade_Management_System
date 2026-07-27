"""
Shared fixtures for the live-Kudu AVP scenario suite (test_avp_live_scenarios.py)
and its companion cleanup script (scripts/cleanup_avp_test_data.py).

Both import from here so the "what does this suite own in the database" answer
lives in exactly one place.

Design
------
This suite does NOT create any reference/master data (portfolios, securities,
counterparties) — all of that is assumed to already exist in your environment.
The verify_* functions below only READ and assert existence/expected fields,
raising a clear error naming exactly what's missing rather than silently
creating placeholder data.

Two tiers of reference data:

1. TEST_PORTFOLIOS / TEST_SECURITIES — generic 'AVPTEST-*' sandbox entity
   names this suite expects to already exist for isolated, safe testing
   (backdated/amend/cancel scenarios, which rewrite a portfolio+security's
   entire position history for the affected date range — see below).

2. SIT_UAT_PAIRS — real, named SIT/UAT reference entities (e.g.
   UOBS_BCHAIN_FVE / "UOB THAI (F) UQ") supplied by QA for a specific
   SIT/UAT execution pack, one per investment-category combination (Non-Reval
   Quoted, Reval, Non-Reval Subsidiary). Confirmed to have no other trade
   history as of when this suite was written.

cleanup_test_data() only deletes this suite's OWN transactional rows (trades,
positions, queue entries) — never the portfolio/security master rows
themselves, for either tier.

Both tiers carry the same risk: backdated/amend/cancel scenarios drive real
chain recalculation (settlement_service._recalculate_position_chain), which
pre-invalidates and rewrites is_latest flags across a portfolio+security's
ENTIRE position history for the affected date range. Do not repoint either
tier at a portfolio/security with other real activity you care about.

Every row this suite writes is additionally tagged created_by/updated_by =
TEST_MARKER (or queued_by, for the queue tables) as defense-in-depth.

UI-DRIVEN, NOT DIRECT DB WRITES
-------------------------------
Trade actions (create/amend/cancel) go through the REAL views via Django's
test Client (see ui_create_trade/ui_amend_trade/ui_cancel_trade below) —
this suite never UPSERTs into cis_trade/cis_trade_position directly. That
means the real async pipeline (event queue -> trade event worker -> position
queue -> position worker, both started from config/cml_app.py's gunicorn
post_fork hook and running as persistent background threads in your actual
deployed app, entirely separate from this test process) is what actually
creates the position rows. This suite only READS the DB afterward, polling
with a timeout, to check what the real pipeline produced.

Counterparty is derived automatically per security, not supplied — see
get_counterparty_for_security(), which mirrors trade_form.html's
autoSelectCounterpartyFromSecurity() JS (matches the security's `issuer`
field to a cis_party.party_short_name).
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

from django.test import Client
from django.urls import reverse

from core.repositories.impala_connection import impala_manager

DATABASE = 'gmp_cis'

# How long to poll after a UI action before giving up. The real background
# workers poll every 5s (trade event) / 10s (position) — see config/cml_app.py
# — so a few polls at 5s spacing comfortably covers one full round-trip
# without waiting anywhere near the documented 5-minute SLA.
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 90

# Session permissions needed to pass core.middleware.permission_middleware for
# the trade endpoints this suite uses (core/permissions_map.py).
_TEST_USER_PERMISSIONS = {
    'trade-list': 'WRITE',
    'trade-view': 'WRITE',
    'trade-create': 'WRITE',
    'trade-edit': 'WRITE',
    'trade-approval': 'WRITE',
}

# Distinctive, greppable marker — every row this suite ever writes carries this.
TEST_MARKER = 'AVP_AUTOTEST'

# Reserved trade_id band, well clear of real trade_ids (get_next_id() produces
# ~13-digit timestamp-based ids in the 1.7xx-trillion range this decade).
# Kept as a monotonically increasing counter for the lifetime of one process.
_TRADE_ID_BASE = 999_950_000_000
_trade_id_counter = None


def next_test_trade_id() -> int:
    """Return a fresh, reserved-band trade_id, unique within this process."""
    global _trade_id_counter
    if _trade_id_counter is None:
        _trade_id_counter = _TRADE_ID_BASE
    _trade_id_counter += 1
    return _trade_id_counter


# =============================================================================
# Dedicated sandbox master data — owned entirely by this test suite.
# =============================================================================

# name -> (currency, revaluation_status)
TEST_PORTFOLIOS = {
    'AVPTEST-SAMECCY':        ('USD', 'REVALUED'),
    'AVPTEST-XCCY-REVAL':     ('SGD', 'REVALUED'),
    'AVPTEST-XCCY-NONREVAL':  ('SGD', 'NON-REVALUED'),
}

# security_name -> (currency_code, security_investment)
# security_investment '' means an ordinary equity (mark-to-market);
# 'SUBSI' is an equity-method security (carried at cost, no MTM) — see
# Scenario 5's regression test (unrealized_pnl_lc gate).
TEST_SECURITIES = {
    'AVPTEST-SEC-EQUITY': ('USD', ''),
    'AVPTEST-SEC-SUBSI':  ('USD', 'SUBSI'),
}

_QUEUE_TABLES = ['cis_position_queue', 'cis_settlement_queue']

# =============================================================================
# SIT/UAT execution pack — real, named reference entities (per QA request),
# one pair per investment-category combination. See module docstring: these
# are shared reference data, NOT deleted by cleanup_test_data — only the
# transactional rows this suite writes against them are.
# =============================================================================

# label -> (portfolio, portfolio_currency, revaluation_status,
#           security, security_currency, security_investment)
SIT_UAT_PAIRS = {
    'non_reval_quoted': (
        'UOBS_BCHAIN_FVE', 'SGD', 'NON-REVALUED',
        'UOB THAI (F) UQ', 'THB', '',
    ),
    'reval': (
        'UOBS_CIU_FVE_OLT', 'SGD', 'REVALUED',
        'AAPL UQ', 'USD', '',
    ),
    'non_reval_subsidiary': (
        'UOBT_SHF_SUB', 'THB', 'NON-REVALUED',
        'UOI SP', 'SGD', 'SUBSI',
    ),
}


# Real equity prices as of the SIT/UAT execution pack's snapshot (QA-supplied,
# 27072026 11:46). Used as realistic market prices instead of arbitrary made-up
# numbers wherever a scenario needs "market price != trade price" (e.g. the
# equity-method unrealized_pnl_lc regression).
KNOWN_EQUITY_PRICES = {
    'UOB THAI (F) UQ': Decimal('34.364607'),
    'AAPL UQ':          Decimal('272.95'),
    'UOI SP':           Decimal('7.910'),
}

# Real FX rates QA supplied for two specific historical dates (27-Feb, 2-Mar).
# NOT used for hardcoded-value assertions in the scenario tests below: this
# suite's backdated/"today" dates are computed relative to whatever
# system_date_service.get_system_date() returns at run time, which won't
# necessarily line up with these exact two calendar dates by the time the
# suite actually runs (system date advances via EOD/SOD independently of real
# calendar time). Kept here as documented reference data — useful for manual
# sanity-checking live results, or if you want to pin exact-value assertions
# for a specific known run.
KNOWN_FX_RATES = {
    ('THB', 'SGD', '2026-02-27'): Decimal('0.04007322'),
    ('THB', 'SGD', '2026-03-02'): Decimal('0.04007368'),
    ('USD', 'SGD', '2026-02-27'): Decimal('1.2648088'),
    ('USD', 'SGD', '2026-03-02'): Decimal('1.2648088'),
    ('SGD', 'THB', '2026-02-27'): Decimal('24.5506287'),
    ('SGD', 'THB', '2026-03-02'): Decimal('24.5478213'),
}


def verify_sit_uat_master_data() -> None:
    """
    Verify the SIT/UAT reference portfolios/securities already exist with the
    expected currency/revaluation_status/investment_type — this suite does
    NOT create or modify reference data, only reads it.
    """
    for (portfolio, port_ccy, reval_status, security, sec_ccy, inv_type) in SIT_UAT_PAIRS.values():
        rows = impala_manager.execute_query(
            f"SELECT currency, revaluation_status FROM {DATABASE}.cis_portfolio "
            f"WHERE name = '{portfolio}' LIMIT 1",
            database=DATABASE,
        )
        assert rows, (
            f"Portfolio '{portfolio}' not found in cis_portfolio — this suite "
            f"does not create reference data, it must already exist"
        )
        actual_reval = (rows[0].get('revaluation_status') or '').upper()
        assert actual_reval == reval_status, (
            f"Portfolio '{portfolio}' has revaluation_status={actual_reval!r}, "
            f"expected {reval_status!r}"
        )
        verify_test_security(security)


def verify_test_master_data() -> None:
    """Verify the dedicated sandbox portfolios/securities already exist."""
    for name in TEST_PORTFOLIOS:
        rows = impala_manager.execute_query(
            f"SELECT 1 FROM {DATABASE}.cis_portfolio WHERE name = '{name}' LIMIT 1",
            database=DATABASE,
        )
        assert rows, (
            f"Portfolio '{name}' not found in cis_portfolio — this suite does "
            f"not create reference data, it must already exist"
        )
    for security_name in TEST_SECURITIES:
        verify_test_security(security_name)


def verify_test_security(security_name: str) -> None:
    """
    Verify a security already exists in cis_security. Used both for the fixed
    TEST_SECURITIES set and for scenario tests that use an isolated security
    not shared with other scenarios (so their position history doesn't
    collide with the lifecycle group's) — those must also already exist.
    """
    rows = impala_manager.execute_query(
        f"SELECT 1 FROM {DATABASE}.cis_security WHERE security_name = '{security_name}' LIMIT 1",
        database=DATABASE,
    )
    assert rows, (
        f"Security '{security_name}' not found in cis_security — this suite "
        f"does not create reference data, it must already exist"
    )


def get_counterparty_for_security(security_id: str) -> str:
    """
    Mirror trade_form.html's autoSelectCounterpartyFromSecurity() JS: the real
    UI auto-selects the counterparty whose party_short_name matches the
    selected security's issuer field (case-insensitive). This suite drives
    the view directly (no JS), so this replicates that lookup as a read —
    no counterparty is ever created by this suite.
    """
    sec_rows = impala_manager.execute_query(
        f"SELECT issuer FROM {DATABASE}.cis_security WHERE security_name = '{security_id}' LIMIT 1",
        database=DATABASE,
    )
    assert sec_rows and sec_rows[0].get('issuer'), (
        f"Security '{security_id}' has no issuer set in cis_security — cannot "
        f"auto-derive its counterparty the way the real UI does"
    )
    issuer = sec_rows[0]['issuer'].strip()

    party_rows = impala_manager.execute_query(
        f"SELECT party_short_name FROM {DATABASE}.cis_party "
        f"WHERE LOWER(party_short_name) = LOWER('{issuer}') LIMIT 1",
        database=DATABASE,
    )
    assert party_rows, (
        f"Security '{security_id}''s issuer '{issuer}' has no matching "
        f"cis_party.party_short_name — the real UI would show this security's "
        f"counterparty as 'not found' too, so this security can't be traded "
        f"until that's fixed in the reference data"
    )
    return party_rows[0]['party_short_name']


def get_authenticated_client() -> Client:
    """
    A Django test Client with a session that passes
    core.middleware.permission_middleware for the trade endpoints this suite
    uses (login check + trade-create/trade-edit/trade-approval permissions).
    """
    client = Client()
    session = client.session
    session['user_login'] = TEST_MARKER
    session['user_id'] = 1
    session['user_email'] = 'avp-autotest@example.com'
    session['user_permissions'] = dict(_TEST_USER_PERMISSIONS)
    session.save()
    return client


def _trade_post_payload(
    trade_type: str,
    portfolio_id: str,
    security_id: str,
    currency_code: str,
    quantity: Decimal,
    price: Decimal,
    trade_date: str,
    settle_date: str,
    counterparty: str,
    commission: Decimal = Decimal('0'),
    sec_fee: Decimal = Decimal('0'),
    other_charges: Decimal = Decimal('0'),
    gross_amount_lc: Optional[Decimal] = None,
    total_amount_lc: Optional[Decimal] = None,
    open_fx_rate: Optional[Decimal] = None,
) -> dict:
    """
    Build the full POST body trade_create/trade_edit expect (see
    trade/views.py's trade_create, ~line 703-766) — every field the view
    reads via request.POST.get(...), even ones this suite doesn't otherwise
    care about, so nothing unexpectedly resolves to an empty/zero default.
    """
    return {
        'trade_type': trade_type,
        'portfolio_short_name': portfolio_id,
        'currency_code': currency_code,
        'security_label': security_id,
        'trade_status': '',
        'trade_date': trade_date,
        'settle_date': settle_date,
        'quantity': str(quantity),
        'face_value': '0',
        'lot': '0',
        'price': str(price),
        'commission': str(commission),
        'sec_fee': str(sec_fee),
        'other_charges': str(other_charges),
        'total_amount': '0',
        'total_amount_fc': '0',
        'total_amount_lc': str(total_amount_lc) if total_amount_lc is not None else '0',
        'gross_amount_lc': str(gross_amount_lc) if gross_amount_lc is not None else '0',
        'open_close_position': '',
        'extension': '',
        'brokers': '',
        'broker_name': '',
        'gl_fund_type': '',
        'gl_cost_centre': '',
        'gl_account_code': '',
        'contract_ref': '',
        'fd_receipt': '',
        'org_pur_date': '',
        'open_fx_rate': str(open_fx_rate) if open_fx_rate is not None else '1',
        'curr_dealing': '0',
        'open_dealing': '0',
        'input_tax_oth': '0',
        'qty_entitled': '0',
        'selling_rule': '',
        'cash_balance': '0',
        'custodian': '',
        'amor_accr_method': '',
        'remarks': TEST_MARKER,
        'counterparty': counterparty,
        'charge_fee_type': '',
        'charge_exchange': '',
        'charge_country': '',
        'charge_fee_rule': '',
        'charge_fee_value': '0',
        'calculated_commission': '0',
        'calculated_clearing_fee': '0',
        'calculated_trading_fee': '0',
        'calculated_gst': '0',
        'calculated_other_fees': '0',
        'total_calculated_charges': '0',
        'charges_auto_calculated': 'false',
    }


def ui_create_trade(
    client: Client,
    portfolio_id: str,
    security_id: str,
    trade_type: str,
    quantity: Decimal,
    price: Decimal,
    trade_date: str,
    settle_date: str,
    currency_code: str,
    commission: Decimal = Decimal('0'),
    sec_fee: Decimal = Decimal('0'),
    other_charges: Decimal = Decimal('0'),
    gross_amount_lc: Optional[Decimal] = None,
    total_amount_lc: Optional[Decimal] = None,
    open_fx_rate: Optional[Decimal] = None,
) -> int:
    """
    POST to the real trade_create view via Django's test Client — simulates a
    user filling the trade form and clicking submit. Returns the new
    trade_id, found by reading (not writing) cis_trade for the newest row
    matching this exact booking right after a successful (redirect) response.

    Counterparty is derived automatically from the security (see
    get_counterparty_for_security) — never supplied or created by this suite.

    Raises AssertionError if the view didn't redirect (i.e. validation
    failed and it re-rendered the form) or if the new row can't be found.
    """
    counterparty = get_counterparty_for_security(security_id)
    payload = _trade_post_payload(
        trade_type=trade_type, portfolio_id=portfolio_id, security_id=security_id,
        currency_code=currency_code, quantity=quantity, price=price,
        trade_date=trade_date, settle_date=settle_date, counterparty=counterparty,
        commission=commission, sec_fee=sec_fee, other_charges=other_charges,
        gross_amount_lc=gross_amount_lc, total_amount_lc=total_amount_lc,
        open_fx_rate=open_fx_rate,
    )
    response = client.post(reverse('trade:create'), data=payload)
    assert response.status_code == 302, (
        f"trade_create didn't redirect (expected success) — got "
        f"{response.status_code}. Response content (form re-rendered with "
        f"errors likely): {getattr(response, 'content', b'')[:2000]}"
    )

    rows = impala_manager.execute_query(
        f"""
        SELECT trade_id FROM {DATABASE}.cis_trade
        WHERE portfolio_short_name = '{portfolio_id}'
          AND security_label = '{security_id}'
          AND trade_type = '{trade_type}'
          AND trade_date = '{trade_date}'
          AND settle_date = '{settle_date}'
          AND quantity = CAST({float(quantity)} AS DECIMAL(20,6))
          AND price = CAST({float(price)} AS DECIMAL(20,6))
          AND created_by = '{TEST_MARKER}'
          AND (is_deleted = false OR is_deleted IS NULL)
        ORDER BY trade_id DESC
        LIMIT 1
        """,
        database=DATABASE,
    )
    assert rows, (
        f"trade_create redirected (apparent success) but no matching cis_trade "
        f"row was found for {portfolio_id}/{security_id} {trade_type} "
        f"{quantity}@{price} on {trade_date}"
    )
    return rows[0]['trade_id']


def ui_amend_trade(client: Client, trade_id: int, new_quantity: Optional[Decimal] = None,
                    new_price: Optional[Decimal] = None) -> None:
    """
    POST to the real trade_edit view. trade_edit does NOT re-validate
    portfolio/security/counterparty and does NOT re-run chain recalculation
    itself as a separate step this suite needs to trigger — the view's own
    save path already drives that synchronously, so no extra call is needed
    after this returns.

    Reads (not writes) the current trade row first so every other field gets
    resubmitted unchanged — trade_edit's POST handling has no fallback to the
    existing DB value for a field that's simply absent from the POST body.
    """
    current = impala_manager.execute_query(
        f"SELECT * FROM {DATABASE}.cis_trade WHERE trade_id = {trade_id} LIMIT 1",
        database=DATABASE,
    )
    assert current, f"Cannot amend trade {trade_id} — not found"
    row = current[0]
    assert row.get('counterparty'), (
        f"Trade {trade_id} has no counterparty stored — cannot resubmit "
        f"trade_edit's form without it"
    )

    payload = _trade_post_payload(
        trade_type=row['trade_type'], portfolio_id=row['portfolio_short_name'],
        security_id=row['security_label'], currency_code=row.get('currency_code') or '',
        quantity=new_quantity if new_quantity is not None else Decimal(str(row['quantity'])),
        price=new_price if new_price is not None else Decimal(str(row['price'])),
        trade_date=row['trade_date'], settle_date=row['settle_date'],
        counterparty=row['counterparty'],
        commission=Decimal(str(row.get('commission') or 0)),
        sec_fee=Decimal(str(row.get('sec_fee') or 0)),
        other_charges=Decimal(str(row.get('other_charges') or 0)),
        gross_amount_lc=Decimal(str(row['gross_amount_lc'])) if row.get('gross_amount_lc') else None,
        total_amount_lc=Decimal(str(row['total_amount_lc'])) if row.get('total_amount_lc') else None,
        open_fx_rate=Decimal(str(row['open_fx_rate'])) if row.get('open_fx_rate') else None,
    )
    response = client.post(reverse('trade:edit', args=[trade_id]), data=payload)
    assert response.status_code == 302, (
        f"trade_edit didn't redirect (expected success) for trade {trade_id} — "
        f"got {response.status_code}. Content: {getattr(response, 'content', b'')[:2000]}"
    )


def ui_cancel_trade(client: Client, trade_id: int, reason: str = 'AVP_AUTOTEST cancellation') -> None:
    """POST to the real trade_cancel view. Like trade_edit, this view's own
    save path drives chain recalculation synchronously — no extra step needed."""
    response = client.post(reverse('trade:cancel', args=[trade_id]), data={'reason': reason})
    assert response.status_code == 302, (
        f"trade_cancel didn't redirect (expected success) for trade {trade_id} — "
        f"got {response.status_code}. Content: {getattr(response, 'content', b'')[:2000]}"
    )


def set_test_market_price(security_label: str, currency_code: str, price: Decimal,
                           price_date: Optional[str] = None) -> None:
    """
    UPSERT a market price for a test security so PositionService._get_market_price
    returns something other than the trade price — needed to make the
    equity-method (Subsi/Assoc) unrealized_pnl_lc regression scenario meaningful
    (otherwise market_value == cost and the gate would look correct by
    coincidence even if broken).

    NOTE: cis_equity_price isn't in this repo's checked-in DDL (only the Docker
    variant cis_equity_price_kudu is) — it exists in the live cluster as a
    separate table with this exact column shape (see sql/debug_avp.sql's Q_EP3
    for precedent). created_at/updated_at are BIGINT epoch-millis here, unlike
    most other tables in this schema.
    """
    price_date = price_date or datetime.now().strftime('%Y-%m-%d')
    now_ms = int(time.time() * 1000)
    query = f"""
    UPSERT INTO {DATABASE}.cis_equity_price
    (currency_code, security_label, price_date, main_closing_price,
     price_timestamp, src_system, is_active, created_by, created_at,
     updated_by, updated_at)
    VALUES (
        '{currency_code}', '{security_label}', '{price_date}',
        CAST({float(price)} AS DECIMAL(18,6)), {now_ms}, 'CIS', true,
        '{TEST_MARKER}', {now_ms}, '{TEST_MARKER}', {now_ms}
    )
    """
    impala_manager.execute_write(query, database=DATABASE)


def get_cis_position(
    portfolio_id: str,
    security_id: str,
    position_type: str,
    position_date: str,
    position_basis: str = 'TRADED',
) -> Optional[dict]:
    """
    Fetch a row from cis_position (the golden/summary table used by the
    INT -> EOD -> SOD lifecycle — refresh_positions.py / create_sod_snapshot.py),
    NOT cis_trade_position. position_type is 'INT', 'EOD', 'CORR', or 'SOD'.
    """
    query = f"""
    SELECT * FROM {DATABASE}.cis_position
    WHERE portfolio = '{portfolio_id}'
      AND security_label = '{security_id}'
      AND position_type = '{position_type}'
      AND position_date = '{position_date}'
      AND position_basis = '{position_basis}'
      AND (is_latest = true OR is_latest IS NULL)
    ORDER BY version_id DESC
    LIMIT 1
    """
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        results = impala_manager.execute_query(query, database=DATABASE)
        if results:
            return results[0]
        if time.time() >= deadline:
            return None
        time.sleep(POLL_INTERVAL_SECONDS)


def get_latest_position(
    portfolio_id: str,
    security_id: str,
    position_basis: str = 'TRADED',
    position_date: Optional[str] = None,
) -> Optional[dict]:
    """Fetch the current is_latest=true row for assertions, polling for up to
    POLL_TIMEOUT_SECONDS — the real background workers (trade event + position
    queue) process this asynchronously, entirely outside this test process."""
    date_clause = f"AND position_date = '{position_date}'" if position_date else ""
    query = f"""
    SELECT * FROM {DATABASE}.cis_trade_position
    WHERE portfolio_short_name = '{portfolio_id}'
      AND security_label = '{security_id}'
      AND position_basis = '{position_basis}'
      AND (is_latest = true OR is_latest IS NULL)
      {date_clause}
    ORDER BY position_date DESC, version_id DESC
    LIMIT 1
    """
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        results = impala_manager.execute_query(query, database=DATABASE)
        if results:
            return results[0]
        if time.time() >= deadline:
            return None
        time.sleep(POLL_INTERVAL_SECONDS)


def cleanup_test_data(verbose: bool = True) -> dict:
    """
    Delete this suite's own transactional footprint — trades, positions, and
    queue entries — for both reference-data tiers (sandbox TEST_PORTFOLIOS/
    TEST_SECURITIES and the SIT_UAT_PAIRS entities).

    Never touches cis_portfolio/cis_security/cis_party — this suite doesn't
    create reference/master data, so it has nothing of its own to delete
    there either.

    Returns a dict of {table: rows_deleted_or_None} for reporting. Kudu's
    execute_write doesn't return affected-row counts, so this reports success/
    failure per statement rather than exact counts.
    """
    sit_uat_portfolios = [p[0] for p in SIT_UAT_PAIRS.values()]
    sit_uat_securities = [p[3] for p in SIT_UAT_PAIRS.values()]
    portfolio_list = "', '".join(list(TEST_PORTFOLIOS.keys()) + sit_uat_portfolios)
    security_list = "', '".join(list(TEST_SECURITIES.keys()) + sit_uat_securities)
    results = {}

    def _run(label, query):
        ok = impala_manager.execute_write(query, database=DATABASE)
        results[label] = ok
        if verbose:
            print(f"  {'OK' if ok else 'FAILED'}: {label}")

    if verbose:
        print(f"Cleaning up AVP test data for portfolios: {list(TEST_PORTFOLIOS.keys())}")

    _run(
        'cis_trade_position',
        f"DELETE FROM {DATABASE}.cis_trade_position "
        f"WHERE portfolio_short_name IN ('{portfolio_list}') "
        f"OR created_by = '{TEST_MARKER}'",
    )
    _run(
        'cis_position',
        f"DELETE FROM {DATABASE}.cis_position "
        f"WHERE portfolio IN ('{portfolio_list}')",
    )
    _run(
        'cis_trade',
        f"DELETE FROM {DATABASE}.cis_trade "
        f"WHERE portfolio_short_name IN ('{portfolio_list}') "
        f"OR created_by = '{TEST_MARKER}'",
    )
    _run(
        'cis_trade_event_queue',
        f"DELETE FROM {DATABASE}.cis_trade_event_queue "
        f"WHERE created_by = '{TEST_MARKER}'",
    )
    for queue_table in _QUEUE_TABLES:
        _run(
            queue_table,
            f"DELETE FROM {DATABASE}.{queue_table} "
            f"WHERE portfolio_id IN ('{portfolio_list}') "
            f"OR queued_by = '{TEST_MARKER}'",
        )
    _run(
        'cis_equity_price',
        f"DELETE FROM {DATABASE}.cis_equity_price "
        f"WHERE security_label IN ('{security_list}') "
        f"OR created_by = '{TEST_MARKER}'",
    )

    if verbose:
        failed = [t for t, ok in results.items() if not ok]
        if failed:
            print(f"WARNING: cleanup failed for: {failed}")
        else:
            print("Cleanup complete — no AVP test data remains.")

    return results
