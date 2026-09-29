"""Tests for edge_jobs_py36/backfill_cancelled_trade_visibility.py."""
from unittest.mock import MagicMock, patch

import pytest

from backfill_cancelled_trade_visibility import Command
from lib.management_base import CommandError


def _mock_connection(fetchone_result):
    """Build a mock impala_manager whose get_connection() context manager
    yields a connection with a cursor that returns fetchone_result."""
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = fetchone_result
    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_mgr = MagicMock()
    mock_mgr.get_connection.return_value.__enter__.return_value = mock_conn
    mock_mgr.get_connection.return_value.__exit__.return_value = False
    return mock_mgr, mock_cursor


class TestNothingToBackfill:
    def test_prints_success_message_when_count_is_zero(self, capsys):
        mock_mgr, _ = _mock_connection((0,))
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=False)
        out = capsys.readouterr().out
        assert 'Nothing to backfill.' in out

    def test_does_not_run_update_when_count_is_zero(self):
        mock_mgr, _ = _mock_connection((0,))
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=True)
        mock_mgr.execute_write.assert_not_called()

    def test_treats_none_row_as_zero_affected(self, capsys):
        mock_mgr, _ = _mock_connection(None)
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=False)
        out = capsys.readouterr().out
        assert 'Nothing to backfill.' in out


class TestDryRun:
    def test_prints_count_and_warning_without_apply(self, capsys):
        mock_mgr, _ = _mock_connection((5,))
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=False)
        out = capsys.readouterr().out
        assert '5' in out
        assert 'Dry run only' in out

    def test_does_not_call_execute_write_without_apply(self):
        mock_mgr, _ = _mock_connection((5,))
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=False)
        mock_mgr.execute_write.assert_not_called()


class TestApply:
    def test_runs_update_and_prints_success_on_apply(self, capsys):
        mock_mgr, _ = _mock_connection((5,))
        mock_mgr.execute_write.return_value = True
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=True)
        out = capsys.readouterr().out
        assert 'Backfill complete' in out
        assert '5' in out

    def test_update_query_contains_expected_filter(self):
        mock_mgr, _ = _mock_connection((3,))
        mock_mgr.execute_write.return_value = True
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=True)
        update_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'is_deleted = false' in update_sql
        assert "status = 'CANCELLED'" in update_sql
        assert 'is_deleted = true' in update_sql

    def test_raises_command_error_when_update_fails(self):
        mock_mgr, _ = _mock_connection((3,))
        mock_mgr.execute_write.return_value = False
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            with pytest.raises(CommandError, match='Backfill UPDATE failed'):
                cmd.handle(apply=True)


class TestAddArguments:
    def test_add_arguments_registers_apply_flag(self):
        import argparse
        parser = argparse.ArgumentParser()
        cmd = Command()
        cmd.add_arguments(parser)
        args = parser.parse_args(['--apply'])
        assert args.apply is True

    def test_apply_flag_defaults_to_false(self):
        import argparse
        parser = argparse.ArgumentParser()
        cmd = Command()
        cmd.add_arguments(parser)
        args = parser.parse_args([])
        assert args.apply is False


class TestCountQuery:
    def test_count_query_uses_trade_table_and_database(self):
        mock_mgr, _ = _mock_connection((0,))
        with patch('backfill_cancelled_trade_visibility.impala_manager', mock_mgr):
            cmd = Command()
            cmd.handle(apply=False)
        count_sql = mock_mgr.get_connection.return_value.__enter__.return_value.cursor.return_value.execute.call_args[0][0]
        assert 'cis_trade' in count_sql
        assert "status = 'CANCELLED'" in count_sql
        assert 'is_deleted = true' in count_sql
