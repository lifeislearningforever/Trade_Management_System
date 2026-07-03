"""
Comprehensive AVP (Average Price Position) Scenario Tests
=========================================================

End-to-end scenario coverage for the dual-basis position engine across the
three trade lifecycle operations: CREATE, AMEND, CANCEL. Each scenario drives
the real service code (`position_service`, `settlement_service`,
`trade_event_queue_service`) with `impala_manager` mocked at the module level
so no database is required and the tests run fast.

Mocking strategy
----------------
- `impala_manager.execute_query` / `impala_manager.execute_write` are patched so
  the services never touch Kudu/Impala.
- `_save_position` / `_mark_old_versions_not_latest` / `_sync_to_cis_position`
  are stubbed so we assert on the *computed* position dict returned by
  `_process_buy` / `_process_sell` (the AVP math) rather than on SQL.
- `_get_market_price` returns None (so the code falls back to the trade price
  and unrealized P&L is neutral), `_get_fx_rate` returns 1.0 (single currency).
- `system_date_service.get_system_date` is pinned to a fixed "today" so the
  future-date guard in `_derive_position_type` is deterministic. Backdated
  scenarios choose dates strictly before this pinned today.

Position identity
-----------------
`position_id` = deterministic hash of
(portfolio | security | basis | position_date | 'CIS'). Every scenario recomputes
the expected id via the real `position_id` helper so assertions stay in lockstep
with the production formula.

AVP formulas under test
-----------------------
- BUY : new_avg = (old_qty*old_avg + qty*price + charges) / (old_qty + qty)
- SELL: avg unchanged; realized_pnl = (sell_price - avg) * qty
"""

from decimal import Decimal
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest

from trade.services.position_service import PositionService
from trade.services.settlement_service import SettlementService
from trade.services.trade_event_queue_service import TradeEventQueueService
from trade.services.position_id_service import position_id as calc_position_id


# =============================================================================
# Fixed reference dates (pinned "today" so future-date guard is deterministic)
# =============================================================================

TODAY = date(2026, 7, 3)
TODAY_STR = TODAY.isoformat()
YESTERDAY_STR = (TODAY - timedelta(days=1)).isoformat()
TEN_DAYS_AGO_STR = (TODAY - timedelta(days=10)).isoformat()

PORTFOLIO = 'FUND-001'
SECURITY = 'AAPL'


# =============================================================================
# Helpers
# =============================================================================

def _expected_position_id(position_date: str, basis: str = 'TRADED') -> int:
    """Compute the deterministic position_id the service will produce."""
    return calc_position_id(PORTFOLIO, SECURITY, basis, position_date, 'CIS')


def _make_position_service():
    """
    Build a PositionService with persistence + market/fx side-effects stubbed.

    Returns (service, save_mock). `save_mock` captures every position_data dict
    passed to `_save_position`, so tests can inspect the full write history when
    a single call triggers multiple saves (e.g. chain recalc).
    """
    service = PositionService()

    save_mock = MagicMock(return_value=True)
    service._save_position = save_mock
    service._get_market_price = MagicMock(side_effect=lambda sec: None)  # fall back to trade price
    service._get_fx_rate = MagicMock(return_value=Decimal('1'))
    service._is_equity_method_security = MagicMock(return_value=False)
    return service, save_mock


def _existing_position(quantity, avg_cost, position_date, basis='TRADED',
                       realized_pnl=0.0):
    """
    Build a prior-position dict shaped like a `cis_trade_position` row, as
    returned by `_get_position_as_of_date`. Only the fields the AVP math reads
    are populated.
    """
    return {
        'position_id': _expected_position_id(position_date, basis),
        'quantity': quantity,
        'average_cost_fc': avg_cost,
        'total_cost_fc': float(Decimal(str(quantity)) * Decimal(str(avg_cost))),
        'average_cost_lc': avg_cost,
        'total_cost_lc': float(Decimal(str(quantity)) * Decimal(str(avg_cost))),
        'realized_pnl_fc': realized_pnl,
        'realized_pnl_lc': realized_pnl,
        'position_date': position_date,
        'position_basis': basis,
        'position_type': 'INT',
    }


