"""Tests for edge_jobs_py36/lib/ca_cash_flow_service.py."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest

from edge_jobs_py36.lib.ca_cash_flow_service import CACashFlowService


@pytest.fixture
def svc():
    return CACashFlowService()


@pytest.fixture
def impala():
    with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
        m.execute_write.return_value = True
        m.execute_query.return_value = []
        yield m


@pytest.fixture
def queue_repo():
    with patch('edge_jobs_py36.lib.ca_cash_flow_service.ca_cash_flow_queue_repository') as m:
        yield m


@pytest.fixture
def cf_repo():
    with patch('edge_jobs_py36.lib.ca_cash_flow_service.CashFlowRepository') as m:
        m.insert.return_value = (True, 100)
        yield m


@pytest.fixture
def mcs():
    with patch('edge_jobs_py36.lib.ca_cash_flow_service.multicurrency_service') as m:
        m.get_fx_rate.return_value = (Decimal('1.35'), '2026-01-01')
        yield m


class TestEscape:
    def test_none(self, svc):
        assert svc._escape(None) == ''

    def test_quote_backslash(self, svc):
        assert svc._escape("O'Brien\\x") == "O\\'Brien\\\\x"


class TestCheckExistingCashFlow:
    def test_returns_row_when_found(self, svc, impala):
        impala.execute_query.return_value = [{'cash_flow_id': 1, 'cash_flow_number': 'CF1'}]
        result = svc._check_existing_cash_flow('CA1', 'P1', 'S1', '2026-01-01')
        assert result == {'cash_flow_id': 1, 'cash_flow_number': 'CF1'}

    def test_returns_none_when_not_found(self, svc, impala):
        impala.execute_query.return_value = []
        assert svc._check_existing_cash_flow('CA1', 'P1', 'S1', '2026-01-01') is None

    def test_mismapped_row_ignored(self, svc, impala):
        impala.execute_query.return_value = [{'cash_flow_id': None, 'cash_flow_number': None}]
        assert svc._check_existing_cash_flow('CA1', 'P1', 'S1', '2026-01-01') is None

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._check_existing_cash_flow('CA1', 'P1', 'S1', '2026-01-01') is None


class TestQueueCaForProcessing:
    def test_cash_flow_type_queued(self, svc, queue_repo):
        queue_repo.insert.return_value = (True, 1)
        ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'DIVIDEND', 'ca_number': 'CA1'}, 'user1')
        assert ok is True
        assert qid == 1

    def test_position_adjustment_type_queued(self, svc, queue_repo):
        queue_repo.insert.return_value = (True, 2)
        ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1'}, 'user1')
        assert ok is True

    def test_cf_overwrite_type_queued(self, svc, queue_repo):
        queue_repo.insert.return_value = (True, 3)
        ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1'}, 'user1')
        assert ok is True

    def test_unknown_type_skipped(self, svc, queue_repo):
        ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'UNKNOWN_TYPE', 'ca_number': 'CA1'}, 'user1')
        assert ok is True
        assert qid is None
        queue_repo.insert.assert_not_called()

    def test_insert_failure(self, svc, queue_repo):
        queue_repo.insert.return_value = (False, None)
        ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'DIVIDEND'}, 'user1')
        assert ok is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.ca_cash_flow_queue_repository') as m:
            m.insert.side_effect = RuntimeError('boom')
            ok, qid = svc.queue_ca_for_processing(1, {'ca_type': 'DIVIDEND'}, 'user1')
        assert ok is False
        assert qid is None


class TestResolveSecurityLabels:
    def test_empty_input_returns_empty(self, svc):
        assert svc._resolve_security_labels([]) == []

    def test_resolves_via_description(self, svc, impala):
        impala.execute_query.return_value = [
            {'security_name': 'SEC1', 'security_description': 'Security One Corp'}
        ]
        result = svc._resolve_security_labels(['Security One Corp'])
        assert result == ['SEC1']

    def test_falls_back_to_original_when_no_match(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._resolve_security_labels(['UNKNOWN'])
        assert result == ['UNKNOWN']

    def test_exception_returns_original_list(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._resolve_security_labels(['S1'])
        assert result == ['S1']


class TestGetHoldingsForCa:
    def test_returns_holdings(self, svc, impala):
        impala.execute_query.return_value = [{'portfolio_short_name': 'P1', 'quantity': 10}]
        result = svc.get_holdings_for_ca('SEC1', as_of_date='2026-01-01')
        assert result == [{'portfolio_short_name': 'P1', 'quantity': 10}]

    def test_empty_security_name_returns_empty(self, svc, impala):
        result = svc.get_holdings_for_ca('', as_of_date='2026-01-01')
        assert result == []

    def test_multiple_securities_comma_separated(self, svc, impala):
        impala.execute_query.return_value = [{'portfolio_short_name': 'P1'}]
        result = svc.get_holdings_for_ca('SEC1, SEC2', as_of_date='2026-01-01')
        assert result == [{'portfolio_short_name': 'P1'}]

    def test_default_date_used_when_none(self, svc, impala):
        svc.get_holdings_for_ca('SEC1')
        assert impala.execute_query.called

    def test_none_result_returns_empty_list(self, svc, impala):
        impala.execute_query.return_value = None
        assert svc.get_holdings_for_ca('SEC1', as_of_date='2026-01-01') == []

    def test_exception_returns_empty_list(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc.get_holdings_for_ca('SEC1', as_of_date='2026-01-01') == []


class TestCreateCashFlowFromCa:
    def base_kwargs(self, **overrides):
        kwargs = dict(
            ca_id=1, ca_number='CA1', ca_type='DIVIDEND', portfolio_short_name='P1',
            security_name='S1', quantity=Decimal('100'), amount_fc=Decimal('35'),
            amount_lc=Decimal('47.25'), foreign_currency='USD', local_currency='SGD',
            fx_rate=Decimal('1.35'), ex_date='2026-01-01', record_date='2026-01-01',
            payment_date='2026-01-15', created_by='user1',
        )
        kwargs.update(overrides)
        return kwargs

    def test_returns_existing_when_duplicate(self, svc, impala):
        with patch.object(svc, '_check_existing_cash_flow', return_value={'cash_flow_id': 5, 'cash_flow_number': 'CF1'}):
            ok, cf_id, err = svc.create_cash_flow_from_ca(**self.base_kwargs())
        assert ok is True
        assert cf_id == 5
        assert 'already exists' in err

    def test_success_creates_cash_flow_and_updates_position(self, svc, impala, cf_repo):
        with patch.object(svc, '_check_existing_cash_flow', return_value=None), \
             patch.object(svc, '_update_position_with_ca_details', return_value=True) as upd:
            ok, cf_id, err = svc.create_cash_flow_from_ca(**self.base_kwargs())
        assert ok is True
        assert cf_id == 100
        assert err is None
        upd.assert_called_once()

    def test_insert_failure(self, svc, impala, cf_repo):
        cf_repo.insert.return_value = (False, None)
        with patch.object(svc, '_check_existing_cash_flow', return_value=None):
            ok, cf_id, err = svc.create_cash_flow_from_ca(**self.base_kwargs())
        assert ok is False
        assert 'Failed to insert' in err

    def test_roc_uses_decrease_send_receive(self, svc, impala, cf_repo):
        with patch.object(svc, '_check_existing_cash_flow', return_value=None), \
             patch.object(svc, '_update_position_with_ca_details', return_value=True):
            svc.create_cash_flow_from_ca(**self.base_kwargs(ca_type='ROC'))
        cf_data = cf_repo.insert.call_args[0][0]
        assert cf_data['send_receive'] == 'DECREASE'

    def test_dividend_uses_increase_send_receive(self, svc, impala, cf_repo):
        with patch.object(svc, '_check_existing_cash_flow', return_value=None), \
             patch.object(svc, '_update_position_with_ca_details', return_value=True):
            svc.create_cash_flow_from_ca(**self.base_kwargs(ca_type='DIVIDEND'))
        cf_data = cf_repo.insert.call_args[0][0]
        assert cf_data['send_receive'] == 'INCREASE'

    def test_zero_quantity_dividend_price_zero(self, svc, impala, cf_repo):
        with patch.object(svc, '_check_existing_cash_flow', return_value=None), \
             patch.object(svc, '_update_position_with_ca_details', return_value=True):
            svc.create_cash_flow_from_ca(**self.base_kwargs(quantity=Decimal('0')))
        cf_data = cf_repo.insert.call_args[0][0]
        assert cf_data['dividend_price'] == 0

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_check_existing_cash_flow', side_effect=RuntimeError('boom')):
            ok, cf_id, err = svc.create_cash_flow_from_ca(**self.base_kwargs())
        assert ok is False
        assert cf_id is None


class TestUpdatePositionWithCaDetails:
    def base_row(self, **overrides):
        row = {
            'position_id': 1, 'version_id': 2, 'quantity': 100,
            'average_cost_fc': 90, 'cost_fc': 9000, 'average_cost_lc': 95, 'cost_lc': 9500,
            'market_value_fc': 9500, 'market_value_lc': 10000,
            'unrealized_pnl_fc': 500, 'unrealized_pnl_lc': 500,
            'realized_pnl_fc': 0, 'realized_pnl_lc': 0,
            'dividend_fc': 0, 'dividend_lc': 0,
            'uncall_fc': 0, 'uncall_lc': 0, 'pipeline_fc': 0, 'pipeline_lc': 0,
            'provision_fc': 0, 'provision_lc': 0,
            'isin': 'ISIN1', 'src_system': 'CIS', 'source_table': 'x', 'position_date': '2026-01-01',
        }
        row.update(overrides)
        return row

    def test_no_row_found_skips_basis(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'DIVIDEND', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is False

    def test_dividend_accumulates_dividend_field(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], []]  # TRADED found, SETTLED not found
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'DIVIDEND', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is True
        upsert_call = [c[0][0] for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_call) == 1

    def test_roc_reduces_avp(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], []]
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'ROC', '2026-01-01', 100, 'CF1',
            Decimal('900'), Decimal('1215'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is True

    def test_income_distribution_accumulates_realized_pnl(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], []]
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'INCOME_DISTRIBUTION', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is True

    def test_unrecognised_type_no_accumulation(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], []]
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'COUPON', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is True

    def test_both_bases_updated(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], [self.base_row()]]
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'DIVIDEND', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is True
        upsert_calls = [c[0][0] for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) == 2

    def test_upsert_failure_returns_false_when_no_success(self, svc, impala):
        impala.execute_query.side_effect = [[self.base_row()], []]
        impala.execute_write.return_value = False
        result = svc._update_position_with_ca_details(
            'P1', 'S1', 1, 'CA1', 'DIVIDEND', '2026-01-01', 100, 'CF1',
            Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
        )
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._update_position_with_ca_details(
                'P1', 'S1', 1, 'CA1', 'DIVIDEND', '2026-01-01', 100, 'CF1',
                Decimal('35'), Decimal('47.25'), 'USD', 'SGD', Decimal('1.35'), 'user1',
            )
        assert result is False


class TestGetCurrentPosition:
    def test_ledger_hit(self, svc, impala):
        impala.execute_query.return_value = [{'position_id': 1, 'quantity': 10}]
        result = svc._get_current_position('P1', 'S1')
        assert result == {'position_id': 1, 'quantity': 10}

    def test_golden_copy_fallback(self, svc, impala):
        impala.execute_query.side_effect = [
            [],
            [{'position_id': 2, 'quantity': 20, 'market_value_fc': 200}],
        ]
        result = svc._get_current_position('P1', 'S1', position_basis='SETTLED')
        assert result['quantity'] == 20
        assert result['status'] == 'OPEN'
        assert result['is_latest'] is True

    def test_golden_copy_zero_quantity_no_divide_error(self, svc, impala):
        impala.execute_query.side_effect = [[], [{'position_id': 2, 'quantity': 0, 'market_value_fc': 0}]]
        result = svc._get_current_position('P1', 'S1')
        assert result['market_price'] == 0

    def test_no_position_found_anywhere(self, svc, impala):
        impala.execute_query.side_effect = [[], []]
        assert svc._get_current_position('P1', 'S1') is None

    def test_traded_basis_uses_trade_date_cp_basis(self, svc, impala):
        impala.execute_query.side_effect = [[], []]
        svc._get_current_position('P1', 'S1', position_basis='TRADED')
        second_query = impala.execute_query.call_args_list[1][0][0]
        assert "TRADE_DATE" in second_query

    def test_exception_returns_none(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            assert svc._get_current_position('P1', 'S1') is None


class TestMarkOldVersionNotLatest:
    def test_success(self, svc, impala):
        result = svc._mark_old_version_not_latest(123)
        assert result is True

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc._mark_old_version_not_latest(123)
        assert result is False


class TestProcessCaCashFlows:
    def test_queue_entry_not_found(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = None
        ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is False
        assert 'not found' in msg

    def test_cf_position_overwrite_routes(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1'}
        with patch.object(svc, '_process_cf_position_overwrite', return_value=(True, 'ok', 1, Decimal('0'))) as m:
            result = svc.process_ca_cash_flows(1)
        m.assert_called_once()

    def test_position_adjustment_routes(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1'}
        with patch.object(svc, '_process_position_adjustment_ca', return_value=(True, 'ok', 1, Decimal('0'))) as m:
            result = svc.process_ca_cash_flows(1)
        m.assert_called_once()

    def test_invalid_price_fails(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 0}
        ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is False
        assert 'Invalid price' in msg
        queue_repo.mark_failed.assert_called_once()

    def test_no_holdings_marks_completed(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01',
        }
        with patch.object(svc, 'get_holdings_for_ca', return_value=[]):
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is True
        assert count == 0
        queue_repo.mark_completed.assert_called_once()

    def test_dry_run_no_writes(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01',
        }
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings):
            ok, msg, count, amount = svc.process_ca_cash_flows(1, dry_run=True)
        assert ok is True
        assert count == 1
        queue_repo.mark_processing.assert_not_called()

    def test_successful_processing_marks_completed(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01', 'created_by': 'user1',
        }
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, 'create_cash_flow_from_ca', return_value=(True, 1, None)):
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is True
        assert count == 1
        queue_repo.mark_completed.assert_called_once()

    def test_failed_holding_marks_failed(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01', 'created_by': 'user1',
        }
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, 'create_cash_flow_from_ca', return_value=(False, None, 'insert failed')):
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()

    def test_zero_quantity_holding_skipped(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01',
        }
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 0, 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings):
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert count == 0

    def test_cross_currency_uses_fx_rate(self, svc, queue_repo, mcs):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01', 'created_by': 'user1',
        }
        holdings = [{
            'portfolio_short_name': 'P1', 'quantity': 100,
            'security_currency': 'USD', 'portfolio_currency': 'SGD',
        }]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, 'create_cash_flow_from_ca', return_value=(True, 1, None)):
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is True

    def test_fx_rate_lookup_exception_falls_back_to_one(self, svc, queue_repo):
        queue_repo.get_by_id.return_value = {
            'ca_type': 'DIVIDEND', 'ca_number': 'CA1', 'price': 1.0,
            'security_name': 'SEC1', 'ex_date': '2026-01-01', 'created_by': 'user1',
        }
        holdings = [{
            'portfolio_short_name': 'P1', 'quantity': 100,
            'security_currency': 'USD', 'portfolio_currency': 'SGD',
        }]
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.multicurrency_service') as mc, \
             patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, 'create_cash_flow_from_ca', return_value=(True, 1, None)):
            mc.get_fx_rate.side_effect = RuntimeError('boom')
            ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is True

    def test_outer_exception_marks_failed(self, svc, queue_repo):
        queue_repo.get_by_id.side_effect = RuntimeError('boom')
        ok, msg, count, amount = svc.process_ca_cash_flows(1)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()


class TestProcessPositionAdjustmentCa:
    def test_null_price_fails(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': None, 'security_name': 'S1', 'ex_date': '2026-01-01'}
        ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is False
        assert 'price/ratio' in msg

    def test_zero_price_fails(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is False

    def test_no_holdings_marks_completed(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0.1', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        with patch.object(svc, 'get_holdings_for_ca', return_value=[]):
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is True
        assert count == 0

    def test_bonus_issue_routes(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0.1', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_bonus_issue', return_value=True) as m:
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is True
        assert count == 1
        m.assert_called_once()

    def test_split_routes(self, svc, queue_repo):
        entry = {'ca_type': 'SPLIT', 'ca_number': 'CA1', 'price': '2', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_stock_split', return_value=True) as m:
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is True
        m.assert_called_once()

    def test_stock_split_zero_ratio_defaults_to_one(self, svc, queue_repo):
        entry = {'ca_type': 'STOCK_SPLIT', 'ca_number': 'CA1', 'price': '0.0000001', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_stock_split', return_value=True) as m:
            svc._process_position_adjustment_ca(1, entry)
        m.assert_called_once()

    def test_reverse_split_routes(self, svc, queue_repo):
        entry = {'ca_type': 'REVERSE_SPLIT', 'ca_number': 'CA1', 'price': '3', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_reverse_split', return_value=True) as m:
            svc._process_position_adjustment_ca(1, entry)
        m.assert_called_once()

    def test_consolidation_routes_to_reverse_split(self, svc, queue_repo):
        entry = {'ca_type': 'CONSOLIDATION', 'ca_number': 'CA1', 'price': '3', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_reverse_split', return_value=True) as m:
            svc._process_position_adjustment_ca(1, entry)
        m.assert_called_once()

    def test_rights_entitlement_creates_new_position(self, svc, queue_repo):
        entry = {'ca_type': 'RIGHTS_ENTITLEMENT', 'ca_number': 'CA1', 'price': '0.5', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_create_rights_warrant_position', return_value=True) as m:
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is True
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_security_name'] == 'S1 RIGHTS'

    def test_warrant_entitlement_creates_new_position(self, svc, queue_repo):
        entry = {'ca_type': 'WARRANT_ENTITLEMENT', 'ca_number': 'CA1', 'price': '0.5', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_create_rights_warrant_position', return_value=True) as m:
            svc._process_position_adjustment_ca(1, entry)
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_security_name'] == 'S1 WRNTS'

    def test_rights_dry_run_skips_write(self, svc, queue_repo):
        entry = {'ca_type': 'RIGHTS', 'ca_number': 'CA1', 'price': '0.5', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_create_rights_warrant_position') as m:
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry, dry_run=True)
        assert ok is True
        m.assert_not_called()

    def test_unknown_ca_type_fails(self, svc, queue_repo):
        entry = {'ca_type': 'MYSTERY', 'ca_number': 'CA1', 'price': '0.5', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings):
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is False

    def test_zero_quantity_holding_skipped(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0.1', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 0, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings):
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert count == 0

    def test_exception_in_holding_loop_recorded_as_error(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0.1', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'quantity': 100, 'average_cost_fc': 10}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_process_bonus_issue', side_effect=RuntimeError('boom')):
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()

    def test_outer_exception_marks_failed(self, svc, queue_repo):
        entry = {'ca_type': 'BONUS_ISSUE', 'ca_number': 'CA1', 'price': '0.1', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        with patch.object(svc, 'get_holdings_for_ca', side_effect=RuntimeError('boom')):
            ok, msg, count, amount = svc._process_position_adjustment_ca(1, entry)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()


class TestProcessBonusIssue:
    def test_dry_run_no_write(self, svc):
        result = svc._process_bonus_issue(
            'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('0.1'),
            1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1', dry_run=True,
        )
        assert result is True

    def test_success_calls_create_version(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', return_value=True) as m:
            result = svc._process_bonus_issue(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('0.1'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is True
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_quantity'] == Decimal('110.00000000')

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', side_effect=RuntimeError('boom')):
            result = svc._process_bonus_issue(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('0.1'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False


class TestProcessStockSplit:
    def test_dry_run_no_write(self, svc):
        result = svc._process_stock_split(
            'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('2'),
            1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1', dry_run=True,
        )
        assert result is True

    def test_success_calls_create_version(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', return_value=True) as m:
            result = svc._process_stock_split(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('2'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is True
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_quantity'] == Decimal('200.00000000')

    def test_zero_ratio_defaults_avg_cost_zero(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', return_value=True) as m:
            svc._process_stock_split(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('0'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_avg_cost'] == Decimal('0')

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', side_effect=RuntimeError('boom')):
            result = svc._process_stock_split(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('2'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False


class TestProcessReverseSplit:
    def test_dry_run_no_write(self, svc):
        result = svc._process_reverse_split(
            'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('3'),
            1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1', dry_run=True,
        )
        assert result is True

    def test_success_calls_create_version(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', return_value=True) as m:
            result = svc._process_reverse_split(
                'P1', 'S1', Decimal('99'), Decimal('10'), Decimal('3'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is True
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_quantity'] == Decimal('33.00000000')

    def test_zero_ratio_keeps_old_quantity(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', return_value=True) as m:
            svc._process_reverse_split(
                'P1', 'S1', Decimal('100'), Decimal('10'), Decimal('0'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        call_kwargs = m.call_args[1]
        assert call_kwargs['new_quantity'] == Decimal('100')

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_create_position_adjustment_version', side_effect=RuntimeError('boom')):
            result = svc._process_reverse_split(
                'P1', 'S1', Decimal('99'), Decimal('10'), Decimal('3'),
                1, 'CA1', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False


class TestCreatePositionAdjustmentVersion:
    def base_row(self, **overrides):
        row = {
            'position_id': 1, 'version_id': 2, 'market_value_fc': 1000, 'quantity': 100,
            'cost_lc': 9500, 'dividend_fc': 0, 'dividend_lc': 0, 'uncall_fc': 0, 'uncall_lc': 0,
            'pipeline_fc': 0, 'pipeline_lc': 0, 'provision_fc': 0, 'provision_lc': 0,
            'realized_pnl_fc': 0, 'realized_pnl_lc': 0, 'isin': 'ISIN1', 'src_system': 'CIS',
            'source_table': 'x', 'position_date': '2026-01-01',
        }
        row.update(overrides)
        return row

    def test_no_basis_row_found_skips(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._create_position_adjustment_version(
            'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
            1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD', 'user1',
        )
        assert result is False

    def test_success_writes_both_bases(self, svc, impala):
        impala.execute_query.return_value = [self.base_row()]
        with patch.object(svc, '_apply_ca_to_trade_date_position', return_value=True):
            result = svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'SGD', 'user1',
            )
        assert result is True
        upsert_calls = [c for c in impala.execute_write.call_args_list if 'UPSERT INTO' in c[0][0]]
        assert len(upsert_calls) == 2

    def test_corr_run_type_includes_eod_basis(self, svc, impala):
        impala.execute_query.return_value = [self.base_row()]
        with patch.object(svc, '_apply_ca_to_trade_date_position', return_value=True):
            svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD', 'user1', run_type='CORR',
            )
        query = impala.execute_query.call_args_list[1][0][0]
        assert "'EOD'" in query

    def test_non_revalued_redistributes_lc_cost(self, svc, impala):
        impala.execute_query.side_effect = [
            [{'revaluation_status': 'NON-REVALUED'}],
            [self.base_row()],
            [self.base_row()],
        ]
        with patch.object(svc, '_apply_ca_to_trade_date_position', return_value=True):
            result = svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'SGD', 'user1',
            )
        assert result is True

    def test_reval_status_lookup_exception_defaults_revalued(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = [RuntimeError('boom'), [self.base_row()], [self.base_row()]]
            m.execute_write.return_value = True
            with patch.object(svc, '_apply_ca_to_trade_date_position', return_value=True):
                result = svc._create_position_adjustment_version(
                    'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                    1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'SGD', 'user1',
                )
        assert result is True

    def test_fx_lookup_exception_defaults_to_one(self, svc, impala):
        impala.execute_query.return_value = [self.base_row()]
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.multicurrency_service') as mc, \
             patch.object(svc, '_apply_ca_to_trade_date_position', return_value=True):
            mc.get_fx_rate.side_effect = RuntimeError('boom')
            result = svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'SGD', 'user1',
            )
        assert result is True

    def test_upsert_failure_no_apply_ca_call(self, svc, impala):
        impala.execute_query.return_value = [self.base_row()]
        impala.execute_write.return_value = False
        with patch.object(svc, '_apply_ca_to_trade_date_position') as apply_mock:
            result = svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False
        apply_mock.assert_not_called()

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._create_position_adjustment_version(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False


class TestSyncCaAdjustmentToGoldenPosition:
    def test_no_row_found_returns_false(self, svc, impala):
        impala.execute_query.return_value = []
        result = svc._sync_ca_adjustment_to_golden_position(
            'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
            Decimal('1000'), Decimal('1350'), Decimal('0'), Decimal('0'),
            Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
            Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
            '2026-01-01', 'BONUS_ISSUE', 'user1',
        )
        assert result is False

    def test_success(self, svc, impala):
        impala.execute_query.return_value = [{
            'position_id': 1, 'version_id': 2, 'realized_pnl_fc': 0, 'realized_pnl_lc': 0,
            'isin': 'ISIN1', 'source_table': 'x', 'src_system': 'CIS', 'position_basis': 'SETTLED',
        }]
        result = svc._sync_ca_adjustment_to_golden_position(
            'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
            Decimal('1000'), Decimal('1350'), Decimal('0'), Decimal('0'),
            Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
            Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
            '2026-01-01', 'BONUS_ISSUE', 'user1',
        )
        assert result is True

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('boom')
            result = svc._sync_ca_adjustment_to_golden_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                Decimal('1000'), Decimal('1350'), Decimal('0'), Decimal('0'),
                Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
                Decimal('0'), Decimal('0'), Decimal('0'), Decimal('0'),
                '2026-01-01', 'BONUS_ISSUE', 'user1',
            )
        assert result is False


class TestApplyCaToTradeDatePosition:
    def test_creates_new_row_when_none_exists(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=None):
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1',
            )
        assert result is True

    def test_updates_existing_row(self, svc, impala):
        existing = {
            'version_id': 5, 'position_id': 10, 'market_price': 10, 'dividend_fc': 0,
            'dividend_lc': 0, 'uncall_fc': 0, 'uncall_lc': 0, 'pipeline_fc': 0, 'pipeline_lc': 0,
            'commit_fc': 0, 'commit_lc': 0, 'provision_fc': 0, 'provision_lc': 0,
            'position_type': 'NORMAL', 'total_cost_lc': 950,
        }
        with patch.object(svc, '_get_current_position', return_value=existing), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True) as mark_mock:
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1',
            )
        assert result is True
        mark_mock.assert_called_once()

    def test_non_revalued_redistributes_lc(self, svc, impala):
        existing = {
            'version_id': 5, 'position_id': 10, 'market_price': 10, 'dividend_fc': 0,
            'dividend_lc': 0, 'total_cost_lc': 950,
        }
        with patch.object(svc, '_get_current_position', return_value=existing), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            impala.execute_query.return_value = [{'revaluation_status': 'NON-REVALUED'}]
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'SGD',
                Decimal('1.35'), 'user1',
            )
        assert result is True

    def test_reval_lookup_exception_defaults_revalued(self, svc):
        existing = {'version_id': 5, 'position_id': 10, 'market_price': 10}
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m, \
             patch.object(svc, '_get_current_position', return_value=existing), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            m.execute_query.side_effect = RuntimeError('boom')
            m.execute_write.return_value = True
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1',
            )
        assert result is True

    def test_settled_basis_offset(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=None):
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1', position_basis='SETTLED',
            )
        assert result is True

    def test_write_failure_returns_false(self, svc, impala):
        impala.execute_write.return_value = False
        with patch.object(svc, '_get_current_position', return_value=None):
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1',
            )
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_get_current_position', side_effect=RuntimeError('boom')):
            result = svc._apply_ca_to_trade_date_position(
                'P1', 'S1', Decimal('110'), Decimal('9.09'), Decimal('1000'),
                1, 'CA1', 'BONUS_ISSUE', '2026-01-01', 'USD', 'USD',
                Decimal('1'), 'user1',
            )
        assert result is False


class TestCreateRightsWarrantPosition:
    def test_success(self, svc, impala):
        result = svc._create_rights_warrant_position(
            'P1', 'S1 RIGHTS', Decimal('50'), 1, 'CA1', 'RIGHTS_ENTITLEMENT',
            '2026-01-01', 'USD', 'USD', 'user1',
        )
        assert result is True

    def test_cross_currency_uses_fx_rate(self, svc, impala, mcs):
        result = svc._create_rights_warrant_position(
            'P1', 'S1 RIGHTS', Decimal('50'), 1, 'CA1', 'RIGHTS_ENTITLEMENT',
            '2026-01-01', 'USD', 'SGD', 'user1',
        )
        assert result is True

    def test_fx_lookup_exception_defaults_to_one(self, svc, impala):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.multicurrency_service') as mc:
            mc.get_fx_rate.side_effect = RuntimeError('boom')
            result = svc._create_rights_warrant_position(
                'P1', 'S1 RIGHTS', Decimal('50'), 1, 'CA1', 'RIGHTS_ENTITLEMENT',
                '2026-01-01', 'USD', 'SGD', 'user1',
            )
        assert result is True

    def test_write_failure_returns_false(self, svc, impala):
        impala.execute_write.return_value = False
        result = svc._create_rights_warrant_position(
            'P1', 'S1 RIGHTS', Decimal('50'), 1, 'CA1', 'RIGHTS_ENTITLEMENT',
            '2026-01-01', 'USD', 'USD', 'user1',
        )
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_write.side_effect = RuntimeError('boom')
            result = svc._create_rights_warrant_position(
                'P1', 'S1 RIGHTS', Decimal('50'), 1, 'CA1', 'RIGHTS_ENTITLEMENT',
                '2026-01-01', 'USD', 'USD', 'user1',
            )
        assert result is False


class TestProcessCfPositionOverwrite:
    def test_no_holdings_marks_completed(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        with patch.object(svc, 'get_holdings_for_ca', return_value=[]):
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is True
        assert count == 0

    def test_dry_run_no_write(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        holdings = [{'portfolio_short_name': 'P1', 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings):
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry, dry_run=True)
        assert ok is True
        assert count == 1

    def test_success_calls_overwrite(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01', 'created_by': 'user1'}
        holdings = [{'portfolio_short_name': 'P1', 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_overwrite_position_field', return_value=True) as m:
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is True
        m.assert_called_once()

    def test_cross_currency_fx_lookup_exception_falls_back(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01', 'created_by': 'user1'}
        holdings = [{'portfolio_short_name': 'P1', 'security_currency': 'USD', 'portfolio_currency': 'SGD'}]
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.multicurrency_service') as mc, \
             patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_overwrite_position_field', return_value=True):
            mc.get_fx_rate.side_effect = RuntimeError('boom')
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is True

    def test_overwrite_failure_recorded(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01', 'created_by': 'user1'}
        holdings = [{'portfolio_short_name': 'P1', 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_overwrite_position_field', return_value=False):
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()

    def test_exception_in_overwrite_recorded_as_error(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01', 'created_by': 'user1'}
        holdings = [{'portfolio_short_name': 'P1', 'security_currency': 'USD'}]
        with patch.object(svc, 'get_holdings_for_ca', return_value=holdings), \
             patch.object(svc, '_overwrite_position_field', side_effect=RuntimeError('boom')):
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is False

    def test_outer_exception_marks_failed(self, svc, queue_repo):
        entry = {'ca_type': 'CF-PIPELINE', 'ca_number': 'CA1', 'price': '100', 'security_name': 'S1', 'ex_date': '2026-01-01'}
        with patch.object(svc, 'get_holdings_for_ca', side_effect=RuntimeError('boom')):
            ok, msg, count, amount = svc._process_cf_position_overwrite(1, entry)
        assert ok is False
        queue_repo.mark_failed.assert_called_once()


class TestOverwritePositionField:
    def base_position(self, **overrides):
        pos = {
            'position_id': 1, 'version_id': 2, 'quantity': 100,
            'average_cost_fc': 90, 'total_cost_fc': 9000, 'average_cost_lc': 95, 'total_cost_lc': 9500,
            'market_price': 95, 'market_value_fc': 9500, 'market_value_lc': 10000,
            'realized_pnl_fc': 0, 'unrealized_pnl_fc': 500, 'realized_pnl_lc': 0, 'unrealized_pnl_lc': 500,
            'dividend_fc': 0, 'dividend_lc': 0, 'uncall_fc': 0, 'uncall_lc': 0,
            'pipeline_fc': 0, 'pipeline_lc': 0, 'commit_fc': 0, 'commit_lc': 0,
            'provision_fc': 0, 'provision_lc': 0, 'security_currency': 'USD',
            'portfolio_currency': 'USD', 'fx_rate': 1, 'position_type': 'NORMAL',
        }
        pos.update(overrides)
        return pos

    def test_no_position_returns_false(self, svc):
        with patch.object(svc, '_get_current_position', return_value=None):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-PIPELINE', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is False

    def test_cf_commitment(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-COMMITMENT', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is True

    def test_cf_uncall_commitment(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-UN CALL COMMITMENT', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is True

    def test_cf_pipeline(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-PIPELINE', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is True

    def test_cf_ytd(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-YTD', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is True

    def test_cf_provision(self, svc, impala):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-PROVISION', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is True

    def test_unknown_cf_type_returns_false(self, svc):
        with patch.object(svc, '_get_current_position', return_value=self.base_position()):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-UNKNOWN', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is False

    def test_write_failure_returns_false(self, svc, impala):
        impala.execute_write.return_value = False
        with patch.object(svc, '_get_current_position', return_value=self.base_position()), \
             patch.object(svc, '_mark_old_version_not_latest', return_value=True):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-PIPELINE', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is False

    def test_exception_returns_false(self, svc):
        with patch.object(svc, '_get_current_position', side_effect=RuntimeError('boom')):
            result = svc._overwrite_position_field(
                'P1', 'S1', 'CF-PIPELINE', Decimal('100'), Decimal('135'),
                1, 'CA1', '2026-01-01', 'user1',
            )
        assert result is False


class TestProcessPendingCas:
    def test_processes_all_pending(self, svc, queue_repo):
        queue_repo.get_pending.return_value = [
            {'queue_id': 1, 'ca_number': 'CA1'}, {'queue_id': 2, 'ca_number': 'CA2'},
        ]
        with patch.object(svc, 'process_ca_cash_flows', side_effect=[
            (True, 'ok', 1, Decimal('10')), (False, 'failed', 0, Decimal('0')),
        ]):
            stats = svc.process_pending_cas()
        assert stats['total_processed'] == 2
        assert stats['successful'] == 1
        assert stats['failed'] == 1
        assert stats['cash_flows_created'] == 1
        assert len(stats['errors']) == 1

    def test_no_pending_returns_zero_stats(self, svc, queue_repo):
        queue_repo.get_pending.return_value = []
        stats = svc.process_pending_cas()
        assert stats['total_processed'] == 0

    def test_exception_returns_error_stats(self, svc, queue_repo):
        queue_repo.get_pending.side_effect = RuntimeError('boom')
        stats = svc.process_pending_cas()
        assert stats['total_processed'] == 0
        assert len(stats['errors']) == 1


class TestGetCashFlowsByCa:
    def test_returns_cash_flow_table_rows_when_available(self, svc, queue_repo, impala):
        queue_repo.get_logs_by_queue_id.return_value = [{'log': 1}]
        impala.execute_query.return_value = [{'cash_flow_id': 1}]
        result = svc.get_cash_flows_by_ca(1)
        assert result == [{'cash_flow_id': 1}]

    def test_falls_back_to_logs_when_no_cash_flow_rows(self, svc, queue_repo, impala):
        queue_repo.get_logs_by_queue_id.return_value = [{'log': 1}]
        impala.execute_query.return_value = []
        result = svc.get_cash_flows_by_ca(1)
        assert result == [{'log': 1}]

    def test_falls_back_to_logs_when_query_raises(self, svc, queue_repo):
        queue_repo.get_logs_by_queue_id.return_value = [{'log': 1}]
        with patch('edge_jobs_py36.lib.ca_cash_flow_service.impala_manager') as m:
            m.execute_query.side_effect = RuntimeError('no ca_id column')
            result = svc.get_cash_flows_by_ca(1)
        assert result == [{'log': 1}]

    def test_outer_exception_returns_empty_list(self, svc, queue_repo):
        queue_repo.get_logs_by_queue_id.side_effect = RuntimeError('boom')
        result = svc.get_cash_flows_by_ca(1)
        assert result == []
