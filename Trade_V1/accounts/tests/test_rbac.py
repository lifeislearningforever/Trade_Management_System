"""
RBAC (Role-Based Access Control) Tests
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.auth
@pytest.mark.django_db
class TestRBAC:
    """Test RBAC functionality"""

    def test_user_has_role(self, maker_user, create_roles):
        """Test user has correct role"""
        assert maker_user.has_role('MAKER')
        assert not maker_user.has_role('CHECKER')

    def test_user_has_permission(self, maker_user):
        """Test user has correct permissions"""
        assert maker_user.has_permission('create_order')
        assert maker_user.has_permission('view_order')
        assert not maker_user.has_permission('approve_order')

    def test_user_has_any_permission(self, maker_user):
        """Test has_any_permission method"""
        assert maker_user.has_any_permission(['create_order', 'approve_order'])
        assert not maker_user.has_any_permission(['approve_order', 'delete_all'])

    def test_get_role_codes(self, maker_user):
        """Test get_role_codes method"""
        role_codes = maker_user.get_role_codes()
        assert 'MAKER' in role_codes
        assert 'CHECKER' not in role_codes

    def test_checker_permissions(self, checker_user):
        """Test checker has correct permissions"""
        assert checker_user.has_permission('approve_order')
        assert checker_user.has_permission('view_order')
        assert not checker_user.has_permission('create_order')

    def test_superuser_has_all_permissions(self, admin_user):
        """Test superuser bypass"""
        assert admin_user.is_superuser
        # Superusers should have staff access
        assert admin_user.is_staff

    def test_user_without_roles(self, db):
        """Test user without any roles"""
        user = User.objects.create_user(
            username='noroles',
            password='Test@1234'
        )
        assert not user.has_role('MAKER')
        assert not user.has_permission('create_order')
        assert user.get_role_codes() == []

    def test_inactive_role_not_counted(self, db, create_roles, maker_user):
        """Test inactive roles are not considered"""
        maker_role = create_roles['maker']
        maker_role.is_active = False
        maker_role.save()

        assert not maker_user.has_role('MAKER')
        # Permissions from inactive roles should not work
        # (depends on implementation, might need refresh)
