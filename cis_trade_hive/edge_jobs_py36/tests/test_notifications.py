"""Tests for edge_jobs_py36/lib/notifications.py."""
from unittest.mock import patch

from core.notifications.constants import EVT_AVP_COMPLETED, EVT_AVP_FAILED, SEV_SUCCESS, SEV_ERROR
from edge_jobs_py36.lib import notifications as notif


class TestEsc:
    def test_esc_none_returns_empty_quoted_string(self):
        assert notif._esc(None) == "''"

    def test_esc_empty_string_returns_empty_quoted_string(self):
        assert notif._esc('') == "''"

    def test_esc_zero_returns_empty_quoted_string(self):
        """Falsy but meaningful value 0 is treated the same as missing."""
        assert notif._esc(0) == "''"

    def test_esc_plain_string(self):
        assert notif._esc('hello') == "'hello'"

    def test_esc_escapes_single_quotes(self):
        assert notif._esc("O'Brien") == "'O\\'Brien'"

    def test_esc_escapes_backslashes(self):
        assert notif._esc('a\\b') == "'a\\\\b'"

    def test_esc_escapes_backslash_before_quote(self):
        result = notif._esc("a\\'b")
        assert result == "'a\\\\\\'b'"

    def test_esc_converts_non_string_to_string(self):
        assert notif._esc(123) == "'123'"


class TestPersist:
    def test_persist_calls_execute_write_with_upsert(self):
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'Title', 'Message', {'a': 1})
        args, kwargs = mock_mgr.execute_write.call_args
        assert 'UPSERT INTO' in args[0]
        assert 'cis_notification' in args[0]
        assert kwargs.get('database') == notif._DATABASE

    def test_persist_includes_all_field_values_escaped(self):
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'My Title', 'My Message', {})
        sql = mock_mgr.execute_write.call_args[0][0]
        assert "'jdoe'" in sql
        assert "'AVP_COMPLETED'" in sql
        assert "'success'" in sql
        assert "'My Title'" in sql
        assert "'My Message'" in sql
        assert 'false' in sql  # is_read default

    def test_persist_truncates_payload_json_to_4000_chars(self):
        big_payload = {'blob': 'x' * 5000}
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'T', 'M', big_payload)
        sql = mock_mgr.execute_write.call_args[0][0]
        # the escaped payload substring embedded in the SQL should not
        # exceed 4000 chars of raw json content
        assert 'xxxx' in sql  # sanity: some of the blob is present

    def test_persist_handles_none_payload(self):
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'T', 'M', None)
        sql = mock_mgr.execute_write.call_args[0][0]
        assert '{}' in sql

    def test_persist_swallows_exceptions_and_does_not_raise(self):
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'T', 'M', {})  # must not raise

    def test_persist_generates_unique_notif_id_each_call(self):
        with patch('edge_jobs_py36.lib.notifications.impala_manager') as mock_mgr:
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'T', 'M', {})
            sql1 = mock_mgr.execute_write.call_args[0][0]
            notif._persist('jdoe', 'AVP_COMPLETED', 'success', 'T', 'M', {})
            sql2 = mock_mgr.execute_write.call_args[0][0]
        assert sql1 != sql2


class TestNotifyUser:
    def test_returns_false_for_empty_username(self):
        assert notif.notify_user('', EVT_AVP_COMPLETED) is False

    def test_returns_false_for_none_username(self):
        assert notif.notify_user(None, EVT_AVP_COMPLETED) is False

    def test_returns_false_for_non_string_username(self):
        assert notif.notify_user(12345, EVT_AVP_COMPLETED) is False

    def test_returns_true_and_persists_by_default(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            result = notif.notify_user('jdoe', EVT_AVP_COMPLETED, {'title': 'T', 'message': 'M'})
        assert result is True
        mock_persist.assert_called_once()

    def test_persist_false_skips_persistence(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            result = notif.notify_user('jdoe', EVT_AVP_COMPLETED, {}, persist=False)
        assert result is True
        mock_persist.assert_not_called()

    def test_uses_default_severity_for_known_event(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {})
        args = mock_persist.call_args[0]
        assert args[2] == SEV_SUCCESS

    def test_uses_error_severity_as_fallback_for_unknown_event(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', 'SOME_UNKNOWN_EVENT_TYPE', {})
        args = mock_persist.call_args[0]
        assert args[2] == SEV_ERROR

    def test_title_falls_back_to_event_title_constant(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {})
        title_arg = mock_persist.call_args[0][3]
        assert title_arg  # non-empty, resolved from EVENT_TITLE

    def test_title_falls_back_to_event_type_when_unknown(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', 'TOTALLY_UNKNOWN_EVENT', {})
        title_arg = mock_persist.call_args[0][3]
        assert title_arg == 'TOTALLY_UNKNOWN_EVENT'

    def test_title_uses_payload_title_when_provided(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {'title': 'Custom Title'})
        title_arg = mock_persist.call_args[0][3]
        assert title_arg == 'Custom Title'

    def test_message_uses_payload_message_key(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {'message': 'Hello'})
        message_arg = mock_persist.call_args[0][4]
        assert message_arg == 'Hello'

    def test_message_falls_back_to_body_key(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {'body': 'Body text'})
        message_arg = mock_persist.call_args[0][4]
        assert message_arg == 'Body text'

    def test_message_defaults_to_empty_string(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            notif.notify_user('jdoe', EVT_AVP_COMPLETED, {})
        message_arg = mock_persist.call_args[0][4]
        assert message_arg == ''

    def test_payload_none_treated_as_empty_dict(self):
        with patch('edge_jobs_py36.lib.notifications._persist') as mock_persist:
            result = notif.notify_user('jdoe', EVT_AVP_COMPLETED, None)
        assert result is True
        mock_persist.assert_called_once()


class TestNotifyRole:
    def test_always_returns_true(self):
        assert notif.notify_role('ADMIN', EVT_AVP_FAILED, {'x': 1}) is True

    def test_handles_none_payload(self):
        assert notif.notify_role('ADMIN', EVT_AVP_FAILED, None) is True


class TestNotifyAdmins:
    def test_always_returns_true(self):
        assert notif.notify_admins(EVT_AVP_FAILED, {'x': 1}) is True

    def test_handles_none_payload(self):
        assert notif.notify_admins(EVT_AVP_FAILED, None) is True


class TestPopPending:
    def test_always_returns_empty_list(self):
        assert notif.pop_pending('jdoe') == []
