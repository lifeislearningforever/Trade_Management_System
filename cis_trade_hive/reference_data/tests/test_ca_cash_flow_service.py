"""
CA Cash Flow Service Tests

Tests for CACashFlowService with 95%+ coverage target.
All database operations are mocked.
"""

import pytest
from django.test import TestCase
from unittest.mock import patch, Mock, MagicMock
from decimal import Decimal
from datetime import datetime


class CACashFlowServiceTestCase(TestCase):
    """Test cases for CACashFlowService"""

    def setUp(self):
        """Set up test fixtures"""
        self.sample_ca_data = {
            'ca_id': 1710758300000,
            'ca_number': 'CA-20260318-00001',
            'ca_type': 'DIVIDEND',
            'security_name': 'AAPL',
            'portfolio_name': 'EQUITY_FUND',
            'ex_date': '2026-03-15',
            'record_date': '2026-03-16',
            'payment_date': '2026-03-20',
            'price': Decimal('0.25'),
            'currency': 'USD',
        }

        self.sample_queue_entry = {
            'queue_id': 1710758400000,
            'ca_id': 1710758300000,
            'ca_number': 'CA-20260318-00001',
            'ca_type': 'DIVIDEND',
            'security_name': 'AAPL',
            'portfolio_name': None,
            'ex_date': '2026-03-15',
            'record_date': '2026-03-16',
            'payment_date': '2026-03-20',
            'price': Decimal('0.25'),
            'currency': 'USD',
            'status': 'PENDING',
            'created_by': 'test_user',
        }

        self.sample_holdings = [
            {
                'portfolio_short_name': 'EQUITY_FUND_A',
                'security_label': 'AAPL',
                'quantity': Decimal('10000'),
                'average_cost': Decimal('150.00'),
                'security_currency': 'USD',
            },
            {
                'portfolio_short_name': 'GROWTH_FUND_B',
                'security_label': 'AAPL',
                'quantity': Decimal('5000'),
                'average_cost': Decimal('155.00'),
                'security_currency': 'USD',
            },
        ]

    # =========================================================================
    # _escape tests
    # =========================================================================

    def test_escape_none(self):
        """Test _escape with None"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        service = CACashFlowService()
        result = service._escape(None)
        self.assertEqual(result, '')

    def test_escape_string(self):
        """Test _escape with string"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        service = CACashFlowService()
        result = service._escape("test's value")
        self.assertEqual(result, "test''s value")

    # =========================================================================
    # queue_ca_for_processing tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_dividend(self, mock_repo):
        """Test queue_ca_for_processing queues DIVIDEND type"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (True, 1710758400000)

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=self.sample_ca_data,
            username='test_user'
        )

        self.assertTrue(success)
        self.assertIsNotNone(queue_id)
        mock_repo.insert.assert_called_once()

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_interest(self, mock_repo):
        """Test queue_ca_for_processing queues INTEREST type"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (True, 1710758400000)

        ca_data = self.sample_ca_data.copy()
        ca_data['ca_type'] = 'INTEREST'

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=ca_data,
            username='test_user'
        )

        self.assertTrue(success)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_coupon(self, mock_repo):
        """Test queue_ca_for_processing queues COUPON type"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (True, 1710758400000)

        ca_data = self.sample_ca_data.copy()
        ca_data['ca_type'] = 'COUPON'

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=ca_data,
            username='test_user'
        )

        self.assertTrue(success)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_stock_split_queued(self, mock_repo):
        """Test queue_ca_for_processing queues STOCK_SPLIT type for position adjustment"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (True, 1710758400000)

        ca_data = self.sample_ca_data.copy()
        ca_data['ca_type'] = 'STOCK_SPLIT'

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=ca_data,
            username='test_user'
        )

        self.assertTrue(success)
        self.assertEqual(queue_id, 1710758400000)
        mock_repo.insert.assert_called_once()

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_bonus_issue_queued(self, mock_repo):
        """Test queue_ca_for_processing queues BONUS_ISSUE type for position adjustment"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (True, 1710758400000)

        ca_data = self.sample_ca_data.copy()
        ca_data['ca_type'] = 'BONUS_ISSUE'

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=ca_data,
            username='test_user'
        )

        self.assertTrue(success)
        self.assertEqual(queue_id, 1710758400000)
        mock_repo.insert.assert_called_once()

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_unknown_type_skipped(self, mock_repo):
        """Test queue_ca_for_processing skips unknown CA types"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        ca_data = self.sample_ca_data.copy()
        ca_data['ca_type'] = 'UNKNOWN_TYPE'

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=ca_data,
            username='test_user'
        )

        self.assertTrue(success)
        self.assertIsNone(queue_id)
        mock_repo.insert.assert_not_called()

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_failure(self, mock_repo):
        """Test queue_ca_for_processing handles insert failure"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.return_value = (False, None)

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=self.sample_ca_data,
            username='test_user'
        )

        self.assertFalse(success)
        self.assertIsNone(queue_id)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_queue_ca_for_processing_exception(self, mock_repo):
        """Test queue_ca_for_processing handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_repo.insert.side_effect = Exception("Database error")

        service = CACashFlowService()
        success, queue_id = service.queue_ca_for_processing(
            ca_id=1710758300000,
            ca_data=self.sample_ca_data,
            username='test_user'
        )

        self.assertFalse(success)
        self.assertIsNone(queue_id)

    # =========================================================================
    # get_holdings_for_ca tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_success(self, mock_impala):
        """Test get_holdings_for_ca returns holdings"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL',
            as_of_date='2026-03-15'
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['portfolio_short_name'], 'EQUITY_FUND_A')

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_returns_all_portfolios(self, mock_impala):
        """Test get_holdings_for_ca returns all portfolios holding security (no filter)"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        # CA applies at security level - returns ALL portfolios holding the security
        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL',
            as_of_date='2026-03-15'
        )

        # Should return all portfolios holding AAPL
        self.assertEqual(len(result), 2)
        call_args = mock_impala.execute_query.call_args[0][0]
        # Query should filter by security but not portfolio
        self.assertIn('security_label', call_args)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_multiple_securities(self, mock_impala):
        """Test get_holdings_for_ca with multiple securities"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL,MSFT',
            as_of_date='2026-03-15'
        )

        call_args = mock_impala.execute_query.call_args[0][0]
        self.assertIn('AAPL', call_args)
        self.assertIn('MSFT', call_args)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_finds_multiple_portfolios(self, mock_impala):
        """Test get_holdings_for_ca finds all portfolios holding security"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        # Simulate multiple portfolios holding the same security
        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL',
            as_of_date='2026-03-15'
        )

        # Should return both portfolios holding AAPL
        self.assertEqual(len(result), 2)
        portfolio_names = [h['portfolio_short_name'] for h in result]
        self.assertIn('EQUITY_FUND_A', portfolio_names)
        self.assertIn('GROWTH_FUND_B', portfolio_names)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_no_date(self, mock_impala):
        """Test get_holdings_for_ca uses today when no date provided"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL',
            as_of_date=None
        )

        self.assertEqual(len(result), 2)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_empty(self, mock_impala):
        """Test get_holdings_for_ca returns empty list"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.return_value = []

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='UNKNOWN',
            as_of_date='2026-03-15'
        )

        self.assertEqual(result, [])

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_empty_security(self, mock_impala):
        """Test get_holdings_for_ca with empty security name"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='',
            as_of_date='2026-03-15'
        )

        self.assertEqual(result, [])
        mock_impala.execute_query.assert_not_called()

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    def test_get_holdings_for_ca_exception(self, mock_impala):
        """Test get_holdings_for_ca handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.side_effect = Exception("Database error")

        service = CACashFlowService()
        result = service.get_holdings_for_ca(
            security_name='AAPL',
            as_of_date='2026-03-15'
        )

        self.assertEqual(result, [])

    # =========================================================================
    # create_cash_flow_from_ca tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    def test_create_cash_flow_from_ca_success(self, mock_cf_repo):
        """Test create_cash_flow_from_ca creates cash flow"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_cf_repo.insert.return_value = (True, 1710758500000)

        service = CACashFlowService()
        success, cf_id, error = service.create_cash_flow_from_ca(
            ca_id=1710758300000,
            ca_number='CA-20260318-00001',
            ca_type='DIVIDEND',
            portfolio_short_name='EQUITY_FUND_A',
            security_name='AAPL',
            quantity=Decimal('10000'),
            amount_fc=Decimal('2500.00'),
            amount_lc=Decimal('2500.00'),
            foreign_currency='USD',
            local_currency='USD',
            fx_rate=Decimal('1.0'),
            ex_date='2026-03-15',
            record_date='2026-03-16',
            payment_date='2026-03-20',
            created_by='test_user'
        )

        self.assertTrue(success)
        self.assertIsNotNone(cf_id)
        self.assertIsNone(error)

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    def test_create_cash_flow_from_ca_failure(self, mock_cf_repo):
        """Test create_cash_flow_from_ca handles insert failure"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_cf_repo.insert.return_value = (False, None)

        service = CACashFlowService()
        success, cf_id, error = service.create_cash_flow_from_ca(
            ca_id=1710758300000,
            ca_number='CA-20260318-00001',
            ca_type='DIVIDEND',
            portfolio_short_name='EQUITY_FUND_A',
            security_name='AAPL',
            quantity=Decimal('10000'),
            amount_fc=Decimal('2500.00'),
            amount_lc=Decimal('2500.00'),
            foreign_currency='USD',
            local_currency='USD',
            fx_rate=Decimal('1.0'),
            ex_date='2026-03-15',
            record_date='2026-03-16',
            payment_date='2026-03-20',
            created_by='test_user'
        )

        self.assertFalse(success)
        self.assertIsNone(cf_id)
        self.assertIsNotNone(error)

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    def test_create_cash_flow_from_ca_exception(self, mock_cf_repo):
        """Test create_cash_flow_from_ca handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_cf_repo.insert.side_effect = Exception("Database error")

        service = CACashFlowService()
        success, cf_id, error = service.create_cash_flow_from_ca(
            ca_id=1710758300000,
            ca_number='CA-20260318-00001',
            ca_type='DIVIDEND',
            portfolio_short_name='EQUITY_FUND_A',
            security_name='AAPL',
            quantity=Decimal('10000'),
            amount_fc=Decimal('2500.00'),
            amount_lc=Decimal('2500.00'),
            foreign_currency='USD',
            local_currency='USD',
            fx_rate=Decimal('1.0'),
            ex_date='2026-03-15',
            record_date='2026-03-16',
            payment_date='2026-03-20',
            created_by='test_user'
        )

        self.assertFalse(success)
        self.assertIsNotNone(error)

    # =========================================================================
    # process_ca_cash_flows tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_success(self, mock_queue_repo, mock_impala, mock_cf_repo):
        """Test process_ca_cash_flows creates cash flows"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_queue_repo.mark_processing.return_value = True
        mock_queue_repo.mark_completed.return_value = True
        mock_queue_repo.insert_log.return_value = (True, 123)
        mock_impala.execute_query.return_value = self.sample_holdings
        mock_cf_repo.insert.return_value = (True, 1710758500000)

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertTrue(success)
        self.assertEqual(cf_count, 2)  # Two portfolios
        self.assertEqual(amount, Decimal('3750.00'))  # (10000 + 5000) * 0.25

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_queue_not_found(self, mock_queue_repo):
        """Test process_ca_cash_flows handles queue not found"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.return_value = None

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=999999
        )

        self.assertFalse(success)
        self.assertIn('not found', message)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_invalid_price(self, mock_queue_repo):
        """Test process_ca_cash_flows handles invalid price"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        queue_entry = self.sample_queue_entry.copy()
        queue_entry['price'] = None
        mock_queue_repo.get_by_id.return_value = queue_entry
        mock_queue_repo.mark_failed.return_value = True

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertFalse(success)
        self.assertIn('Invalid price', message)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_zero_price(self, mock_queue_repo):
        """Test process_ca_cash_flows handles zero price"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        queue_entry = self.sample_queue_entry.copy()
        queue_entry['price'] = Decimal('0')
        mock_queue_repo.get_by_id.return_value = queue_entry
        mock_queue_repo.mark_failed.return_value = True

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertFalse(success)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_no_holdings(self, mock_queue_repo, mock_impala):
        """Test process_ca_cash_flows with no holdings"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_queue_repo.mark_processing.return_value = True
        mock_queue_repo.mark_completed.return_value = True
        mock_impala.execute_query.return_value = []

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertTrue(success)
        self.assertEqual(cf_count, 0)
        self.assertIn('No holdings found', message)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_dry_run(self, mock_queue_repo, mock_impala):
        """Test process_ca_cash_flows dry run mode"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_impala.execute_query.return_value = self.sample_holdings

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000,
            dry_run=True
        )

        self.assertTrue(success)
        self.assertEqual(cf_count, 2)
        mock_queue_repo.mark_processing.assert_not_called()
        mock_queue_repo.mark_completed.assert_not_called()

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_partial_failure(self, mock_queue_repo, mock_impala, mock_cf_repo):
        """Test process_ca_cash_flows with partial failures"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_queue_repo.mark_processing.return_value = True
        mock_queue_repo.mark_failed.return_value = True
        mock_queue_repo.insert_log.return_value = (True, 123)
        # First returns holdings, subsequent calls for position updates return empty
        mock_impala.execute_query.side_effect = [self.sample_holdings, None, None, None, None]
        mock_impala.execute_write.return_value = True
        # First succeeds, second fails
        mock_cf_repo.insert.side_effect = [(True, 123), (False, None)]

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertFalse(success)
        self.assertEqual(cf_count, 1)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_cash_flows_exception(self, mock_queue_repo):
        """Test process_ca_cash_flows handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_by_id.side_effect = Exception("Database error")
        mock_queue_repo.mark_failed.return_value = True

        service = CACashFlowService()
        success, message, cf_count, amount = service.process_ca_cash_flows(
            queue_id=1710758400000
        )

        self.assertFalse(success)
        self.assertIn('Error', message)

    # =========================================================================
    # process_pending_cas tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.CashFlowRepository')
    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_pending_cas_success(self, mock_queue_repo, mock_impala, mock_cf_repo):
        """Test process_pending_cas processes all pending"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_queue_repo.mark_processing.return_value = True
        mock_queue_repo.mark_completed.return_value = True
        mock_queue_repo.insert_log.return_value = (True, 123)
        mock_impala.execute_query.return_value = self.sample_holdings
        mock_cf_repo.insert.return_value = (True, 1710758500000)

        service = CACashFlowService()
        stats = service.process_pending_cas()

        self.assertEqual(stats['total_processed'], 1)
        self.assertEqual(stats['successful'], 1)
        self.assertEqual(stats['failed'], 0)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_pending_cas_empty(self, mock_queue_repo):
        """Test process_pending_cas with no pending entries"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_pending.return_value = []

        service = CACashFlowService()
        stats = service.process_pending_cas()

        self.assertEqual(stats['total_processed'], 0)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_pending_cas_with_payment_date(self, mock_queue_repo):
        """Test process_pending_cas filters by payment date"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_pending.return_value = []

        service = CACashFlowService()
        stats = service.process_pending_cas(payment_date='2026-03-20')

        mock_queue_repo.get_pending.assert_called_once()
        call_kwargs = mock_queue_repo.get_pending.call_args[1]
        self.assertEqual(call_kwargs['payment_date'], '2026-03-20')

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_pending_cas_dry_run(self, mock_queue_repo):
        """Test process_pending_cas dry run mode"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_pending.return_value = [self.sample_queue_entry]
        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry

        service = CACashFlowService()
        with patch.object(service, 'get_holdings_for_ca', return_value=self.sample_holdings):
            stats = service.process_pending_cas(dry_run=True)

        self.assertEqual(stats['total_processed'], 1)

    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_pending_cas_exception(self, mock_queue_repo):
        """Test process_pending_cas handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_pending.side_effect = Exception("Database error")

        service = CACashFlowService()
        stats = service.process_pending_cas()

        self.assertEqual(stats['total_processed'], 0)
        self.assertIn('Database error', stats['errors'][0])

    # =========================================================================
    # get_cash_flows_by_ca tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_get_cash_flows_by_ca_from_table(self, mock_queue_repo, mock_impala):
        """Test get_cash_flows_by_ca returns from cash flow table"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.return_value = [
            {'cf_id': 1, 'ca_id': 123, 'amount': 2500.00}
        ]

        service = CACashFlowService()
        result = service.get_cash_flows_by_ca(123)

        self.assertEqual(len(result), 1)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_get_cash_flows_by_ca_fallback_to_logs(self, mock_queue_repo, mock_impala):
        """Test get_cash_flows_by_ca falls back to logs"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_impala.execute_query.side_effect = Exception("Column not found")
        mock_queue_repo.get_logs_by_queue_id.return_value = [
            {'log_id': 1, 'ca_id': 123}
        ]

        service = CACashFlowService()
        result = service.get_cash_flows_by_ca(123)

        self.assertEqual(len(result), 1)

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_get_cash_flows_by_ca_exception(self, mock_queue_repo, mock_impala):
        """Test get_cash_flows_by_ca handles exceptions"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        mock_queue_repo.get_logs_by_queue_id.side_effect = Exception("Error")
        mock_impala.execute_query.side_effect = Exception("Error")

        service = CACashFlowService()
        result = service.get_cash_flows_by_ca(123)

        self.assertEqual(result, [])

    # =========================================================================
    # Constants and singleton tests
    # =========================================================================

    def test_cash_flow_ca_types(self):
        """Test CASH_FLOW_CA_TYPES constant"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        # Cash flow CA types include various dividend and interest types
        expected_types = ['DIVIDEND', 'SPECIAL_DIVIDEND', 'INTEREST', 'COUPON', 'ROC', 'CAPITAL_DISTRIBUTION']
        self.assertEqual(CACashFlowService.CASH_FLOW_CA_TYPES, expected_types)

    def test_ca_to_cf_type_map(self):
        """Test CA_TO_CF_TYPE_MAP constant"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        self.assertEqual(CACashFlowService.CA_TO_CF_TYPE_MAP['DIVIDEND'], 'DIVIDEND')
        self.assertEqual(CACashFlowService.CA_TO_CF_TYPE_MAP['INTEREST'], 'INTEREST')
        self.assertEqual(CACashFlowService.CA_TO_CF_TYPE_MAP['COUPON'], 'COUPON')

    def test_singleton_instance(self):
        """Test singleton instance exists"""
        from reference_data.services.ca_cash_flow_service import ca_cash_flow_service

        self.assertIsNotNone(ca_cash_flow_service)

    # =========================================================================
    # Edge case tests
    # =========================================================================

    @patch('reference_data.services.ca_cash_flow_service.impala_manager')
    @patch('reference_data.services.ca_cash_flow_service.ca_cash_flow_queue_repository')
    def test_process_ca_zero_quantity_skipped(self, mock_queue_repo, mock_impala):
        """Test process_ca_cash_flows skips zero quantity holdings"""
        from reference_data.services.ca_cash_flow_service import CACashFlowService

        holdings_with_zero = [
            {'portfolio_short_name': 'FUND_A', 'security_label': 'AAPL', 'quantity': Decimal('0')},
            {'portfolio_short_name': 'FUND_B', 'security_label': 'AAPL', 'quantity': Decimal('100')},
        ]

        mock_queue_repo.get_by_id.return_value = self.sample_queue_entry
        mock_queue_repo.mark_processing.return_value = True
        mock_queue_repo.mark_completed.return_value = True
        mock_queue_repo.insert_log.return_value = (True, 123)
        mock_impala.execute_query.return_value = holdings_with_zero

        with patch('reference_data.services.ca_cash_flow_service.CashFlowRepository') as mock_cf:
            mock_cf.insert.return_value = (True, 123)

            service = CACashFlowService()
            success, message, cf_count, amount = service.process_ca_cash_flows(
                queue_id=1710758400000
            )

            # Only one cash flow created (skipped zero quantity)
            self.assertEqual(cf_count, 1)
