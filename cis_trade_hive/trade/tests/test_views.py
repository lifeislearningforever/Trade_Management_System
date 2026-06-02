"""
Trade Views Tests

Comprehensive tests for trade views including:
- TradeWrapper class
- List, detail, create, edit views
- Workflow actions (submit, validate, settle, cancel)
- Pending approval views
- API endpoints
"""

import json
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock


class TradeWrapperTestCase(TestCase):
    """Test cases for TradeWrapper class"""

    def test_trade_wrapper_basic_fields(self):
        """Test TradeWrapper basic field mapping"""
        from trade.views import TradeWrapper

        data = {
            'trade_id': 1001,
            'deal_number': 'DEAL-001',
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'status': 'INITIAL'
        }

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.trade_id, 1001)
        self.assertEqual(wrapper.deal_number, 'DEAL-001')
        self.assertEqual(wrapper.trade_type, 'BUY')
        self.assertEqual(wrapper.portfolio_short_name, 'PORT001')
        self.assertEqual(wrapper.security_label, 'SEC001')
        self.assertEqual(wrapper.status, 'INITIAL')

    def test_trade_wrapper_numeric_fields(self):
        """Test TradeWrapper numeric field mapping"""
        from trade.views import TradeWrapper

        data = {
            'quantity': 100,
            'price': 50.25,
            'total_amount': 5025.00,
            'commission': 10.00,
            'accrued_interest': 5.00
        }

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.quantity, 100)
        self.assertEqual(wrapper.price, 50.25)
        self.assertEqual(wrapper.total_amount, 5025.00)
        self.assertEqual(wrapper.commission, 10.00)
        self.assertEqual(wrapper.accrued_interest, 5.00)

    def test_trade_wrapper_date_fields(self):
        """Test TradeWrapper date field mapping"""
        from trade.views import TradeWrapper

        data = {
            'trade_date': '2024-01-15',
            'settle_date': '2024-01-17',
            'org_pur_date': '2024-01-10'
        }

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.trade_date, '2024-01-15')
        self.assertEqual(wrapper.settle_date, '2024-01-17')
        self.assertEqual(wrapper.org_pur_date, '2024-01-10')

    def test_trade_wrapper_udf_fields(self):
        """Test TradeWrapper UDF field mapping"""
        from trade.views import TradeWrapper

        data = {
            'udf_fund_type': 'EQUITY',
            'udf_section_31_26': 'SEC_31',
            'udf_disclosure_req': True,
            'udf_counter_pledged': False,
            'udf_currency_hedge': True
        }

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.udf_fund_type, 'EQUITY')
        self.assertEqual(wrapper.udf_section_31_26, 'SEC_31')
        self.assertTrue(wrapper.udf_disclosure_req)
        self.assertFalse(wrapper.udf_counter_pledged)
        self.assertTrue(wrapper.udf_currency_hedge)

    def test_trade_wrapper_workflow_fields(self):
        """Test TradeWrapper workflow field mapping"""
        from trade.views import TradeWrapper

        data = {
            'submitted_by': 'maker_user',
            'submitted_at': '2024-01-15 10:00:00',
            'validated_by': 'checker_user',
            'validated_at': '2024-01-15 11:00:00',
            'validation_comments': 'Approved',
            'settled_by': 'settler_user',
            'settled_at': '2024-01-17 10:00:00'
        }

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.submitted_by, 'maker_user')
        self.assertEqual(wrapper.validated_by, 'checker_user')
        self.assertEqual(wrapper.validation_comments, 'Approved')
        self.assertEqual(wrapper.settled_by, 'settler_user')

    def test_trade_wrapper_default_values(self):
        """Test TradeWrapper default values for missing fields"""
        from trade.views import TradeWrapper

        data = {}

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.trade_id, 0)
        self.assertEqual(wrapper.deal_number, '')
        self.assertEqual(wrapper.quantity, 0)
        self.assertEqual(wrapper.status, 'INITIAL')
        self.assertFalse(wrapper.is_active)
        self.assertFalse(wrapper.is_deleted)

    def test_trade_wrapper_data_attribute(self):
        """Test TradeWrapper stores original data"""
        from trade.views import TradeWrapper

        data = {'trade_id': 1001, 'custom_field': 'custom_value'}

        wrapper = TradeWrapper(data)

        self.assertEqual(wrapper.data, data)
        self.assertEqual(wrapper.data['custom_field'], 'custom_value')


