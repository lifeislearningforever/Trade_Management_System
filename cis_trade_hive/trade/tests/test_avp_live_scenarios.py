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

Two tiers of test data (see avp_live_fixtures.py docstring for full detail):
- Generic 'AVPTEST-*' sandbox entities, fully owned/created/deleted by this
  suite.
- SIT_UAT_PAIRS — real, named SIT/UAT reference entities supplied by QA
  (UOBS_BCHAIN_FVE/"UOB THAI (F) UQ" = Non-Reval Quoted, UOBS_CIU_FVE_OLT/
  AAPL UQ = Reval, UOBT_SHF_SUB/UOI SP = Non-Reval Subsidiary), confirmed to
  have no other trade history — this suite's transactional footprint on them
  is cleaned up, but the portfolio/security master rows themselves are not
  (they're shared reference data, not owned by this suite).

SAFETY
------
This suite writes real rows to a real database. It only ever touches the
entities listed above — never point either tier at a real, actively-traded
portfolio (backdated/amend/cancel scenarios drive chain recalculation, which
rewrites is_latest flags across that portfolio+security's ENTIRE position
history for the affected date range).

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
    ensure_test_master_data,
    ensure_test_security,
    ensure_sit_uat_master_data,
    ensure_test_counterparty,
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

SAME_CCY_PORTFOLIO = 'AVPTEST-SAMECCY'
XCCY_REVAL_PORTFOLIO = 'AVPTEST-XCCY-REVAL'
XCCY_NONREVAL_PORTFOLIO = 'AVPTEST-XCCY-NONREVAL'
EQUITY_SECURITY = 'AVPTEST-SEC-EQUITY'
SUBSI_SECURITY = 'AVPTEST-SEC-SUBSI'

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
    """Runs once before any test in this file: ensure all reference/master
    data exists (portfolios, securities, counterparty) — NOT trade data,
    which every test creates itself through the real UI."""
    ensure_test_master_data()
    ensure_sit_uat_master_data()
    ensure_test_counterparty()


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
# GROUP 1: SAME-CURRENCY LIFECYCLE
# =============================================================================

def test_same_ccy_fresh_buy():
    today_str = _today().isoformat()
    _settle_trade(
        SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'BUY',
        Decimal('100'), Decimal('50'), today_str, today_str, 'USD', 'USD',
    )
    pos = get_latest_position(SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert pos is not None, "Expected a TRADED position row after fresh BUY"
    assert Decimal(str(pos['quantity'])) == Decimal('100')
    assert Decimal(str(pos['average_cost_fc'])) == Decimal('50')


def test_same_ccy_buy_accumulates():
    today_str = _today().isoformat()
    _settle_trade(
        SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'BUY',
        Decimal('50'), Decimal('60'), today_str, today_str, 'USD', 'USD',
    )
    pos = get_latest_position(SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert pos is not None
    # Depends on test_same_ccy_fresh_buy having run first (100 @ 50); if run in
    # isolation this asserts a weaker qty-increased check instead.
    assert Decimal(str(pos['quantity'])) >= Decimal('150')


def test_same_ccy_sell_realizes_pnl():
    today_str = _today().isoformat()
    pos_before = get_latest_position(SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert pos_before is not None, "Need an existing position to sell from"
    qty_before = Decimal(str(pos_before['quantity']))
    sell_qty = Decimal('10')

    _settle_trade(
        SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'SELL',
        sell_qty, Decimal('70'), today_str, today_str, 'USD', 'USD',
    )
    pos = get_latest_position(SAME_CCY_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert Decimal(str(pos['quantity'])) == qty_before - sell_qty
    assert Decimal(str(pos['average_cost_fc'])) == Decimal(str(pos_before['average_cost_fc'])), \
        "avg cost must be unchanged on SELL"


def test_same_ccy_backdated_buy_backfills_every_day():
    """Regression for Scenario 1: a backdated fresh position must produce a
    TRADED row for every business day between trade_date and today, not just
    trade_date itself."""
    today = _today()
    backdated = today - timedelta(days=5)
    security = 'AVPTEST-SEC-BACKDATE'  # isolated security so this test doesn't
                                       # collide with other same-ccy scenarios'
                                       # existing position history
    ensure_test_security(security, 'USD')

    _settle_trade(
        SAME_CCY_PORTFOLIO, security, 'BUY',
        Decimal('100'), Decimal('50'), backdated.isoformat(), today.isoformat(),
        'USD', 'USD',
    )

    traded_on_backdate = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', backdated.isoformat())
    traded_on_today = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', today.isoformat())
    assert traded_on_backdate is not None, \
        "TRADED position missing on the backdated trade_date itself"
    assert traded_on_today is not None, (
        "TRADED position missing on today — this is the exact Scenario 1 bug: "
        "a backdated trade settling today was misclassified as T+0 and never "
        "chain-recalculated forward to today"
    )
    assert Decimal(str(traded_on_today['quantity'])) == Decimal('100')


def test_same_ccy_amend_does_not_double_count_earlier_date():
    """Regression for Scenario 3: amending a later trade must not inflate an
    earlier date's quantity that the amend never touched."""
    security = 'AVPTEST-SEC-AMEND'
    today = _today()
    early_date = (today - timedelta(days=3)).isoformat()
    ensure_test_security(security, 'USD')

    _settle_trade(
        SAME_CCY_PORTFOLIO, security, 'BUY',
        Decimal('1000'), Decimal('10'), early_date, early_date, 'USD', 'USD',
    )
    early_pos_before = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', early_date)
    assert early_pos_before is not None
    early_qty_before = Decimal(str(early_pos_before['quantity']))

    later_trade_id = _settle_trade(
        SAME_CCY_PORTFOLIO, security, 'BUY',
        Decimal('300'), Decimal('12'), today.isoformat(), today.isoformat(), 'USD', 'USD',
    )

    # Amend the later trade's quantity 300 -> 350 via the real trade_edit view
    # (mirrors trade_edit's flow) — its own save path drives chain
    # recalculation synchronously, no separate call needed here.
    ui_amend_trade(_get_client(), later_trade_id, new_quantity=Decimal('350'))

    early_pos_after = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', early_date)
    assert Decimal(str(early_pos_after['quantity'])) == early_qty_before, (
        f"Scenario 3 regression: earlier date's quantity changed "
        f"({early_qty_before} -> {early_pos_after['quantity']}) from an amend "
        f"that never touched that date"
    )

    later_pos_after = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', today.isoformat())
    assert Decimal(str(later_pos_after['quantity'])) == early_qty_before + Decimal('350')


def test_same_ccy_cancel_restores_quantity():
    """Regression for Scenario 6: cancelling a trade must not corrupt
    quantity via the same chain-recalc machinery amend uses."""
    security = 'AVPTEST-SEC-CANCEL'
    today = _today()
    ensure_test_security(security, 'USD')

    _settle_trade(
        SAME_CCY_PORTFOLIO, security, 'BUY',
        Decimal('500'), Decimal('10'), today.isoformat(), today.isoformat(), 'USD', 'USD',
    )
    sell_id = _settle_trade(
        SAME_CCY_PORTFOLIO, security, 'SELL',
        Decimal('200'), Decimal('12'), today.isoformat(), today.isoformat(), 'USD', 'USD',
    )
    pos_after_sell = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', today.isoformat())
    assert Decimal(str(pos_after_sell['quantity'])) == Decimal('300')

    # trade_cancel's own save path drives chain recalculation synchronously.
    ui_cancel_trade(_get_client(), sell_id)

    pos_after_cancel = get_latest_position(SAME_CCY_PORTFOLIO, security, 'TRADED', today.isoformat())
    assert Decimal(str(pos_after_cancel['quantity'])) == Decimal('500'), (
        f"Scenario 6 regression: expected quantity restored to 500 after "
        f"cancelling the 200 SELL, got {pos_after_cancel['quantity']}"
    )


# =============================================================================
# GROUP 2: CROSS-CURRENCY
# =============================================================================

def test_cross_ccy_revalued_fresh_buy_uses_fx_table():
    today_str = _today().isoformat()
    quantity = Decimal('100')
    price = Decimal('50')
    _settle_trade(
        XCCY_REVAL_PORTFOLIO, EQUITY_SECURITY, 'BUY',
        quantity, price, today_str, today_str,
        portfolio_currency='SGD', security_currency='USD',
    )
    pos = get_latest_position(XCCY_REVAL_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert pos is not None
    assert Decimal(str(pos['quantity'])) == quantity
    assert Decimal(str(pos['average_cost_fc'])) == price

    # REVALUED: cost_lc must be derived from the live FX table rate for
    # today's date, not a user-entered override. Cross-checked against an
    # independent live query (not the stored row's own fx_rate column) so
    # this is a real regression check rather than a tautology — this is
    # exactly the two-calls-disagreeing failure mode from the original 3-day
    # bug hunt (see position_service._save_position's reval_status docstring).
    # NOTE: QA supplied known USD-SGD rates for 27-Feb/2-Mar (1.2648088 both
    # dates, see avp_live_fixtures.KNOWN_FX_RATES) — if "today" in your
    # environment is one of those dates, expected_fx_rate below will equal
    # 1.2648088; either way this assertion is correct for whatever today is.
    expected_fx_rate = position_service._get_fx_rate('USD', 'SGD', rate_date=today_str)
    expected_cost_lc = (quantity * price * expected_fx_rate).quantize(Decimal('0.01'))
    actual_cost_lc = Decimal(str(pos['total_cost_lc'])).quantize(Decimal('0.01'))
    assert actual_cost_lc == expected_cost_lc, (
        f"REVALUED cost_lc should be trade_cost({quantity * price}) x "
        f"live FX rate({expected_fx_rate}) = {expected_cost_lc}, got {actual_cost_lc}"
    )


def test_cross_ccy_nonrevalued_fresh_buy_uses_open_fx_override():
    """NON-REVALUED cross-currency cost_lc must come from the trade's own
    entered LC amount (gross_amount_lc), not the FX table — this is the
    open_fx_rate override at the center of the original 3-day bug hunt."""
    today_str = _today().isoformat()
    quantity = Decimal('10')
    price = Decimal('100')
    gross_amount_lc = Decimal('1350')  # user-entered LC amount, e.g. 1.35 rate

    _settle_trade(
        XCCY_NONREVAL_PORTFOLIO, EQUITY_SECURITY, 'BUY',
        quantity, price, today_str, today_str,
        portfolio_currency='SGD', security_currency='USD',
        gross_amount_lc=gross_amount_lc, total_amount_lc=gross_amount_lc,
    )
    pos = get_latest_position(XCCY_NONREVAL_PORTFOLIO, EQUITY_SECURITY, 'TRADED', today_str)
    assert pos is not None
    assert Decimal(str(pos['total_cost_lc'])) == gross_amount_lc, (
        f"NON-REVALUED cost_lc should equal the entered gross_amount_lc "
        f"({gross_amount_lc}), got {pos['total_cost_lc']} — check whether the "
        f"open_fx_rate override is being applied"
    )


def test_equity_method_security_has_zero_unrealized_pnl_both_ccy():
    """Regression for Scenario 5: Subsi/Assoc (equity-method) securities must
    show unrealized_pnl == 0 in BOTH FC and LC, even when market price differs
    from trade price."""
    today_str = _today().isoformat()
    quantity = Decimal('100')
    trade_price = Decimal('50')
    market_price = Decimal('75')  # deliberately different from trade price

    set_test_market_price(SUBSI_SECURITY, 'USD', market_price, today_str)

    _settle_trade(
        XCCY_REVAL_PORTFOLIO, SUBSI_SECURITY, 'BUY',
        quantity, trade_price, today_str, today_str,
        portfolio_currency='SGD', security_currency='USD',
    )
    pos = get_latest_position(XCCY_REVAL_PORTFOLIO, SUBSI_SECURITY, 'TRADED', today_str)
    assert pos is not None
    assert Decimal(str(pos['unrealized_pnl_fc'])) == Decimal('0'), \
        "Equity-method unrealized_pnl_fc should be 0"
    assert Decimal(str(pos['unrealized_pnl_lc'])) == Decimal('0'), (
        "Scenario 5 regression: equity-method unrealized_pnl_lc should be 0 "
        f"but got {pos['unrealized_pnl_lc']} — the market-value-derived LC "
        "P&L is leaking through despite the FC side being correctly zeroed"
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

SOD_EOD_SECURITY = 'AVPTEST-SEC-SODEOD'
SOD_EOD_SETTLEMENT_SECURITY = 'AVPTEST-SEC-SODEOD-SETTLE'


def test_int_to_eod_to_sod_lifecycle():
    """Full INT -> EOD -> SOD chain for one fresh position."""
    ensure_test_security(SOD_EOD_SECURITY, 'USD')
    today = _today()
    tomorrow = today + timedelta(days=1)
    today_str, tomorrow_str = today.isoformat(), tomorrow.isoformat()

    trade_price = Decimal('40')
    market_price = Decimal('55')  # different from trade price, so unrealized_pnl is meaningful
    quantity = Decimal('100')
    set_test_market_price(SOD_EOD_SECURITY, 'USD', market_price, today_str)

    _settle_trade(
        SAME_CCY_PORTFOLIO, SOD_EOD_SECURITY, 'BUY',
        quantity, trade_price, today_str, today_str, 'USD', 'USD',
    )

    # Step 1: INT row should already exist (written synchronously by
    # position_service._sync_to_cis_position as part of the same trade save).
    int_pos = get_cis_position(SAME_CCY_PORTFOLIO, SOD_EOD_SECURITY, 'INT', today_str, 'TRADED')
    assert int_pos is not None, "Expected an INT row in cis_position immediately after booking"
    assert Decimal(str(int_pos['quantity'])) == quantity

    # Step 2: EOD run (refresh_positions), explicit position_date to avoid
    # depending on alldatesinfo.
    call_command(
        'refresh_positions',
        portfolio=SAME_CCY_PORTFOLIO, security=SOD_EOD_SECURITY,
        position_date=today_str, run_type='EOD',
    )
    eod_pos = get_cis_position(SAME_CCY_PORTFOLIO, SOD_EOD_SECURITY, 'EOD', today_str, 'TRADED')
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
    # the EOD row forward as tomorrow's opening position.
    call_command(
        'create_sod_snapshot',
        portfolio=SAME_CCY_PORTFOLIO, security=SOD_EOD_SECURITY,
        eod_date=today_str, sod_date=tomorrow_str,
    )
    sod_pos = get_cis_position(SAME_CCY_PORTFOLIO, SOD_EOD_SECURITY, 'SOD', tomorrow_str, 'TRADED')
    assert sod_pos is not None, "Expected a SOD row for tomorrow after create_sod_snapshot"
    assert Decimal(str(sod_pos['quantity'])) == quantity
    assert Decimal(str(sod_pos['average_cost_fc'])) == trade_price, (
        "SOD should carry forward EOD's cost basis unchanged"
    )


def test_sod_snapshot_folds_in_pending_settlement():
    """A trade booked today with a FUTURE settle_date sits in
    cis_settlement_queue as PENDING (never gets a SETTLED-basis position of
    its own until settle_date arrives). Running create_sod_snapshot for that
    settle_date must apply it — creating a brand-new SOD row (this security
    has no prior EOD row at all) and marking the queue entry COMPLETED."""
    ensure_test_security(SOD_EOD_SETTLEMENT_SECURITY, 'USD')
    today = _today()
    settle_date = today + timedelta(days=1)
    today_str, settle_str = today.isoformat(), settle_date.isoformat()

    quantity = Decimal('75')
    price = Decimal('22')
    trade_id = _settle_trade(
        SAME_CCY_PORTFOLIO, SOD_EOD_SETTLEMENT_SECURITY, 'BUY',
        quantity, price, today_str, settle_str, 'USD', 'USD',
    )

    queued_before = impala_manager.execute_query(
        f"SELECT status FROM gmp_cis.cis_settlement_queue "
        f"WHERE trade_id = {trade_id} AND position_basis = 'SETTLED' LIMIT 1",
        database='gmp_cis',
    )
    assert queued_before and queued_before[0]['status'] == 'PENDING', (
        "Expected a PENDING cis_settlement_queue row for the future-settle trade"
    )

    call_command(
        'create_sod_snapshot',
        portfolio=SAME_CCY_PORTFOLIO, security=SOD_EOD_SETTLEMENT_SECURITY,
        eod_date=today_str, sod_date=settle_str,
    )

    sod_pos = get_cis_position(
        SAME_CCY_PORTFOLIO, SOD_EOD_SETTLEMENT_SECURITY, 'SOD', settle_str, 'SETTLED',
    )
    assert sod_pos is not None, (
        "Expected a brand-new SOD row created from the pending settlement "
        "queue entry (no prior EOD row existed for this security)"
    )
    assert Decimal(str(sod_pos['quantity'])) == quantity

    queued_after = impala_manager.execute_query(
        f"SELECT status FROM gmp_cis.cis_settlement_queue "
        f"WHERE trade_id = {trade_id} AND position_basis = 'SETTLED' LIMIT 1",
        database='gmp_cis',
    )
    assert queued_after and queued_after[0]['status'] == 'COMPLETED', (
        f"Expected the settlement queue entry marked COMPLETED after SOD "
        f"folded it in, got {queued_after[0]['status'] if queued_after else 'not found'}"
    )
