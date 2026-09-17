"""
Security View Tests
"""

from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch, MagicMock


class SecurityListViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('security:list')
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session['user_email'] = 'test@example.com'
        session.save()

        self.sample_securities = [
            {
                'security_id': 1, 'security_name': 'Test Security',
                'isin': 'US0000000001', 'ticker': 'TST',
                'security_type': 'EQUITY', 'currency_code': 'USD',
                'status': 'ACTIVE', 'src_system': 'CIS',
                'created_at': '2024-01-01', 'created_by': 'admin',
            }
        ]

    @patch('security.views.security_hive_repository')
    def test_security_list_view_success(self, mock_repo):
        mock_repo.get_all_securities.return_value = self.sample_securities
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'security/security_list.html')

    @patch('security.views.security_hive_repository')
    def test_security_list_empty(self, mock_repo):
        mock_repo.get_all_securities.return_value = []
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    @patch('security.views.security_hive_repository')
    def test_security_list_with_search(self, mock_repo):
        mock_repo.get_all_securities.return_value = self.sample_securities
        response = self.client.get(self.url, {'search': 'TST'})
        self.assertEqual(response.status_code, 200)
        call_kwargs = mock_repo.get_all_securities.call_args[1]
        self.assertEqual(call_kwargs.get('search'), 'TST')

    @patch('security.views.security_hive_repository')
    def test_security_list_with_status_filter(self, mock_repo):
        mock_repo.get_all_securities.return_value = self.sample_securities
        response = self.client.get(self.url, {'status': 'ACTIVE'})
        self.assertEqual(response.status_code, 200)

    @patch('security.views.security_hive_repository')
    def test_security_list_csv_export(self, mock_repo):
        mock_repo.get_all_securities.return_value = self.sample_securities
        response = self.client.get(self.url, {'export': 'csv'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('securities', response['Content-Disposition'])
        content = response.content.decode('utf-8')
        self.assertIn('Security ID', content)
        self.assertIn('Test Security', content)


class SecurityDetailViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

        self.security_data = {
            'security_id': 1, 'security_name': 'Test Security',
            'isin': 'US0000000001', 'status': 'ACTIVE', 'src_system': 'CIS',
            'security_type': 'EQUITY', 'currency_code': 'USD',
        }

    @patch('security.views.security_hive_repository')
    def test_security_detail_view_success(self, mock_repo):
        mock_repo.get_security_by_id.return_value = self.security_data
        response = self.client.get(reverse('security:detail', args=[1]))
        self.assertEqual(response.status_code, 200)

    @patch('security.views.security_hive_repository')
    def test_security_detail_not_found(self, mock_repo):
        mock_repo.get_security_by_id.return_value = None
        response = self.client.get(reverse('security:detail', args=[9999]))
        self.assertEqual(response.status_code, 302)


class SecurityDashboardViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session['user_login'] = 'testuser'
        session['user_id'] = 1
        session.save()

    @patch('security.views.security_service')
    @patch('security.views.security_hive_repository')
    def test_security_dashboard_success(self, mock_repo, mock_service):
        mock_repo.get_all_securities.return_value = []
        mock_service.get_security_statistics.return_value = {'total': 0}
        response = self.client.get(reverse('security:dashboard'))
        self.assertEqual(response.status_code, 200)
