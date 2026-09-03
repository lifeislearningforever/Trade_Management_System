from decimal import Decimal
from unittest.mock import patch

from trade.management.commands.refresh_positions import Command


class TestRefreshPositions:
    def setup_method(self):
        self.command = Command()

    def test_get_open_positions_does_not_filter_out_zero_quantity_rows(self):
        with patch(
            'trade.management.commands.refresh_positions.impala_manager.execute_query',
            return_value=[]
        ) as mock_execute:
            self.command._get_open_positions(
                portfolio_filter=None,
                sources=['CIS'],
                position_date='2026-08-16',
                security_filter=None,
                fill_gaps=False,
                position_type='INT',
            )

        query = mock_execute.call_args[0][0]
        assert 'AND quantity > 0' not in query

    def test_process_position_zero_quantity_uses_safe_fallbacks(self):
        position = {
            'position_id': 1,
            'portfolio': 'PORT-1',
            'security_label': 'SEC-1',
            'quantity': Decimal('0'),
            'cost_fc': Decimal('0'),
            'cost_lc': Decimal('0'),
            'provision_fc': Decimal('0'),
            'provision_lc': Decimal('0'),
            'average_cost_fc': Decimal('0'),
            'average_cost_lc': Decimal('0'),
            'market_value_fc': Decimal('123.45'),
            'market_value_lc': Decimal('123.45'),
            'position_date': '2026-08-16',
        }
        ref = {
            'port_info': {'PORT-1': {'currency': 'USD', 'revaluation_status': 'NON-REVALUED'}},
            'sec_ccy': {'SEC-1': 'USD'},
            'equity_method': {'SEC-1': False},
            'prices': {'SEC-1': None},
            'fx_rates': {},
            'fx_rate_dates': {},
            'currency_dp': {'USD': 2},
        }
        insert_rows = []

        result = self.command._process_position(
            position=position,
            dry_run=False,
            run_date='2026-08-16',
            ref=ref,
            insert_rows=insert_rows,
            ams_no_reval=False,
            run_type='EOD',
        )

        assert result == 'updated'
        assert len(insert_rows) == 1
        assert insert_rows[0]['price_dec'] == Decimal('0')
        assert insert_rows[0]['market_value_fc'] == Decimal('123.45')
        assert insert_rows[0]['market_value_lc'] == Decimal('123.45')

    def test_process_position_missing_quantity_still_skips(self):
        ref = {
            'port_info': {},
            'sec_ccy': {},
            'equity_method': {},
            'prices': {},
            'fx_rates': {},
            'fx_rate_dates': {},
            'currency_dp': {},
        }

        result = self.command._process_position(
            position={
                'position_id': 1,
                'portfolio': 'PORT-1',
                'security_label': 'SEC-1',
                'quantity': None,
            },
            dry_run=False,
            run_date='2026-08-16',
            ref=ref,
            insert_rows=[],
            ams_no_reval=False,
            run_type='EOD',
        )

        assert result == 'skipped'
