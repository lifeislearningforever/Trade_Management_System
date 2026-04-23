"""
Tests for Settlement Service - Settlement Date Logic

Phase 2: Settlement date handling tests.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta

from trade.services.settlement_service import SettlementService, settlement_service
from trade.services.position_service import PositionService


class TestSettlementDateRules:
    """Test settlement date classification and rules."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = SettlementService()

    def test_current_date_settlement(self):
        """Test same-day settlement is processed immediately (sync mode)."""
        today = datetime.now().strftime('%Y-%m-%d')

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        # Use async_mode=False to test synchronous immediate processing
        success, message, result = self.service.process_trade_settlement(
            trade_id=12345,
            portfolio_id='FUND-001',
            security_id='AAPL',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('50.00'),
            charges=Decimal('10.00'),
            trade_date=today,
            settle_date=today,  # Same day
            updated_by='test_user',
            async_mode=False
        )

        assert success is True
        assert 'Immediate settlement' in message
        assert mock_position_service.calculate_position.call_count >= 1

    def test_future_date_settlement_queued(self):
        """Test future SETTLE_DATE is queued; TRADE_DATE processed immediately (sync mode)."""
        today = datetime.now()
        future_date = (today + timedelta(days=2)).strftime('%Y-%m-%d')
        trade_date = today.strftime('%Y-%m-%d')

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        with patch.object(self.service, '_queue_for_settlement') as mock_queue:
            mock_queue.return_value = (True, f"Queued for {future_date}", {'queue_id': 123})

            # async_mode=False: TRADE_DATE → immediate, SETTLE_DATE future → queue
            success, message, result = self.service.process_trade_settlement(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                trade_date=trade_date,
                settle_date=future_date,  # T+2
                updated_by='test_user',
                async_mode=False
            )

            assert success is True
            # SETTLE_DATE queue was called once for the future basis
            mock_queue.assert_called_once()

    def test_backdated_within_limit_allowed(self):
        """Test backdated settlement within previous month-end is allowed."""
        today = datetime.now()
        # Get a date after previous month-end but before today
        first_of_month = today.replace(day=1)
        backdated = (first_of_month + timedelta(days=1)).strftime('%Y-%m-%d')

        if today.day <= 2:
            # If we're at start of month, skip this test
            pytest.skip("Test requires being past the first few days of month")

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        with patch.object(self.service, '_recalculate_position_chain') as mock_recalc:
            mock_recalc.return_value = {'recalculated': 0, 'errors': 0}

            mock_position_service = MagicMock()
            mock_position_service.calculate_position.return_value = (
                True, "Position updated", {'quantity': 100}
            )
            self.service.position_service = mock_position_service

            # Use async_mode=False to exercise the backdated sync path
            success, message, result = self.service.process_trade_settlement(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                trade_date=backdated,
                settle_date=backdated,
                updated_by='test_user',
                async_mode=False
            )

            # If backdated is before today, it should be processed as backdated
            if self.service._parse_date(backdated) < today.date():
                assert success is True
                assert 'Backdated' in message or 'completed' in message or 'Immediate' in message

    def test_backdated_beyond_limit_warns_but_allowed(self):
        """Test backdated settlement beyond previous month-end is allowed with a warning."""
        # The service allows all backdated dates — it only logs a warning for old dates.
        # Use validate_backdated_settlement to confirm the warning message.
        today = datetime.now()
        two_months_ago = today.replace(day=1) - timedelta(days=32)
        old_date = two_months_ago.strftime('%Y-%m-%d')

        is_valid, message = self.service.validate_backdated_settlement(old_date)

        # Service allows it but warns about closed-period impact
        assert is_valid is True
        assert 'Warning' in message or 'month-end' in message.lower() or 'allowed' in message.lower()


