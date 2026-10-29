"""Tests for edge_jobs_py36/delete_security_labels.py."""
import argparse
from unittest.mock import patch

import pytest

from delete_security_labels import Command, TeeWriter, _esc, SECURITY_TABLE
from lib.management_base import CommandError


def _write_csv(tmp_path, lines, name='securities.csv'):
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

    def test_plain_string_unchanged(self):
        assert _esc('ACME CORP') == 'ACME CORP'


class TestTeeWriter:
    def test_writes_to_stdout_wrapper(self):
        captured = []

        class FakeStdout:
            def write(self, msg):
                captured.append(msg)

        tee = TeeWriter(FakeStdout())
        tee.write('hello')
        assert captured == ['hello']

    def test_writes_to_file_when_path_given(self, tmp_path):
        out_path = tmp_path / 'log.txt'

        class FakeStdout:
            def write(self, msg):
                pass

        tee = TeeWriter(FakeStdout(), str(out_path))
        tee.write('hello')
        tee.close()
        assert out_path.read_text() == 'hello\n'

    def test_strips_ansi_codes_before_writing_to_file(self, tmp_path):
        out_path = tmp_path / 'log.txt'

        class FakeStdout:
            def write(self, msg):
                pass

        tee = TeeWriter(FakeStdout(), str(out_path))
        tee.write('\x1b[33mwarning\x1b[0m')
        tee.close()
        assert out_path.read_text() == 'warning\n'

    def test_close_without_file_does_not_raise(self):
        class FakeStdout:
            def write(self, msg):
                pass
        tee = TeeWriter(FakeStdout())
        tee.close()  # must not raise

    def test_no_file_write_when_filepath_is_none(self):
        class FakeStdout:
            def write(self, msg):
                pass
        tee = TeeWriter(FakeStdout(), None)
        assert tee._file is None
        tee.write('x')  # must not raise


class TestReadCsv:
    def test_reads_simple_list_without_header(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP', 'BETA INC'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP', 'BETA INC']

    def test_skips_recognized_header_row(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['security_name', 'ACME CORP'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP']

    def test_header_detection_is_case_insensitive(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['Security_Name', 'ACME CORP'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP']

    def test_first_row_not_a_recognized_header_is_kept_as_data(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP', 'BETA INC'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert 'ACME CORP' in names

    def test_skips_blank_lines(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP', '', 'BETA INC'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP', 'BETA INC']

    def test_skips_row_with_empty_first_column(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP', ',extra', 'BETA INC'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP', 'BETA INC']

    def test_strips_whitespace_from_names(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['  ACME CORP  '])
        cmd = Command()
        names = cmd._read_csv(csv_path, ',')
        assert names == ['ACME CORP']

    def test_custom_delimiter(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP;extra', 'BETA INC;extra'])
        cmd = Command()
        names = cmd._read_csv(csv_path, ';')
        assert names == ['ACME CORP', 'BETA INC']

    def test_raises_command_error_when_file_missing(self):
        cmd = Command()
        with pytest.raises(CommandError, match='CSV file not found'):
            cmd._read_csv('/nonexistent/path.csv', ',')

    def test_empty_file_returns_empty_list(self, tmp_path):
        csv_path = tmp_path / 'empty.csv'
        csv_path.write_text('', encoding='utf-8')
        cmd = Command()
        names = cmd._read_csv(str(csv_path), ',')
        assert names == []

    def test_raises_command_error_on_unexpected_read_failure(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('builtins.open', side_effect=OSError('disk error')):
            with pytest.raises(CommandError, match='Error reading CSV'):
                cmd._read_csv(csv_path, ',')


class TestCount:
    def test_returns_count_from_query_result(self):
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            assert cmd._count('ACME CORP') == 5

    def test_returns_zero_when_no_rows(self):
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd._count('ACME CORP') == 0

    def test_returns_negative_one_on_exception(self):
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd._count('ACME CORP') == -1

    def test_query_uses_escaped_name(self):
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 0}]
            cmd._count("O'BRIEN CO")
        query = mock_mgr.execute_query.call_args[0][0]
        assert "O\\'BRIEN CO" in query
        assert SECURITY_TABLE in query


class TestHandleDryRun:
    def test_no_names_raises_command_error(self, tmp_path):
        csv_path = _write_csv(tmp_path, [])
        cmd = Command()
        with pytest.raises(CommandError, match='No security names found'):
            cmd.handle(csv=csv_path, execute=False, dry_run=False, delimiter=',', output=None)

    def test_dry_run_shows_counts_and_does_not_delete(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 3}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'DRY-RUN' in out
        assert 'rows=3' in out
        mock_mgr.execute_write.assert_not_called()

    def test_dry_run_flag_overrides_execute(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 3}]
            cmd.handle(csv=csv_path, execute=True, dry_run=True, delimiter=',', output=None)
        mock_mgr.execute_write.assert_not_called()

    def test_no_match_names_are_flagged(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['UNKNOWN CO'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 0}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'NO MATCH' in out

    def test_writes_output_file_when_requested(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        out_path = tmp_path / 'log.txt'
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 1}]
            cmd.handle(csv=csv_path, execute=False, dry_run=False, delimiter=',', output=str(out_path))
        assert out_path.exists()
        assert 'ACME CORP' in out_path.read_text()


class TestHandleExecute:
    def test_execute_deletes_matching_rows(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 5}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'Deleted 5 cis_security row(s)' in out
        mock_mgr.execute_write.assert_called_once()

    def test_execute_skips_zero_row_names(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['UNKNOWN CO'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 0}]
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)
        out = capsys.readouterr().out
        assert 'SKIP (0 rows)' in out
        mock_mgr.execute_write.assert_not_called()

    def test_execute_reports_fail_when_delete_returns_false(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit) as exc_info:
            mock_mgr.execute_query.return_value = [{'cnt': 2}]
            mock_mgr.execute_write.return_value = False
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert 'FAIL' in out

    def test_execute_reports_error_and_exits_on_exception(self, tmp_path, capsys):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr, \
             pytest.raises(SystemExit) as exc_info:
            mock_mgr.execute_query.return_value = [{'cnt': 2}]
            mock_mgr.execute_write.side_effect = RuntimeError('connection lost')
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert 'ERROR' in out

    def test_delete_query_uses_escaped_name_and_table(self, tmp_path):
        csv_path = _write_csv(tmp_path, ["O'BRIEN CO"])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 1}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)
        delete_sql = mock_mgr.execute_write.call_args[0][0]
        assert 'DELETE FROM' in delete_sql
        assert "O\\'BRIEN CO" in delete_sql

    def test_execute_with_no_errors_does_not_exit(self, tmp_path):
        csv_path = _write_csv(tmp_path, ['ACME CORP'])
        cmd = Command()
        with patch('delete_security_labels.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 1}]
            mock_mgr.execute_write.return_value = True
            cmd.handle(csv=csv_path, execute=True, dry_run=False, delimiter=',', output=None)  # no SystemExit


class TestAddArguments:
    def test_registers_all_expected_flags(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args(['--csv', 'x.csv'])
        assert args.csv == 'x.csv'
        assert args.execute is False
        assert args.dry_run is False
        assert args.delimiter == ','
        assert args.output is None

    def test_csv_is_required(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_execute_and_output_flags_parse(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args(['--csv', 'x.csv', '--execute', '--output', 'log.txt', '--delimiter', ';'])
        assert args.execute is True
        assert args.output == 'log.txt'
        assert args.delimiter == ';'