class GetUserInfoTestCase(TestCase):
    """Test cases for get_user_info helper function"""

    def test_get_user_info_from_session(self):
        """Test extracting user info from session"""
        from trade.views import get_user_info

        mock_request = Mock()
        mock_session = MagicMock()
        mock_session.get.side_effect = lambda key, default='': {
            'user_login': 'testuser',
            'user_id': 123,
            'user_email': 'test@example.com'
        }.get(key, default)
        mock_request.session = mock_session

        result = get_user_info(mock_request)

        self.assertEqual(result['username'], 'testuser')
        self.assertEqual(result['user_id'], '123')
        self.assertEqual(result['user_email'], 'test@example.com')

    def test_get_user_info_defaults(self):
        """Test get_user_info with missing session values"""
        from trade.views import get_user_info

        mock_request = Mock()
        mock_session = MagicMock()
        mock_session.get.side_effect = lambda key, default='': default
        mock_request.session = mock_session

        result = get_user_info(mock_request)

        self.assertEqual(result['username'], 'anonymous')


class TradeListViewTestCase(TestCase):
    """Test cases for trade_list view"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.trade_dropdown_service')
    def test_trade_list_basic(self, mock_dropdown, mock_repo):
        """Test basic trade list view"""
        mock_repo.get_all_trades_multi_filter.return_value = [
            {'trade_id': 1, 'deal_number': 'DEAL-001', 'status': 'INITIAL'}
        ]
        mock_repo.get_trade_statistics.return_value = {
            'total_trades': 1,
            'pending_validation': 0,
            'pending_settlement': 0,
            'settled': 0
        }
        mock_dropdown.get_all_dropdown_options.return_value = {
            'trade_types': [],
            'portfolios': [],
            'securities': []
        }

        response = self.client.get(reverse('trade:list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'trade/trade_list.html')

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.trade_dropdown_service')
    def test_trade_list_with_filters(self, mock_dropdown, mock_repo):
        """Test trade list with filters"""
        mock_repo.get_all_trades_multi_filter.return_value = []
        mock_repo.get_trade_statistics.return_value = {'total_trades': 0, 'pending_validation': 0, 'pending_settlement': 0}
        mock_dropdown.get_all_dropdown_options.return_value = {'trade_types': [], 'portfolios': [], 'securities': []}

        response = self.client.get(
            reverse('trade:list'),
            {'status': 'INITIAL', 'trade_type': 'BUY', 'search': 'test'}
        )

        self.assertEqual(response.status_code, 200)
        mock_repo.get_all_trades_multi_filter.assert_called_once()

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_list_csv_export(self, mock_audit, mock_dropdown, mock_repo):
        """Test trade list CSV export"""
        mock_repo.get_all_trades_multi_filter.return_value = [
            {
                'deal_number': 'DEAL-001',
                'trade_type': 'BUY',
                'portfolio_short_name': 'PORT001',
                'security_label': 'SEC001',
                'trade_date': '2024-01-15',
                'settle_date': '2024-01-17',
                'quantity': 100,
                'price': 50.00,
                'total_amount': 5000,
                'status': 'INITIAL'
            }
        ]
        mock_repo.get_trade_statistics.return_value = {'total_trades': 1, 'pending_validation': 0, 'pending_settlement': 0}
        mock_dropdown.get_all_dropdown_options.return_value = {'trade_types': [], 'portfolios': [], 'securities': []}

        response = self.client.get(
            reverse('trade:list'),
            {'export': 'csv'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.trade_dropdown_service')
    def test_trade_list_pagination(self, mock_dropdown, mock_repo):
        """Test trade list pagination"""
        # Create more than one page of trades
        trades = [{'trade_id': i, 'deal_number': f'DEAL-{i}', 'status': 'INITIAL'} for i in range(30)]
        mock_repo.get_all_trades_multi_filter.return_value = trades
        mock_repo.get_trade_statistics.return_value = {'total_trades': 30, 'pending_validation': 0, 'pending_settlement': 0}
        mock_dropdown.get_all_dropdown_options.return_value = {'trade_types': [], 'portfolios': [], 'securities': []}

        response = self.client.get(reverse('trade:list'), {'page': 2})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['page_obj'].has_previous())


class TradeDetailViewTestCase(TestCase):
    """Test cases for trade_detail view"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_detail_basic(self, mock_repo):
        """Test basic trade detail view"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'INITIAL',
            'src_system': 'CIS'
        }
        mock_repo.get_trade_history.return_value = []

        response = self.client.get(reverse('trade:detail', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'trade/trade_detail.html')

    @patch('trade.views.trade_kudu_repository')
    def test_trade_detail_not_found(self, mock_repo):
        """Test trade detail with non-existent trade"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.get(reverse('trade:detail', kwargs={'trade_id': 9999}))

        self.assertEqual(response.status_code, 404)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_detail_action_permissions_initial(self, mock_repo):
        """Test action permissions for INITIAL status"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'INITIAL',
            'src_system': 'CIS'
        }
        mock_repo.get_trade_history.return_value = []

        response = self.client.get(reverse('trade:detail', kwargs={'trade_id': 1}))

        self.assertTrue(response.context['can_edit'])
        self.assertTrue(response.context['can_submit'])
        self.assertFalse(response.context['can_validate'])
        self.assertFalse(response.context['can_settle'])

    @patch('trade.views.trade_kudu_repository')
    def test_trade_detail_action_permissions_pending_validation(self, mock_repo):
        """Test action permissions for PENDING_VALIDATION status"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'PENDING_VALIDATION',
            'src_system': 'CIS'
        }
        mock_repo.get_trade_history.return_value = []

        response = self.client.get(reverse('trade:detail', kwargs={'trade_id': 1}))

        self.assertFalse(response.context['can_edit'])
        self.assertFalse(response.context['can_submit'])
        self.assertTrue(response.context['can_validate'])

    @patch('trade.views.trade_kudu_repository')
    def test_trade_detail_gmp_record_no_actions(self, mock_repo):
        """Test GMP records have no edit actions"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'INITIAL',
            'src_system': 'GMP'  # Non-CIS record
        }
        mock_repo.get_trade_history.return_value = []

        response = self.client.get(reverse('trade:detail', kwargs={'trade_id': 1}))

        self.assertFalse(response.context['can_edit'])
        self.assertFalse(response.context['can_submit'])
        self.assertFalse(response.context['is_cis_record'])


class TradeCreateViewTestCase(TestCase):
    """Test cases for trade_create view"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('trade.views.trade_dropdown_service')
    def test_trade_create_get(self, mock_dropdown):
        """Test trade create form GET"""
        mock_dropdown.get_all_dropdown_options.return_value = {
            'trade_types': [{'value': 'BUY', 'label': 'Buy'}]
        }

        response = self.client.get(reverse('trade:create'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'trade/trade_form.html')

    @patch('trade.views.cache')
    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_create_post_success(self, mock_audit, mock_repo, mock_dropdown, mock_cache):
        """Test successful trade creation using fast insert"""
        mock_cache.get.return_value = None  # No dedup hit
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.validate_trade_data.return_value = (True, [], {})
        mock_repo.insert_trade_fast.return_value = (1001, 'DEAL-20240115-1001')

        response = self.client.post(reverse('trade:create'), {
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'trade_date': '2024-01-15',
            'quantity': 100,
            'price': 50.00
        })

        self.assertEqual(response.status_code, 302)  # Redirect
        mock_repo.insert_trade_fast.assert_called_once()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_create_post_validation_failure(self, mock_repo, mock_dropdown):
        """Test trade creation with validation failure"""
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.validate_trade_data.return_value = (False, ['Portfolio is required'], {})  # Now returns 3 values

        response = self.client.post(reverse('trade:create'), {
            'trade_type': 'BUY',
            'security_label': 'SEC001',
            'trade_date': '2024-01-15'
        })

        self.assertEqual(response.status_code, 200)  # Stays on form
        # Should show error message


class TradeEditViewTestCase(TestCase):
    """Test cases for trade_edit view"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_get(self, mock_repo, mock_dropdown):
        """Test trade edit form GET"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'INITIAL',
            'src_system': 'CIS'
        }
        mock_dropdown.get_all_dropdown_options.return_value = {}

        response = self.client.get(reverse('trade:edit', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_edit'])

    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_not_found(self, mock_repo):
        """Test edit non-existent trade"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.get(reverse('trade:edit', kwargs={'trade_id': 9999}))

        self.assertEqual(response.status_code, 302)  # Redirect to list

    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_gmp_record(self, mock_repo):
        """Test cannot edit GMP record"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'INITIAL',
            'src_system': 'GMP'
        }

        response = self.client.get(reverse('trade:edit', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 302)  # Redirect

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_invalid_status(self, mock_repo, mock_dropdown):
        """Test CIS settled trade can be edited (all statuses allowed)"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'status': 'SETTLED',
            'src_system': 'CIS'
        }
        mock_dropdown.get_all_dropdown_options.return_value = {}

        response = self.client.get(reverse('trade:edit', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 200)  # Edit allowed in any status


class TradeWorkflowViewsTestCase(TestCase):
    """Test cases for workflow action views"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    # =========================================================================
    # SUBMIT FOR VALIDATION TESTS
    # =========================================================================

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_submit_success(self, mock_audit, mock_repo):
        """Test successful trade submission"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'INITIAL'
        }
        mock_repo.submit_for_validation.return_value = True

        response = self.client.post(reverse('trade:submit', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 302)
        mock_repo.submit_for_validation.assert_called_once()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_submit_get_redirects(self, mock_repo):
        """Test GET request to submit redirects"""
        response = self.client.get(reverse('trade:submit', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 302)
        mock_repo.submit_for_validation.assert_not_called()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_submit_not_found(self, mock_repo):
        """Test submit non-existent trade"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.post(reverse('trade:submit', kwargs={'trade_id': 9999}))

        self.assertEqual(response.status_code, 302)

    # =========================================================================
    # VALIDATE TESTS
    # =========================================================================

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_validate_approve(self, mock_audit, mock_repo):
        """Test trade validation approval"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'other_user'
        }
        mock_repo.validate_trade.return_value = True

        response = self.client.post(
            reverse('trade:validate', kwargs={'trade_id': 1}),
            {'action': 'approve', 'comments': 'Approved'}
        )

        self.assertEqual(response.status_code, 302)
        mock_repo.validate_trade.assert_called_once()

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_validate_reject(self, mock_audit, mock_repo):
        """Test trade validation rejection"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'other_user'
        }
        mock_repo.reject_trade.return_value = True

        response = self.client.post(
            reverse('trade:validate', kwargs={'trade_id': 1}),
            {'action': 'reject', 'comments': 'Rejected - invalid data'}
        )

        self.assertEqual(response.status_code, 302)
        mock_repo.reject_trade.assert_called_once()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_validate_four_eyes_violation(self, mock_repo):
        """Test four-eyes violation on validation"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'testuser'  # Same as logged-in user
        }

        response = self.client.post(
            reverse('trade:validate', kwargs={'trade_id': 1}),
            {'action': 'approve'}
        )

        self.assertEqual(response.status_code, 302)
        mock_repo.validate_trade.assert_not_called()

    # =========================================================================
    # SETTLE TESTS
    # =========================================================================

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_settle_success(self, mock_audit, mock_repo):
        """Test successful trade settlement"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'VALIDATED'
        }
        mock_repo.settle_trade.return_value = True

        response = self.client.post(
            reverse('trade:settle', kwargs={'trade_id': 1}),
            {'comments': 'Settled'}
        )

        self.assertEqual(response.status_code, 302)
        mock_repo.settle_trade.assert_called_once()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_settle_get_redirects(self, mock_repo):
        """Test GET request to settle redirects"""
        response = self.client.get(reverse('trade:settle', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 302)

    # =========================================================================
    # CANCEL TESTS
    # =========================================================================

    @patch('trade.views.trade_kudu_repository')
    @patch('trade.views.audit_log_kudu_repository')
    def test_trade_cancel_success(self, mock_audit, mock_repo):
        """Test successful trade cancellation"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001',
            'status': 'INITIAL'
        }
        mock_repo.soft_delete_trade.return_value = True

        response = self.client.post(
            reverse('trade:cancel', kwargs={'trade_id': 1}),
            {'reason': 'User requested cancellation'}
        )

        self.assertEqual(response.status_code, 302)
        mock_repo.soft_delete_trade.assert_called_once()


class PendingApprovalsViewsTestCase(TestCase):
    """Test cases for pending approval views"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('trade.views.trade_kudu_repository')
    def test_pending_validation_view(self, mock_repo):
        """Test pending validation list view"""
        mock_repo.get_pending_validation_trades.return_value = [
            {'trade_id': 1, 'status': 'PENDING_VALIDATION'}
        ]
        mock_repo.get_trade_statistics.return_value = {
            'pending_validation': 1,
            'pending_settlement': 0
        }

        response = self.client.get(reverse('trade:pending_validation'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['view_type'], 'validation')
        self.assertEqual(response.context['pending_count'], 1)

    @patch('trade.views.trade_kudu_repository')
    def test_pending_settlement_view(self, mock_repo):
        """Test pending settlement list view"""
        mock_repo.get_pending_settlement_trades.return_value = [
            {'trade_id': 1, 'status': 'VALIDATED'}
        ]
        mock_repo.get_trade_statistics.return_value = {
            'pending_validation': 0,
            'pending_settlement': 1
        }

        response = self.client.get(reverse('trade:pending_settlement'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['view_type'], 'settlement')


class TradeHistoryViewTestCase(TestCase):
    """Test cases for trade_history view"""

    def setUp(self):
        """Set up test client and session"""
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_history_view(self, mock_repo):
        """Test trade history view"""
        mock_repo.get_trade_by_id.return_value = {
            'trade_id': 1,
            'deal_number': 'DEAL-001'
        }
        mock_repo.get_trade_history.return_value = [
            {'history_id': 1, 'action': 'CREATE'},
            {'history_id': 2, 'action': 'SUBMIT'}
        ]

        response = self.client.get(reverse('trade:history', kwargs={'trade_id': 1}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['history']), 2)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_history_not_found(self, mock_repo):
        """Test trade history for non-existent trade"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.get(reverse('trade:history', kwargs={'trade_id': 9999}))

        self.assertEqual(response.status_code, 404)


class TradeAPIViewsTestCase(TestCase):
    """Test cases for API endpoints"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    # =========================================================================
    # VALIDATION API TESTS
    # =========================================================================

    @patch('trade.views.trade_validation_repository')
    def test_api_validate_portfolio_valid(self, mock_repo):
        """Test portfolio validation API - valid"""
        from trade.repositories.trade_validation_repository import ValidationResult
        mock_repo.validate_portfolio.return_value = ValidationResult(
            is_valid=True,
            entity_type='PORTFOLIO',
            entity_name='PORT001',
            message='Portfolio is valid',
            details={'name': 'PORT001'}
        )

        response = self.client.get(
            reverse('trade:api_validate_portfolio'),
            {'name': 'PORT001'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['is_valid'])

    @patch('trade.views.trade_validation_repository')
    def test_api_validate_portfolio_invalid(self, mock_repo):
        """Test portfolio validation API - invalid"""
        from trade.repositories.trade_validation_repository import ValidationResult
        mock_repo.validate_portfolio.return_value = ValidationResult(
            is_valid=False,
            entity_type='PORTFOLIO',
            entity_name='INVALID',
            message='Portfolio not found'
        )

        response = self.client.get(
            reverse('trade:api_validate_portfolio'),
            {'name': 'INVALID'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertFalse(data['is_valid'])

    @patch('trade.views.trade_validation_repository')
    def test_api_validate_security(self, mock_repo):
        """Test security validation API"""
        from trade.repositories.trade_validation_repository import ValidationResult
        mock_repo.validate_security.return_value = ValidationResult(
            is_valid=True,
            entity_type='SECURITY',
            entity_name='SEC001',
            message='Security is valid',
            details={'security_name': 'SEC001'}
        )

        response = self.client.get(
            reverse('trade:api_validate_security'),
            {'name': 'SEC001'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['is_valid'])

    @patch('trade.views.trade_validation_repository')
    def test_api_validate_counterparty(self, mock_repo):
        """Test counterparty validation API"""
        from trade.repositories.trade_validation_repository import ValidationResult
        mock_repo.validate_counterparty.return_value = ValidationResult(
            is_valid=True,
            entity_type='COUNTERPARTY',
            entity_name='CP001',
            message='Counterparty is valid'
        )

        response = self.client.get(
            reverse('trade:api_validate_counterparty'),
            {'name': 'CP001'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['is_valid'])

    # =========================================================================
    # DROPDOWN API TESTS
    # =========================================================================

    @patch('trade.views.trade_dropdown_service')
    def test_api_portfolios(self, mock_dropdown):
        """Test portfolios dropdown API"""
        mock_dropdown.get_portfolios.return_value = [
            {'value': 'PORT001', 'label': 'PORT001'}
        ]

        response = self.client.get(reverse('trade:api_portfolios'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 1)

    @patch('trade.views.trade_dropdown_service')
    def test_api_portfolios_with_search(self, mock_dropdown):
        """Test portfolios dropdown API with search"""
        mock_dropdown.get_portfolios.return_value = []

        response = self.client.get(
            reverse('trade:api_portfolios'),
            {'search': 'test'}
        )

        self.assertEqual(response.status_code, 200)
        mock_dropdown.get_portfolios.assert_called_with(search='test')

    @patch('trade.views.trade_dropdown_service')
    def test_api_securities(self, mock_dropdown):
        """Test securities dropdown API"""
        mock_dropdown.get_securities.return_value = [
            {'value': 'SEC001', 'label': 'SEC001'}
        ]

        response = self.client.get(reverse('trade:api_securities'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)

    @patch('trade.views.trade_dropdown_service')
    def test_api_counterparties(self, mock_dropdown):
        """Test counterparties dropdown API"""
        mock_dropdown.get_counterparties.return_value = [
            {'value': 'CP001', 'label': 'CP001'}
        ]

        response = self.client.get(reverse('trade:api_counterparties'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)

    # =========================================================================
    # DETAILED API TESTS
    # =========================================================================

    @patch('trade.views.trade_validation_repository')
    def test_api_portfolios_detailed(self, mock_repo):
        """Test portfolios detailed API"""
        mock_repo.get_valid_portfolios.return_value = [
            {
                'portfolio_short_name': 'PORT001',
                'portfolio_full_name': 'Portfolio One',
                'currency': 'USD',
                'manager': 'John'
            }
        ]

        response = self.client.get(reverse('trade:api_portfolios_detailed'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        self.assertIn('total', data)

    @patch('trade.views.trade_validation_repository')
    def test_api_securities_detailed(self, mock_repo):
        """Test securities detailed API"""
        mock_repo.get_valid_securities.return_value = [
            {
                'security_label': 'SEC001',
                'security_type': 'EQUITY',
                'isin': 'US123'
            }
        ]

        response = self.client.get(reverse('trade:api_securities_detailed'))

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        self.assertIn('total', data)


class TradeAPIMethodRestrictionsTestCase(TestCase):
    """Test HTTP method restrictions on API endpoints"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    def test_api_validate_portfolio_post_not_allowed(self):
        """Test POST not allowed on validation API"""
        response = self.client.post(
            reverse('trade:api_validate_portfolio'),
            {'name': 'PORT001'}
        )

        self.assertEqual(response.status_code, 405)

    def test_api_portfolios_post_not_allowed(self):
        """Test POST not allowed on portfolios API"""
        response = self.client.post(reverse('trade:api_portfolios'))

        self.assertEqual(response.status_code, 405)

    def test_api_securities_post_not_allowed(self):
        """Test POST not allowed on securities API"""
        response = self.client.post(reverse('trade:api_securities'))

        self.assertEqual(response.status_code, 405)


class TradeListFilterTestCase(TestCase):
    """Test trade list view with various filter scenarios"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_list_with_single_portfolio_fallback(self, mock_repo, mock_dropdown):
        """Test trade list with single portfolio filter fallback"""
        mock_repo.get_all_trades_multi_filter.return_value = []
        mock_repo.get_trade_statistics.return_value = {}
        mock_dropdown.get_all_dropdown_options.return_value = {}

        # Use 'portfolio' param instead of 'portfolios' to test fallback
        response = self.client.get(
            reverse('trade:list'),
            {'portfolio': 'PORT001'}
        )

        self.assertEqual(response.status_code, 200)
        # Verify the repository was called with the correct filter
        mock_repo.get_all_trades_multi_filter.assert_called_once()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_list_with_single_security_fallback(self, mock_repo, mock_dropdown):
        """Test trade list with single security filter fallback"""
        mock_repo.get_all_trades_multi_filter.return_value = []
        mock_repo.get_trade_statistics.return_value = {}
        mock_dropdown.get_all_dropdown_options.return_value = {}

        # Use 'security' param instead of 'securities' to test fallback
        response = self.client.get(
            reverse('trade:list'),
            {'security': 'SEC001'}
        )

        self.assertEqual(response.status_code, 200)
        mock_repo.get_all_trades_multi_filter.assert_called_once()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_list_pagination_not_integer(self, mock_repo, mock_dropdown):
        """Test trade list pagination with non-integer page"""
        mock_repo.get_all_trades_multi_filter.return_value = [
            {'trade_id': i, 'deal_number': f'DL{i}'} for i in range(50)
        ]
        mock_repo.get_trade_statistics.return_value = {}
        mock_dropdown.get_all_dropdown_options.return_value = {}

        response = self.client.get(
            reverse('trade:list'),
            {'page': 'invalid'}
        )

        self.assertEqual(response.status_code, 200)

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_list_pagination_empty_page(self, mock_repo, mock_dropdown):
        """Test trade list pagination with page beyond range"""
        mock_repo.get_all_trades_multi_filter.return_value = [
            {'trade_id': i, 'deal_number': f'DL{i}'} for i in range(10)
        ]
        mock_repo.get_trade_statistics.return_value = {}
        mock_dropdown.get_all_dropdown_options.return_value = {}

        response = self.client.get(
            reverse('trade:list'),
            {'page': '999'}
        )

        self.assertEqual(response.status_code, 200)


class TradeCreateExceptionTestCase(TestCase):
    """Test trade create exception handling"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    @patch('trade.views.cache')
    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_create_insert_returns_none(self, mock_repo, mock_dropdown, mock_cache):
        """Test trade create when insert_trade_fast returns None"""
        mock_cache.get.return_value = None  # No dedup hit
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.validate_trade_data.return_value = (True, [], {})
        mock_repo.insert_trade_fast.return_value = None  # Simulate failure (using fast insert)

        response = self.client.post(
            reverse('trade:create'),
            {
                'trade_type': 'BUY',
                'portfolio_short_name': 'PORT001',
                'security_label': 'SEC001',
                'quantity': '100',
                'price': '50.00',
                'trade_date': '2024-01-01',
                'settle_date': '2024-01-03',
            }
        )

        self.assertEqual(response.status_code, 200)  # Re-render form

    @patch('trade.views.cache')
    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_create_value_error(self, mock_repo, mock_dropdown, mock_cache):
        """Test trade create with ValueError exception using fast insert"""
        mock_cache.get.return_value = None  # No dedup hit
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.validate_trade_data.return_value = (True, [], {})
        mock_repo.insert_trade_fast.side_effect = ValueError("Invalid data")

        response = self.client.post(
            reverse('trade:create'),
            {
                'trade_type': 'BUY',
                'portfolio_short_name': 'PORT001',
                'security_label': 'SEC001',
                'quantity': '100',
                'price': '50.00',
                'trade_date': '2024-01-01',
                'settle_date': '2024-01-03',
            }
        )

        self.assertEqual(response.status_code, 200)

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_create_generic_exception(self, mock_repo, mock_dropdown):
        """Test trade create with generic exception using fast insert"""
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.validate_trade_data.return_value = (True, [], {})  # Now returns 3 values
        mock_repo.insert_trade_fast.side_effect = Exception("Database error")

        response = self.client.post(
            reverse('trade:create'),
            {
                'trade_type': 'BUY',
                'portfolio_short_name': 'PORT001',
                'security_label': 'SEC001',
                'quantity': '100',
                'price': '50.00',
                'trade_date': '2024-01-01',
                'settle_date': '2024-01-03',
            }
        )

        self.assertEqual(response.status_code, 200)


class TradeEditPostTestCase(TestCase):
    """Test trade edit POST flow"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.trade_data = {
            'trade_id': 1,
            'deal_number': 'DL001',
            'trade_type': 'BUY',
            'portfolio_short_name': 'PORT001',
            'security_label': 'SEC001',
            'status': 'INITIAL',
            'src_system': 'CIS',
        }

    @patch('trade.views.audit_log_kudu_repository')
    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_post_success(self, mock_repo, mock_dropdown, mock_audit):
        """Test successful trade edit POST"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.update_trade.return_value = True

        response = self.client.post(
            reverse('trade:edit', args=[1]),
            {
                'trade_status': 'MODIFIED',
                'trade_date': '2024-01-01',
                'settle_date': '2024-01-03',
                'quantity': '100',
                'price': '50.00',
            }
        )

        self.assertEqual(response.status_code, 302)  # Redirect on success
        mock_repo.update_trade.assert_called_once()

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_post_update_fails(self, mock_repo, mock_dropdown):
        """Test trade edit POST when update returns False"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.update_trade.return_value = False  # Update fails

        response = self.client.post(
            reverse('trade:edit', args=[1]),
            {
                'trade_status': 'MODIFIED',
                'trade_date': '2024-01-01',
            }
        )

        self.assertEqual(response.status_code, 200)  # Re-render form

    @patch('trade.views.trade_dropdown_service')
    @patch('trade.views.trade_kudu_repository')
    def test_trade_edit_post_exception(self, mock_repo, mock_dropdown):
        """Test trade edit POST with exception"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_dropdown.get_all_dropdown_options.return_value = {}
        mock_repo.update_trade.side_effect = Exception("Database error")

        response = self.client.post(
            reverse('trade:edit', args=[1]),
            {
                'trade_status': 'MODIFIED',
                'trade_date': '2024-01-01',
            }
        )

        self.assertEqual(response.status_code, 200)  # Re-render form


class TradeWorkflowExceptionsTestCase(TestCase):
    """Test workflow action exception handling"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()
        self.trade_data = {
            'trade_id': 1,
            'deal_number': 'DL001',
            'status': 'PENDING_VALIDATION',
            'submitted_by': 'maker1',
        }

    @patch('trade.views.trade_kudu_repository')
    def test_trade_submit_failure(self, mock_repo):
        """Test trade submit when repository returns False"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.submit_for_validation.return_value = False

        response = self.client.post(reverse('trade:submit', args=[1]))

        self.assertEqual(response.status_code, 302)  # Redirect

    @patch('trade.views.trade_kudu_repository')
    def test_trade_validate_not_found(self, mock_repo):
        """Test trade validate when trade not found"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.post(
            reverse('trade:validate', args=[1]),
            {'action': 'approve'}
        )

        self.assertEqual(response.status_code, 302)  # Redirect to list

    @patch('trade.views.trade_kudu_repository')
    def test_trade_validate_get_redirects(self, mock_repo):
        """Test GET request to validate redirects"""
        response = self.client.get(reverse('trade:validate', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_validate_failure(self, mock_repo):
        """Test trade validate when repository returns False"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.validate_trade.return_value = False

        response = self.client.post(
            reverse('trade:validate', args=[1]),
            {'action': 'approve'}
        )

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_validate_exception(self, mock_repo):
        """Test trade validate with exception"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.validate_trade.side_effect = Exception("Database error")

        response = self.client.post(
            reverse('trade:validate', args=[1]),
            {'action': 'approve'}
        )

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_settle_not_found(self, mock_repo):
        """Test trade settle when trade not found"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.post(reverse('trade:settle', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_settle_failure(self, mock_repo):
        """Test trade settle when repository returns False"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.settle_trade.return_value = False

        response = self.client.post(reverse('trade:settle', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_settle_exception(self, mock_repo):
        """Test trade settle with exception"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.settle_trade.side_effect = Exception("Database error")

        response = self.client.post(reverse('trade:settle', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_cancel_get_redirects(self, mock_repo):
        """Test GET request to cancel redirects"""
        response = self.client.get(reverse('trade:cancel', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_cancel_not_found(self, mock_repo):
        """Test trade cancel when trade not found"""
        mock_repo.get_trade_by_id.return_value = None

        response = self.client.post(reverse('trade:cancel', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_cancel_failure(self, mock_repo):
        """Test trade cancel when repository returns False"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.soft_delete_trade.return_value = False

        response = self.client.post(reverse('trade:cancel', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_cancel_exception(self, mock_repo):
        """Test trade cancel with exception"""
        mock_repo.get_trade_by_id.return_value = self.trade_data
        mock_repo.soft_delete_trade.side_effect = Exception("Database error")

        response = self.client.post(reverse('trade:cancel', args=[1]))

        self.assertEqual(response.status_code, 302)


class TradeReactivateDeleteTestCase(TestCase):
    """Test reactivate and delete views"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    @patch('trade.views.trade_kudu_repository')
    def test_trade_reactivate_get_redirects(self, mock_repo):
        """Test GET request to reactivate redirects"""
        response = self.client.get(reverse('trade:reactivate', args=[1]))

        self.assertEqual(response.status_code, 302)

    def test_trade_reactivate_post(self):
        """Test POST to reactivate shows info message"""
        response = self.client.post(reverse('trade:reactivate', args=[1]))

        self.assertEqual(response.status_code, 302)

    @patch('trade.views.trade_kudu_repository')
    def test_trade_delete_calls_cancel(self, mock_repo):
        """Test trade delete delegates to cancel"""
        mock_repo.get_trade_by_id.return_value = {'trade_id': 1, 'deal_number': 'DL001'}
        mock_repo.soft_delete_trade.return_value = True

        response = self.client.post(reverse('trade:delete', args=[1]))

        self.assertEqual(response.status_code, 302)


class TradeAPIPositionTestCase(TestCase):
    """Test position API endpoint"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

    @patch('trade.views.trade_kudu_repository')
    def test_api_get_position_exists(self, mock_repo):
        """Test get position when position exists"""
        mock_repo.get_position.return_value = {
            'quantity': 1000,
            'average_cost': 50.00,
            'status': 'ACTIVE'
        }

        response = self.client.get(
            reverse('trade:api_get_position'),
            {'portfolio': 'PORT001', 'security': 'SEC001'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['exists'])
        self.assertEqual(data['quantity'], 1000)

    @patch('trade.views.trade_kudu_repository')
    def test_api_get_position_not_exists(self, mock_repo):
        """Test get position when position doesn't exist"""
        mock_repo.get_position.return_value = None

        response = self.client.get(
            reverse('trade:api_get_position'),
            {'portfolio': 'PORT001', 'security': 'SEC001'}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data['exists'])
        self.assertEqual(data['quantity'], 0)
