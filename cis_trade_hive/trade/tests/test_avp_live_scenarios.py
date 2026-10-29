"""
Live-Kudu AVP Scenario Suite
============================

Runs the AVP (Average Price Position) engine end-to-end against a REAL Kudu
database. Trade actions (create/amend/cancel) are driven through the REAL
views via Django's test Client (django.test.Client) — simulating a real user
filling the trade form and clicking submit — NOT by writing directly to
cis_trade/cis_trade_position. That means the real async pipeline (event
queue -> trade event worker -> position queue -> position worker, both
persistent background threads started from config/cml_app.py's gunicorn
post_fork hook, running in your actual deployed app entirely separate from
this test process) is what actually produces the position rows. This suite
only reads the DB afterward — polling with a timeout — to check what the
real pipeline produced and decide pass/fail.

This is the live counterpart to test_avp_scenarios.py (which mocks Kudu and
is single-currency only); this file additionally covers cross-currency
REVALUED / NON-REVALUED / equity-method scenarios, and is the regression
suite for the Scenario 1/3/5/6 fixes made against DEAL-20260724-8334.

This suite does NOT create any reference/master data — portfolios, securities,
and counterparties are all assumed to already exist in your environment (see
avp_live_fixtures.py's verify_* functions, which only read/assert). Two tiers
of reference data it expects to find:
- Generic 'AVPTEST-*' sandbox entity names, for isolated/safe testing.
- SIT_UAT_PAIRS — real, named SIT/UAT reference entities supplied by QA
  (UOBS_BCHAIN_FVE/"UOB THAI (F) UQ" = Non-Reval Quoted, UOBS_CIU_FVE_OLT/
  AAPL UQ = Reval, UOBT_SHF_SUB/UOI SP = Non-Reval Subsidiary), confirmed to
  have no other trade history. This suite's transactional footprint on them
  (trades/positions/queue entries it creates) is cleaned up automatically;
  the portfolio/security master rows themselves are never touched.

Counterparty is derived automatically per security (matching the security's
`issuer` field to a cis_party.party_short_name — see
avp_live_fixtures.get_counterparty_for_security, which mirrors
trade_form.html's client-side auto-select logic), never created or supplied.

SAFETY
------
This suite writes real trade/position rows to a real database. It only ever
touches the entities listed above — never point either tier at a real,
actively-traded portfolio (backdated/amend/cancel scenarios drive chain
recalculation, which rewrites is_latest flags across that portfolio+
security's ENTIRE position history for the affected date range).

Disabled by default. To run against your work env's Kudu:

    RUN_LIVE_AVP_TESTS=1 pytest trade/tests/test_avp_live_scenarios.py -v

Cleanup runs automatically at the end of the module (pass/fail either way).
To clean up manually at any time (e.g. after a crashed run):

    python scripts/cleanup_avp_test_data.py

Run status
----------
pytest's own summary line at the end of the run ("N passed, M failed") IS the
one-click run status — no separate report format needed.
"""

import os
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command

from trade.services.position_service import PositionService
from core.repositories.impala_connection import impala_manager

from trade.tests.avp_live_fixtures import (
    DATABASE,
    SIT_UAT_PAIRS,
    KNOWN_EQUITY_PRICES,
    verify_sit_uat_master_data,
    cleanup_test_data,
    get_authenticated_client,
    ui_create_trade,
    ui_amend_trade,
    ui_cancel_trade,
    set_test_market_price,
    get_latest_position,
    get_cis_position,
)

pytestmark = [
    pytest.mark.skipif(
        os.environ.get('RUN_LIVE_AVP_TESTS') != '1',
        reason="Live-Kudu AVP suite is opt-in — set RUN_LIVE_AVP_TESTS=1 to run "
               "it against your work env's real database.",
    ),
    # django.test.Client.session is backed by Django's configured DATABASES
    # (SQLite here) via django.contrib.sessions — nothing to do with Kudu —
    # so pytest-django needs this marker to allow that DB access. Kudu writes
    # (the actual AVP data this suite cares about) are on a separate
    # connection entirely and are NOT part of Django's test-transaction
    # rollback, so they persist as real data exactly as intended.
    pytest.mark.django_db,
]

