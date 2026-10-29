"""
Tests for trade/services/cash_flow_service.py
"""

from unittest.mock import patch, MagicMock

from django.test import TestCase

from trade.services.cash_flow_service import CashFlowService


class CashFlowServiceTestCase(TestCase):
    def setUp(self):
        self.service = CashFlowService()

    @patch.object(CashFlowService, 'repository', create=True)
    def test_list_all_delegates_to_repository(self, mock_repo):
        mock_repo.get_all.return_value = [{'cf_id': 1}]
        with patch.object(self.service, 'repository', mock_repo):
            result = self.service.list_all(limit=10)
        mock_repo.get_all.assert_called_once()

    def test_status_constants(self):
        self.assertEqual(CashFlowService.STATUS_INITIAL, 'INITIAL')
        self.assertEqual(CashFlowService.STATUS_MODIFIED, 'MODIFIED')
        self.assertEqual(CashFlowService.STATUS_APPROVED, 'APPROVED')
        self.assertEqual(CashFlowService.STATUS_REJECTED, 'REJECTED')

    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_list_all_passes_filters(self, mock_repo):
        mock_repo.get_all.return_value = []
        service = CashFlowService()
        service.list_all(status='INITIAL', search='test', portfolio_short_name='PORT001')
        mock_repo.get_all.assert_called_once_with(
            limit=1000,
            offset=0,
            status='INITIAL',
            search='test',
            portfolio_short_name='PORT001',
            cash_flow_type=None
        )

    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_get_by_id(self, mock_repo):
        mock_repo.get_by_id.return_value = {'cf_id': 42}
        service = CashFlowService()
        result = service.get_by_id(42)
        self.assertEqual(result['cf_id'], 42)
        mock_repo.get_by_id.assert_called_once_with(42)

    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_get_by_id_not_found(self, mock_repo):
        mock_repo.get_by_id.return_value = None
        service = CashFlowService()
        result = service.get_by_id(9999)
        self.assertIsNone(result)

    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_get_pending_approvals(self, mock_repo):
        mock_repo.get_pending_approvals.return_value = []
        service = CashFlowService()
        result = service.get_pending_approvals(limit=25)
        mock_repo.get_pending_approvals.assert_called_once_with(limit=25)

    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_get_by_portfolio(self, mock_repo):
        mock_repo.get_by_portfolio.return_value = [{'cf_id': 1}]
        service = CashFlowService()
        result = service.get_by_portfolio('PORT001')
        mock_repo.get_by_portfolio.assert_called_once()
        self.assertEqual(len(result), 1)

    @patch('trade.services.cash_flow_service.trade_validation_repository')
    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_create_missing_required_field_returns_error(self, mock_repo, mock_val_repo):
        service = CashFlowService()
        cf_data = {
            'cash_flow_type': 'DIVIDEND',
            'value_date': '2024-01-15',
            'payment_date': '2024-01-16',
            'local_ccy': 'USD',
            # Missing portfolio_short_name
        }
        success, cf_id, error = service.create(cf_data, '1', 'testuser', 'test@example.com')
        self.assertFalse(success)
        self.assertIsNone(cf_id)
        self.assertIn('required', error.lower())

    @patch('trade.services.cash_flow_service.AuditLogKuduRepository')
    @patch('trade.services.cash_flow_service.trade_validation_repository')
    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_create_invalid_portfolio_returns_error(self, mock_repo, mock_val_repo, mock_audit):
        validation_result = MagicMock()
        validation_result.is_valid = False
        validation_result.message = 'Portfolio not found'
        mock_val_repo.validate_portfolio.return_value = validation_result

        service = CashFlowService()
        cf_data = {
            'portfolio_short_name': 'INVALID',
            'cash_flow_type': 'DIVIDEND',
            'value_date': '2024-01-15',
            'payment_date': '2024-01-16',
            'local_ccy': 'USD',
        }
        success, cf_id, error = service.create(cf_data, '1', 'testuser', 'test@example.com')
        self.assertFalse(success)
        self.assertEqual(error, 'Portfolio not found')

    @patch('trade.services.cash_flow_service.AuditLogKuduRepository')
    @patch('trade.services.cash_flow_service.trade_validation_repository')
    @patch('trade.services.cash_flow_service.cash_flow_repository')
    def test_create_success(self, mock_repo, mock_val_repo, mock_audit):
        validation_result = MagicMock()
        validation_result.is_valid = True
        mock_val_repo.validate_portfolio.return_value = validation_result

        mock_repo.get_by_cash_flow_number.return_value = None
        mock_repo.generate_cash_flow_number.return_value = 'CF-001'
        mock_repo.insert.return_value = (True, 101)
        mock_repo.insert_history.return_value = True

        service = CashFlowService()
        cf_data = {
            'portfolio_short_name': 'PORT001',
            'cash_flow_type': 'DIVIDEND',
            'value_date': '2024-01-15',
            'payment_date': '2024-01-16',
            'local_ccy': 'USD',
        }
        success, cf_id, error = service.create(cf_data, '1', 'testuser', 'test@example.com')
        self.assertTrue(success)
        self.assertEqual(cf_id, 101)
        self.assertIsNone(error)
