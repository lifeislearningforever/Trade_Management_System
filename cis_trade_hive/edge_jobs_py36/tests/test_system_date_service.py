"""Tests for edge_jobs_py36/lib/system_date_service.py."""
from datetime import date, datetime
from unittest.mock import patch

import pytest

from edge_jobs_py36.lib.system_date_service import (
    SystemDateService,
    SystemDateInfo,
    CACHE_KEY_SYSTEM_DATE,
    system_date_service,
)


GMP_ROW = {
    'system_date': '20260917',
    'report_date': '20260916',
    'processing_date': '20260917',
    'settlement_t1': '20260918',
    'settlement_t2': '20260919',
    'is_business_day': True,
    'source_file': 'gmp_cis_sta_dly_alldatesinfo',
    'loaded_at': '2026-09-17 06:00:00',
}


@pytest.fixture(autouse=True)
def _no_real_cache():
    """Every test gets a fresh, empty cache so results don't leak between
    tests via the shared module-level singleton cache."""
    with patch('edge_jobs_py36.lib.system_date_service.cache') as mock_cache:
        mock_cache.get.return_value = None
        yield mock_cache


class TestParseDate:
    def test_parses_valid_yyyymmdd_string(self):
        svc = SystemDateService()
        assert svc._parse_date('20260917') == date(2026, 9, 17)

    def test_raises_on_empty_string(self):
        svc = SystemDateService()
        with pytest.raises(ValueError, match='Invalid date string'):
            svc._parse_date('')

    def test_raises_on_none(self):
        svc = SystemDateService()
        with pytest.raises(ValueError, match='Invalid date string'):
            svc._parse_date(None)

    def test_raises_on_wrong_length(self):
        svc = SystemDateService()
        with pytest.raises(ValueError, match='Invalid date string'):
            svc._parse_date('2026-09-17')


class TestGetSystemDateInfoFromGmp:
    def test_returns_populated_info_from_repository_row(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            info = svc.get_system_date_info()

        assert info.source == 'GMP_FILE'
        assert info.system_date == date(2026, 9, 17)
        assert info.report_date == date(2026, 9, 16)
        assert info.processing_date == date(2026, 9, 17)
        assert info.settlement_t1 == '20260918'
        assert info.settlement_t2 == '20260919'
        assert info.settlement_t2_display == '2026-09-19'
        assert info.is_business_day is True
        assert info.source_file == 'gmp_cis_sta_dly_alldatesinfo'
        assert info.loaded_at == datetime(2026, 9, 17, 6, 0, 0)

    def test_caches_result_on_success(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            svc.get_system_date_info()

        _no_real_cache.set.assert_called_once()
        args = _no_real_cache.set.call_args[0]
        assert args[0] == CACHE_KEY_SYSTEM_DATE
        assert isinstance(args[1], SystemDateInfo)

    def test_returns_cached_value_without_hitting_repository(self, _no_real_cache):
        cached_info = object()
        _no_real_cache.get.return_value = cached_info
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            svc = SystemDateService()
            result = svc.get_system_date_info()
        assert result is cached_info
        mock_repo.get_current_system_date.assert_not_called()

    def test_report_date_none_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['report_date'] = None
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.report_date is None
        assert info.report_date_display is None

    def test_processing_date_none_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['processing_date'] = None
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.processing_date is None

    def test_settlement_t1_none_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['settlement_t1'] = None
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.settlement_t1 is None

    def test_settlement_t2_display_none_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['settlement_t2'] = None
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.settlement_t2 is None
        assert info.settlement_t2_display is None

    def test_settlement_t2_display_none_when_unparseable(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['settlement_t2'] = 'not-a-date'
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.settlement_t2 == 'not-a-date'
        assert info.settlement_t2_display is None

    def test_loaded_at_parsed_from_string_timestamp(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['loaded_at'] = '2026-09-17 06:00:00'
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.loaded_at == datetime(2026, 9, 17, 6, 0, 0)

    def test_loaded_at_none_when_string_unparseable(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['loaded_at'] = 'garbage-timestamp'
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.loaded_at is None

    def test_loaded_at_parsed_from_epoch_millis(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['loaded_at'] = 1600000000000  # non-string, epoch millis
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.loaded_at == datetime.fromtimestamp(1600000000000 / 1000)

    def test_loaded_at_none_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['loaded_at'] = None
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.loaded_at is None

    def test_is_business_day_defaults_true_when_absent(self, _no_real_cache):
        row = dict(GMP_ROW)
        del row['is_business_day']
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.is_business_day is True


class TestGetSystemDateInfoFallback:
    def test_falls_back_to_today_when_repository_returns_none(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.source == 'FALLBACK'
        assert info.system_date == date.today()

    def test_fallback_report_date_is_yesterday(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            info = svc.get_system_date_info()
        from datetime import timedelta
        assert info.report_date == date.today() - timedelta(days=1)

    def test_fallback_settlement_t2_is_today_plus_two(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            info = svc.get_system_date_info()
        from datetime import timedelta
        expected = (date.today() + timedelta(days=2)).strftime('%Y%m%d')
        assert info.settlement_t2 == expected

    def test_fallback_settlement_t1_is_none(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.settlement_t1 is None

    def test_fallback_source_file_is_none(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.source_file is None

    def test_falls_back_when_repository_row_has_invalid_date(self, _no_real_cache):
        row = dict(GMP_ROW)
        row['system_date'] = 'bad-date'
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = row
            svc = SystemDateService()
            info = svc.get_system_date_info()
        assert info.source == 'FALLBACK'

    def test_fallback_does_not_write_to_cache(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = None
            svc = SystemDateService()
            svc.get_system_date_info()
        _no_real_cache.set.assert_not_called()


class TestConvenienceGetters:
    def test_get_system_date_returns_date_object(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.get_system_date() == date(2026, 9, 17)

    def test_get_system_date_str_default_format(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.get_system_date_str() == '20260917'

    def test_get_system_date_str_custom_format(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.get_system_date_str(format='%d/%m/%Y') == '17/09/2026'

    def test_get_report_date(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.get_report_date() == date(2026, 9, 16)

    def test_get_processing_date(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.get_processing_date() == date(2026, 9, 17)


class TestIsBusinessDay:
    def test_uses_system_date_info_when_no_date_given(self, _no_real_cache):
        with patch('edge_jobs_py36.lib.system_date_service.system_date_repository') as mock_repo:
            mock_repo.get_current_system_date.return_value = dict(GMP_ROW)
            svc = SystemDateService()
            assert svc.is_business_day() is True

    def test_weekday_date_is_business_day(self):
        svc = SystemDateService()
        monday = date(2026, 9, 21)  # confirmed weekday, see below
        # 2026-09-21 is a Monday
        assert svc.is_business_day(monday) is True

    def test_weekend_date_is_not_business_day(self):
        svc = SystemDateService()
        saturday = date(2026, 9, 19)  # 2026-09-19 is a Saturday
        assert svc.is_business_day(saturday) is False


class TestClearCache:
    def test_clear_cache_deletes_key(self, _no_real_cache):
        svc = SystemDateService()
        svc.clear_cache()
        _no_real_cache.delete.assert_called_once_with(CACHE_KEY_SYSTEM_DATE)


class TestSingleton:
    def test_module_exposes_singleton_instance(self):
        assert isinstance(system_date_service, SystemDateService)