def _patch_today():
    """Patch system_date_service.get_system_date to a fixed 'today'."""
    return patch(
        'trade.services.position_service.system_date_service.get_system_date',
        return_value=TODAY,
    )


# =============================================================================
# SCENARIO GROUP 1: NEW TRADE (CREATE)
# =============================================================================

def test_s01_buy_same_date_fresh():
    """
    S01 -- BUY same-date, first trade, fresh position.

    BUY 100 @ 80.00, charges 0, trade_date = settle_date = today, no prior position.
    Expected: qty=100, avg_cost_fc=80.0, TRADED position keyed on today.
    """
    service, _ = _make_position_service()

    with _patch_today():
        with patch.object(service, '_get_position_as_of_date', return_value=None):
            success, msg, pos = service.calculate_position(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                trade_type='BUY', quantity=Decimal('100'), price=Decimal('80.00'),
                charges=Decimal('0'), position_date=TODAY_STR, trade_id=1001,
                updated_by='tester', position_basis='TRADED',
            )

    assert success is True
    assert pos['quantity'] == 100.0
    assert pos['average_cost_fc'] == 80.0
    assert pos['total_cost_fc'] == 8000.0
    assert pos['status'] == 'OPEN'
    assert pos['is_active'] is True
    assert pos['position_basis'] == 'TRADED'
    assert pos['position_id'] == _expected_position_id(TODAY_STR, 'TRADED')


def test_s02_buy_same_date_accumulates():
    """
    S02 -- Second BUY same portfolio/security/date accumulates into one position.

    Prior: 100 @ 80.00 (today). New BUY 50 @ 90.00, charges 0.
    old_total = 100*80 = 8000; trade_cost = 50*90 = 4500
    new_qty = 150; new_avg = 12500/150 = 83.33333333
    position_id identical to prior (same natural key: same date + basis).
    """
    service, _ = _make_position_service()
    prior = _existing_position(100, 80.0, TODAY_STR, 'TRADED')

    with _patch_today():
        with patch.object(service, '_get_position_as_of_date', return_value=prior):
            success, msg, pos = service.calculate_position(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                trade_type='BUY', quantity=Decimal('50'), price=Decimal('90.00'),
                charges=Decimal('0'), position_date=TODAY_STR, trade_id=1002,
                updated_by='tester', position_basis='TRADED',
            )

    assert success is True
    assert pos['quantity'] == 150.0
    assert round(pos['average_cost_fc'], 8) == round(83.33333333, 8)
    assert pos['total_cost_fc'] == 12500.0
    assert pos['position_id'] == _expected_position_id(TODAY_STR, 'TRADED')
    assert pos['position_id'] == prior['position_id']


def test_s03_sell_same_date_after_buy():
    """
    S03 -- SELL after BUY on the same date; AVP unchanged, realized P&L booked.

    Prior: 150 @ 83.33333333 (today). SELL 30 @ 100.00.
    realized_pnl = (100 - 83.33333333) * 30 ~ 500.0
    new_qty = 120; avg_cost unchanged at 83.33333333.
    """
    service, _ = _make_position_service()
    prior = _existing_position(150, 83.33333333, TODAY_STR, 'TRADED')

    with _patch_today():
        with patch.object(service, '_get_position_as_of_date', return_value=prior):
            success, msg, pos = service.calculate_position(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                trade_type='SELL', quantity=Decimal('30'), price=Decimal('100.00'),
                charges=Decimal('0'), position_date=TODAY_STR, trade_id=1003,
                updated_by='tester', position_basis='TRADED',
            )

    assert success is True
    assert pos['quantity'] == 120.0
    assert round(pos['average_cost_fc'], 8) == round(83.33333333, 8)  # unchanged
    assert abs(pos['realized_pnl_fc'] - 500.0) < 1e-4
    assert pos['status'] == 'OPEN'
    assert pos['position_id'] == _expected_position_id(TODAY_STR, 'TRADED')


