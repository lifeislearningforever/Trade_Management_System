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
