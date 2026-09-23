"""Tests for edge_jobs_py36/lib/equity_price_repository.py."""
from unittest.mock import patch

from edge_jobs_py36.lib.equity_price_repository import (
    EquityPriceRepository,
    equity_price_repository,
)


def _full_payload(**overrides):
    payload = {
        'currency_code': 'USD',
        'security_label': 'UQ-AAPL US',
        'isin': 'US0378331005',
        'price_date': '2026-09-17',
        'main_closing_price': 150.25,
        'price_timestamp': '2026-09-17 16:00:00',
        'src_system': 'GMP',
        'created_by': 'GMP_ETL',
        'created_at': '2026-09-17 16:05:00',
        'updated_by': 'jdoe',
        'updated_at': '2026-09-17 16:10:00',
    }
    payload.update(overrides)
    return payload


class TestUpsertSuccess:
    def test_returns_true_when_write_succeeds(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert(_full_payload())
        assert result is True

    def test_query_contains_upsert_and_table_name(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(_full_payload())
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'UPSERT INTO' in query
        assert 'cis_equity_price' in query

    def test_query_includes_database_kwarg(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(_full_payload())
        kwargs = mock_mgr.execute_write.call_args[1]
        assert kwargs.get('database') == EquityPriceRepository.DATABASE

    def test_query_embeds_all_provided_values(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(_full_payload())
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'USD' in query
        assert 'UQ-AAPL US' in query
        assert 'US0378331005' in query
        assert '150.25' in query
        assert 'jdoe' in query


class TestUpsertDefaults:
    def test_missing_isin_becomes_null(self):
        payload = _full_payload()
        del payload['isin']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_missing_updated_by_becomes_null(self):
        payload = _full_payload()
        del payload['updated_by']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_missing_updated_at_becomes_null(self):
        payload = _full_payload()
        del payload['updated_at']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'NULL' in query

    def test_missing_src_system_defaults_to_gmp(self):
        payload = _full_payload()
        del payload['src_system']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert "'GMP'" in query

    def test_missing_created_by_defaults_to_gmp_etl(self):
        payload = _full_payload()
        del payload['created_by']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'GMP_ETL' in query

    def test_missing_main_closing_price_defaults_to_zero(self):
        payload = _full_payload()
        del payload['main_closing_price']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert(payload)
        assert result is True
        query = mock_mgr.execute_write.call_args[0][0]
        assert 'main_closing_price' in query

    def test_missing_price_timestamp_uses_now(self):
        payload = _full_payload()
        del payload['price_timestamp']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert(payload)
        assert result is True  # exercised the datetime.now() default path

    def test_missing_created_at_uses_now(self):
        payload = _full_payload()
        del payload['created_at']
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert(payload)
        assert result is True

    def test_none_currency_code_treated_as_empty_string(self):
        payload = _full_payload(currency_code=None)
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert(payload)
        assert result is True


class TestUpsertEscaping:
    def test_single_quote_in_security_label_is_escaped(self):
        payload = _full_payload(security_label="O'BRIEN CO")
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert "O\\'BRIEN CO" in query

    def test_single_quote_in_currency_code_is_escaped(self):
        payload = _full_payload(currency_code="US'D")
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            EquityPriceRepository.upsert(payload)
        query = mock_mgr.execute_write.call_args[0][0]
        assert "US\\'D" in query


class TestUpsertFailure:
    def test_returns_false_when_write_fails(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = False
            result = EquityPriceRepository.upsert(_full_payload())
        assert result is False

    def test_returns_false_and_swallows_exception(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.side_effect = RuntimeError('connection dropped')
            result = EquityPriceRepository.upsert(_full_payload())
        assert result is False

    def test_handles_empty_dict_without_raising(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = EquityPriceRepository.upsert({})
        assert result is True


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(equity_price_repository, EquityPriceRepository)

    def test_singleton_upsert_works(self):
        with patch('edge_jobs_py36.lib.equity_price_repository.impala_manager') as mock_mgr:
            mock_mgr.execute_write.return_value = True
            result = equity_price_repository.upsert(_full_payload())
        assert result is True
