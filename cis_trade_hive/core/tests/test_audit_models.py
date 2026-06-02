"""
Tests for core/audit/audit_models.py
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from django.test import TestCase

from core.audit.audit_models import (
    ActionType,
    ActionCategory,
    AuditStatus,
    EntityType,
    AuditEntry,
)


class ActionTypeEnumTestCase(TestCase):
    def test_all_action_types_have_values(self):
        for member in ActionType:
            self.assertEqual(member.value, member.name)

    def test_create_value(self):
        self.assertEqual(ActionType.CREATE.value, 'CREATE')

    def test_login_value(self):
        self.assertEqual(ActionType.LOGIN.value, 'LOGIN')

    def test_approve_value(self):
        self.assertEqual(ActionType.APPROVE.value, 'APPROVE')


class AuditStatusEnumTestCase(TestCase):
    def test_success(self):
        self.assertEqual(AuditStatus.SUCCESS.value, 'SUCCESS')

    def test_failure(self):
        self.assertEqual(AuditStatus.FAILURE.value, 'FAILURE')

    def test_partial(self):
        self.assertEqual(AuditStatus.PARTIAL.value, 'PARTIAL')


class EntityTypeEnumTestCase(TestCase):
    def test_portfolio(self):
        self.assertEqual(EntityType.PORTFOLIO.value, 'PORTFOLIO')

    def test_trade(self):
        self.assertEqual(EntityType.TRADE.value, 'TRADE')


class AuditEntryTestCase(TestCase):
    def setUp(self):
        self.entry = AuditEntry(
            action_type=ActionType.CREATE,
            action_category=ActionCategory.TRADE,
            username='testuser',
        )

    def test_creates_with_required_fields(self):
        self.assertEqual(self.entry.action_type, ActionType.CREATE)
        self.assertEqual(self.entry.username, 'testuser')

    def test_auto_sets_timestamp(self):
        self.assertIsNotNone(self.entry.audit_timestamp)

    def test_auto_sets_audit_date(self):
        self.assertIsNotNone(self.entry.audit_date)
        self.assertRegex(self.entry.audit_date, r'\d{4}-\d{2}-\d{2}')

    def test_default_status_is_success(self):
        self.assertEqual(self.entry.status, AuditStatus.SUCCESS)

    def test_optional_fields_default_to_none(self):
        self.assertIsNone(self.entry.user_id)
        self.assertIsNone(self.entry.entity_type)
        self.assertIsNone(self.entry.ip_address)

    def test_to_dict_converts_enums_to_values(self):
        data = self.entry.to_dict()
        self.assertEqual(data['action_type'], 'CREATE')
        self.assertEqual(data['action_category'], 'TRADE')
        self.assertEqual(data['status'], 'SUCCESS')

    def test_to_dict_with_entity_type(self):
        entry = AuditEntry(
            action_type=ActionType.UPDATE,
            action_category=ActionCategory.TRADE,
            username='testuser',
            entity_type=EntityType.PORTFOLIO,
        )
        data = entry.to_dict()
        self.assertEqual(data['entity_type'], 'PORTFOLIO')

    def test_to_dict_with_none_entity_type(self):
        data = self.entry.to_dict()
        self.assertIsNone(data['entity_type'])

    def test_to_dict_serializes_request_params(self):
        entry = AuditEntry(
            action_type=ActionType.READ,
            action_category=ActionCategory.DATA,
            username='testuser',
            request_params={'page': '1', 'limit': '25'},
        )
        data = entry.to_dict()
        self.assertIsInstance(data['request_params'], str)
        parsed = json.loads(data['request_params'])
        self.assertEqual(parsed['page'], '1')

    def test_to_dict_serializes_tags(self):
        entry = AuditEntry(
            action_type=ActionType.CREATE,
            action_category=ActionCategory.DATA,
            username='testuser',
            tags=['tag1', 'tag2'],
        )
        data = entry.to_dict()
        self.assertEqual(data['tags'], 'tag1,tag2')

    def test_to_dict_serializes_metadata(self):
        entry = AuditEntry(
            action_type=ActionType.CREATE,
            action_category=ActionCategory.DATA,
            username='testuser',
            metadata={'key': 'value'},
        )
        data = entry.to_dict()
        self.assertIsInstance(data['metadata'], str)
        parsed = json.loads(data['metadata'])
        self.assertEqual(parsed['key'], 'value')

    def test_to_hive_values_returns_tuple(self):
        result = self.entry.to_hive_values()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 30)

    def test_to_hive_values_contains_username(self):
        result = self.entry.to_hive_values()
        self.assertIn('testuser', result)

    def test_to_hive_values_contains_action_type(self):
        result = self.entry.to_hive_values()
        self.assertIn('CREATE', result)

    def test_from_request_authenticated_user(self):
        request = MagicMock()
        request.user.is_authenticated = True
        request.user.username = 'alice'
        request.user.id = 42
        request.user.email = 'alice@example.com'
        request.method = 'GET'
        request.path = '/test/'
        request.GET = {'page': '1'}
        request.POST = {}
        request.session.session_key = 'sess123'
        request.META = {'REMOTE_ADDR': '127.0.0.1', 'HTTP_USER_AGENT': 'TestBrowser/1.0'}

        entry = AuditEntry.from_request(
            request,
            ActionType.READ,
            ActionCategory.DATA,
        )

        self.assertEqual(entry.username, 'alice')
        self.assertEqual(entry.user_id, '42')
        self.assertEqual(entry.ip_address, '127.0.0.1')

    def test_from_request_anonymous_user(self):
        request = MagicMock()
        request.user.is_authenticated = False
        request.method = 'GET'
        request.path = '/test/'
        request.GET = {}
        request.POST = {}
        request.session.session_key = None
        request.META = {'REMOTE_ADDR': '10.0.0.1'}

        entry = AuditEntry.from_request(request, ActionType.READ, ActionCategory.DATA)

        self.assertEqual(entry.username, 'anonymous')
        self.assertIsNone(entry.user_id)

    def test_from_request_post_method(self):
        request = MagicMock()
        request.user.is_authenticated = False
        request.method = 'POST'
        request.path = '/create/'
        request.GET = {}
        request.POST = {'name': 'test'}
        request.session.session_key = None
        request.META = {'REMOTE_ADDR': '127.0.0.1'}

        entry = AuditEntry.from_request(request, ActionType.CREATE, ActionCategory.DATA)

        self.assertEqual(entry.request_method, 'POST')

    def test_get_client_ip_x_forwarded_for(self):
        request = MagicMock()
        request.META = {
            'HTTP_X_FORWARDED_FOR': '203.0.113.1, 198.51.100.2',
            'REMOTE_ADDR': '127.0.0.1',
        }
        ip = AuditEntry._get_client_ip(request)
        self.assertEqual(ip, '203.0.113.1')

    def test_get_client_ip_remote_addr_fallback(self):
        request = MagicMock()
        request.META = {'REMOTE_ADDR': '192.168.1.1'}
        ip = AuditEntry._get_client_ip(request)
        self.assertEqual(ip, '192.168.1.1')
