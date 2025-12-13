"""
Order Workflow Integration Tests
"""
import pytest
from django.urls import reverse
from orders.models import Order


@pytest.mark.workflow
@pytest.mark.django_db
class TestOrderWorkflow:
    """Test complete order workflow"""

    def test_create_order_workflow(self, client, maker_user, test_stock, test_client):
        """Test creating an order"""
        client.force_login(maker_user)

        response = client.post(reverse('order_create'), {
            'stock': test_stock.id,
            'side': 'BUY',
            'order_type': 'MARKET',
            'quantity': 100,
            'price': 2500.00,
            'client': test_client.id,
            'validity': 'DAY',
            'notes': 'Test order'
        })

        assert response.status_code == 302  # Redirect after creation

        # Verify order was created
        order = Order.objects.filter(created_by=maker_user).first()
        assert order is not None
        assert order.status == 'DRAFT'
        assert order.created_by_name == maker_user.get_full_name()
        assert order.created_by_employee_id == maker_user.employee_id

    def test_edit_draft_order_workflow(self, client, maker_user, draft_order):
        """Test editing a draft order"""
        client.force_login(maker_user)

        response = client.post(reverse('order_edit', args=[draft_order.pk]), {
            'stock': draft_order.stock.id,
            'side': 'SELL',  # Changed from BUY
            'order_type': 'LIMIT',  # Changed from MARKET
            'quantity': 200,  # Changed from 100
            'price': 2600.00,
            'client': draft_order.client.id,
            'validity': 'DAY'
        })

        assert response.status_code == 302

        # Verify changes
        draft_order.refresh_from_db()
        assert draft_order.side == 'SELL'
        assert draft_order.quantity == 200

    def test_cannot_edit_other_users_order(self, client, checker_user, draft_order):
        """Test cannot edit other user's order"""
        client.force_login(checker_user)

        response = client.get(reverse('order_edit', args=[draft_order.pk]))
        assert response.status_code == 302  # Redirected

        # Verify order unchanged
        draft_order.refresh_from_db()
        assert draft_order.side == 'BUY'  # Unchanged

    def test_submit_order_workflow(self, client, maker_user, draft_order):
        """Test submitting order for approval"""
        client.force_login(maker_user)

        response = client.post(reverse('order_submit', args=[draft_order.pk]))
        assert response.status_code == 302

        # Verify status changed
        draft_order.refresh_from_db()
        assert draft_order.status == 'PENDING_APPROVAL'

    def test_approve_order_workflow(self, client, checker_user, pending_order):
        """Test approving an order"""
        client.force_login(checker_user)

        response = client.post(reverse('order_approve', args=[pending_order.pk]))
        assert response.status_code == 302

        # Verify approval
        pending_order.refresh_from_db()
        assert pending_order.status == 'APPROVED'
        assert pending_order.approved_by == checker_user
        assert pending_order.approved_by_name == checker_user.get_full_name()
        assert pending_order.approved_at is not None

    def test_cannot_approve_own_order(self, client, maker_user, pending_order):
        """Test maker cannot approve their own order"""
        client.force_login(maker_user)

        response = client.post(reverse('order_approve', args=[pending_order.pk]))
        assert response.status_code == 302  # Redirected

        # Verify order not approved
        pending_order.refresh_from_db()
        assert pending_order.status == 'PENDING_APPROVAL'
        assert pending_order.approved_by is None

    def test_reject_order_workflow(self, client, checker_user, pending_order):
        """Test rejecting an order"""
        client.force_login(checker_user)

        response = client.post(reverse('order_reject', args=[pending_order.pk]), {
            'rejection_reason': 'Price is too high for current market conditions'
        })
        assert response.status_code == 302

        # Verify rejection
        pending_order.refresh_from_db()
        assert pending_order.status == 'REJECTED'
        assert pending_order.approved_by == checker_user
        assert pending_order.rejection_reason == 'Price is too high for current market conditions'
        assert pending_order.approved_at is not None

    def test_delete_draft_order_workflow(self, client, maker_user, draft_order):
        """Test deleting a draft order"""
        client.force_login(maker_user)
        order_pk = draft_order.pk

        response = client.post(reverse('order_delete', args=[draft_order.pk]))
        assert response.status_code == 302

        # Verify order deleted
        assert not Order.objects.filter(pk=order_pk).exists()

    def test_cannot_delete_pending_order(self, client, maker_user, pending_order):
        """Test cannot delete pending order"""
        client.force_login(maker_user)
        order_pk = pending_order.pk

        response = client.post(reverse('order_delete', args=[pending_order.pk]))
        assert response.status_code == 302  # Redirected

        # Verify order still exists
        assert Order.objects.filter(pk=order_pk).exists()

    def test_complete_workflow_draft_to_approved(self, client, maker_user, checker_user, test_stock, test_client):
        """Test complete workflow: create -> submit -> approve"""
        # Step 1: Maker creates order
        client.force_login(maker_user)
        response = client.post(reverse('order_create'), {
            'stock': test_stock.id,
            'side': 'BUY',
            'order_type': 'MARKET',
            'quantity': 100,
            'client': test_client.id,
            'validity': 'DAY'
        })

        order = Order.objects.filter(created_by=maker_user).first()
        assert order.status == 'DRAFT'

        # Step 2: Maker submits for approval
        response = client.post(reverse('order_submit', args=[order.pk]))
        order.refresh_from_db()
        assert order.status == 'PENDING_APPROVAL'

        # Step 3: Checker approves
        client.force_login(checker_user)
        response = client.post(reverse('order_approve', args=[order.pk]))
        order.refresh_from_db()
        assert order.status == 'APPROVED'
        assert order.approved_by == checker_user

    def test_order_list_view(self, client, maker_user, draft_order, pending_order):
        """Test order list view"""
        client.force_login(maker_user)
        response = client.get(reverse('order_list'))

        assert response.status_code == 200
        content = response.content.decode()
        assert draft_order.order_id in content
        assert pending_order.order_id in content

    def test_order_list_filter_by_status(self, client, maker_user, draft_order, pending_order):
        """Test filtering orders by status"""
        client.force_login(maker_user)
        response = client.get(reverse('order_list') + '?status=DRAFT')

        assert response.status_code == 200
        content = response.content.decode()
        assert draft_order.order_id in content
        # Pending order should not appear in DRAFT filter

    def test_order_detail_view(self, client, maker_user, draft_order):
        """Test order detail view"""
        client.force_login(maker_user)
        response = client.get(reverse('order_detail', args=[draft_order.pk]))

        assert response.status_code == 200
        content = response.content.decode()
        assert draft_order.order_id in content
        assert draft_order.stock.symbol in content