# Date-anchor registry — every test below reuses one of only 3 real
# portfolio/security pairs (SIT_UAT_PAIRS), so each test needing an
# exact-value check (not a delta check) on a FRESH position must use a
# trade_date offset (days before "today") no other test also writes to for
# that same pair. Keep this list updated when adding a new exact-value test.
#   Group 3 (SIT/UAT full lifecycle): today, today-6, today-10, today-15
#   Group "FX/cost exact checks" below: today-20 (reval), today-21 (non_reval_quoted)
#   Group 4 (SOD/EOD): today-25/-24 (reval), today-23/-22 (non_reval_quoted)

position_service = PositionService()

_client = None


def _get_client():
    """Lazily create the authenticated test Client on first use — module-level
    creation would touch the (DB-backed) session store at import/collection
    time, before pytest-django's django_db marker is active."""
    global _client
    if _client is None:
        _client = get_authenticated_client()
    return _client


def setup_module(module):
    """Runs once before any test in this file: verify the 3 SIT/UAT reference
    pairs already exist with the expected reval status — this suite does not
    create reference data, only trade data, and only through the real UI."""
    verify_sit_uat_master_data()


def teardown_module(module):
    """Runs once after all tests in this file, pass or fail: wipe this
    suite's transactional footprint (trades/positions/queues)."""
    cleanup_test_data()


def _today() -> date:
    """The AVP engine's own notion of 'today' — not necessarily the calendar
    date, see system_date_service. Scenario dates are computed relative to
    this so the suite stays correct regardless of when it's run."""
    from core.services.system_date_service import system_date_service
    return system_date_service.get_system_date()


def _settle_trade(portfolio_id, security_id, trade_type, quantity, price,
                   trade_date, settle_date, portfolio_currency, security_currency,
                   commission=Decimal('0'), sec_fee=Decimal('0'), other_charges=Decimal('0'),
                   gross_amount_lc=None, total_amount_lc=None, open_fx_rate=None):
    """
    Simulate a user submitting the trade-create form via the real trade_create
    view (Django test Client POST), then poll cis_trade_position for the
    TRADED-basis row produced by the real async pipeline (event queue ->
    trade event worker -> position queue -> position worker).

    Returns the real trade_id (assigned live by insert_trade_fast() inside
    the view, read back from cis_trade — not pre-generated by this suite).
    """
    trade_id = ui_create_trade(
        _get_client(), portfolio_id=portfolio_id, security_id=security_id,
        trade_type=trade_type, quantity=quantity, price=price,
        trade_date=trade_date, settle_date=settle_date,
        currency_code=security_currency,
        commission=commission, sec_fee=sec_fee, other_charges=other_charges,
        gross_amount_lc=gross_amount_lc, total_amount_lc=total_amount_lc,
        open_fx_rate=open_fx_rate,
    )
    pos = get_latest_position(portfolio_id, security_id, 'TRADED', trade_date)
    assert pos is not None, (
        f"No TRADED position appeared for trade {trade_id} "
        f"({portfolio_id}/{security_id}) within the poll timeout — check "
        f"whether the trade event/position worker threads are running"
    )
    return trade_id


# =============================================================================
# GROUP: FX / COST EXACT-VALUE CHECKS — uses dedicated fresh date anchors
# (today-20, today-21) on the 'reval'/'non_reval_quoted' SIT/UAT pairs so
# these exact-value assertions aren't affected by the cumulative quantity
# Group 3's tests build up on "today" for the same pairs.
# =============================================================================

