import re
from decimal import Decimal
from unittest.mock import patch

from trade.management.commands.process_approved_cashflows import Command
from trade.services.position_id_service import position_id as calc_position_id


class TestProcessApprovedCashflowsSeedPositions:
    def setup_method(self):
        self.command = Command()
        self.cash_flow = {
            'cash_flow_id': 101,
            'cash_flow_number': 'CF-101',
        }

    def test_apply_to_position_seeds_uncall_position_when_missing(self):
        with patch.object(self.command, '_get_current_positions', return_value=[]), \
             patch.object(self.command, '_get_security_currency', return_value='USD'), \
             patch.object(self.command, '_get_portfolio_currency', return_value='SGD'), \
             patch.object(self.command, '_get_currency_dp', return_value=2), \
             patch.object(self.command, '_write_new_position_version', return_value=True) as write_mock:
            success, _ = self.command._apply_to_position(
                cf=self.cash_flow,
                cf_type='UNCALL_COMMITMENT',
                portfolio='PORT-1',
                security='SEC-1',
                amount_fc=Decimal('100'),
                amount_lc=Decimal('135'),
                send_receive='SEND',
                payment_date='2026-08-15',
                dry_run=False,
                run_type='EOD',
                position_date='2026-08-15',
            )

        assert success is True
        current, portfolio, security, position_date, cf_type, overrides = write_mock.call_args.args[:6]
        assert portfolio == 'PORT-1'
        assert security == 'SEC-1'
        assert position_date == '2026-08-15'
        assert cf_type == 'UNCALL_COMMITMENT'
        assert current['position_id'] == calc_position_id(
            portfolio='PORT-1',
            security_label='SEC-1',
            position_basis='SETTLED',
            position_date='2026-08-15',
            src_system='CIS',
        )
        assert current['quantity'] == 0
        assert current['position_basis'] == 'SETTLED'
        assert overrides == {'uncall_fc': 100.0, 'uncall_lc': 135.0}

    def test_apply_to_position_seeds_pipeline_position_when_missing(self):
        with patch.object(self.command, '_get_current_positions', return_value=[]), \
             patch.object(self.command, '_get_security_currency', return_value='USD'), \
             patch.object(self.command, '_get_portfolio_currency', return_value='SGD'), \
             patch.object(self.command, '_get_currency_dp', return_value=2), \
             patch.object(self.command, '_write_new_position_version', return_value=True) as write_mock:
            success, _ = self.command._apply_to_position(
                cf=self.cash_flow,
                cf_type='PIPELINE',
                portfolio='PORT-1',
                security='SEC-1',
                amount_fc=Decimal('25'),
                amount_lc=Decimal('30'),
                send_receive='RECEIVE',
                payment_date='2026-08-15',
                dry_run=False,
                run_type='EOD',
                position_date='2026-08-15',
            )

        assert success is True
        overrides = write_mock.call_args.args[5]
        assert overrides == {'pipeline_fc': -25.0, 'pipeline_lc': -30.0}

    def test_apply_to_position_keeps_non_seed_types_as_no_position(self):
        with patch.object(self.command, '_get_current_positions', return_value=[]):
            success, message = self.command._apply_to_position(
                cf=self.cash_flow,
                cf_type='DIVIDEND',
                portfolio='PORT-1',
                security='SEC-1',
                amount_fc=Decimal('10'),
                amount_lc=Decimal('13'),
                send_receive='SEND',
                payment_date='2026-08-15',
                dry_run=False,
                run_type='EOD',
                position_date='2026-08-15',
            )

        assert success is False
        assert 'No open position' in message

    def test_write_new_position_version_skips_latest_update_for_seed_position(self):
        current = {
            'position_id': calc_position_id(
                portfolio='PORT-1',
                security_label='SEC-1',
                position_basis='SETTLED',
                position_date='2026-08-15',
                src_system='CIS',
            ),
            'position_basis': 'SETTLED',
            'quantity': 0,
            'average_cost_fc': 0,
            'total_cost_fc': 0,
            'average_cost_lc': 0,
            'total_cost_lc': 0,
            'market_price': 0,
            'market_value_fc': 0,
            'market_value_lc': 0,
            'realized_pnl_fc': 0,
            'unrealized_pnl_fc': 0,
            'realized_pnl_lc': 0,
            'unrealized_pnl_lc': 0,
            'dividend_fc': 0,
            'dividend_lc': 0,
            'uncall_fc': 0,
            'uncall_lc': 0,
            'pipeline_fc': 0,
            'pipeline_lc': 0,
            'commit_fc': 0,
            'commit_lc': 0,
            'provision_fc': 0,
            'provision_lc': 0,
        }

        with patch.object(self.command, '_get_security_currency', return_value='USD'), \
             patch.object(self.command, '_get_portfolio_currency', return_value='SGD'), \
             patch('trade.management.commands.process_approved_cashflows.impala_manager.execute_write', return_value=True) as write_sql, \
             patch.object(self.command, '_sync_to_golden_position') as sync_mock:
            success = self.command._write_new_position_version(
                current=current,
                portfolio='PORT-1',
                security='SEC-1',
                position_date='2026-08-15',
                cf_type='UNCALL_COMMITMENT',
                overrides={'uncall_fc': 100.0, 'uncall_lc': 135.0},
                cf_id=101,
                cf_number='CF-101',
                cf_amount_fc=100.0,
                cf_amount_lc=135.0,
                fc_dp=2,
                lc_dp=2,
                pos_src='CIS',
                run_type='EOD',
            )

        assert success is True
        assert write_sql.call_count == 1
        sql = write_sql.call_args.args[0].lstrip()
        assert sql.startswith('INSERT INTO')
        sync_mock.assert_called_once()

    def test_write_new_position_version_routes_golden_fallback_row_to_golden_even_when_src_is_cis(self):
        """
        Regression: a position found via the golden-copy fallback in
        _get_current_positions (no cis_trade_position ledger row exists) is
        still tagged pos_src=row['src_system'], which can be 'CIS'. Routing on
        pos_src alone previously sent this into the ledger UPDATE/INSERT branch
        using a version_id that was really just the golden position_id,
        silently producing no new ledger version (the exact "TRADED never got
        an INT row" bug reported live for UOBS_BCHAIN_FVE / UQ-UOB-102 CH).
        The _from_ledger=False marker must force the golden-only path
        regardless of pos_src.
        """
        current = {
            'position_id': 12345,
            'version_id': 12345,  # aliased from golden's position_id, NOT a real ledger version_id
            'position_basis': 'TRADED',
            'quantity': 1679,
            'src_system': 'CIS',
            '_from_ledger': False,
        }

        with patch.object(self.command, '_get_security_currency', return_value='CHF'), \
             patch.object(self.command, '_get_portfolio_currency', return_value='SGD'), \
             patch('trade.management.commands.process_approved_cashflows.impala_manager.execute_write') as write_sql, \
             patch.object(self.command, '_sync_to_golden_position') as sync_mock:
            success = self.command._write_new_position_version(
                current=current,
                portfolio='UOBS_BCHAIN_FVE',
                security='UQ-UOB-102 CH',
                position_date='2026-03-16',
                cf_type='RETURN_OF_CAPITAL',
                overrides={'total_cost_fc': 100.0},
                cf_id=1,
                cf_number='CF-20260902-00001',
                cf_amount_fc=10.0,
                cf_amount_lc=13.0,
                fc_dp=2,
                lc_dp=2,
                pos_src='CIS',
                run_type='EOD',
            )

        assert success is True
        write_sql.assert_not_called()  # must not touch cis_trade_position at all
        sync_mock.assert_called_once()

    def test_sync_to_golden_position_reuses_existing_position_id(self):
        """
        Regression: cis_position's PRIMARY KEY is position_id alone. An UPSERT
        keyed on a freshly-computed hash instead of the existing row's own
        position_id (e.g. a timestamp-based id from refresh_positions.py's
        carry-forward writer) inserts a brand-new row rather than updating the
        one just found — the update becomes invisible on the position_id the
        user is actually watching. This was the "reprocessed the cash flow,
        TRADED still not showing" symptom for UOBS_BCHAIN_FVE / UQ-UOB-102 CH,
        whose existing golden row has position_id=1788335199514 (a
        timestamp+random id, not the position_id_service hash).
        """
        existing_row = {
            'position_id': 1788335199514,
            'version_id': 1788334199514,
            'src_system': 'CIS',
            'position_basis': 'TRADED',
            'quantity': 1679,
            'average_cost_fc': 1445.04921767,
            'cost_fc': 2426237.64,
        }
        current = {'position_basis': 'TRADED', 'quantity': 1679}

        with patch(
            'trade.management.commands.process_approved_cashflows.impala_manager.execute_query',
            return_value=[existing_row],
        ), patch(
            'trade.management.commands.process_approved_cashflows.impala_manager.execute_write',
            return_value=True,
        ) as write_sql:
            self.command._sync_to_golden_position(
                portfolio='UOBS_BCHAIN_FVE',
                security='UQ-UOB-102 CH',
                position_date='2026-03-16',
                cf_type='RETURN_OF_CAPITAL',
                current=current,
                overrides={'total_cost_fc': 2400000.0},
                cf_id=1,
                cf_number='CF-20260902-00001',
                cf_amount_fc=10.0,
                cf_amount_lc=13.0,
                fc_dp=2,
                lc_dp=2,
                src_system='CIS',
                run_type='EOD',
            )

        sql = write_sql.call_args.args[0]
        values_clause = sql.split('VALUES', 1)[1]
        leading_ids = re.findall(r'\d+', values_clause)[:2]
        assert leading_ids == ['1788335199514', '1788335199514'], (
            f'expected UPSERT to reuse the existing row\'s position_id, got {leading_ids}'
        )

    def test_apply_to_position_return_of_capital_updates_settled_and_traded(self):
        positions = [
            ({'position_basis': 'SETTLED', 'quantity': 100}, 'CIS'),
            ({'position_basis': 'TRADED', 'quantity': 100}, 'CIS'),
        ]
        with patch.object(self.command, '_get_current_positions', return_value=positions) as get_positions_mock, \
             patch.object(self.command, '_get_security_currency', return_value='USD'), \
             patch.object(self.command, '_get_portfolio_currency', return_value='SGD'), \
             patch.object(self.command, '_get_currency_dp', return_value=2), \
             patch.object(self.command, '_reduce_avp', return_value=(True, 'ok')) as reduce_mock:
            success, _ = self.command._apply_to_position(
                cf=self.cash_flow,
                cf_type='RETURN_OF_CAPITAL',
                portfolio='PORT-1',
                security='SEC-1',
                amount_fc=Decimal('10'),
                amount_lc=Decimal('13'),
                send_receive='DECREASE',
                payment_date='2026-08-15',
                dry_run=False,
                run_type='EOD',
                position_date='2026-08-15',
            )

        assert success is True
        get_positions_mock.assert_called_once_with(
            'PORT-1', 'SEC-1', position_date='2026-08-15', include_traded=True
        )
        assert reduce_mock.call_count == 2
        processed_bases = [call.args[0]['position_basis'] for call in reduce_mock.call_args_list]
        assert processed_bases == ['SETTLED', 'TRADED']

    def test_apply_to_position_non_roc_uses_settled_only_lookup(self):
        with patch.object(self.command, '_get_current_positions', return_value=[]) as get_positions_mock:
            success, _ = self.command._apply_to_position(
                cf=self.cash_flow,
                cf_type='DIVIDEND',
                portfolio='PORT-1',
                security='SEC-1',
                amount_fc=Decimal('10'),
                amount_lc=Decimal('13'),
                send_receive='SEND',
                payment_date='2026-08-15',
                dry_run=False,
                run_type='EOD',
                position_date='2026-08-15',
            )

        assert success is False
        get_positions_mock.assert_called_once_with(
            'PORT-1', 'SEC-1', position_date='2026-08-15', include_traded=False
        )
