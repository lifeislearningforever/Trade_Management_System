"""
Tests for Position Service - AVP (Average Price Position) Calculator

Phase 1: Basic AVP with weighted average calculation tests.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime

from trade.services.position_service import PositionService, position_service
from core.repositories.impala_connection import impala_manager


class TestAVPCalculation:
    """Test weighted average price calculation logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = PositionService()

    # =========================================================================
    # BUY Tests
    # =========================================================================

    def test_buy_new_position(self):
        """Test BUY when no existing position - creates new position."""
        # Scenario: First purchase of 100 shares at $50 with $10 commission
        # Expected: qty=100, avg_cost=50.10 (including charges), total_cost=5010

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=None):
                with patch.object(self.service, '_get_market_price', return_value=50.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, message, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='AAPL',
                            trade_type='BUY',
                            quantity=Decimal('100'),
                            price=Decimal('50.00'),
                            charges=Decimal('10.00'),
                            position_date='2026-03-04',
                            trade_id=12345,
                            updated_by='test_user'
                        )

        assert success is True
        assert position is not None
        assert position['quantity'] == 100.0
        # avg_cost = (100 * 50 + 10) / 100 = 5010/100 = 50.10
        assert position['average_cost_fc'] == 50.1
        assert position['total_cost_fc'] == 5010.0
        assert position['status'] == 'OPEN'
        assert position['src_system'] == 'CIS'

    def test_buy_add_to_existing_position(self):
        """Test BUY adding to existing position - recalculates AVP."""
        # Scenario: Already have 100 shares at $50 avg. Buy 50 more at $60 with $5 commission
        # Old total_cost = 100 * 50 = 5000
        # New trade_cost = (50 * 60) + 5 = 3005
        # New total_cost = 5000 + 3005 = 8005
        # New qty = 100 + 50 = 150
        # New avg_cost = 8005 / 150 = 53.36666667 (rounded to 8 decimals)

        existing_position = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 50.0,
            'realized_pnl': 0
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
                with patch.object(self.service, '_get_market_price', return_value=60.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, message, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='AAPL',
                            trade_type='BUY',
                            quantity=Decimal('50'),
                            price=Decimal('60.00'),
                            charges=Decimal('5.00'),
                            position_date='2026-03-04',
                            trade_id=12346,
                            updated_by='test_user'
                        )

        assert success is True
        assert position is not None
        assert position['quantity'] == 150.0
        # avg_cost = 8005 / 150 = 53.36666667
        assert round(position['average_cost_fc'], 8) == round(53.36666667, 8)
        assert position['total_cost_fc'] == 8005.0
        assert position['position_id'] == 99999  # Same position

    def test_buy_multiple_times_avp_accumulates(self):
        """Test multiple BUYs correctly accumulate AVP."""
        # Start: 0 shares
        # BUY 1: 100 @ $10 = $1000 total -> avg = $10
        # BUY 2: 100 @ $20 = $2000 total -> total = $3000, qty = 200, avg = $15
        # BUY 3: 100 @ $30 = $3000 total -> total = $6000, qty = 300, avg = $20

        # Test BUY 2 scenario (after BUY 1)
        existing_after_buy1 = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 10.0,
            'realized_pnl': 0
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_after_buy1):
                with patch.object(self.service, '_get_market_price', return_value=20.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, _, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='TEST',
                            trade_type='BUY',
                            quantity=Decimal('100'),
                            price=Decimal('20.00'),
                            charges=Decimal('0'),
                            position_date='2026-03-04',
                            trade_id=12347,
                            updated_by='test_user'
                        )

        assert success is True
        assert position['quantity'] == 200.0
        assert position['average_cost_fc'] == 15.0  # (1000 + 2000) / 200

    # =========================================================================
    # SELL Tests
    # =========================================================================

    def test_sell_partial_position(self):
        """Test SELL partial position - AVP unchanged, realized P&L calculated."""
        # Scenario: Have 100 shares at $50 avg. Sell 30 at $70
        # Realized P&L = (70 - 50) * 30 = $600
        # New qty = 100 - 30 = 70
        # AVP stays at $50

        existing_position = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 50.0,
            'realized_pnl': 0
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
                with patch.object(self.service, '_get_market_price', return_value=70.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, message, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='AAPL',
                            trade_type='SELL',
                            quantity=Decimal('30'),
                            price=Decimal('70.00'),
                            charges=Decimal('0'),
                            position_date='2026-03-04',
                            trade_id=12348,
                            updated_by='test_user'
                        )

        assert success is True
        assert position is not None
        assert position['quantity'] == 70.0
        assert position['average_cost_fc'] == 50.0  # Unchanged
        assert position['realized_pnl_fc'] == 600.0  # (70-50) * 30
        assert position['status'] == 'OPEN'

    def test_sell_full_position_closes(self):
        """Test SELL entire position - closes position."""
        # Scenario: Have 100 shares at $50 avg. Sell all 100 at $60
        # Realized P&L = (60 - 50) * 100 = $1000
        # Position should be CLOSED

        existing_position = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 50.0,
            'realized_pnl': 0
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
                with patch.object(self.service, '_save_position', return_value=True):
                    success, message, position = self.service.calculate_position(
                        portfolio_id='FUND-001',
                        security_id='AAPL',
                        trade_type='SELL',
                        quantity=Decimal('100'),
                        price=Decimal('60.00'),
                        charges=Decimal('0'),
                        position_date='2026-03-04',
                        trade_id=12349,
                        updated_by='test_user'
                    )

        assert success is True
        assert position['quantity'] == 0
        assert position['average_cost_fc'] == 0
        assert position['realized_pnl_fc'] == 1000.0
        assert position['status'] == 'CLOSED'
        assert position['is_active'] is False

    def test_sell_at_loss(self):
        """Test SELL at loss - negative realized P&L."""
        # Scenario: Have 100 shares at $50 avg. Sell 50 at $40
        # Realized P&L = (40 - 50) * 50 = -$500 (loss)

        existing_position = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 50.0,
            'realized_pnl': 0
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
                with patch.object(self.service, '_get_market_price', return_value=40.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, _, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='AAPL',
                            trade_type='SELL',
                            quantity=Decimal('50'),
                            price=Decimal('40.00'),
                            charges=Decimal('0'),
                            position_date='2026-03-04',
                            trade_id=12350,
                            updated_by='test_user'
                        )

        assert success is True
        assert position['realized_pnl_fc'] == -500.0  # Loss

    def test_sell_cumulative_realized_pnl(self):
        """Test multiple SELLs accumulate realized P&L."""
        # Scenario: Have 100 shares at $50 avg, already realized $200
        # Sell 20 at $60 -> additional P&L = (60-50)*20 = $200
        # Total realized P&L = $200 + $200 = $400

        existing_position = {
            'position_id': 99999,
            'quantity': 100,
            'average_cost': 50.0,
            'realized_pnl': 200.0  # Already had some realized gains
        }

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
                with patch.object(self.service, '_get_market_price', return_value=60.0):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, _, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='AAPL',
                            trade_type='SELL',
                            quantity=Decimal('20'),
                            price=Decimal('60.00'),
                            charges=Decimal('0'),
                            position_date='2026-03-04',
                            trade_id=12351,
                            updated_by='test_user'
                        )

        assert success is True
        assert position['realized_pnl_fc'] == 400.0  # 200 + 200

    # =========================================================================
    # Validation Tests
    # =========================================================================

    def test_sell_no_position_rejected(self):
        """Test SELL without existing position is rejected."""
        with patch.object(self.service, '_get_position_as_of_date', return_value=None):
            success, message, position = self.service.calculate_position(
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='SELL',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('0'),
                position_date='2026-03-04',
                trade_id=12352,
                updated_by='test_user'
            )

        assert success is False
        assert 'No position found' in message
        assert position is None

    def test_sell_insufficient_quantity_rejected(self):
        """Test SELL more than available quantity is rejected (no short selling)."""
        existing_position = {
            'position_id': 99999,
            'quantity': 50,
            'average_cost': 50.0,
            'realized_pnl': 0
        }

        with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
            success, message, position = self.service.calculate_position(
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='SELL',
                quantity=Decimal('100'),  # More than available 50
                price=Decimal('50.00'),
                charges=Decimal('0'),
                position_date='2026-03-04',
                trade_id=12353,
                updated_by='test_user'
            )

        assert success is False
        assert 'Insufficient quantity' in message
        assert position is None

    def test_negative_quantity_rejected(self):
        """Test negative quantity is rejected."""
        with patch.object(self.service, '_get_position_as_of_date', return_value=None):
            success, message, _ = self.service.calculate_position(
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('-100'),
                price=Decimal('50.00'),
                charges=Decimal('0'),
                position_date='2026-03-04',
                trade_id=12354,
                updated_by='test_user'
            )

        assert success is False
        assert 'positive' in message.lower()

    def test_negative_price_rejected(self):
        """Test negative price is rejected."""
        with patch.object(self.service, '_get_position_as_of_date', return_value=None):
            success, message, _ = self.service.calculate_position(
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('-50.00'),
                charges=Decimal('0'),
                position_date='2026-03-04',
                trade_id=12355,
                updated_by='test_user'
            )

        assert success is False
        assert 'positive' in message.lower()

    def test_non_position_affecting_trade_type_ignored(self):
        """Test trade types other than BUY/SELL don't affect position."""
        success, message, position = self.service.calculate_position(
            portfolio_id='FUND-001',
            security_id='AAPL',
            trade_type='DIVIDEND',  # Not a position-affecting type
            quantity=Decimal('100'),
            price=Decimal('5.00'),
            charges=Decimal('0'),
            position_date='2026-03-04',
            trade_id=12356,
            updated_by='test_user'
        )

        assert success is True
        assert 'does not affect position' in message
        assert position is None

    # =========================================================================
    # Precision Tests (8 decimal places)
    # =========================================================================

    def test_avp_precision_8_decimals(self):
        """Test AVP is calculated to 8 decimal precision."""
        # Scenario: 3 shares at $10.12345678 each = $30.37037034 total
        # avg = 30.37037034 / 3 = 10.12345678

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=None):
                with patch.object(self.service, '_get_market_price', return_value=10.12345678):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, _, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='TEST',
                            trade_type='BUY',
                            quantity=Decimal('3'),
                            price=Decimal('10.12345678'),
                            charges=Decimal('0'),
                            position_date='2026-03-04',
                            trade_id=12357,
                            updated_by='test_user'
                        )

        assert success is True
        # Check 8 decimal precision
        avg_cost = Decimal(str(position['average_cost_fc']))
        assert abs(avg_cost - Decimal('10.12345678')) < Decimal('0.000000005')

    def test_charges_included_in_avp(self):
        """Test that charges are included in AVP calculation."""
        # BUY 100 @ $10 with $50 commission
        # Total cost = (100 * 10) + 50 = 1050
        # AVP = 1050 / 100 = $10.50

        with patch('core.repositories.impala_connection.impala_manager.execute_query', return_value=[]):
            with patch.object(self.service, '_get_position_as_of_date', return_value=None):
                with patch.object(self.service, '_get_market_price', return_value=10.50):
                    with patch.object(self.service, '_save_position', return_value=True):
                        success, _, position = self.service.calculate_position(
                            portfolio_id='FUND-001',
                            security_id='TEST',
                            trade_type='BUY',
                            quantity=Decimal('100'),
                            price=Decimal('10.00'),
                            charges=Decimal('50.00'),
                            position_date='2026-03-04',
                            trade_id=12358,
                            updated_by='test_user'
                        )

        assert success is True
        assert position['average_cost_fc'] == 10.5  # Includes charges
        assert position['total_cost_fc'] == 1050.0


