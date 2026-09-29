"""
Tests for trade/services/trade_event_queue_service.py
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase

from trade.services.trade_event_queue_service import TradeEventQueueService


class TradeEventQueueServiceConstantsTestCase(TestCase):
    def test_status_constants(self):
        self.assertEqual(TradeEventQueueService.STATUS_PENDING, 'PENDING')
        self.assertEqual(TradeEventQueueService.STATUS_PROCESSING, 'PROCESSING')
        self.assertEqual(TradeEventQueueService.STATUS_COMPLETED, 'COMPLETED')
        self.assertEqual(TradeEventQueueService.STATUS_FAILED, 'FAILED')
        self.assertEqual(TradeEventQueueService.STATUS_DEAD_LETTER, 'DEAD_LETTER')

    def test_config_constants(self):
        self.assertEqual(TradeEventQueueService.MAX_RETRIES, 3)
        self.assertEqual(TradeEventQueueService.BATCH_SIZE, 50)
        self.assertGreater(TradeEventQueueService.POLL_INTERVAL_SECONDS, 0)


class TradeEventQueueServiceWorkerTestCase(TestCase):
    def setUp(self):
        self.service = TradeEventQueueService()

    def test_initial_state_not_running(self):
        self.assertFalse(self.service.is_running())

    def test_start_worker_returns_true(self):
        result = self.service.start_worker()
        self.assertTrue(result)
        self.assertTrue(self.service.is_running())
        self.service.stop_worker()

    def test_start_worker_second_call_returns_false(self):
        self.service.start_worker()
        result = self.service.start_worker()
        self.assertFalse(result)
        self.service.stop_worker()

    def test_stop_worker_returns_true_when_running(self):
        self.service.start_worker()
        result = self.service.stop_worker()
        self.assertTrue(result)

    def test_stop_worker_returns_false_when_not_running(self):
        result = self.service.stop_worker()
        self.assertFalse(result)

    def test_get_stats_returns_dict(self):
        stats = self.service.get_stats()
        self.assertIn('processed', stats)
        self.assertIn('failed', stats)
        self.assertIn('dead_letter', stats)
        self.assertIn('is_running', stats)


class TradeEventQueueServiceHelperTestCase(TestCase):
    def setUp(self):
        self.service = TradeEventQueueService()

    def test_escape_normal_string(self):
        result = self.service._escape('hello')
        self.assertEqual(result, 'hello')

    def test_escape_single_quote(self):
        result = self.service._escape("it's")
        self.assertEqual(result, "it''s")

    def test_escape_none(self):
        result = self.service._escape(None)
        self.assertEqual(result, '')

    def test_calculate_charges_all_zero(self):
        trade_data = {}
        result = self.service._calculate_charges(trade_data)
        self.assertEqual(result, Decimal('0'))

    def test_calculate_charges_manual(self):
        trade_data = {
            'commission': '10.00',
            'sec_fee': '5.00',
            'other_charges': '2.50',
        }
        result = self.service._calculate_charges(trade_data)
        self.assertEqual(result, Decimal('17.50'))

    def test_calculate_charges_auto(self):
        trade_data = {
            'calculated_commission': '8.00',
            'calculated_clearing_fee': '2.00',
            'calculated_trading_fee': '1.50',
            'calculated_gst': '0.50',
            'calculated_other_fees': '0.00',
        }
        result = self.service._calculate_charges(trade_data)
        self.assertEqual(result, Decimal('12.00'))

    def test_calculate_charges_mixed(self):
        trade_data = {
            'commission': '10.00',
            'calculated_commission': '8.00',
        }
        result = self.service._calculate_charges(trade_data)
        self.assertEqual(result, Decimal('18.00'))

    def test_calculate_charges_none_values(self):
        trade_data = {'commission': None, 'sec_fee': None}
        result = self.service._calculate_charges(trade_data)
        self.assertEqual(result, Decimal('0'))


class TradeEventQueueServiceQueryTestCase(TestCase):
    def setUp(self):
        self.service = TradeEventQueueService()

    @patch('trade.services.trade_event_queue_service.impala_manager')
    def test_get_pending_count(self, mock_impala):
        mock_impala.execute_query.return_value = [{'cnt': 5}]
        result = self.service.get_pending_count()
        self.assertEqual(result, 5)

    @patch('trade.services.trade_event_queue_service.impala_manager')
    def test_get_pending_count_empty(self, mock_impala):
        mock_impala.execute_query.return_value = []
        result = self.service.get_pending_count()
        self.assertEqual(result, 0)

    @patch('trade.services.trade_event_queue_service.impala_manager')
    def test_get_pending_count_exception(self, mock_impala):
        mock_impala.execute_query.side_effect = Exception("DB error")
        result = self.service.get_pending_count()
        self.assertEqual(result, 0)

    @patch('trade.services.trade_event_queue_service.impala_manager')
    def test_get_failed_events(self, mock_impala):
        mock_impala.execute_query.return_value = [
            {'event_id': 1, 'status': 'FAILED', 'retry_count': 3}
        ]
        result = self.service.get_failed_events(limit=10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'FAILED')

    @patch('trade.services.trade_event_queue_service.impala_manager')
    def test_get_failed_events_empty(self, mock_impala):
        mock_impala.execute_query.return_value = []
        result = self.service.get_failed_events()
        self.assertEqual(result, [])
