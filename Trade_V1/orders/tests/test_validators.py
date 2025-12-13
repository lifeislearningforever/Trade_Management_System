"""
Order Validators Tests
"""
import pytest
from orders.validators import (
    can_edit_order, can_submit_order, can_approve_order,
    can_reject_order, can_delete_order, get_workflow_error_message
)


@pytest.mark.unit
@pytest.mark.django_db
class TestOrderValidators:
    """Test order workflow validators"""

    def test_can_edit_draft_order_by_creator(self, maker_user, draft_order):
        """Maker can edit their own DRAFT order"""
        assert can_edit_order(maker_user, draft_order) is True

    def test_cannot_edit_draft_order_by_other_user(self, checker_user, draft_order):
        """Other users cannot edit draft order"""
        assert can_edit_order(checker_user, draft_order) is False

    def test_cannot_edit_pending_order(self, maker_user, pending_order):
        """Cannot edit PENDING_APPROVAL order"""
        assert can_edit_order(maker_user, pending_order) is False

    def test_cannot_edit_approved_order(self, maker_user, approved_order):
        """Cannot edit APPROVED order"""
        assert can_edit_order(maker_user, approved_order) is False

    def test_can_submit_draft_order_by_creator(self, maker_user, draft_order):
        """Maker can submit their own DRAFT order"""
        assert can_submit_order(maker_user, draft_order) is True

    def test_cannot_submit_pending_order(self, maker_user, pending_order):
        """Cannot submit PENDING_APPROVAL order"""
        assert can_submit_order(maker_user, pending_order) is False

    def test_cannot_submit_other_users_order(self, checker_user, draft_order):
        """Cannot submit other user's order"""
        assert can_submit_order(checker_user, draft_order) is False

    def test_can_approve_pending_order_by_checker(self, checker_user, pending_order):
        """Checker can approve PENDING_APPROVAL order"""
        assert can_approve_order(checker_user, pending_order) is True

    def test_cannot_approve_own_order(self, maker_user, pending_order):
        """Cannot approve own order (four-eyes principle)"""
        assert can_approve_order(maker_user, pending_order) is False

    def test_cannot_approve_draft_order(self, checker_user, draft_order):
        """Cannot approve DRAFT order"""
        assert can_approve_order(checker_user, draft_order) is False

    def test_cannot_approve_approved_order(self, checker_user, approved_order):
        """Cannot approve already APPROVED order"""
        assert can_approve_order(checker_user, approved_order) is False

    def test_can_reject_pending_order_by_checker(self, checker_user, pending_order):
        """Checker can reject PENDING_APPROVAL order"""
        assert can_reject_order(checker_user, pending_order) is True

    def test_cannot_reject_own_order(self, maker_user, pending_order):
        """Cannot reject own order (four-eyes principle)"""
        assert can_reject_order(maker_user, pending_order) is False

    def test_can_delete_draft_order_by_creator(self, maker_user, draft_order):
        """Maker can delete their own DRAFT order"""
        assert can_delete_order(maker_user, draft_order) is True

    def test_cannot_delete_pending_order(self, maker_user, pending_order):
        """Cannot delete PENDING_APPROVAL order"""
        assert can_delete_order(maker_user, pending_order) is False

    def test_cannot_delete_other_users_order(self, checker_user, draft_order):
        """Cannot delete other user's order"""
        assert can_delete_order(checker_user, draft_order) is False

    def test_get_workflow_error_message_edit(self, checker_user, draft_order):
        """Test error message for edit"""
        msg = get_workflow_error_message('edit', checker_user, draft_order)
        assert 'only edit orders you created' in msg.lower()

    def test_get_workflow_error_message_approve_own(self, maker_user, pending_order):
        """Test error message for approving own order"""
        msg = get_workflow_error_message('approve', maker_user, pending_order)
        assert 'cannot approve your own order' in msg.lower()
        assert 'four-eyes' in msg.lower()
