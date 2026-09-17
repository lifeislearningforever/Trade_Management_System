"""
Tests for the {% can_act %} template tag (core/templatetags/core_filters.py).

No test coverage existed for this tag at all before this file -- it is what
trade_detail.html and trade_list.html actually render permission-gated
buttons from (the trade_detail view's own can_validate/can_approve_
cancellation context is dead code by comparison, since neither template
reads it). That gap is how the maker-sees-checker-buttons bug went
unnoticed: the four-eyes guard was added to the backend views
(trade_validate, trade_approve_cancellation, trade_reject_cancellation) but
never mirrored into this tag, so the UI kept showing Validate/Approve/Reject
to the same user who created the trade or requested its cancellation.
"""

from unittest.mock import MagicMock

from django.test import RequestFactory, TestCase, override_settings

from core.templatetags.core_filters import can_act


@override_settings(SKIP_PERMISSION_CHECKS=False)
class CanActTradeTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, username, permissions=None):
        request = self.factory.get('/')
        request.session = {
            'user_login': username,
            'user_permissions': permissions or {'trade-edit': 'WRITE', 'trade-approval': 'WRITE'},
        }
        return {'request': request}

    def _trade(self, **overrides):
        base = {
            'src_system': 'CIS',
            'status': 'INITIAL',
            'is_deleted': False,
            'created_by': 'MAKER1',
            'cancelled_by': '',
        }
        base.update(overrides)
        return base

    def test_creator_cannot_validate_own_trade(self):
        trade = self._trade(status='INITIAL', created_by='MAKER1')
        context = self._request('MAKER1')
        actions = can_act(context, trade, 'trade')
        self.assertFalse(actions['can_validate'])

    def test_different_user_can_validate(self):
        trade = self._trade(status='INITIAL', created_by='MAKER1')
        context = self._request('CHECKER1')
        actions = can_act(context, trade, 'trade')
        self.assertTrue(actions['can_validate'])

    def test_requester_cannot_approve_own_cancellation(self):
        trade = self._trade(status='MODIFIED', is_deleted=True, cancelled_by='MAKER1')
        context = self._request('MAKER1')
        actions = can_act(context, trade, 'trade')
        self.assertFalse(actions['can_approve_cancellation'])
        self.assertFalse(actions['can_reject_cancellation'])

    def test_requester_cannot_reject_own_cancellation(self):
        trade = self._trade(status='MODIFIED', is_deleted=True, cancelled_by='MAKER1')
        context = self._request('MAKER1')
        actions = can_act(context, trade, 'trade')
        self.assertFalse(actions['can_reject_cancellation'])

    def test_different_user_can_approve_cancellation(self):
        trade = self._trade(status='MODIFIED', is_deleted=True, cancelled_by='MAKER1')
        context = self._request('CHECKER1')
        actions = can_act(context, trade, 'trade')
        self.assertTrue(actions['can_approve_cancellation'])
        self.assertTrue(actions['can_reject_cancellation'])

    def test_no_write_permission_still_blocks_regardless_of_identity(self):
        trade = self._trade(status='MODIFIED', is_deleted=True, cancelled_by='MAKER1')
        context = self._request('CHECKER1', permissions={'trade-edit': 'WRITE', 'trade-approval': 'READ'})
        actions = can_act(context, trade, 'trade')
        self.assertFalse(actions['can_approve_cancellation'])
