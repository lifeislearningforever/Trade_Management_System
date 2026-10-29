"""Tests for edge_jobs_py36/rename_security_labels.py."""
import argparse
from unittest.mock import patch

import pytest

from rename_security_labels import Command, TeeWriter, _esc, POSITION_TABLE, TRADE_TABLE
from lib.management_base import CommandError


def _write_csv(tmp_path, lines, name='mapping.csv'):
    path = tmp_path / name
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


class TestEsc:
    def test_escapes_single_quote(self):
        assert _esc("O'Brien") == "O\\'Brien"

    def test_escapes_backslash(self):
        assert _esc('a\\b') == 'a\\\\b'

    def test_strips_null_bytes(self):
        assert _esc('a\x00b') == 'ab'


class TestTeeWriter:
    def test_writes_to_stdout(self):
        captured = []

        class FakeStdout:
            def write(self, msg):
                captured.append(msg)
        tee = TeeWriter(FakeStdout())
        tee.write('hi')
        assert captured == ['hi']

    def test_writes_stripped_to_file(self, tmp_path):
        out_path = tmp_path / 'log.txt'

        class FakeStdout:
            def write(self, msg):
                pass
        tee = TeeWriter(FakeStdout(), str(out_path))
        tee.write('\x1b[31mred\x1b[0m')
        tee.close()
        assert out_path.read_text() == 'red\n'

    def test_close_without_file_is_safe(self):
        class FakeStdout:
            def write(self, msg):
                pass
        TeeWriter(FakeStdout()).close()


class TestReadCsv:
    def test_reads_two_column_rows(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ',')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_skips_recognized_header_row(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['old_security_name,new_security_name', 'LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ',')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_skips_rows_with_fewer_than_two_columns(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ONLY_ONE_COLUMN', 'LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ',')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_skips_rows_with_empty_old_or_new(self, tmp_path):
        csv_path = _write_csv(tmp_path, [',NEW', 'OLD,', 'LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ',')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_strips_whitespace(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['  LEGACY SEC  ,  REPLACEMENT SEC  '])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ',')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_custom_delimiter(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC;REPLACEMENT SEC'])
        cmd = Command()
        rows = cmd._read_csv(csv_path, ';')
        assert rows == [('LEGACY SEC', 'REPLACEMENT SEC')]

    def test_raises_command_error_when_file_missing(self):
        cmd = Command()
        with pytest.raises(CommandError, match='CSV file not found'):
            cmd._read_csv('/no/such/file.csv', ',')

    def test_raises_command_error_on_unexpected_failure(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('builtins.open', side_effect=OSError('disk error')):
            with pytest.raises(CommandError, match='Error reading CSV'):
                cmd._read_csv(csv_path, ',')

    def test_empty_file_returns_empty_list(self, tmp_path):
        csv_path = tmp_path / 'empty.csv'
        csv_path.write_text('', encoding='utf-8')
        cmd = Command()
        assert cmd._read_csv(str(csv_path), ',') == []


class TestCount:
    def test_returns_count(self):
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 4}]
            assert cmd._count(POSITION_TABLE, 'OLD') == 4

    def test_returns_zero_when_no_rows(self):
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd._count(POSITION_TABLE, 'OLD') == 0

    def test_returns_negative_one_on_exception(self):
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd._count(POSITION_TABLE, 'OLD') == -1


class TestHandleDryRun:
    def test_no_rows_raises_command_error(self, tmp_path):
        csv_path = _write_csv(tmp_path, [])
        cmd = Command()
        with pytest.raises(CommandError, match='No rows found'):
            cmd.handle(csv=csv_path, execute=False, dry_run=False, update_trades=False,
                       delimiter=',', output=None)

    def test_dry_run_shows_position_counts_only_by_default(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 3}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'positions=3' in out
        assert 'trades=' not in out
        mock_mgr.execute_write.assert_not_called()

    def test_dry_run_shows_trade_counts_when_update_trades(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 2}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, update_trades=True,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'trades=2' in out
        assert 'TOTAL trade rows to rename' in out

    def test_dry_run_flag_overrides_execute(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 3}]
            cmd.handle(csv=csv_path, execute=True, dry_run=True, update_trades=False,
                       delimiter=',', output=None)
        mock_mgr.execute_write.assert_not_called()

    def test_no_match_rows_are_flagged(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['UNKNOWN,NEW'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 0}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'NO MATCH' in out

    def test_writes_output_file(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        out_path = tmp_path / 'log.txt'
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 1}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, update_trades=False,
                       delimiter=',', output=str(out_path))
        assert 'LEGACY SEC' in out_path.read_text()


class TestHandleExecute:
    def test_execute_renames_position_rows(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'Renamed 5 position row(s)' in out
        assert 'trade row(s)' not in out

    def test_execute_also_renames_trade_rows_when_flagged(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=True,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'Renamed 5 trade row(s)' in out
        assert mock_mgr.execute_write.call_count == 2

    def test_execute_skips_zero_row_names(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['UNKNOWN,NEW'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 0}]
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'SKIP (0 rows)' in out
        mock_mgr.execute_write.assert_not_called()

    def test_execute_does_not_update_trades_when_trade_count_zero(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            # position count 5, trade count 0
            mock_mgr.execute_query.side_effect = [[{'cnt': 5}], [{'cnt': 0}]]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=True,
                       delimiter=',', output=None)
        assert mock_mgr.execute_write.call_count == 1  # only position update ran

    def test_execute_reports_fail_on_position_update_false(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit) as exc_info:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.return_value = False
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert 'FAIL position' in out

    def test_execute_reports_error_on_position_update_exception(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit):
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.side_effect = RuntimeError('boom')
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'ERROR position' in out

    def test_execute_reports_fail_on_trade_update_false(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit):
            mock_mgr.execute_query.side_effect = [[{'cnt': 5}], [{'cnt': 3}]]
            mock_mgr.execute_write.side_effect = [True, False]
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=True,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'FAIL trade' in out

    def test_execute_reports_error_on_trade_update_exception(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit):
            mock_mgr.execute_query.side_effect = [[{'cnt': 5}], [{'cnt': 3}]]
            mock_mgr.execute_write.side_effect = [True, RuntimeError('boom')]
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=True,
                       delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'ERROR trade' in out

    def test_execute_all_success_does_not_exit(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['LEGACY SEC,REPLACEMENT SEC'])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)  # no SystemExit

    def test_update_query_targets_correct_table_and_values(self, tmp_path):
        csv_path = _write_csv(tmp_path, ["O'LD,N'EW"])
        cmd = Command()
        with patch('rename_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 1}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, update_trades=False,
                       delimiter=',', output=None)
        update_sql = mock_mgr.execute_write.call_args[0][0]
        assert POSITION_TABLE in update_sql
        assert "O\\'LD" in update_sql
        assert "N\\'EW" in update_sql


class TestAddArguments:
    def test_csv_required(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args(['--csv', 'x.csv'])
        assert args.execute is False
        assert args.dry_run is False
        assert args.update_trades is False
        assert args.delimiter == ','
        assert args.output is None

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([
            '--csv', 'x.csv', '--execute', '--update-trades', '--delimiter', ';', '--output', 'o.txt',
        ])
        assert args.execute is True
        assert args.update_trades is True
        assert args.delimiter == ';'
        assert args.output == 'o.txt'
