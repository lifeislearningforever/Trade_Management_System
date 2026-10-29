"""
Tests for Multi-Currency Service - FX Rate Lookup and Currency Conversion

Phase 4: Multi-currency support tests.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime

from trade.services.multicurrency_service import MultiCurrencyService, multicurrency_service


class TestFXRateLookup:
    """Test FX rate lookup operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_same_currency_returns_one(self):
        """Test same currency returns rate of 1."""
        rate, date_used = self.service.get_fx_rate('USD', 'USD')

        assert rate == Decimal('1')

    def test_direct_pair_lookup(self):
        """Test direct pair lookup (e.g., USD-SGD)."""
        mock_result = [{'spot_rate_d': 1.35, 'date': '2026-03-04'}]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_result

            rate, date_used = self.service.get_fx_rate('USD', 'SGD')

            assert rate == Decimal('1.35')
            assert date_used == '2026-03-04'

    def test_reverse_pair_inverted(self):
        """Test reverse pair is inverted (SGD-USD = 1/USD-SGD)."""
        # First call returns None (direct pair not found)
        # Second call returns the reverse pair
        mock_results = [
            None,  # USD-SGD not found
            [{'spot_rate_d': 0.74, 'date': '2026-03-04'}]  # SGD-USD found
        ]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.side_effect = [[], mock_results[1]]

            rate, date_used = self.service.get_fx_rate('USD', 'SGD')

            # Rate should be inverted: 1/0.74 ≈ 1.35135135
            expected = (Decimal('1') / Decimal('0.74')).quantize(Decimal('0.00000001'))
            assert abs(rate - expected) < Decimal('0.00000001')

    def test_no_rate_returns_one(self):
        """Test missing rate returns 1.0 as default."""
        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = []

            rate, _ = self.service.get_fx_rate('XYZ', 'ABC')

            assert rate == Decimal('1')

    def test_null_currencies_return_one(self):
        """Test null/empty currencies return 1.0."""
        rate, _ = self.service.get_fx_rate(None, 'USD')
        assert rate == Decimal('1')

        rate, _ = self.service.get_fx_rate('USD', None)
        assert rate == Decimal('1')

        rate, _ = self.service.get_fx_rate('', '')
        assert rate == Decimal('1')

    def test_historical_rate_lookup(self):
        """Test looking up historical FX rate."""
        mock_result = [{'spot_rate_d': 1.30, 'date': '2026-02-15'}]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_result

            rate, date_used = self.service.get_fx_rate('USD', 'SGD', '2026-02-15')

            assert rate == Decimal('1.30')
            assert date_used == '2026-02-15'