class TestBackdatedValidation:
    """Test backdated settlement validation."""

    def setup_method(self):
        self.service = SettlementService()

    def test_validate_future_date(self):
        """Future dates are valid (will be queued)."""
        future = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
        is_valid, message = self.service.validate_backdated_settlement(future)

        assert is_valid is True
        assert 'queue' in message.lower() or 'future' in message.lower()

    def test_validate_today(self):
        """Today's date is valid (immediate processing)."""
        today = datetime.now().strftime('%Y-%m-%d')
        is_valid, message = self.service.validate_backdated_settlement(today)

        assert is_valid is True
        assert 'immediate' in message.lower() or 'same-day' in message.lower()

    def test_validate_within_month(self):
        """Dates within current month are valid."""
        today = datetime.now()
        if today.day > 5:
            within_month = today.replace(day=today.day - 2).strftime('%Y-%m-%d')
            is_valid, message = self.service.validate_backdated_settlement(within_month)

            assert is_valid is True
            assert 'allowed' in message.lower()

    def test_validate_too_old(self):
        """Dates before previous month-end are allowed but carry a warning."""
        today = datetime.now()
        # Go back 2 months to ensure we're definitely past the limit
        two_months_ago = (today.replace(day=1) - timedelta(days=45)).strftime('%Y-%m-%d')

        is_valid, message = self.service.validate_backdated_settlement(two_months_ago)

        # Service allows all backdated dates, warns for closed-period impact
        assert is_valid is True
        assert 'Warning' in message or 'month-end' in message.lower() or 'allowed' in message.lower()

    def test_validate_invalid_format(self):
        """Invalid date formats are rejected."""
        is_valid, message = self.service.validate_backdated_settlement("invalid-date")

        assert is_valid is False
        assert 'invalid' in message.lower()


class TestDateUtilities:
    """Test date utility methods."""

    def setup_method(self):
        self.service = SettlementService()

    def test_get_previous_month_end(self):
        """Test previous month-end calculation."""
        prev_month_end = self.service._get_previous_month_end()
        today = datetime.now().date()

        # Previous month-end should be before today
        assert prev_month_end < today

        # Should be the last day of previous month
        first_of_this_month = today.replace(day=1)
        expected = first_of_this_month - timedelta(days=1)
        assert prev_month_end == expected

    def test_get_current_month_start(self):
        """Test current month start calculation."""
        month_start = self.service._get_current_month_start()
        today = datetime.now().date()

        assert month_start.day == 1
        assert month_start.month == today.month
        assert month_start.year == today.year

    def test_parse_date_various_formats(self):
        """Test date parsing with various formats."""
        # YYYY-MM-DD
        result = self.service._parse_date('2026-03-04')
        assert result == date(2026, 3, 4)

        # YYYYMMDD
        result = self.service._parse_date('20260304')
        assert result == date(2026, 3, 4)

        # DD-MM-YYYY
        result = self.service._parse_date('04-03-2026')
        assert result == date(2026, 3, 4)

        # Invalid
        result = self.service._parse_date('invalid')
        assert result is None

        # None
        result = self.service._parse_date(None)
        assert result is None

    def test_get_dates_in_range(self):
        """Test getting dates in a range."""
        dates = self.service._get_dates_in_range('2026-03-01', '2026-03-05')

        assert len(dates) == 5
        assert dates[0] == '2026-03-01'
        assert dates[4] == '2026-03-05'


class TestSettlementQueue:
    """Test settlement queue operations."""

    def setup_method(self):
        self.service = SettlementService()

    def test_queue_creates_pending_entry(self):
        """Test queueing a trade creates a PENDING entry."""
        future_date = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')

        with patch('trade.services.settlement_service.impala_manager') as mock_impala:
            mock_impala.execute_write.return_value = True

            success, message, result = self.service._queue_for_settlement(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                settle_date=future_date,
                updated_by='test_user'
            )

            assert success is True
            assert result['status'] == 'PENDING'
            assert result['settle_date'] == future_date
            mock_impala.execute_write.assert_called_once()

    def test_process_pending_settlements(self):
        """Test processing pending settlements."""
        today = datetime.now().strftime('%Y-%m-%d')

        mock_pending = [
            {
                'queue_id': 1,
                'trade_id': 100,
                'portfolio_id': 'FUND-001',
                'security_id': 'AAPL',
                'trade_type': 'BUY',
                'quantity': 100,
                'price': 50.0,
                'charges': 10.0,
                'settle_date': today
            }
        ]

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        with patch.object(self.service, 'get_pending_settlements', return_value=mock_pending):
            with patch.object(self.service, '_update_queue_status', return_value=True):
                counters = self.service.process_pending_settlements(today)

                assert counters['processed'] == 1
                assert counters['failed'] == 0


