"""Tests for edge_jobs_py36/lib/system_date_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.system_date_repository import (
    SystemDateRepository,
    system_date_repository,
    DATABASE,
    ALLDATES_TABLE,
)


class TestGetCurrentSystemDate:
    def test_returns_row_with_flags_when_found(self):
        row = {
            'system_date': '20260917',
            'report_date': '20260916',
            'processing_date': '20260917',
            'settlement_t1': '20260918',
            'settlement_t2': '20260919',
            'reporting_date': '20260917',
            'loaded_at': '20260917',
        }
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [row]
            result = SystemDateRepository.get_current_system_date()

        assert result['system_date'] == '20260917'
        assert result['is_business_day'] is True
        assert result['source_file'] == ALLDATES_TABLE

    def test_calls_execute_query_with_database(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'system_date': '20260917'}]
            SystemDateRepository.get_current_system_date()

        _, kwargs = mock_mgr.execute_query.call_args
        assert kwargs.get('database') == DATABASE

    def test_query_includes_alldates_table_and_filter(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'system_date': '20260917'}]
            SystemDateRepository.get_current_system_date()

        query = mock_mgr.execute_query.call_args[0][0]
        assert ALLDATES_TABLE in query
        assert "src_system = 'gmp'" in query
        assert "sub_system = 'cis'" in query
        assert "data_frq = 'dly'" in query
        assert "record_type = 'D'" in query
        assert 'MAX(processing_date)' in query

    def test_returns_none_when_no_rows(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = []
            result = SystemDateRepository.get_current_system_date()
        assert result is None

    def test_returns_none_when_results_is_none(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = None
            result = SystemDateRepository.get_current_system_date()
        assert result is None

    def test_returns_none_and_logs_on_exception(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.side_effect = RuntimeError('connection lost')
            result = SystemDateRepository.get_current_system_date()
        assert result is None

    def test_uses_first_row_when_multiple_returned(self):
        rows = [
            {'system_date': 'FIRST'},
            {'system_date': 'SECOND'},
        ]
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = rows
            result = SystemDateRepository.get_current_system_date()
        assert result['system_date'] == 'FIRST'


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(system_date_repository, SystemDateRepository)

    def test_singleton_method_works(self):
        with patch('edge_jobs_py36.lib.system_date_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_query.return_value = [{'system_date': '20260917'}]
            result = system_date_repository.get_current_system_date()
        assert result['system_date'] == '20260917'
