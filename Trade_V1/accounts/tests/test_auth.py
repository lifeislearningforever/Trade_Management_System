"""
Authentication and Login Tests
"""
import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.auth
@pytest.mark.django_db
class TestAuthentication:
    """Test authentication functionality"""

    def test_login_view_get(self, client):
        """Test login page loads"""
        response = client.get(reverse('login'))
        assert response.status_code == 200
        assert 'login' in response.content.decode().lower()

    def test_login_with_valid_credentials(self, client, maker_user):
        """Test successful login"""
        response = client.post(reverse('login'), {
            'username': 'testmaker',
            'password': 'Test@1234'
        })
        assert response.status_code == 302  # Redirect after login
        assert response.url == reverse('dashboard')

    def test_login_with_invalid_credentials(self, client):
        """Test login failure with wrong password"""
        User.objects.create_user(username='testuser', password='correct')
        response = client.post(reverse('login'), {
            'username': 'testuser',
            'password': 'wrong'
        })
        assert response.status_code == 200  # Stays on login page
        messages = list(response.context['messages'])
        assert any('Invalid username or password' in str(m) for m in messages)

    def test_login_with_inactive_user(self, client):
        """Test login failure for inactive user"""
        user = User.objects.create_user(
            username='inactive',
            password='Test@1234',
            is_active=False
        )
        response = client.post(reverse('login'), {
            'username': 'inactive',
            'password': 'Test@1234'
        })
        assert response.status_code == 200
        messages = list(response.context['messages'])
        assert any('deactivated' in str(m).lower() for m in messages)

    def test_logout(self, client, maker_user):
        """Test logout functionality"""
        client.force_login(maker_user)
        response = client.post(reverse('logout'))
        assert response.status_code == 302
        assert response.url == reverse('login')

    def test_redirect_when_already_logged_in(self, client, maker_user):
        """Test redirect to dashboard if already logged in"""
        client.force_login(maker_user)
        response = client.get(reverse('login'))
        assert response.status_code == 302
        assert response.url == reverse('dashboard')

    def test_dashboard_requires_login(self, client):
        """Test dashboard redirects to login when not authenticated"""
        response = client.get(reverse('dashboard'))
        assert response.status_code == 302
        assert '/login/' in response.url
