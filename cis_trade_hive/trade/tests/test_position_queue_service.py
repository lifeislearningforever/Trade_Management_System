"""
Tests for Position Queue Service - Async Background Processing

Phase 3: Async background processing tests.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from queue import Queue

from trade.services.position_queue_service import PositionQueueService, position_queue_service


class TestQueueEnqueue:
    """Test queue enqueue operations."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = PositionQueueService()

    def test_enqueue_to_db_queue(self):
        """Test enqueueing to database queue."""
        with patch.object(self.service, '_insert_queue_item', return_value=True):
            success, message, queue_id = self.service.enqueue_position_calculation(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                settle_date='2026-03-04',
                queued_by='test_user',
                use_db_queue=True
            )

            assert success is True
            assert queue_id is not None
            assert 'queued' in message.lower()

    def test_enqueue_to_memory_queue(self):
        """Test enqueueing to in-memory queue."""
        success, message, queue_id = self.service.enqueue_position_calculation(
            trade_id=12345,
            portfolio_id='FUND-001',
            security_id='AAPL',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('50.00'),
            charges=Decimal('10.00'),
            settle_date='2026-03-04',
            queued_by='test_user',
            use_db_queue=False  # In-memory
        )

        assert success is True
        assert queue_id is not None
        assert not self.service._in_memory_queue.empty()

    def test_enqueue_includes_multicurrency_fields(self):
        """Test that multi-currency fields are included in queue item."""
        captured_item = None

        def capture_insert(item):
            nonlocal captured_item
            captured_item = item
            return True

        with patch.object(self.service, '_insert_queue_item', side_effect=capture_insert):
            self.service.enqueue_position_calculation(
                trade_id=12345,
                portfolio_id='FUND-001',
                security_id='AAPL',
                trade_type='BUY',
                quantity=Decimal('100'),
                price=Decimal('50.00'),
                charges=Decimal('10.00'),
                settle_date='2026-03-04',
                queued_by='test_user',
                security_currency='USD',
                portfolio_currency='SGD',
                isin='US0378331005',
                use_db_queue=True
            )

            assert captured_item is not None
            assert captured_item['security_currency'] == 'USD'
            assert captured_item['portfolio_currency'] == 'SGD'
            assert captured_item['isin'] == 'US0378331005'


class TestQueueProcessing:
    """Test queue processing operations."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_process_item_success(self):
        """Test successful processing of queue item."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'queued_at': datetime.now()
        }

        with patch.object(self.service, '_update_status', return_value=True):
            self.service._process_item(item)

            mock_position_service.calculate_position.assert_called_once()

    def test_process_item_failure_retry(self):
        """Test failed processing triggers retry."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            False, "Position calculation failed", None
        )
        self.service.position_service = mock_position_service

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'retry_count': 0,
            'queued_at': datetime.now()
        }

        with patch.object(self.service, '_update_status', return_value=True) as mock_update:
            self.service._process_item(item)

            # Should update status with retry
            calls = mock_update.call_args_list
            assert len(calls) >= 2  # PROCESSING, then PENDING (retry)

    def test_process_item_max_retries_dead_letter(self):
        """Test item moved to dead letter after max retries."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            False, "Position calculation failed", None
        )
        self.service.position_service = mock_position_service

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'retry_count': 3,  # Max retries reached
            'queued_at': datetime.now()
        }

        with patch.object(self.service, '_update_status', return_value=True) as mock_update:
            self.service._process_item(item)

            # Check that status was updated to DEAD_LETTER
            final_call = mock_update.call_args_list[-1]
            assert 'DEAD_LETTER' in str(final_call)