class TestFXRateCache:
    """Test FX rate caching."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_rate_cached(self):
        """Test that FX rates are cached."""
        mock_result = [{'spot_rate_d': 1.35, 'date': '2026-03-04'}]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_result

            # First call - hits database
            self.service.get_fx_rate('USD', 'SGD')
            assert mock_impala.execute_query.call_count == 1

            # Second call - should use cache
            self.service.get_fx_rate('USD', 'SGD')
            assert mock_impala.execute_query.call_count == 1  # No additional calls

    def test_cache_cleared(self):
        """Test cache clearing."""
        self.service._fx_cache['test-key'] = (datetime.now(), (Decimal('1.35'), '2026-03-04'))

        self.service.clear_cache()

        assert len(self.service._fx_cache) == 0


class TestCurrencyConversion:
    """Test currency conversion."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_convert_amount(self):
        """Test converting amount between currencies."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            converted, rate = self.service.convert_amount(
                amount=Decimal('1000'),
                from_currency='USD',
                to_currency='SGD'
            )

            assert converted == Decimal('1350.00000000')
            assert rate == Decimal('1.35')

    def test_convert_same_currency(self):
        """Test conversion of same currency returns original."""
        converted, rate = self.service.convert_amount(
            amount=Decimal('1000'),
            from_currency='USD',
            to_currency='USD'
        )

        assert converted == Decimal('1000')
        assert rate == Decimal('1')


class TestPositionValueCalculation:
    """Test position value calculations in multiple currencies."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_calculate_position_values(self):
        """Test calculating all position values in both currencies."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.calculate_position_values(
                quantity=Decimal('100'),
                avg_cost_local=Decimal('50.00'),
                current_price=Decimal('55.00'),
                security_currency='USD',
                portfolio_currency='SGD'
            )

            # Local values (USD)
            assert result['cost_value_local'] == 5000.0  # 100 * 50
            assert result['market_value_local'] == 5500.0  # 100 * 55
            assert result['unrealized_pnl_local'] == 500.0  # 5500 - 5000

            # Base values (SGD) - multiplied by 1.35
            assert result['cost_value_base'] == 6750.0  # 5000 * 1.35
            assert result['market_value_base'] == 7425.0  # 5500 * 1.35
            assert result['unrealized_pnl_base'] == 675.0  # 500 * 1.35

            # FX info
            assert result['fx_rate'] == 1.35
            assert result['security_currency'] == 'USD'
            assert result['portfolio_currency'] == 'SGD'

    def test_calculate_position_values_same_currency(self):
        """Test position values when currencies are the same."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1'), '2026-03-04')):
            result = self.service.calculate_position_values(
                quantity=Decimal('100'),
                avg_cost_local=Decimal('50.00'),
                current_price=Decimal('55.00'),
                security_currency='USD',
                portfolio_currency='USD'
            )

            # Local and base should be equal
            assert result['cost_value_local'] == result['cost_value_base']
            assert result['market_value_local'] == result['market_value_base']
            assert result['fx_rate'] == 1.0