class TestRecalculationChain:
    """Test position recalculation chain for backdated settlements."""

    def setup_method(self):
        self.service = SettlementService()

    def test_recalculation_processes_subsequent_trades(self):
        """Test that recalculation processes trades after the backdated date."""
        mock_trades = [
            {
                'trade_id': 101,
                'trade_type': 'BUY',
                'quantity': 50,
                'price': 55.0,
                'charges': 5.0,
                'settle_date': '2026-03-02'
            },
            {
                'trade_id': 102,
                'trade_type': 'SELL',
                'quantity': 30,
                'price': 60.0,
                'charges': 3.0,
                'settle_date': '2026-03-03'
            }
        ]

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (True, "OK", {})
        self.service.position_service = mock_position_service

        with patch('trade.services.settlement_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_trades

            result = self.service._recalculate_position_chain(
                portfolio_id='FUND-001',
                security_id='AAPL',
                from_date='2026-03-01',
                updated_by='test_user'
            )

            assert result['recalculated'] == 2
            assert result['errors'] == 0
            assert mock_position_service.calculate_position.call_count == 2


class TestIntegration:
    """Integration tests for complete settlement flow."""

    def setup_method(self):
        self.service = SettlementService()

    def test_full_settlement_flow_immediate(self):
        """Test complete flow for immediate settlement (sync mode)."""
        today = datetime.now().strftime('%Y-%m-%d')

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated",
            {
                'quantity': 100,
                'average_cost_fc': 50.1,
                'total_cost_fc': 5010.0,
                'status': 'OPEN'
            }
        )
        self.service.position_service = mock_position_service

        # Use async_mode=False so positions are calculated synchronously
        success, message, result = self.service.process_trade_settlement(
            trade_id=12345,
            portfolio_id='FUND-001',
            security_id='AAPL',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('50.00'),
            charges=Decimal('10.00'),
            trade_date=today,
            settle_date=today,
            updated_by='test_user',
            security_currency='USD',
            portfolio_currency='USD',
            isin='US0378331005',
            async_mode=False
        )

        assert success is True
        assert result is not None
        assert 'Immediate' in message

    def test_full_settlement_flow_future(self):
        """Test complete flow for future settlement (sync mode)."""
        today = datetime.now()
        future = (today + timedelta(days=2)).strftime('%Y-%m-%d')

        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100, 'average_cost_fc': 50.1}
        )
        self.service.position_service = mock_position_service

        with patch('trade.services.settlement_service.impala_manager') as mock_impala:
            mock_impala.execute_write.return_value = True

            # async_mode=False: TRADE_DATE processes immediately, SETTLE_DATE queues
            success, message, result = self.service.process_trade_settlement(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                trade_date=today.strftime('%Y-%m-%d'),
                settle_date=future,
                updated_by='test_user',
                async_mode=False
            )

            assert success is True
            assert 'queue' in message.lower() or future in message or 'Immediate' in message


# =========================================================================
# Example Test Scenarios
# =========================================================================

EXAMPLE_SCENARIOS = """
Settlement Date Test Scenarios for Manual Testing
==================================================

Scenario 1: Immediate Settlement (T+0)
--------------------------------------
Trade Date: 2026-03-04
Settle Date: 2026-03-04 (same day)
Expected: Position calculated immediately

Scenario 2: Future Settlement (T+2)
-----------------------------------
Trade Date: 2026-03-04
Settle Date: 2026-03-06 (T+2)
Expected: Trade queued, position calculated on 2026-03-06

Scenario 3: Backdated Settlement (Within Limit)
----------------------------------------------
Today: 2026-03-15
Settle Date: 2026-03-05 (within current month)
Expected: Position calculated, chain recalculated from 03-05 to today

Scenario 4: Backdated Settlement (Beyond Limit)
-----------------------------------------------
Today: 2026-03-15
Previous Month End: 2026-02-29
Settle Date: 2026-02-15 (before month-end)
Expected: REJECTED - "Backdated settlement not allowed before 2026-02-29"

Commands to run tests:
- pytest trade/tests/test_settlement_service.py -v
- pytest trade/tests/test_settlement_service.py -v -k "test_backdated"
- pytest trade/tests/test_settlement_service.py -v -k "test_future"
"""

if __name__ == '__main__':
    print(EXAMPLE_SCENARIOS)