def test_s04_buy_one_day_backdated():
    """
    S04 -- BUY 1-day backdated (yesterday) with an existing TODAY trade.

    Trades in cis_trade after insertion:
      - t=1004 BUY 200 @ 25.00 on YESTERDAY  (newly added backdated trade)
      - t=1005 BUY 100 @ 80.00 on TODAY       (pre-existing later trade)

    Chain recalc from YESTERDAY replays both trades in date order.

    Expected TRADED chain:
      * YESTERDAY: qty=200, avg=25.00, total=5000
      * TODAY:     qty=300, avg=(200*25 + 100*80)/300 = 10000/300 + 8000/300
                         = 18000/300 = 60.00
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    chain_trades = [
        {'trade_id': 1004, 'trade_type': 'BUY', 'quantity': 200, 'price': 25.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
        {'trade_id': 1005, 'trade_type': 'BUY', 'quantity': 100, 'price': 80.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [chain_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=YESTERDAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    assert result['recalculated'] == 4  # 2 trades x 2 bases

    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert len(traded) == 2

    yesterday_pos = traded[0]
    assert yesterday_pos['position_date'] == YESTERDAY_STR
    assert yesterday_pos['quantity'] == 200.0
    assert yesterday_pos['average_cost_fc'] == 25.0
    assert yesterday_pos['total_cost_fc'] == 5000.0
    assert yesterday_pos['position_id'] == _expected_position_id(YESTERDAY_STR, 'TRADED')

    today_pos = traded[1]
    assert today_pos['position_date'] == TODAY_STR
    assert today_pos['quantity'] == 300.0
    # new_avg = (200*25 + 100*80) / 300 = (5000+8000)/300 = 13000/300 = 43.33...
    assert round(today_pos['average_cost_fc'], 8) == round(43.33333333, 8)
    assert today_pos['total_cost_fc'] == 13000.0
    assert today_pos['position_id'] == _expected_position_id(TODAY_STR, 'TRADED')


def test_s05_buy_multi_day_backdated():
    """
    S05 -- BUY 10 days backdated with an existing TODAY trade.

    Trades in cis_trade after insertion:
      - t=1006 BUY 100 @ 40.00, charges=20 on TEN_DAYS_AGO  (new backdated trade)
      - t=1007 BUY 100 @ 80.00 on TODAY                       (pre-existing later trade)

    Chain recalc from TEN_DAYS_AGO replays both trades.

    Expected TRADED chain:
      * TEN_DAYS_AGO: qty=100, avg=40.20 (cost=4000+20=4020 / 100)
      * TODAY:        qty=200, avg=(4020 + 100*80) / 200 = 12020/200 = 60.10
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    chain_trades = [
        {'trade_id': 1006, 'trade_type': 'BUY', 'quantity': 100, 'price': 40.0,
         'charges': 20, 'trade_date': TEN_DAYS_AGO_STR, 'settle_date': TEN_DAYS_AGO_STR},
        {'trade_id': 1007, 'trade_type': 'BUY', 'quantity': 100, 'price': 80.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [chain_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TEN_DAYS_AGO_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    assert result['recalculated'] == 4  # 2 trades x 2 bases

    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert len(traded) == 2

    old_pos = traded[0]
    assert old_pos['position_date'] == TEN_DAYS_AGO_STR
    assert old_pos['quantity'] == 100.0
    assert old_pos['average_cost_fc'] == 40.2        # (100*40 + 20) / 100
    assert old_pos['total_cost_fc'] == 4020.0
    assert old_pos['position_id'] == _expected_position_id(TEN_DAYS_AGO_STR, 'TRADED')

    today_pos = traded[1]
    assert today_pos['position_date'] == TODAY_STR
    assert today_pos['quantity'] == 200.0
    # new_avg = (4020 + 100*80) / 200 = 12020/200 = 60.10
    assert today_pos['average_cost_fc'] == 60.1
    assert today_pos['total_cost_fc'] == 12020.0
    assert today_pos['position_id'] == _expected_position_id(TODAY_STR, 'TRADED')


def test_s06_buy_backdated_with_existing_later_position_chain():
    """
    S06 -- Backdated BUY with an existing later position: chain recalc must
    replay the later trade on top of the inserted backdated trade.

    Trades in cis_trade (as read by _recalculate_position_chain):
      - t=2010 BUY 100 @ 50 on 10-days-ago  (the newly inserted backdated trade)
      - t=2011 BUY 100 @ 70 on yesterday    (pre-existing later trade)

    Expected chain (TRADED basis, in-memory accumulator seeded empty):
      * 10-days-ago:  qty=100, avg=50.0
      * yesterday:    qty=200, avg=(100*50 + 100*70)/200 = 60.0
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    chain_trades = [
        {'trade_id': 2010, 'trade_type': 'BUY', 'quantity': 100, 'price': 50.0,
         'charges': 0, 'trade_date': TEN_DAYS_AGO_STR, 'settle_date': TEN_DAYS_AGO_STR},
        {'trade_id': 2011, 'trade_type': 'BUY', 'quantity': 100, 'price': 70.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
    ]
    query_results = [chain_trades, [], []]

    def query_side_effect(*args, **kwargs):
        return query_results.pop(0) if query_results else []

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=query_side_effect):
            with patch.object(service, '_get_position_as_of_date', return_value=None):
                result = settlement._recalculate_position_chain(
                    portfolio_id=PORTFOLIO, security_id=SECURITY,
                    from_date=TEN_DAYS_AGO_STR, updated_by='tester',
                )

    assert result['recalculated'] == 4  # 2 trades x 2 bases
    assert result['errors'] == 0

    traded_saves = [
        c.args[0] for c in save_mock.call_args_list
        if c.args[0]['position_basis'] == 'TRADED'
    ]
    assert len(traded_saves) == 2
    assert traded_saves[0]['position_date'] == TEN_DAYS_AGO_STR
    assert traded_saves[0]['quantity'] == 100.0
    assert traded_saves[0]['average_cost_fc'] == 50.0
    assert traded_saves[1]['position_date'] == YESTERDAY_STR
    assert traded_saves[1]['quantity'] == 200.0
    assert traded_saves[1]['average_cost_fc'] == 60.0


# =============================================================================
# SCENARIO GROUP 2: AMEND TRADE
# =============================================================================

def test_s07_amend_qty_same_date():
    """
    S07 -- Amend quantity on a same-date (today) trade: 100 -> 101.

    Amend replays the chain from the trade date. The amended cis_trade row now
    reads qty=101. Single trade, fresh accumulator.
    Expected: qty=101, avg=80.0 (price unchanged).
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    amended_trade = [
        {'trade_id': 1001, 'trade_type': 'BUY', 'quantity': 101, 'price': 80.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [amended_trade, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TODAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert len(traded) == 1
    assert traded[0]['quantity'] == 101.0
    assert traded[0]['average_cost_fc'] == 80.0
    assert traded[0]['position_date'] == TODAY_STR


def test_s08_amend_price_same_date():
    """
    S08 -- Amend price on a same-date trade: 80 -> 85 (qty stays 100).

    Replayed chain reads the amended price. Expected: qty=100, avg=85.0.
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    amended_trade = [
        {'trade_id': 1001, 'trade_type': 'BUY', 'quantity': 100, 'price': 85.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [amended_trade, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TODAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert traded[0]['quantity'] == 100.0
    assert traded[0]['average_cost_fc'] == 85.0


def test_s09_amend_qty_one_day_backdated():
    """
    S09 -- Amend qty on a 1-day backdated trade: chain recalc from that date.

    Amended cis_trade: BUY 60 @ 50 on yesterday.
    Fresh accumulator. Expected: qty=60, avg=50.0 on the yesterday-keyed position.
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    amended_trade = [
        {'trade_id': 3001, 'trade_type': 'BUY', 'quantity': 60, 'price': 50.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
    ]
    query_results = [amended_trade, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=YESTERDAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert traded[0]['position_date'] == YESTERDAY_STR
    assert traded[0]['quantity'] == 60.0
    assert traded[0]['average_cost_fc'] == 50.0
    assert traded[0]['position_id'] == _expected_position_id(YESTERDAY_STR, 'TRADED')


def test_s10_amend_qty_multi_day_backdated_updates_later():
    """
    S10 -- Amend qty on a multi-day backdated trade; all later positions update.

    cis_trade after amend:
      - t=4001 BUY 200 @ 50 on 10-days-ago   (amended qty: 100 -> 200)
      - t=4002 BUY 100 @ 80 on yesterday      (untouched later trade)

    Expected TRADED chain:
      * 10-days-ago: qty=200, avg=50.0
      * yesterday:   qty=300, avg=(200*50 + 100*80)/300 = 60.0
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    chain_trades = [
        {'trade_id': 4001, 'trade_type': 'BUY', 'quantity': 200, 'price': 50.0,
         'charges': 0, 'trade_date': TEN_DAYS_AGO_STR, 'settle_date': TEN_DAYS_AGO_STR},
        {'trade_id': 4002, 'trade_type': 'BUY', 'quantity': 100, 'price': 80.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
    ]
    query_results = [chain_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TEN_DAYS_AGO_STR, updated_by='tester',
            )

    assert result['recalculated'] == 4
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert traded[0]['quantity'] == 200.0
    assert traded[0]['average_cost_fc'] == 50.0
    assert traded[1]['quantity'] == 300.0
    assert traded[1]['average_cost_fc'] == 60.0


def test_s11_amend_sell_qty_backdated():
    """
    S11 -- Amend a backdated SELL's qty; chain recalc from that date.

    cis_trade after amend:
      - t=5001 BUY 100 @ 50 on 10-days-ago
      - t=5002 SELL 40 @ 90 on yesterday  (SELL qty amended 30 -> 40)

    Expected TRADED chain:
      * 10-days-ago: qty=100, avg=50.0
      * yesterday:   qty=60,  avg=50.0 (unchanged), realized=(90-50)*40=1600
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    chain_trades = [
        {'trade_id': 5001, 'trade_type': 'BUY', 'quantity': 100, 'price': 50.0,
         'charges': 0, 'trade_date': TEN_DAYS_AGO_STR, 'settle_date': TEN_DAYS_AGO_STR},
        {'trade_id': 5002, 'trade_type': 'SELL', 'quantity': 40, 'price': 90.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
    ]
    query_results = [chain_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TEN_DAYS_AGO_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert traded[0]['quantity'] == 100.0
    assert traded[0]['average_cost_fc'] == 50.0
    assert traded[1]['quantity'] == 60.0
    assert traded[1]['average_cost_fc'] == 50.0
    assert abs(traded[1]['realized_pnl_fc'] - 1600.0) < 1e-6


# =============================================================================
# SCENARIO GROUP 3: CANCEL TRADE
# =============================================================================

def test_s12_cancel_same_date_buy_only_trade():
    """
    S12 -- Cancel a same-date BUY that is the only trade: position goes to zero.

    After cancel, the cancelled trade is is_deleted=true so the chain query
    returns NO trades. _recalculate_position_chain replays nothing -- no save
    occurs, and the position is left with no live version (effectively zeroed).
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    query_results = [[], [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TODAY_STR, updated_by='tester',
            )

    assert result['recalculated'] == 0
    assert result['errors'] == 0
    save_mock.assert_not_called()


def test_s13_cancel_same_date_buy_multiple_trades():
    """
    S13 -- Cancel one same-date BUY when multiple trades share the date;
    remaining trades still produce the correct cumulative position.

    cis_trade after cancel (cancelled t=6002 excluded):
      - t=6001 BUY 100 @ 80 on today
      - t=6003 BUY 50  @ 90 on today
    Expected TRADED position (today): qty=150, avg=(100*80 + 50*90)/150 = 83.33333333
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    surviving_trades = [
        {'trade_id': 6001, 'trade_type': 'BUY', 'quantity': 100, 'price': 80.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
        {'trade_id': 6003, 'trade_type': 'BUY', 'quantity': 50, 'price': 90.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [surviving_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TODAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    final = traded[-1]
    assert final['position_date'] == TODAY_STR
    assert final['quantity'] == 150.0
    assert round(final['average_cost_fc'], 8) == round(83.33333333, 8)


def test_s14_cancel_one_day_backdated_buy():
    """
    S14 -- Cancel a 1-day backdated BUY; chain recalc from that date.

    cis_trade after cancel (backdated BUY on yesterday removed) leaves:
      - t=7001 BUY 100 @ 80 on today  (a later same-security trade)
    Chain recalc from yesterday replays only the surviving today trade.
    Expected: today position qty=100, avg=80.0; nothing on yesterday.
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    surviving_trades = [
        {'trade_id': 7001, 'trade_type': 'BUY', 'quantity': 100, 'price': 80.0,
         'charges': 0, 'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    ]
    query_results = [surviving_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=YESTERDAY_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert all(t['position_date'] != YESTERDAY_STR for t in traded)
    today_pos = [t for t in traded if t['position_date'] == TODAY_STR]
    assert len(today_pos) == 1
    assert today_pos[0]['quantity'] == 100.0
    assert today_pos[0]['average_cost_fc'] == 80.0


def test_s15_cancel_multi_day_backdated_buy_updates_later():
    """
    S15 -- Cancel a multi-day backdated BUY; all later positions update.

    After cancelling the backdated one, cis_trade leaves only:
      - t=8002 BUY 100 @ 70 on yesterday
    Chain recalc from 10-days-ago replays only the surviving later trade.
    Expected: yesterday position qty=100, avg=70.0 (no longer 200 @ blended cost).
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    surviving_trades = [
        {'trade_id': 8002, 'trade_type': 'BUY', 'quantity': 100, 'price': 70.0,
         'charges': 0, 'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
    ]
    query_results = [surviving_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TEN_DAYS_AGO_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert all(t['position_date'] != TEN_DAYS_AGO_STR for t in traded)
    later = [t for t in traded if t['position_date'] == YESTERDAY_STR]
    assert len(later) == 1
    assert later[0]['quantity'] == 100.0        # was 200 before cancel
    assert later[0]['average_cost_fc'] == 70.0  # blended cost gone


def test_s16_cancel_backdated_sell_restores_position():
    """
    S16 -- Cancel a backdated SELL; the position quantity is restored.

    Original chain: BUY 100 @ 50 (10-days-ago), then SELL 40 @ 90 (yesterday).
    After cancelling the SELL, cis_trade leaves only the BUY. Chain recalc from
    yesterday (the cancelled SELL's date) is seeded from the pre-SELL BUY
    position (100 @ 50). With the SELL gone and no other trade on/after
    yesterday, no new save is produced -- the seeded 100-share BUY position
    remains the live position (restored quantity).
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    seed_traded = [{
        'position_id': _expected_position_id(TEN_DAYS_AGO_STR, 'TRADED'),
        'quantity': 100, 'average_cost_fc': 50.0, 'average_cost_lc': 50.0,
        'total_cost_fc': 5000.0, 'total_cost_lc': 5000.0,
        'realized_pnl_fc': 0, 'realized_pnl_lc': 0,
        'dividend_fc': 0, 'dividend_lc': 0, 'pipeline_fc': 0, 'pipeline_lc': 0,
        'provision_fc': 0, 'provision_lc': 0,
    }]
    query_results = [[], seed_traded, []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=YESTERDAY_STR, updated_by='tester',
            )

    assert result['recalculated'] == 0
    assert result['errors'] == 0
    save_mock.assert_not_called()


def test_s16b_cancel_backdated_sell_via_full_chain_replay():
    """
    S16 (variant) -- Cancel a backdated SELL, replaying the WHOLE chain from the
    original BUY date to prove the restored quantity end-to-end.

    cis_trade after cancel (SELL removed) leaves only:
      - t=9001 BUY 100 @ 50 on 10-days-ago
    Recalc from 10-days-ago (fresh accumulator) replays just the BUY.
    Expected TRADED position: qty=100, avg=50.0 (SELL's -40 fully reversed).
    """
    service, save_mock = _make_position_service()
    settlement = SettlementService(position_svc=service)

    surviving_trades = [
        {'trade_id': 9001, 'trade_type': 'BUY', 'quantity': 100, 'price': 50.0,
         'charges': 0, 'trade_date': TEN_DAYS_AGO_STR, 'settle_date': TEN_DAYS_AGO_STR},
    ]
    query_results = [surviving_trades, [], []]

    with _patch_today():
        with patch('trade.services.settlement_service.impala_manager.execute_query',
                   side_effect=lambda *a, **k: query_results.pop(0) if query_results else []):
            result = settlement._recalculate_position_chain(
                portfolio_id=PORTFOLIO, security_id=SECURITY,
                from_date=TEN_DAYS_AGO_STR, updated_by='tester',
            )

    assert result['errors'] == 0
    traded = [c.args[0] for c in save_mock.call_args_list
              if c.args[0]['position_basis'] == 'TRADED']
    assert len(traded) == 1
    assert traded[0]['quantity'] == 100.0
    assert traded[0]['average_cost_fc'] == 50.0
    assert traded[0]['realized_pnl_fc'] == 0.0


# =============================================================================
# Cross-cutting: event-queue entrypoints delegate to chain recalc
# =============================================================================

def test_position_modify_event_triggers_chain_recalc_from_min_date():
    """
    POSITION_MODIFY worker path delegates to _recalculate_position_chain using
    from_date = min(old/new trade & settle dates).
    """
    svc = TradeEventQueueService()
    event = {'trade_id': 1001, 'created_by': 'tester'}
    event_data = {
        'old_trade': {'portfolio_short_name': PORTFOLIO, 'security_label': SECURITY,
                      'trade_date': YESTERDAY_STR, 'settle_date': YESTERDAY_STR},
        'new_trade': {'portfolio_short_name': PORTFOLIO, 'security_label': SECURITY,
                      'trade_date': TODAY_STR, 'settle_date': TODAY_STR},
    }

    with patch('trade.services.settlement_service.settlement_service._recalculate_position_chain') as mock_recalc:
        mock_recalc.return_value = {'recalculated': 0, 'errors': 0}
        ok = svc._process_position_modify_event(event, event_data, trade={'trade_id': 1001})

    assert ok is True
    mock_recalc.assert_called_once()
    assert mock_recalc.call_args.kwargs['from_date'] == YESTERDAY_STR


def test_position_cancel_event_triggers_chain_recalc_from_trade_date():
    """
    POSITION_CANCEL worker path delegates to _recalculate_position_chain using
    from_date = min(trade_date, settle_date).
    """
    svc = TradeEventQueueService()
    event = {'trade_id': 2002, 'created_by': 'tester'}
    event_data = {
        'portfolio_short_name': PORTFOLIO, 'security_label': SECURITY,
        'trade_date': TEN_DAYS_AGO_STR, 'settle_date': YESTERDAY_STR,
    }

    with patch('trade.services.settlement_service.settlement_service._recalculate_position_chain') as mock_recalc:
        mock_recalc.return_value = {'recalculated': 0, 'errors': 0}
        ok = svc._process_position_cancel_event(event, event_data, trade={'trade_id': 2002})

    assert ok is True
    mock_recalc.assert_called_once()
    assert mock_recalc.call_args.kwargs['from_date'] == TEN_DAYS_AGO_STR
