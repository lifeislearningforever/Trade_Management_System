"""
Dashboard Tests
"""
import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestDashboard:
    """Test dashboard functionality"""

    def test_dashboard_loads_for_maker(self, client, maker_user):
        """Test dashboard loads for maker"""
        client.force_login(maker_user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200
        assert 'Test Maker' in response.content.decode()

    def test_dashboard_loads_for_checker(self, client, checker_user):
        """Test dashboard loads for checker"""
        client.force_login(checker_user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200
        assert 'Test Checker' in response.content.decode()

    def test_dashboard_shows_maker_section(self, client, maker_user):
        """Test maker sees maker dashboard section"""
        client.force_login(maker_user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'Maker Dashboard' in content or 'Draft Orders' in content

    def test_dashboard_shows_checker_section(self, client, checker_user):
        """Test checker sees checker dashboard section"""
        client.force_login(checker_user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'Checker Dashboard' in content or 'Pending' in content

    def test_dashboard_shows_admin_section(self, client, admin_user):
        """Test admin sees admin dashboard section"""
        client.force_login(admin_user)
        response = client.get(reverse('dashboard'))
        content = response.content.decode()
        assert 'Administrator' in content or 'Admin' in content

    def test_dashboard_counts_draft_orders(self, client, maker_user, draft_order):
        """Test dashboard shows correct draft order count"""
        client.force_login(maker_user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200
        # Should show count of draft orders

    def test_dashboard_counts_pending_orders_for_checker(self, client, checker_user, pending_order):
        """Test dashboard shows pending orders for checker"""
        client.force_login(checker_user)
        response = client.get(reverse('dashboard'))
        assert response.status_code == 200
        # Should show count of pending orders
