"""
Portfolio View Tests

Tests for portfolio views including:
- List view with search/filter
- Detail view
- Create/Edit/Delete operations
- Workflow (submit, approve, reject)
- Close/Reactivate operations
- CSV export
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, Mock, MagicMock


class PortfolioListViewTestCase(TestCase):
    """Test cases for portfolio list view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('portfolio:list')

        # Set up session
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_name'] = 'Test User'
        session['user_email'] = 'test@example.com'
        session.save()

        # Sample portfolio data
        self.sample_portfolios = [
            {
                'name': 'TEST_PORT_001',
                'code': 'TP001',
                'description': 'Test Portfolio 1',
                'manager': 'John Doe',
                'currency': 'USD',
                'status': 'APPROVED',
                'is_active': True,
                'cash_balance': 1000000.00,
                'created_at': '2025-12-27 10:00:00',
                'updated_at': '2025-12-27 10:00:00',
                'updated_by': 'testuser'
            },
            {
                'name': 'TEST_PORT_002',
                'code': 'TP002',
                'description': 'Test Portfolio 2',
                'manager': 'Jane Smith',
                'currency': 'EUR',
                'status': 'PENDING_APPROVAL',
                'is_active': True,
                'cash_balance': 500000.00,
                'created_at': '2025-12-27 10:00:00',
                'updated_at': '2025-12-27 10:00:00',
                'updated_by': 'testuser'
            }
        ]

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_all_portfolios')
    def test_portfolio_list_view_success(self, mock_get_all, mock_audit):
        """Test portfolio list view loads successfully"""
        mock_get_all.return_value = self.sample_portfolios

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/portfolio_list.html')
        self.assertIn('page_obj', response.context)

        # Verify audit log was called
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'VIEW')
        self.assertEqual(call_kwargs['entity_type'], 'PORTFOLIO')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_all_portfolios')
    def test_portfolio_list_search(self, mock_get_all, mock_audit):
        """Test portfolio search functionality"""
        mock_get_all.return_value = [self.sample_portfolios[0]]

        response = self.client.get(self.url, {'search': 'TEST_PORT_001'})

        self.assertEqual(response.status_code, 200)
        mock_get_all.assert_called_once()

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_all_portfolios')
    def test_portfolio_list_status_filter(self, mock_get_all, mock_audit):
        """Test filtering by status"""
        mock_get_all.return_value = [self.sample_portfolios[0]]

        response = self.client.get(self.url, {'status': 'APPROVED'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('status_filter', response.context)
        self.assertEqual(response.context['status_filter'], 'APPROVED')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_all_portfolios')
    def test_portfolio_csv_export(self, mock_get_all, mock_audit):
        """Test CSV export functionality"""
        mock_get_all.return_value = self.sample_portfolios

        response = self.client.get(self.url, {'export': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('portfolios', response['Content-Disposition'])

        # Check CSV content
        content = response.content.decode('utf-8')
        self.assertIn('TEST_PORT_001', content)
        self.assertIn('TEST_PORT_002', content)


class PortfolioDetailViewTestCase(TestCase):
    """Test cases for portfolio detail view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.portfolio_data = {
            'name': 'TEST_PORT_001',
            'code': 'TP001',
            'description': 'Test Portfolio',
            'manager': 'John Doe',
            'currency': 'USD',
            'status': 'APPROVED',
            'is_active': True,
            'cash_balance': 1000000.00,
            'created_at': '2025-12-27 10:00:00',
            'updated_at': '2025-12-27 10:00:00',
            'updated_by': 'testuser'
        }

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_detail_view_success(self, mock_get_portfolio, mock_audit):
        """Test portfolio detail view loads successfully"""
        mock_get_portfolio.return_value = self.portfolio_data

        url = reverse('portfolio:detail', args=['TEST_PORT_001'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/portfolio_detail.html')
        self.assertIn('portfolio', response.context)

        # Verify correct portfolio was retrieved
        mock_get_portfolio.assert_called_once_with('TEST_PORT_001')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_detail_not_found(self, mock_get_portfolio, mock_audit):
        """Test detail view with non-existent portfolio"""
        mock_get_portfolio.return_value = None

        url = reverse('portfolio:detail', args=['NONEXISTENT'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)


class PortfolioCreateViewTestCase(TestCase):
    """Test cases for portfolio create view"""

    def setUp(self):
        """Set up test client with logged-in session"""
        self.client = Client()
        self.url = reverse('portfolio:create')

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.form_data = {
            'name': 'NEW_PORT_001',
            'code': 'NP001',
            'description': 'New Test Portfolio',
            'manager': 'John Doe',
            'currency': 'USD',
            'cash_balance': 1000000.00
        }

    @patch('portfolio.services.portfolio_dropdown_service.portfolio_dropdown_service')
    def test_portfolio_create_view_get(self, mock_dropdown):
        """Test GET request to create view"""
        mock_dropdown.get_all_dropdowns.return_value = {
            'currencies': [{'code': 'USD'}, {'code': 'EUR'}],
            'managers': ['John Doe', 'Jane Smith']
        }

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/portfolio_form.html')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.insert_portfolio')
    @patch('portfolio.services.portfolio_dropdown_service.portfolio_dropdown_service')
    def test_portfolio_create_success(self, mock_dropdown, mock_insert, mock_audit):
        """Test successful portfolio creation"""
        mock_dropdown.get_all_dropdowns.return_value = {'currencies': [], 'managers': []}
        mock_insert.return_value = True

        response = self.client.post(self.url, self.form_data)

        self.assertEqual(response.status_code, 302)
        mock_insert.assert_called_once()

        # Verify audit log
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'CREATE')


class PortfolioEditViewTestCase(TestCase):
    """Test cases for portfolio edit view"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.portfolio_data = {
            'name': 'TEST_PORT_001',
            'code': 'TP001',
            'description': 'Test Portfolio',
            'manager': 'John Doe',
            'currency': 'USD',
            'status': 'DRAFT',
            'is_active': True,
            'cash_balance': 1000000.00
        }

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    @patch('portfolio.services.portfolio_dropdown_service.portfolio_dropdown_service')
    def test_portfolio_edit_view_get(self, mock_dropdown, mock_get_portfolio, mock_audit):
        """Test GET request to edit view"""
        mock_get_portfolio.return_value = self.portfolio_data
        mock_dropdown.get_all_dropdowns.return_value = {'currencies': [], 'managers': []}

        url = reverse('portfolio:edit', args=['TEST_PORT_001'])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'portfolio/portfolio_form.html')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('core.repositories.impala_connection.impala_manager.execute_write')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    @patch('portfolio.services.portfolio_dropdown_service.portfolio_dropdown_service')
    def test_portfolio_edit_success(self, mock_dropdown, mock_get, mock_execute, mock_audit):
        """Test successful portfolio edit"""
        mock_get.return_value = self.portfolio_data
        mock_dropdown.get_all_dropdowns.return_value = {'currencies': [], 'managers': []}
        mock_execute.return_value = True

        url = reverse('portfolio:edit', args=['TEST_PORT_001'])
        response = self.client.post(url, {
            'name': 'TEST_PORT_001',
            'code': 'TP001',
            'description': 'Updated Description',
            'manager': 'John Doe',
            'currency': 'USD',
            'cash_balance': 2000000.00
        })

        self.assertEqual(response.status_code, 302)
        mock_execute.assert_called_once()


class PortfolioWorkflowTestCase(TestCase):
    """Test cases for portfolio workflow (submit, approve, reject)"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.portfolio_data = {
            'name': 'TEST_PORT_001',
            'code': 'TP001',
            'status': 'DRAFT',
            'is_active': True
        }

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.update_portfolio_status')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_submit_for_approval(self, mock_get, mock_update_status, mock_audit):
        """Test submitting portfolio for approval"""
        mock_get.return_value = self.portfolio_data
        mock_update_status.return_value = True

        url = reverse('portfolio:submit', args=['TEST_PORT_001'])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        mock_update_status.assert_called_once()

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.update_portfolio_status')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_approve(self, mock_get, mock_update_status, mock_audit):
        """Test approving portfolio"""
        self.portfolio_data['status'] = 'PENDING_APPROVAL'
        mock_get.return_value = self.portfolio_data
        mock_update_status.return_value = True

        url = reverse('portfolio:approve', args=['TEST_PORT_001'])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)

        # Verify audit log
        mock_audit.assert_called()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'APPROVE')

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.update_portfolio_status')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_reject(self, mock_get, mock_update_status, mock_audit):
        """Test rejecting portfolio"""
        self.portfolio_data['status'] = 'PENDING_APPROVAL'
        mock_get.return_value = self.portfolio_data
        mock_update_status.return_value = True

        url = reverse('portfolio:reject', args=['TEST_PORT_001'])
        response = self.client.post(url, {'comments': 'Invalid data'})

        self.assertEqual(response.status_code, 302)

        # Verify audit log
        mock_audit.assert_called()
        call_kwargs = mock_audit.call_args[1]
        self.assertEqual(call_kwargs['action_type'], 'REJECT')


class PortfolioCloseReactivateTestCase(TestCase):
    """Test cases for portfolio close and reactivate operations"""

    def setUp(self):
        """Set up test client"""
        self.client = Client()

        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.update_portfolio_status')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_close(self, mock_get, mock_update_status, mock_audit):
        """Test closing portfolio"""
        mock_get.return_value = {
            'name': 'TEST_PORT_001',
            'status': 'APPROVED',
            'is_active': True
        }
        mock_update_status.return_value = True

        url = reverse('portfolio:close', args=['TEST_PORT_001'])
        response = self.client.post(url, {'reason': 'No longer needed'})

        self.assertEqual(response.status_code, 302)

    @patch('portfolio.views.audit_log_kudu_repository.log_action')
    @patch('portfolio.views.portfolio_hive_repository.update_portfolio_status')
    @patch('portfolio.views.portfolio_hive_repository.get_portfolio_by_code')
    def test_portfolio_reactivate(self, mock_get, mock_update_status, mock_audit):
        """Test reactivating portfolio"""
        mock_get.return_value = {
            'name': 'TEST_PORT_001',
            'status': 'Inactive',
            'is_active': False
        }
        mock_update_status.return_value = True

        url = reverse('portfolio:reactivate', args=['TEST_PORT_001'])
        response = self.client.post(url, {'comments': 'Needed again'})

        self.assertEqual(response.status_code, 302)


class PortfolioWrapperTestCase(TestCase):
    """Test cases for PortfolioWrapper class"""

    def test_wrapper_initialization(self):
        """Test PortfolioWrapper initialization"""
        from portfolio.views import PortfolioWrapper

        data = {
            'name': 'TEST_PORT_001',
            'code': 'TP001',
            'description': 'Test Portfolio',
            'manager': 'John Doe',
            'currency': 'USD',
            'status': 'APPROVED',
            'is_active': True,
            'cash_balance': 1000000.00,
            'created_at': '2025-12-27 10:00:00',
            'updated_at': '2025-12-27 10:00:00',
            'updated_by': 'testuser'
        }

        wrapper = PortfolioWrapper(data, index=0)

        self.assertEqual(wrapper.name, 'TEST_PORT_001')
        self.assertEqual(wrapper.code, 'TEST_PORT_001')  # code is derived from name[:20]
        self.assertEqual(wrapper.status, 'APPROVED')
        self.assertTrue(wrapper.is_active)
        self.assertIsNotNone(wrapper.id)

    def test_wrapper_missing_fields(self):
        """Test PortfolioWrapper handles missing fields"""
        from portfolio.views import PortfolioWrapper

        minimal_data = {
            'name': 'TEST_PORT_001',
            'code': 'TP001'
        }

        wrapper = PortfolioWrapper(minimal_data, index=0)

        self.assertEqual(wrapper.name, 'TEST_PORT_001')
        self.assertEqual(wrapper.code, 'TEST_PORT_001')  # code is derived from name[:20]
        # Missing fields should default to empty strings or defaults
        self.assertEqual(wrapper.description, '')
        self.assertEqual(wrapper.cash_balance, 0)


class PortfolioURLTestCase(TestCase):
    """Test cases for URL routing"""

    def test_portfolio_list_url_resolves(self):
        """Test portfolio list URL resolves correctly"""
        url = reverse('portfolio:list')
        self.assertEqual(url, '/portfolio/')

    def test_portfolio_detail_url_resolves(self):
        """Test portfolio detail URL resolves correctly"""
        url = reverse('portfolio:detail', args=['TEST_PORT_001'])
        self.assertEqual(url, '/portfolio/TEST_PORT_001/')

    def test_portfolio_create_url_resolves(self):
        """Test portfolio create URL resolves correctly"""
        url = reverse('portfolio:create')
        self.assertEqual(url, '/portfolio/create/')

    def test_portfolio_edit_url_resolves(self):
        """Test portfolio edit URL resolves correctly"""
        url = reverse('portfolio:edit', args=['TEST_PORT_001'])
        self.assertEqual(url, '/portfolio/TEST_PORT_001/edit/')
