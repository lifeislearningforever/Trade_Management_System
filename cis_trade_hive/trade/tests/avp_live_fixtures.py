"""
Shared fixtures for the live-Kudu AVP scenario suite (test_avp_live_scenarios.py)
and its companion cleanup script (scripts/cleanup_avp_test_data.py).

Both import from here so the "what does this suite own in the database" answer
lives in exactly one place.

Design
------
Two tiers of test data:

1. TEST_PORTFOLIOS / TEST_SECURITIES — generic 'AVPTEST-*' sandbox entities
   fully OWNED by this suite: created if missing, and fully deleted (including
   the cis_portfolio/cis_security master rows themselves) by cleanup_test_data.
   Safe by construction — nothing else ever uses these names.

2. SIT_UAT_PAIRS — real, named SIT/UAT reference entities (e.g.
   UOBS_BCHAIN_FVE / "UOB THAI (F) UQ") supplied by QA for a specific
   SIT/UAT execution pack, one per investment-category combination (Non-Reval
   Quoted, Reval, Non-Reval Subsidiary). These are confirmed to have no other
   trade history as of when this suite was written — cleanup_test_data only
   deletes this suite's OWN transactional rows (cis_trade, cis_trade_position,
   cis_position, queue tables) for them, scoped by created_by=TEST_MARKER, and
   never touches the cis_portfolio/cis_security rows themselves (shared
   reference data, not owned by this suite).

Both tiers carry the same risk: backdated/amend/cancel scenarios drive real
chain recalculation (settlement_service._recalculate_position_chain), which
pre-invalidates and rewrites is_latest flags across a portfolio+security's
ENTIRE position history for the affected date range. Do not repoint either
tier at a portfolio/security with other real activity you care about.

Every row this suite writes is additionally tagged created_by/updated_by =
TEST_MARKER (or queued_by, for the queue tables) as defense-in-depth.
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.repositories.impala_connection import impala_manager

DATABASE = 'gmp_cis'

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
_POSITION_TABLES = ['cis_trade_position', 'cis_position']

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


def ensure_sit_uat_master_data() -> None:
    """
    UPSERT the SIT/UAT reference portfolios/securities' currency/
    revaluation_status/investment_type fields (idempotent — Kudu UPSERT only
    touches the columns listed, so any other fields already configured on
    these rows, e.g. manager/cost-centre, are left untouched). Does NOT
    delete these rows — see cleanup_test_data.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    seen_portfolios, seen_securities = set(), set()

    for (portfolio, port_ccy, reval_status, security, sec_ccy, inv_type) in SIT_UAT_PAIRS.values():
        if portfolio not in seen_portfolios:
            impala_manager.execute_write(
                f"""
                UPSERT INTO {DATABASE}.cis_portfolio
                (name, currency, revaluation_status, status, is_active,
                 created_by, created_at, updated_by, updated_at)
                VALUES (
                    '{portfolio}', '{port_ccy}', '{reval_status}', 'VALIDATED', true,
                    '{TEST_MARKER}', '{timestamp}', '{TEST_MARKER}', '{timestamp}'
                )
                """,
                database=DATABASE,
            )
            seen_portfolios.add(portfolio)
        if security not in seen_securities:
            impala_manager.execute_write(
                f"""
                UPSERT INTO {DATABASE}.cis_security
                (security_id, security_name, currency_code, investment_type,
                 security_investment, security_type, status,
                 created_by, created_at, updated_by, updated_at)
                VALUES (
                    {abs(hash(security)) % 1_000_000_000}, '{security}',
                    '{sec_ccy}', '{inv_type or "EQUITY"}', '{inv_type}',
                    'EQUITY', 'VALIDATED',
                    '{TEST_MARKER}', '{timestamp}', '{TEST_MARKER}', '{timestamp}'
                )
                """,
                database=DATABASE,
            )
            seen_securities.add(security)