class TestSLAMonitoring:
    """Test SLA monitoring."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_sla_breach_detected(self):
        """Test SLA breach is detected for old queue items."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        # Item queued 10 minutes ago (exceeds 5 min SLA)
        old_time = datetime.now() - timedelta(minutes=10)

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'queued_at': old_time
        }

        with patch.object(self.service, '_update_status', return_value=True):
            with patch('trade.services.position_queue_service.logger') as mock_logger:
                self.service._process_item(item)

                # Check that SLA breach was logged
                warning_calls = [c for c in mock_logger.warning.call_args_list
                               if 'SLA' in str(c)]
                assert len(warning_calls) > 0

    def test_sla_ok_for_recent_items(self):
        """Test SLA is OK for recently queued items."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        # Item queued 1 minute ago (within 5 min SLA)
        recent_time = datetime.now() - timedelta(minutes=1)

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'queued_at': recent_time
        }

        with patch.object(self.service, '_update_status', return_value=True):
            with patch('trade.services.position_queue_service.logger') as mock_logger:
                self.service._process_item(item)

                # No SLA breach warning
                warning_calls = [c for c in mock_logger.warning.call_args_list
                               if 'SLA' in str(c)]
                assert len(warning_calls) == 0


class TestInMemoryQueue:
    """Test in-memory queue operations."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_in_memory_queue_processing(self):
        """Test processing items from in-memory queue."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100}
        )
        self.service.position_service = mock_position_service

        # Add items to in-memory queue
        for i in range(3):
            self.service._in_memory_queue.put({
                'queue_id': i,
                'trade_id': 100 + i,
                'portfolio_id': 'FUND-001',
                'security_id': 'AAPL',
                'trade_type': 'BUY',
                'quantity': 100,
                'price': 50.0,
                'charges': 10.0,
                'settle_date': '2026-03-04',
                'retry_count': 0,
                'queued_at': datetime.now()
            })

        # Process in-memory queue
        self.service._process_in_memory_queue()

        # All items should be processed
        assert self.service._in_memory_queue.empty()
        assert mock_position_service.calculate_position.call_count == 3

    def test_in_memory_retry_on_failure(self):
        """Test failed in-memory items are re-queued for retry."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            False, "Failed", None
        )
        self.service.position_service = mock_position_service

        item = {
            'queue_id': 1,
            'trade_id': 100,
            'portfolio_id': 'FUND-001',
            'security_id': 'AAPL',
            'trade_type': 'BUY',
            'quantity': 100,
            'price': 50.0,
            'charges': 10.0,
            'settle_date': '2026-03-04',
            'retry_count': 0,
            'queued_at': datetime.now()
        }

        # Process single item (not the full queue loop)
        self.service._process_item(item, is_db_queue=False)

        # Item should be re-queued with incremented retry count
        assert not self.service._in_memory_queue.empty()
        requeued = self.service._in_memory_queue.get()
        assert requeued['retry_count'] == 1


class TestSynchronousProcessing:
    """Test synchronous (immediate) processing."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_process_immediately(self):
        """Test immediate processing bypasses queue."""
        mock_position_service = MagicMock()
        mock_position_service.calculate_position.return_value = (
            True, "Position updated", {'quantity': 100, 'average_cost': 50.1}
        )
        self.service.position_service = mock_position_service

        success, message, position = self.service.process_immediately(
            trade_id=12345,
            portfolio_id='FUND-001',
            security_id='AAPL',
            trade_type='BUY',
            quantity=Decimal('100'),
            price=Decimal('50.00'),
            charges=Decimal('10.00'),
            settle_date='2026-03-04',
            updated_by='test_user'
        )

        assert success is True
        assert position is not None
        mock_position_service.calculate_position.assert_called_once()


class TestQueueStatistics:
    """Test queue statistics."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_get_queue_statistics(self):
        """Test getting queue statistics."""
        mock_results = [
            {'status': 'PENDING', 'count': 10, 'avg_retries': 0},
            {'status': 'COMPLETED', 'count': 100, 'avg_retries': 0},
            {'status': 'FAILED', 'count': 2, 'avg_retries': 2.5}
        ]

        with patch('trade.services.position_queue_service.impala_manager') as mock_impala:
            mock_impala.execute_query.return_value = mock_results

            stats = self.service.get_queue_statistics()

            assert stats['pending'] == 10
            assert stats['completed'] == 100
            assert stats['failed'] == 2
            assert stats['total'] == 112


class TestWorkerLifecycle:
    """Test worker start/stop."""

    def setup_method(self):
        self.service = PositionQueueService()

    def test_worker_start_stop(self):
        """Test starting and stopping worker."""
        # Start worker
        self.service.start_worker()
        assert self.service._worker_running is True
        assert self.service._worker_thread is not None

        # Stop worker
        self.service.stop_worker()
        assert self.service._worker_running is False


# =========================================================================
# Example Test Scenarios
# =========================================================================

EXAMPLE_SCENARIOS = """
Async Queue Test Scenarios for Manual Testing
==============================================

Scenario 1: Enqueue and Process
-------------------------------
1. Create a trade
2. Call enqueue_position_calculation()
3. Start worker: position_queue_service.start_worker()
4. Check position is calculated within 5 minutes

Scenario 2: Retry Logic
-----------------------
1. Enqueue a trade that will fail (invalid data)
2. Observe retry_count incrementing
3. After 3 retries, item moves to DEAD_LETTER

Scenario 3: SLA Monitoring
--------------------------
1. Enqueue trade and don't process
2. Wait > 5 minutes
3. Process - observe SLA breach warning in logs

Commands to run tests:
- pytest trade/tests/test_position_queue_service.py -v
- pytest trade/tests/test_position_queue_service.py -v -k "test_enqueue"
- pytest trade/tests/test_position_queue_service.py -v -k "test_sla"
"""

if __name__ == '__main__':
    print(EXAMPLE_SCENARIOS)