class TestValidation:
    """Test validation rules."""

    def setup_method(self):
        self.service = PositionService()

    def test_validate_buy_no_position_passes(self):
        """BUY validation passes when no existing position."""
        with patch.object(self.service, '_get_position_as_of_date', return_value=None):
            is_valid, errors = self.service.validate_trade_for_position(
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                portfolio_id='FUND-001',
                security_id='AAPL'
            )

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_sell_no_position_fails(self):
        """SELL validation fails when no existing position."""
        with patch.object(self.service, '_get_position_as_of_date', return_value=None):
            is_valid, errors = self.service.validate_trade_for_position(
                trade_type='SELL',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                portfolio_id='FUND-001',
                security_id='AAPL'
            )

        assert is_valid is False
        assert 'Insufficient quantity' in errors[0]

    def test_validate_sell_exceeds_quantity_fails(self):
        """SELL validation fails when quantity exceeds position."""
        existing_position = {'quantity': 50}

        with patch.object(self.service, '_get_position_as_of_date', return_value=existing_position):
            is_valid, errors = self.service.validate_trade_for_position(
                trade_type='SELL',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                portfolio_id='FUND-001',
                security_id='AAPL'
            )

        assert is_valid is False
        assert 'Insufficient' in errors[0]


class TestPositionMasterSync:
    """Test synchronization to position_master external table."""

    def setup_method(self):
        self.service = PositionService()

    def test_sync_includes_src_system_cis(self):
        """Test that synced positions have src_system='CIS'."""
        position_data = {
            'position_id': 12345,
            'portfolio_short_name': 'FUND-001',
            'security_label': 'AAPL',
            'quantity': 100,
            'average_cost': 50.0,
            'total_cost': 5000.0,
            'current_price': 55.0,
            'market_value': 5500.0,
            'unrealized_pnl': 500.0,
            'status': 'OPEN'
        }

        with patch.object(impala_manager, 'execute_write', return_value=True) as mock_write:
            self.service._sync_to_position_master(position_data, 'test_user')

            # Verify src_system='CIS' is in the query
            call_args = mock_write.call_args
            query = call_args[0][0]
            assert "'CIS'" in query
            assert "src_id='CIS'" in query or "src_system" in query