def ensure_test_master_data() -> None:
    """
    UPSERT the dedicated sandbox portfolios/securities if they don't already
    exist. Idempotent — safe to call at the start of every test run.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for name, (currency, reval_status) in TEST_PORTFOLIOS.items():
        query = f"""
        UPSERT INTO {DATABASE}.cis_portfolio
        (name, currency, revaluation_status, src_system, status, is_active,
         created_by, created_at, updated_by, updated_at)
        VALUES (
            '{name}', '{currency}', '{reval_status}', 'CIS', 'VALIDATED', true,
            '{TEST_MARKER}', '{timestamp}', '{TEST_MARKER}', '{timestamp}'
        )
        """
        impala_manager.execute_write(query, database=DATABASE)

    for security_name, (currency_code, investment_type) in TEST_SECURITIES.items():
        ensure_test_security(security_name, currency_code, investment_type)


def ensure_test_security(security_name: str, currency_code: str = 'USD',
                          investment_type: str = '') -> None:
    """
    UPSERT one dedicated sandbox security (idempotent). Used both by
    ensure_test_master_data() for the fixed TEST_SECURITIES set, and directly
    by scenario tests that need an isolated security not shared with other
    scenarios (e.g. the backdated/amend/cancel regression tests, so their
    position history doesn't collide with the lifecycle group's).

    Any security created this way is still covered by cleanup_test_data()'s
    created_by = TEST_MARKER filter, even if its name isn't in TEST_SECURITIES.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    query = f"""
    UPSERT INTO {DATABASE}.cis_security
    (security_id, security_name, currency_code, investment_type,
     security_investment, security_type, status,
     created_by, created_at, updated_by, updated_at)
    VALUES (
        {abs(hash(security_name)) % 1_000_000_000}, '{security_name}',
        '{currency_code}', '{investment_type or "EQUITY"}', '{investment_type}',
        'EQUITY', 'VALIDATED',
        '{TEST_MARKER}', '{timestamp}', '{TEST_MARKER}', '{timestamp}'
    )
    """
    impala_manager.execute_write(query, database=DATABASE)


def insert_test_trade(
    trade_id: int,
    portfolio_id: str,
    security_id: str,
    trade_type: str,
    quantity: Decimal,
    price: Decimal,
    trade_date: str,
    settle_date: str,
    portfolio_currency: str,
    security_currency: str,
    commission: Decimal = Decimal('0'),
    sec_fee: Decimal = Decimal('0'),
    other_charges: Decimal = Decimal('0'),
    gross_amount_lc: Optional[Decimal] = None,
    total_amount_lc: Optional[Decimal] = None,
    open_fx_rate: Optional[Decimal] = None,
) -> None:
    """
    Insert a real cis_trade row for one of the dedicated sandbox portfolios,
    tagged created_by/updated_by = TEST_MARKER.

    Only populates the columns the AVP/chain-recalc code path actually reads
    (settlement_service._recalculate_position_chain's trade-selection query,
    position_service._process_buy/_process_sell). Deliberately bypasses
    validate_trade_data/insert_trade_fast (which additionally require a valid
    counterparty and drive the full async event-queue pipeline) so this suite
    stays fast and deterministic.
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    deal_number = f"{TEST_MARKER}-{trade_id}"

    def _dec(v):
        return f"CAST({float(v)} AS DECIMAL(30,8))" if v is not None else 'NULL'

    query = f"""
    UPSERT INTO {DATABASE}.cis_trade
    (trade_id, trade_type, deal_number, portfolio_short_name, security_label,
     currency_code, portfolio_currency, trade_status, status,
     trade_date, settle_date, quantity, price,
     commission, sec_fee, other_charges,
     gross_amount_fc, gross_amount_lc, total_amount_fc, total_amount_lc,
     open_fx_rate, is_active, is_deleted, src_system,
     created_by, created_at, updated_by, updated_at)
    VALUES (
        {trade_id}, '{trade_type}', '{deal_number}',
        '{portfolio_id}', '{security_id}',
        '{security_currency}', '{portfolio_currency}', 'VALIDATED', 'VALIDATED',
        '{trade_date}', '{settle_date}',
        {_dec(quantity)}, {_dec(price)},
        {_dec(commission)}, {_dec(sec_fee)}, {_dec(other_charges)},
        {_dec(quantity * price)}, {_dec(gross_amount_lc)},
        {_dec(quantity * price + commission + sec_fee + other_charges)},
        {_dec(total_amount_lc)},
        {_dec(open_fx_rate)},
        true, false, 'CIS',
        '{TEST_MARKER}', '{timestamp}', '{TEST_MARKER}', '{timestamp}'
    )
    """
    success = impala_manager.execute_write(query, database=DATABASE)
    if not success:
        raise RuntimeError(f"Failed to insert test trade {trade_id}")