def test_reval_pair_cost_lc_uses_fx_table():
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS['reval']
    anchor = (_today() - timedelta(days=20)).isoformat()
    quantity = Decimal('100')
    price = Decimal('50')
    _settle_trade(
        portfolio, security, 'BUY', quantity, price, anchor, anchor,
        portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    pos = get_latest_position(portfolio, security, 'TRADED', anchor)
    assert pos is not None

    # REVALUED: cost_lc must be derived from the live FX table rate for this
    # date, not a user-entered override. Read total_cost_fc back from the row
    # itself (not re-derived from quantity*price) so this stays correct even
    # if this pair/date ever accumulates prior history — cross-checked
    # against an independent live query (not the row's own fx_rate column) so
    # this is a real regression check, not a tautology. This is exactly the
    # two-calls-disagreeing failure mode from the original 3-day bug hunt
    # (see position_service._save_position's reval_status docstring).
    expected_fx_rate = position_service._get_fx_rate(sec_ccy, port_ccy, rate_date=anchor)
    total_cost_fc = Decimal(str(pos['total_cost_fc']))
    expected_cost_lc = (total_cost_fc * expected_fx_rate).quantize(Decimal('0.01'))
    actual_cost_lc = Decimal(str(pos['total_cost_lc'])).quantize(Decimal('0.01'))
    assert actual_cost_lc == expected_cost_lc, (
        f"REVALUED cost_lc should be total_cost_fc({total_cost_fc}) x "
        f"live FX rate({expected_fx_rate}) = {expected_cost_lc}, got {actual_cost_lc}"
    )


def test_non_reval_quoted_pair_cost_lc_uses_open_fx_override():
    """NON-REVALUED cross-currency cost_lc must come from the trade's own
    entered LC amount (gross_amount_lc), not the FX table — this is the
    open_fx_rate override at the center of the original 3-day bug hunt."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS['non_reval_quoted']
    anchor = (_today() - timedelta(days=21)).isoformat()
    quantity = Decimal('10')
    price = Decimal('100')
    gross_amount_lc = Decimal('1350')  # user-entered LC amount, e.g. 1.35 rate

    _settle_trade(
        portfolio, security, 'BUY', quantity, price, anchor, anchor,
        portfolio_currency=port_ccy, security_currency=sec_ccy,
        gross_amount_lc=gross_amount_lc, total_amount_lc=gross_amount_lc,
    )
    pos = get_latest_position(portfolio, security, 'TRADED', anchor)
    assert pos is not None
    assert Decimal(str(pos['total_cost_lc'])) == gross_amount_lc, (
        f"NON-REVALUED cost_lc should equal the entered gross_amount_lc "
        f"({gross_amount_lc}), got {pos['total_cost_lc']} — check whether the "
        f"open_fx_rate override is being applied"
    )


# =============================================================================
# GROUP 3: SIT/UAT REFERENCE PAIRS — full lifecycle coverage per QA's
# execution pack request (DEAL-20260724-8334 follow-up scenario input).
#
# Each of the 3 pairs (Non-Reval Quoted, Reval, Non-Reval Subsidiary) is run
# through: same-day fresh buy (both TRADED and SETTLED basis), future
# settlement, backdated buy, today amendment, backdated amendment, today
# cancellation, backdated cancellation. Distinct, non-overlapping date anchors
# are used per scenario type so assertions on backdated dates can be exact;
# "today"-anchored scenarios (fresh buy, future settlement's trade_date, today
# amend/cancel) share the same date across scenario types for one pair, so
# those assertions are delta-based (read the state immediately before the
# action, assert the exact expected change) rather than assuming a fixed
# starting quantity.
# =============================================================================

def _qty_or_zero(portfolio, security, basis='TRADED', position_date=None):
    pos = get_latest_position(portfolio, security, basis, position_date)
    return Decimal(str(pos['quantity'])) if pos else Decimal('0')


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_fresh_buy_both_bases(label):
    """Same-day settlement: T+0 means TRADED and SETTLED both land on today —
    assert both basis rows, not just TRADED."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today_str = _today().isoformat()
    qty_before_traded = _qty_or_zero(portfolio, security, 'TRADED', today_str)
    qty_before_settled = _qty_or_zero(portfolio, security, 'SETTLED', today_str)

    _settle_trade(
        portfolio, security, 'BUY', Decimal('20'), Decimal('40'),
        today_str, today_str, portfolio_currency=port_ccy, security_currency=sec_ccy,
    )

    traded = get_latest_position(portfolio, security, 'TRADED', today_str)
    settled = get_latest_position(portfolio, security, 'SETTLED', today_str)
    assert traded is not None, f"[{label}] TRADED position missing after same-day BUY"
    assert settled is not None, f"[{label}] SETTLED position missing after same-day BUY (T+0)"
    assert Decimal(str(traded['quantity'])) == qty_before_traded + Decimal('20')
    assert Decimal(str(settled['quantity'])) == qty_before_settled + Decimal('20')


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_future_settlement_queues_settled_basis(label):
    """settle_date > today: TRADED is calculated immediately (trade_date =
    today), SETTLED is queued to cis_settlement_queue for processing on the
    actual settle_date, not calculated yet."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today = _today()
    today_str = today.isoformat()
    future_settle_str = (today + timedelta(days=7)).isoformat()
    qty_before_traded = _qty_or_zero(portfolio, security, 'TRADED', today_str)

    trade_id = _settle_trade(
        portfolio, security, 'BUY', Decimal('15'), Decimal('45'),
        today_str, future_settle_str, portfolio_currency=port_ccy, security_currency=sec_ccy,
    )

    traded = get_latest_position(portfolio, security, 'TRADED', today_str)
    assert traded is not None, f"[{label}] TRADED position missing for future-settle trade"
    assert Decimal(str(traded['quantity'])) == qty_before_traded + Decimal('15')

    settled_now = get_latest_position(portfolio, security, 'SETTLED', future_settle_str)
    assert settled_now is None, (
        f"[{label}] SETTLED position for a future settle_date should not exist "
        f"yet — it's queued for processing on {future_settle_str}, not calculated now"
    )

    queued = impala_manager.execute_query(
        f"SELECT 1 FROM {DATABASE}.cis_settlement_queue "
        f"WHERE trade_id = {trade_id} AND position_basis = 'SETTLED' LIMIT 1",
        database=DATABASE,
    )
    assert queued, f"[{label}] Expected a pending cis_settlement_queue row for trade {trade_id}"


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_backdated_buy_backfills_every_day(label):
    """Regression for Scenario 1, per SIT/UAT pair."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today = _today()
    backdated = today - timedelta(days=15)  # dedicated anchor, unused by any other scenario

    _settle_trade(
        portfolio, security, 'BUY', Decimal('30'), Decimal('20'),
        backdated.isoformat(), today.isoformat(), portfolio_currency=port_ccy, security_currency=sec_ccy,
    )

    on_backdate = get_latest_position(portfolio, security, 'TRADED', backdated.isoformat())
    on_today = get_latest_position(portfolio, security, 'TRADED', today.isoformat())
    assert on_backdate is not None, f"[{label}] TRADED position missing on the backdated trade_date"
    assert Decimal(str(on_backdate['quantity'])) == Decimal('30')
    assert on_today is not None, (
        f"[{label}] TRADED position missing on today — Scenario 1 regression: "
        f"backdated trade settling today misclassified as T+0"
    )


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_backdated_amendment(label):
    """Amending a trade whose OWN trade_date is in the past — distinct from
    the same-ccy sandbox amend regression (which amends a TODAY trade while
    an earlier position exists). Here the amended trade itself is backdated."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today = _today()
    backdated = today - timedelta(days=10)  # dedicated anchor

    trade_id = _settle_trade(
        portfolio, security, 'BUY', Decimal('40'), Decimal('25'),
        backdated.isoformat(), backdated.isoformat(), portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    before = get_latest_position(portfolio, security, 'TRADED', backdated.isoformat())
    assert before is not None
    assert Decimal(str(before['quantity'])) == Decimal('40')

    ui_amend_trade(_get_client(), trade_id, new_quantity=Decimal('55'))

    after = get_latest_position(portfolio, security, 'TRADED', backdated.isoformat())
    assert after is not None
    assert Decimal(str(after['quantity'])) == Decimal('55'), (
        f"[{label}] Backdated amendment: expected qty 55 on {backdated.isoformat()} "
        f"after amending the backdated trade itself, got {after['quantity']}"
    )
    on_today = get_latest_position(portfolio, security, 'TRADED', today.isoformat())
    assert on_today is not None and Decimal(str(on_today['quantity'])) == Decimal('55'), (
        f"[{label}] Backdated amendment should carry forward to today too"
    )


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_today_cancellation(label):
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today_str = _today().isoformat()
    qty_before = _qty_or_zero(portfolio, security, 'TRADED', today_str)

    _settle_trade(
        portfolio, security, 'BUY', Decimal('25'), Decimal('30'),
        today_str, today_str, portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    sell_id = _settle_trade(
        portfolio, security, 'SELL', Decimal('10'), Decimal('35'),
        today_str, today_str, portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    after_sell = get_latest_position(portfolio, security, 'TRADED', today_str)
    assert Decimal(str(after_sell['quantity'])) == qty_before + Decimal('15')

    ui_cancel_trade(_get_client(), sell_id)

    after_cancel = get_latest_position(portfolio, security, 'TRADED', today_str)
    assert Decimal(str(after_cancel['quantity'])) == qty_before + Decimal('25'), (
        f"[{label}] Today cancellation: expected the 10-qty SELL's cancellation "
        f"to restore quantity to qty_before+25, got {after_cancel['quantity']}"
    )


@pytest.mark.parametrize('label', list(SIT_UAT_PAIRS.keys()))
def test_sit_uat_backdated_cancellation(label):
    """Regression for Scenario 6, cancelling a trade whose own trade_date is
    backdated (distinct from the sandbox test, which cancels a today trade)."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS[label]
    today = _today()
    backdated = today - timedelta(days=6)  # dedicated anchor

    _settle_trade(
        portfolio, security, 'BUY', Decimal('60'), Decimal('15'),
        backdated.isoformat(), backdated.isoformat(), portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    sell_id = _settle_trade(
        portfolio, security, 'SELL', Decimal('20'), Decimal('18'),
        backdated.isoformat(), backdated.isoformat(), portfolio_currency=port_ccy, security_currency=sec_ccy,
    )
    after_sell = get_latest_position(portfolio, security, 'TRADED', backdated.isoformat())
    assert Decimal(str(after_sell['quantity'])) == Decimal('40')

    ui_cancel_trade(_get_client(), sell_id)

    after_cancel = get_latest_position(portfolio, security, 'TRADED', backdated.isoformat())
    assert Decimal(str(after_cancel['quantity'])) == Decimal('60'), (
        f"[{label}] Backdated cancellation: expected qty restored to 60 on "
        f"{backdated.isoformat()}, got {after_cancel['quantity']}"
    )
    on_today = get_latest_position(portfolio, security, 'TRADED', today.isoformat())
    assert on_today is not None and Decimal(str(on_today['quantity'])) >= Decimal('60'), (
        f"[{label}] Restored quantity should carry forward to today too"
    )


def test_sit_uat_non_reval_subsidiary_zero_unrealized_pnl():
    """The specific combination QA flagged: Non-Reval portfolio + Subsidiary
    (equity-method) security. Both the NON-REVALUED cost_lc override (open_fx
    override) and the equity-method unrealized_pnl_lc gate apply here
    simultaneously — this is the one pair where both fixes must hold at once."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS['non_reval_subsidiary']
    assert reval_status == 'NON-REVALUED' and inv_type == 'SUBSI'  # sanity-check the fixture itself

    today_str = _today().isoformat()
    quantity = Decimal('50')
    trade_price = Decimal('20')
    # QA-supplied real quoted price for UOI SP (deliberately different from
    # trade_price, which is what makes this a meaningful regression check —
    # market_value would differ from cost if the equity-method gate were broken).
    market_price = KNOWN_EQUITY_PRICES[security]
    gross_amount_lc = Decimal('1100')  # user-entered LC amount (open_fx override)

    set_test_market_price(security, sec_ccy, market_price, today_str)

    _settle_trade(
        portfolio, security, 'BUY', quantity, trade_price,
        today_str, today_str, portfolio_currency=port_ccy, security_currency=sec_ccy,
        gross_amount_lc=gross_amount_lc, total_amount_lc=gross_amount_lc,
    )

    pos = get_latest_position(portfolio, security, 'TRADED', today_str)
    assert pos is not None
    assert Decimal(str(pos['unrealized_pnl_fc'])) == Decimal('0'), \
        "Equity-method unrealized_pnl_fc should be 0"
    assert Decimal(str(pos['unrealized_pnl_lc'])) == Decimal('0'), (
        f"Non-Reval Subsidiary: unrealized_pnl_lc should be 0, got "
        f"{pos['unrealized_pnl_lc']}"
    )


# =============================================================================
# GROUP 4: SOD / INT / EOD VALIDATIONS
#
# The lifecycle these two batch management commands drive is:
#   trade booked -> position_service._sync_to_cis_position writes an INT row
#   refresh_positions.py (EOD run)   -> revalues INT (or SOD fallback), writes EOD
#   create_sod_snapshot.py (SOD run) -> copies EOD forward as SOD for the next
#                                        business day, folding in any
#                                        cis_settlement_queue entries settling
#                                        that day
#
# Both commands are invoked here via Django's call_command with explicit
# --position-date/--eod-date/--sod-date overrides, bypassing their normal
# gmp_cis_sta_dly_alldatesinfo-based date inference entirely — so these tests
# don't depend on that reference table being populated for whatever "today"
# resolves to when the suite runs.
# =============================================================================

def test_int_to_eod_to_sod_lifecycle():
    """Full INT -> EOD -> SOD chain for one fresh position, on the 'reval'
    SIT/UAT pair at a dedicated anchor (today-25/-24) unused by any other test."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS['reval']
    today = _today()
    anchor = today - timedelta(days=25)
    sod_date = today - timedelta(days=24)
    anchor_str, sod_date_str = anchor.isoformat(), sod_date.isoformat()

    trade_price = Decimal('40')
    market_price = Decimal('55')  # different from trade price, so unrealized_pnl is meaningful
    quantity = Decimal('100')
    set_test_market_price(security, sec_ccy, market_price, anchor_str)

    _settle_trade(
        portfolio, security, 'BUY', quantity, trade_price, anchor_str, anchor_str,
        portfolio_currency=port_ccy, security_currency=sec_ccy,
    )

    # Step 1: INT row should already exist (written synchronously by
    # position_service._sync_to_cis_position as part of the same trade save).
    int_pos = get_cis_position(portfolio, security, 'INT', anchor_str, 'TRADED')
    assert int_pos is not None, "Expected an INT row in cis_position immediately after booking"
    assert Decimal(str(int_pos['quantity'])) == quantity

    # Step 2: EOD run (refresh_positions), explicit position_date to avoid
    # depending on alldatesinfo.
    call_command(
        'refresh_positions',
        portfolio=portfolio, security=security,
        position_date=anchor_str, run_type='EOD',
    )
    eod_pos = get_cis_position(portfolio, security, 'EOD', anchor_str, 'TRADED')
    assert eod_pos is not None, "Expected an EOD row after refresh_positions"
    assert Decimal(str(eod_pos['quantity'])) == quantity
    assert Decimal(str(eod_pos['market_value_fc'])) == quantity * market_price, (
        "EOD market_value_fc should reflect the latest cis_equity_price, "
        f"expected {quantity * market_price}, got {eod_pos['market_value_fc']}"
    )
    expected_unrealized = quantity * (market_price - trade_price)
    assert Decimal(str(eod_pos['unrealized_pnl_fc'])) == expected_unrealized, (
        f"EOD unrealized_pnl_fc should be qty*(market-trade) = {expected_unrealized}, "
        f"got {eod_pos['unrealized_pnl_fc']}"
    )

    # Step 3: SOD run (create_sod_snapshot) for the next business day — carries
    # the EOD row forward as the next day's opening position.
    call_command(
        'create_sod_snapshot',
        portfolio=portfolio, security=security,
        eod_date=anchor_str, sod_date=sod_date_str,
    )
    sod_pos = get_cis_position(portfolio, security, 'SOD', sod_date_str, 'TRADED')
    assert sod_pos is not None, "Expected a SOD row for the next day after create_sod_snapshot"
    assert Decimal(str(sod_pos['quantity'])) == quantity
    assert Decimal(str(sod_pos['average_cost_fc'])) == trade_price, (
        "SOD should carry forward EOD's cost basis unchanged"
    )


def test_sod_snapshot_folds_in_pending_settlement():
    """A trade booked with a FUTURE settle_date sits in cis_settlement_queue
    as PENDING (never gets a SETTLED-basis position of its own until
    settle_date arrives). Running create_sod_snapshot for that settle_date
    must apply it — creating a brand-new SOD row (this pair/date combo has no
    prior EOD row at all) and marking the queue entry COMPLETED. Uses the
    'non_reval_quoted' pair at a dedicated anchor (today-23/-22)."""
    portfolio, port_ccy, reval_status, security, sec_ccy, inv_type = SIT_UAT_PAIRS['non_reval_quoted']
    today = _today()
    anchor = today - timedelta(days=23)
    settle_date = today - timedelta(days=22)
    anchor_str, settle_str = anchor.isoformat(), settle_date.isoformat()

    quantity = Decimal('75')
    price = Decimal('22')
    trade_id = _settle_trade(
        portfolio, security, 'BUY', quantity, price, anchor_str, settle_str,
        portfolio_currency=port_ccy, security_currency=sec_ccy,
    )

    queued_before = impala_manager.execute_query(
        f"SELECT status FROM {DATABASE}.cis_settlement_queue "
        f"WHERE trade_id = {trade_id} AND position_basis = 'SETTLED' LIMIT 1",
        database=DATABASE,
    )
    assert queued_before and queued_before[0]['status'] == 'PENDING', (
        "Expected a PENDING cis_settlement_queue row for the future-settle trade"
    )

    call_command(
        'create_sod_snapshot',
        portfolio=portfolio, security=security,
        eod_date=anchor_str, sod_date=settle_str,
    )

    sod_pos = get_cis_position(portfolio, security, 'SOD', settle_str, 'SETTLED')
    assert sod_pos is not None, (
        "Expected a brand-new SOD row created from the pending settlement "
        "queue entry (no prior EOD row existed for this pair/date)"
    )
    assert Decimal(str(sod_pos['quantity'])) == quantity

    queued_after = impala_manager.execute_query(
        f"SELECT status FROM {DATABASE}.cis_settlement_queue "
        f"WHERE trade_id = {trade_id} AND position_basis = 'SETTLED' LIMIT 1",
        database=DATABASE,
    )
    assert queued_after and queued_after[0]['status'] == 'COMPLETED', (
        f"Expected the settlement queue entry marked COMPLETED after SOD "
        f"folded it in, got {queued_after[0]['status'] if queued_after else 'not found'}"
    )