# =========================================================================
# Example Test Scenarios (for manual testing)
# =========================================================================

EXAMPLE_SCENARIOS = """
Example AVP Test Scenarios for Manual Testing
=============================================

Scenario 1: Simple BUY-BUY-SELL
-------------------------------
1. BUY 100 AAPL @ $50.00 (commission: $10)
   Expected: qty=100, avg=$50.10, total_cost=$5,010

2. BUY 50 AAPL @ $60.00 (commission: $5)
   Expected: qty=150, avg=$53.43333333, total_cost=$8,015

3. SELL 30 AAPL @ $70.00
   Expected: qty=120, avg=$53.43333333 (unchanged), realized_pnl=$497.00

Scenario 2: Full Position Lifecycle
-----------------------------------
1. BUY 100 TEST @ $10.00
2. BUY 100 TEST @ $20.00
   avg = (1000+2000)/200 = $15.00
3. SELL 50 TEST @ $25.00
   realized_pnl = (25-15)*50 = $500
   remaining: qty=150, avg=$15.00
4. SELL 150 TEST @ $18.00
   realized_pnl = $500 + (18-15)*150 = $500 + $450 = $950
   Position CLOSED

Scenario 3: Charges Impact on AVP
---------------------------------
1. BUY 100 @ $10.00 (commission=$100, sec_fee=$20)
   total_cost = (100*10) + 100 + 20 = $1,120
   avg = $11.20

Commands to run tests:
- pytest trade/tests/test_position_service.py -v
- pytest trade/tests/test_position_service.py -v -k "test_buy"
- pytest trade/tests/test_position_service.py -v -k "test_sell"
"""

if __name__ == '__main__':
    print(EXAMPLE_SCENARIOS)
