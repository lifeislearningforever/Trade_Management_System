"""
Portfolio Module Tests
Comprehensive test cases for Portfolio models, services, and views.
All tests must pass before commit to GitHub.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.core.exceptions import ValidationError, PermissionDenied
from django.urls import reverse

from .models import Portfolio, PortfolioHistory
from .services import PortfolioService
from core.models import AuditLog


class PortfolioModelTest(TestCase):
    """Test Portfolio model and Four-Eyes workflow."""

    def setUp(self):
        """Set up test data."""
        # Create users
        self.maker = User.objects.create_user('maker1', 'maker@test.com', 'pass123')
        self.checker = User.objects.create_user('checker1', 'checker@test.com', 'pass123')

        # Create groups
        self.makers_group = Group.objects.create(name='Makers')
        self.checkers_group = Group.objects.create(name='Checkers')

        self.maker.groups.add(self.makers_group)
        self.checker.groups.add(self.checkers_group)

    def test_create_portfolio(self):
        """Test creating a portfolio."""
        portfolio = Portfolio.objects.create(
            code='TEST-001',
            name='Test Portfolio',
            currency='USD',
            manager='Test Manager',
            cash_balance=1000000,
            status='DRAFT',
            created_by=self.maker
        )

        self.assertEqual(portfolio.code, 'TEST-001')
        self.assertEqual(portfolio.status, 'DRAFT')
        self.assertFalse(portfolio.is_active)

    def test_submit_for_approval(self):
        """Test submitting portfolio for approval."""
        portfolio = Portfolio.objects.create(
            code='TEST-002',
            name='Test Portfolio 2',
            currency='USD',
            manager='Manager',
            status='DRAFT',
            created_by=self.maker
        )

        portfolio.submit_for_approval(self.maker)

        self.assertEqual(portfolio.status, 'PENDING_APPROVAL')
        self.assertIsNotNone(portfolio.submitted_for_approval_at)
        self.assertEqual(portfolio.submitted_by, self.maker)

    def test_approve_portfolio_four_eyes(self):
        """Test approving portfolio with Four-Eyes principle."""
        portfolio = Portfolio.objects.create(
            code='TEST-003',
            name='Test Portfolio 3',
            currency='USD',
            manager='Manager',
            status='DRAFT',
            created_by=self.maker
        )

        # Submit for approval
        portfolio.submit_for_approval(self.maker)

        # Approve (different user - Four-Eyes principle)
        portfolio.approve(self.checker, 'Approved')

        self.assertEqual(portfolio.status, 'APPROVED')
        self.assertTrue(portfolio.is_active)
        self.assertEqual(portfolio.reviewed_by, self.checker)

    def test_four_eyes_violation(self):
        """Test Four-Eyes principle violation."""
        portfolio = Portfolio.objects.create(
            code='TEST-004',
            name='Test Portfolio 4',
            currency='USD',
            manager='Manager',
            status='DRAFT',
            created_by=self.maker
        )

        portfolio.submit_for_approval(self.maker)

        # Try to approve own portfolio (should fail)
        with self.assertRaises(ValidationError) as context:
            portfolio.approve(self.maker, 'Self approval')

        self.assertIn('Four-Eyes principle', str(context.exception))

    def test_reject_portfolio(self):
        """Test rejecting a portfolio."""
        portfolio = Portfolio.objects.create(
            code='TEST-005',
            name='Test Portfolio 5',
            currency='USD',
            manager='Manager',
            status='DRAFT',
            created_by=self.maker
        )

        portfolio.submit_for_approval(self.maker)
        portfolio.reject(self.checker, 'Needs more information')

        self.assertEqual(portfolio.status, 'REJECTED')
        self.assertFalse(portfolio.is_active)
        self.assertIn('Needs more information', portfolio.review_comments)


class PortfolioServiceTest(TestCase):
    """Test Portfolio Service layer."""

    def setUp(self):
        """Set up test data."""
        self.maker = User.objects.create_user('maker2', 'maker2@test.com', 'pass123')
        self.checker = User.objects.create_user('checker2', 'checker2@test.com', 'pass123')

        self.makers_group = Group.objects.create(name='Makers')
        self.checkers_group = Group.objects.create(name='Checkers')

        self.maker.groups.add(self.makers_group)
        self.checker.groups.add(self.checkers_group)

    def test_create_portfolio_service(self):
        """Test creating portfolio via service."""
        data = {
            'code': 'SVC-001',
            'name': 'Service Test Portfolio',
            'currency': 'USD',
            'manager': 'Test Manager',
            'cash_balance': 5000000
        }

        portfolio = PortfolioService.create_portfolio(self.maker, data)

        self.assertEqual(portfolio.code, 'SVC-001')
        self.assertEqual(portfolio.status, 'DRAFT')
        self.assertEqual(portfolio.created_by, self.maker)

        # Check audit log
        audit = AuditLog.objects.filter(
            action='CREATE',
            object_type='Portfolio',
            object_id=str(portfolio.id)
        ).first()
        self.assertIsNotNone(audit)

    def test_create_duplicate_code(self):
        """Test creating portfolio with duplicate code."""
        data = {
            'code': 'DUP-001',
            'name': 'Original',
            'currency': 'USD',
            'manager': 'Manager',
        }

        PortfolioService.create_portfolio(self.maker, data)

        # Try to create with same code
        with self.assertRaises(ValidationError):
            PortfolioService.create_portfolio(self.maker, data)

    def test_workflow_complete(self):
        """Test complete workflow via service."""
        # Create
        data = {
            'code': 'WF-001',
            'name': 'Workflow Test',
            'currency': 'EUR',
            'manager': 'Manager',
        }
        portfolio = PortfolioService.create_portfolio(self.maker, data)
        self.assertEqual(portfolio.status, 'DRAFT')

        # Submit
        portfolio = PortfolioService.submit_for_approval(portfolio, self.maker)
        self.assertEqual(portfolio.status, 'PENDING_APPROVAL')

        # Approve
        portfolio = PortfolioService.approve_portfolio(portfolio, self.checker, 'LGTM')
        self.assertEqual(portfolio.status, 'APPROVED')
        self.assertTrue(portfolio.is_active)
