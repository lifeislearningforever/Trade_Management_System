"""Tests for edge_jobs_py36/extract_db_ddl.py."""
import argparse
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest

from extract_db_ddl import Command
from lib.management_base import CommandError


class TestAddArguments:
    def test_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([])
        assert args.tables is None
        assert args.include_data is False
        assert args.data_limit is None
        assert args.output_dir == 'scripts/db_migration/output'

    def test_all_flags_parse(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        args = parser.parse_args([
            '--tables', 'cis_trade,cis_portfolio', '--include-data',
            '--data-limit', '100', '--output-dir', '/tmp/out',
        ])
        assert args.tables == 'cis_trade,cis_portfolio'
        assert args.include_data is True
        assert args.data_limit == 100
        assert args.output_dir == '/tmp/out'


class TestGetAllTables:
    def test_returns_sorted_table_names_from_name_key(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'name': 'cis_trade'}, {'name': 'cis_portfolio'}]
            tables = cmd.get_all_tables()
        assert tables == ['cis_portfolio', 'cis_trade']

    def test_falls_back_to_tab_name_key(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'tab_name': 'cis_trade'}]
            tables = cmd.get_all_tables()
        assert tables == ['cis_trade']

    def test_falls_back_to_first_value_when_no_known_key(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'some_col': 'cis_trade'}]
            tables = cmd.get_all_tables()
        assert tables == ['cis_trade']

    def test_returns_empty_list_when_no_results(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd.get_all_tables() == []

    def test_returns_empty_list_on_exception(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd.get_all_tables() == []


class TestGetTableDdl:
    def test_joins_multiple_rows(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'result': 'CREATE TABLE cis_trade ('},
                {'result': '  id BIGINT'},
            ]
            ddl = cmd.get_table_ddl('cis_trade')
        assert 'CREATE TABLE cis_trade (' in ddl
        assert '\n' in ddl

    def test_handles_non_dict_rows(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = ['plain string row']
            ddl = cmd.get_table_ddl('cis_trade')
        assert ddl == 'plain string row'

    def test_returns_none_when_no_results(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd.get_table_ddl('cis_trade') is None

    def test_returns_none_on_exception(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd.get_table_ddl('cis_trade') is None


class TestGetTableColumns:
    def test_returns_column_dicts(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'name': 'trade_id', 'type': 'bigint', 'comment': ''},
            ]
            cols = cmd.get_table_columns('cis_trade')
        assert cols == [{'name': 'trade_id', 'type': 'bigint', 'comment': ''}]

    def test_falls_back_to_col_name_and_data_type_keys(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [
                {'col_name': 'trade_id', 'data_type': 'bigint'},
            ]
            cols = cmd.get_table_columns('cis_trade')
        assert cols[0]['name'] == 'trade_id'
        assert cols[0]['type'] == 'bigint'

    def test_returns_empty_list_when_no_results(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd.get_table_columns('cis_trade') == []

    def test_returns_empty_list_on_exception(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd.get_table_columns('cis_trade') == []


class TestGetTableRowCount:
    def test_returns_count(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'cnt': 42}]
            assert cmd.get_table_row_count('cis_trade') == 42

    def test_returns_zero_when_no_results(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            assert cmd.get_table_row_count('cis_trade') == 0

    def test_returns_zero_on_exception(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd.get_table_row_count('cis_trade') == 0


class TestGetTableData:
    def test_returns_query_results(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'id': 1}]
            data = cmd.get_table_data('cis_trade')
        assert data == [{'id': 1}]

    def test_applies_limit_when_given(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.get_table_data('cis_trade', limit=50)
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT 50' in query

    def test_no_limit_clause_when_absent(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            cmd.get_table_data('cis_trade')
        query = mock_mgr.execute_query.call_args[0][0]
        assert 'LIMIT' not in query

    def test_returns_empty_list_on_exception(self):
        cmd = Command()
        with patch('extract_db_ddl.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('boom')
            assert cmd.get_table_data('cis_trade') == []


class TestFormatValueForInsert:
    def test_none_returns_null(self):
        cmd = Command()
        assert cmd.format_value_for_insert(None, 'string') == 'NULL'

    def test_string_type_is_quoted_and_escaped(self):
        cmd = Command()
        assert cmd.format_value_for_insert("O'Brien", 'string') == "'O\\'Brien'"

    def test_varchar_type_is_quoted(self):
        cmd = Command()
        assert cmd.format_value_for_insert('abc', 'varchar(10)') == "'abc'"

    def test_int_type_unquoted(self):
        cmd = Command()
        assert cmd.format_value_for_insert(42, 'bigint') == '42'

    def test_decimal_type_converted_to_float_string(self):
        cmd = Command()
        assert cmd.format_value_for_insert(Decimal('1.5'), 'decimal(10,2)') == '1.5'

    def test_boolean_true(self):
        cmd = Command()
        assert cmd.format_value_for_insert(True, 'boolean') == 'true'

    def test_boolean_false(self):
        cmd = Command()
        assert cmd.format_value_for_insert(False, 'boolean') == 'false'

    def test_timestamp_type_is_quoted(self):
        cmd = Command()
        assert cmd.format_value_for_insert('2026-09-17 10:00:00', 'timestamp') == "'2026-09-17 10:00:00'"

    def test_unknown_type_defaults_to_quoted_string(self):
        cmd = Command()
        assert cmd.format_value_for_insert('value', 'some_weird_type') == "'value'"


class TestGenerateInsertStatements:
    def test_returns_empty_list_for_no_data(self):
        cmd = Command()
        assert cmd.generate_insert_statements('cis_trade', [{'name': 'id', 'type': 'bigint'}], []) == []

    def test_generates_one_statement_for_small_batch(self):
        cmd = Command()
        columns = [{'name': 'id', 'type': 'bigint'}, {'name': 'name', 'type': 'string'}]
        data = [{'id': 1, 'name': 'ACME'}]
        stmts = cmd.generate_insert_statements('cis_trade', columns, data)
        assert len(stmts) == 1
        assert 'UPSERT INTO' in stmts[0]
        assert "1, 'ACME'" in stmts[0]

    def test_splits_into_multiple_batches(self):
        cmd = Command()
        columns = [{'name': 'id', 'type': 'bigint'}]
        data = [{'id': i} for i in range(5)]
        stmts = cmd.generate_insert_statements('cis_trade', columns, data, batch_size=2)
        assert len(stmts) == 3  # batches of 2, 2, 1


class TestExtractTables:
    def test_extracts_ddl_columns_and_row_count(self):
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', return_value='CREATE TABLE x (id BIGINT)'), \
             patch.object(cmd, 'get_table_columns', return_value=[{'name': 'id', 'type': 'bigint'}]), \
             patch.object(cmd, 'get_table_row_count', return_value=10):
            result = cmd.extract_tables(['cis_trade'])
        assert result['tables']['cis_trade']['status'] == 'success'
        assert result['tables']['cis_trade']['row_count'] == 10
        assert result['summary']['successful'] == 1
        assert result['summary']['total_rows'] == 10

    def test_marks_failed_when_ddl_is_none(self):
        """When DDL comes back None, the table is counted as failed but
        never added to result['tables'] (the code `continue`s before that
        assignment) -- only the summary counter reflects it."""
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', return_value=None):
            result = cmd.extract_tables(['bad_table'])
        assert 'bad_table' not in result['tables']
        assert result['summary']['failed'] == 1
        assert result['summary']['successful'] == 0

    def test_catches_exception_per_table(self):
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', side_effect=RuntimeError('boom')):
            result = cmd.extract_tables(['cis_trade'])
        assert result['tables']['cis_trade']['status'] == 'failed'
        assert 'boom' in result['tables']['cis_trade']['error']
        assert result['summary']['failed'] == 1

    def test_includes_data_when_requested_and_rows_exist(self):
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', return_value='CREATE TABLE x (id BIGINT)'), \
             patch.object(cmd, 'get_table_columns', return_value=[{'name': 'id', 'type': 'bigint'}]), \
             patch.object(cmd, 'get_table_row_count', return_value=1), \
             patch.object(cmd, 'get_table_data', return_value=[{'id': 1}]):
            result = cmd.extract_tables(['cis_trade'], include_data=True)
        assert len(result['tables']['cis_trade']['insert_statements']) == 1

    def test_skips_data_when_row_count_zero(self):
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', return_value='CREATE TABLE x (id BIGINT)'), \
             patch.object(cmd, 'get_table_columns', return_value=[]), \
             patch.object(cmd, 'get_table_row_count', return_value=0), \
             patch.object(cmd, 'get_table_data') as mock_data:
            cmd.extract_tables(['cis_trade'], include_data=True)
        mock_data.assert_not_called()

    def test_total_tables_reflects_input_count(self):
        cmd = Command()
        with patch.object(cmd, 'get_table_ddl', return_value='DDL'), \
             patch.object(cmd, 'get_table_columns', return_value=[]), \
             patch.object(cmd, 'get_table_row_count', return_value=0):
            result = cmd.extract_tables(['a', 'b', 'c'])
        assert result['summary']['total_tables'] == 3


class TestWriteOutputFiles:
    def _result(self, ddl=True, has_data=False, row_count=5):
        result = {
            'timestamp': '2026-09-17T00:00:00',
            'database': 'gmp_cis',
            'tables': {
                'cis_trade': {
                    'ddl': 'CREATE TABLE cis_trade (id BIGINT)' if ddl else None,
                    'columns': [],
                    'row_count': row_count,
                    'insert_statements': ["UPSERT INTO x VALUES (1);"] if has_data else [],
                    'status': 'success' if ddl else 'failed',
                }
            },
            'summary': {'total_tables': 1, 'successful': 1 if ddl else 0, 'failed': 0 if ddl else 1, 'total_rows': row_count},
        }
        return result

    def test_writes_combined_ddl_file(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(), tmp_path)
        files = list(tmp_path.glob('01_all_tables_ddl_*.sql'))
        assert len(files) == 1
        content = files[0].read_text()
        assert 'CREATE TABLE cis_trade' in content
        assert 'DROP TABLE IF EXISTS gmp_cis.cis_trade' in content

    def test_writes_individual_table_file(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(), tmp_path)
        table_file = tmp_path / 'tables' / 'cis_trade.sql'
        assert table_file.exists()
        assert 'CREATE TABLE cis_trade' in table_file.read_text()

    def test_skips_table_without_ddl(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(ddl=False), tmp_path)
        table_file = tmp_path / 'tables' / 'cis_trade.sql'
        assert not table_file.exists()

    def test_writes_data_file_when_insert_statements_present(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(has_data=True), tmp_path)
        data_file = tmp_path / 'data' / 'cis_trade_data.sql'
        assert data_file.exists()
        assert 'UPSERT INTO x' in data_file.read_text()

    def test_no_data_dir_when_no_insert_statements(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(has_data=False), tmp_path)
        assert not (tmp_path / 'data').exists()

    def test_writes_combined_data_file_when_has_data(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(has_data=True), tmp_path)
        files = list(tmp_path.glob('02_all_tables_data_*.sql'))
        assert len(files) == 1

    def test_writes_summary_file(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(), tmp_path)
        files = list(tmp_path.glob('00_migration_summary_*.txt'))
        assert len(files) == 1
        content = files[0].read_text()
        assert 'cis_trade' in content
        assert 'Total Tables: 1' in content

    def test_writes_executable_deploy_script(self, tmp_path):
        cmd = Command()
        cmd.write_output_files(self._result(), tmp_path)
        deploy_script = tmp_path / 'deploy_to_uat.sh'
        assert deploy_script.exists()
        assert deploy_script.stat().st_mode & 0o111  # executable bits set

    def test_ddl_without_trailing_semicolon_gets_one_added(self, tmp_path):
        cmd = Command()
        result = self._result()
        result['tables']['cis_trade']['ddl'] = 'CREATE TABLE cis_trade (id BIGINT)'  # no semicolon
        cmd.write_output_files(result, tmp_path)
        table_file = tmp_path / 'tables' / 'cis_trade.sql'
        assert table_file.read_text().rstrip().endswith(';')

    def test_creates_output_dir_if_missing(self, tmp_path):
        cmd = Command()
        nested = tmp_path / 'a' / 'b' / 'c'
        cmd.write_output_files(self._result(), nested)
        assert nested.exists()


class TestHandle:
    def test_no_tables_raises_command_error(self):
        cmd = Command()
        with patch.object(cmd, 'get_all_tables', return_value=[]):
            with pytest.raises(CommandError, match='No tables found'):
                cmd.handle(tables=None, include_data=False, data_limit=None, output_dir='/tmp/x')

    def test_uses_explicit_tables_list(self, tmp_path):
        cmd = Command()
        with patch.object(cmd, 'extract_tables') as mock_extract, \
             patch.object(cmd, 'write_output_files'):
            mock_extract.return_value = {
                'summary': {'total_tables': 2, 'successful': 2, 'failed': 0, 'total_rows': 0},
                'tables': {},
            }
            cmd.handle(tables='cis_trade, cis_portfolio', include_data=False,
                       data_limit=None, output_dir=str(tmp_path))
        called_tables = mock_extract.call_args[0][0]
        assert called_tables == ['cis_trade', 'cis_portfolio']

    def test_uses_get_all_tables_when_none_given(self, tmp_path):
        cmd = Command()
        with patch.object(cmd, 'get_all_tables', return_value=['cis_trade']), \
             patch.object(cmd, 'extract_tables') as mock_extract, \
             patch.object(cmd, 'write_output_files'):
            mock_extract.return_value = {
                'summary': {'total_tables': 1, 'successful': 1, 'failed': 0, 'total_rows': 0},
                'tables': {},
            }
            cmd.handle(tables=None, include_data=False, data_limit=None, output_dir=str(tmp_path))
        mock_extract.assert_called_once()

    def test_prints_summary(self, tmp_path, capsys):
        cmd = Command()
        with patch.object(cmd, 'extract_tables') as mock_extract, \
             patch.object(cmd, 'write_output_files'):
            mock_extract.return_value = {
                'summary': {'total_tables': 3, 'successful': 2, 'failed': 1, 'total_rows': 99},
                'tables': {},
            }
            cmd.handle(tables='a,b,c', include_data=False, data_limit=None, output_dir=str(tmp_path))
        out = capsys.readouterr().out
        assert 'Total Tables: 3' in out
        assert 'Successful: 2' in out
        assert 'Total Rows: 99' in out