class TestRealizedPnLCalculation:
    """Test realized P&L calculation in multiple currencies."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_realized_pnl_profit(self):
        """Test realized P&L calculation for profit."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.calculate_realized_pnl_multicurrency(
                sell_quantity=Decimal('50'),
                sell_price=Decimal('60.00'),
                avg_cost=Decimal('50.00'),
                security_currency='USD',
                portfolio_currency='SGD'
            )

            # Local P&L: (60 - 50) * 50 = 500
            assert result['realized_pnl_local'] == 500.0

            # Base P&L: 500 * 1.35 = 675
            assert result['realized_pnl_base'] == 675.0

    def test_realized_pnl_loss(self):
        """Test realized P&L calculation for loss."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.calculate_realized_pnl_multicurrency(
                sell_quantity=Decimal('50'),
                sell_price=Decimal('40.00'),
                avg_cost=Decimal('50.00'),
                security_currency='USD',
                portfolio_currency='SGD'
            )

            # Local P&L: (40 - 50) * 50 = -500
            assert result['realized_pnl_local'] == -500.0

            # Base P&L: -500 * 1.35 = -675
            assert result['realized_pnl_base'] == -675.0


class TestCurrencyMetadata:
    """Test currency metadata lookups."""

    def setup_method(self):
        self.service = MultiCurrencyService()

    def test_get_portfolio_currency(self):
        """Test getting portfolio currency."""
        mock_result = [{'currency': 'SGD'}]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_result

            currency = self.service.get_portfolio_currency('FUND-001')

            assert currency == 'SGD'

    def test_get_security_currency(self):
        """Test getting security currency."""
        mock_result = [{'security_currency': 'USD'}]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_result

            currency = self.service.get_security_currency('AAPL')

            assert currency == 'USD'

    def test_get_position_currencies(self):
        """Test getting both currencies for a position."""
        with patch.object(self.service, 'get_security_currency', return_value='USD'):
            with patch.object(self.service, 'get_portfolio_currency', return_value='SGD'):
                sec_ccy, port_ccy = self.service.get_position_currencies('FUND-001', 'AAPL')

                assert sec_ccy == 'USD'
                assert port_ccy == 'SGD'


class TestPositionRefresh:
    """Test position value refresh with latest FX."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_refresh_position_values(self):
        """Test refreshing position values with new price/FX."""
        position = {
            'quantity': 100,
            'average_cost': 50.0,
            'current_price': 55.0,
            'security_currency': 'USD',
            'portfolio_currency': 'SGD'
        }

        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.40'), '2026-03-04')):
            result = self.service.refresh_position_values(
                position=position,
                current_price=Decimal('60.00')  # New price
            )

            # With new price of 60
            assert result['market_value_local'] == 6000.0  # 100 * 60
            assert result['unrealized_pnl_local'] == 1000.0  # 6000 - 5000

            # With new FX rate of 1.40
            assert result['fx_rate'] == 1.40

    def test_refresh_uses_stored_price_if_not_provided(self):
        """Test refresh uses stored price when new price not provided."""
        position = {
            'quantity': 100,
            'average_cost': 50.0,
            'current_price': 55.0,
            'security_currency': 'USD',
            'portfolio_currency': 'SGD'
        }

        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.refresh_position_values(position=position)

            # Should use stored current_price of 55
            assert result['market_value_local'] == 5500.0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def setup_method(self):
        self.service = MultiCurrencyService()
        self.service.clear_cache()

    def test_zero_quantity(self):
        """Test calculations with zero quantity."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.calculate_position_values(
                quantity=Decimal('0'),
                avg_cost_local=Decimal('50.00'),
                current_price=Decimal('55.00'),
                security_currency='USD',
                portfolio_currency='SGD'
            )

            assert result['cost_value_local'] == 0.0
            assert result['market_value_local'] == 0.0
            assert result['unrealized_pnl_local'] == 0.0

    def test_negative_pnl(self):
        """Test calculations with negative P&L (loss)."""
        with patch.object(self.service, 'get_fx_rate', return_value=(Decimal('1.35'), '2026-03-04')):
            result = self.service.calculate_position_values(
                quantity=Decimal('100'),
                avg_cost_local=Decimal('60.00'),  # Bought high
                current_price=Decimal('50.00'),  # Now lower
                security_currency='USD',
                portfolio_currency='SGD'
            )

            assert result['unrealized_pnl_local'] == -1000.0  # Loss
            assert result['unrealized_pnl_base'] == -1350.0


class TestLatestRates:
    """Test getting latest rates for a currency."""

    def setup_method(self):
        self.service = MultiCurrencyService()

    def test_get_latest_rates(self):
        """Test getting all latest rates for a base currency."""
        mock_results = [
            {'ref_quot_ccy': 'USD-SGD', 'spot_rate_d': 1.35, 'date': '2026-03-04'},
            {'ref_quot_ccy': 'USD-EUR', 'spot_rate_d': 0.92, 'date': '2026-03-04'},
            {'ref_quot_ccy': 'USD-GBP', 'spot_rate_d': 0.79, 'date': '2026-03-04'}
        ]

        with patch('trade.services.multicurrency_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_results

            rates = self.service.get_latest_rates_for_currency('USD')

            assert len(rates) == 3
            assert any(r['pair'] == 'USD-SGD' for r in rates)


# =========================================================================
# Example Test Scenarios
# =========================================================================

EXAMPLE_SCENARIOS = """
Multi-Currency Test Scenarios for Manual Testing
=================================================

Scenario 1: Cross-Currency Position
-----------------------------------
Portfolio: FUND-001 (base currency: SGD)
Security: AAPL (currency: USD)
Position: 100 shares @ $50 avg cost

FX Rate: USD-SGD = 1.35

Expected:
- Cost Local (USD): $5,000
- Cost Base (SGD): S$6,750
- If current price = $55:
  - Market Local (USD): $5,500
  - Market Base (SGD): S$7,425
  - Unrealized P&L Local: $500
  - Unrealized P&L Base: S$675

Scenario 2: Realized P&L with FX
--------------------------------
Sell 30 AAPL @ $70 (avg cost was $50)
FX Rate: USD-SGD = 1.40

Local P&L: (70 - 50) * 30 = $600
Base P&L: $600 * 1.40 = S$840

Commands to run tests:
- pytest trade/tests/test_multicurrency_service.py -v
- pytest trade/tests/test_multicurrency_service.py -v -k "test_calculate"
- pytest trade/tests/test_multicurrency_service.py -v -k "test_fx"
"""

if __name__ == '__main__':
    print(EXAMPLE_SCENARIOS)