def amend_test_trade_quantity(trade_id: int, new_quantity: Decimal) -> None:
    """Amend a test trade's quantity in place (mirrors trade_edit's UPDATE)."""
    impala_manager.execute_write(
        f"UPDATE {DATABASE}.cis_trade SET quantity = CAST({float(new_quantity)} AS DECIMAL(20,6)), "
        f"status = 'MODIFIED', updated_by = '{TEST_MARKER}' WHERE trade_id = {trade_id}",
        database=DATABASE,
    )


def cancel_test_trade(trade_id: int) -> None:
    """Soft-delete a test trade (mirrors trade_cancel's is_deleted flag)."""
    impala_manager.execute_write(
        f"UPDATE {DATABASE}.cis_trade SET is_deleted = true, status = 'MODIFIED', "
        f"updated_by = '{TEST_MARKER}' WHERE trade_id = {trade_id}",
        database=DATABASE,
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
    for attempt in range(3):
        results = impala_manager.execute_query(query, database=DATABASE)
        if results:
            return results[0]
        time.sleep(0.5)
    return None


def get_latest_position(
    portfolio_id: str,
    security_id: str,
    position_basis: str = 'TRADED',
    position_date: Optional[str] = None,
) -> Optional[dict]:
    """Fetch the current is_latest=true row for assertions, with a short
    retry — the same stale-read class of issue documented in
    position_service._get_position_as_of_date can surface here too."""
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
    for attempt in range(3):
        results = impala_manager.execute_query(query, database=DATABASE)
        if results:
            return results[0]
        time.sleep(0.5)
    return None


def cleanup_test_data(verbose: bool = True) -> dict:
    """
    Delete every row this suite could have written.

    Transactional tables (cis_trade, cis_trade_position, cis_position, queue
    tables, cis_equity_price) are cleaned for BOTH tiers — the sandbox
    TEST_PORTFOLIOS/TEST_SECURITIES and the SIT_UAT_PAIRS reference entities —
    since this suite owns everything IT wrote against either.

    Master-data tables (cis_portfolio, cis_security) are only ever deleted for
    the sandbox 'AVPTEST-%' names — SIT/UAT reference entities are shared data
    this suite doesn't own and must survive (the WHERE clause's 'AVPTEST-%'
    pattern naturally excludes them, since none of the SIT/UAT names match it).

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
    # Scoped by created_by=TEST_MARKER AND the 'AVPTEST-' naming convention
    # (not just the fixed TEST_PORTFOLIOS/TEST_SECURITIES lists) so ad-hoc
    # securities scenario tests create on the fly (e.g. AVPTEST-SEC-AMEND,
    # AVPTEST-SEC-CANCEL — isolated per scenario so their position history
    # doesn't collide) get cleaned up too, without having to enumerate every
    # one here.
    _run(
        'cis_portfolio (sandbox master data)',
        f"DELETE FROM {DATABASE}.cis_portfolio "
        f"WHERE created_by = '{TEST_MARKER}' AND name LIKE 'AVPTEST-%'",
    )
    _run(
        'cis_security (sandbox master data)',
        f"DELETE FROM {DATABASE}.cis_security "
        f"WHERE created_by = '{TEST_MARKER}' AND security_name LIKE 'AVPTEST-%'",
    )

    if verbose:
        failed = [t for t, ok in results.items() if not ok]
        if failed:
            print(f"WARNING: cleanup failed for: {failed}")
        else:
            print("Cleanup complete — no AVP test data remains.")

    return results
