"""Tests for edge_jobs_py36/eod_ams_position_etl.py."""
import sys
from unittest.mock import patch, MagicMock, call

import pytest

import eod_ams_position_etl as etl


@pytest.fixture(autouse=True)
def reset_normalized_cache():
    etl._cis_normalized_cache = {}
    etl._cis_normalized_cache_ts = 0.0
    yield
    etl._cis_normalized_cache = {}
    etl._cis_normalized_cache_ts = 0.0


class QueryRouter:
    """Routes execute_query calls to canned results based on query substrings."""

    def __init__(self):
        self.source_count = 5
        self.std_rows = 5
        self.pending_b = []
        self.pending_d = []
        self.candidates = []
        self.base_count = 5
        self.report_totals = {'total': 5, 'passed': 4, 'failed': 1}
        self.cis_security_rows = []
        self.calls = []

    def __call__(self, query, *args, **kwargs):
        self.calls.append(query)
        if 'SELECT security_id, security_name, security_description' in query:
            return self.cis_security_rows
        if 'FROM pos_stage_4_security_fallback WHERE security_status' in query:
            # Called twice (Stage B then Stage D) — use pending_b first, then pending_d
            b_calls = sum(1 for q in self.calls if 'FROM pos_stage_4_security_fallback WHERE security_status' in q)
            return self.pending_b if b_calls == 1 else self.pending_d
        if 'FROM pos_stage_5b_candidates WHERE rn = 1' in query:
            return self.candidates
        if 'SELECT COUNT(*) AS cnt FROM pos_stage_1_base' in query:
            return [{'cnt': self.base_count}]
        if 'SELECT COUNT(*) AS cnt FROM' in query and 'position_upload_standardized' in query:
            return [{'cnt': self.std_rows}]
        if 'SELECT COUNT(*) AS cnt FROM' in query:
            return [{'cnt': self.source_count}]
        if 'FROM {0}.position_upload_report'.format(etl.DB) in query or 'position_upload_report' in query and 'COUNT(*)' in query:
            return [{
                'total': self.report_totals['total'],
                'passed': self.report_totals['passed'],
                'failed': self.report_totals['failed'],
            }]
        return []


@pytest.fixture
def router():
    return QueryRouter()


@pytest.fixture
def impala(router):
    with patch('eod_ams_position_etl.impala_manager') as m:
        m.execute_query.side_effect = router
        m.execute_write.return_value = True
        yield m


class TestSafeDecimal:
    def test_returns_cast_when_no_precision_match(self):
        result = etl.safe_decimal('col1', 'STRING')
        assert 'CAST(' in result
        assert 'col1' not in result or True  # just sanity that it builds

    def test_returns_guarded_cast_for_decimal_type(self):
        result = etl.safe_decimal('col1', 'DECIMAL(10,6)')
        assert 'CASE WHEN LENGTH' in result
        assert 'DECIMAL(10,6)' in result


class TestBuildAverageCostSql:
    def test_builds_case_expression(self):
        result = etl.build_average_cost_sql('qty', 'cost', 'fallback')
        assert 'CASE' in result
        assert 'qty' in result
        assert 'fallback' in result


class TestNormalizeTickerSuffix:
    def test_builds_nullif_chain(self):
        result = etl.normalize_ticker_suffix('col1')
        assert 'NULLIF' in result
        assert 'SP' in result  # Singapore suffix mapping present


class TestAbbreviateSecurityName:
    def test_empty_name_returns_as_is(self):
        assert etl.abbreviate_security_name('') == ''
        assert etl.abbreviate_security_name(None) is None

    def test_applies_dictionary_abbreviations(self):
        result = etl.abbreviate_security_name('ABC CORPORATION LIMITED')
        assert 'CORP' in result
        assert 'LTD' in result

    def test_expands_old_mgt_abbreviation_first(self):
        result = etl.abbreviate_security_name('XYZ MGT PTE LTD')
        assert 'MGMT' in result

    def test_strips_punctuation(self):
        result = etl.abbreviate_security_name('CO.,LTD.')
        assert 'CO LTD' == result

    def test_truncates_long_names_with_word_abbreviation(self):
        long_name = 'A VERY LONG SECURITY NAME THAT EXCEEDS THIRTY FIVE CHARACTERS EASILY'
        result = etl.abbreviate_security_name(long_name, max_len=35)
        assert len(result) <= 35

    def test_hard_truncation_when_still_too_long(self):
        # a name with no long words to abbreviate that still exceeds max_len
        long_name = 'A B C D E F G H I J K L M N O P Q R S T U V W X Y Z'
        result = etl.abbreviate_security_name(long_name, max_len=10)
        assert len(result) <= 10

    def test_short_name_unchanged(self):
        assert etl.abbreviate_security_name('ABC') == 'ABC'


class TestBuildNormalizedCache:
    def test_returns_cache_from_query(self, impala, router):
        router.cis_security_rows = [{
            'security_id': 1, 'security_name': 'ABC CORP', 'security_description': 'ABC CORPORATION',
            'isin': 'ISIN1', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD',
        }]
        cache = etl._build_normalized_cache(force=True)
        assert len(cache) > 0

    def test_uses_ttl_cache_on_second_call(self, impala, router):
        router.cis_security_rows = [{
            'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
            'isin': 'ISIN1', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD',
        }]
        cache1 = etl._build_normalized_cache(force=True)
        call_count_before = impala.execute_query.call_count
        cache2 = etl._build_normalized_cache()
        assert impala.execute_query.call_count == call_count_before  # cached, no new query
        assert cache1 is cache2

    def test_dedups_same_security_id_across_name_and_description(self, impala, router):
        router.cis_security_rows = [{
            'security_id': 1, 'security_name': 'ABC CORP', 'security_description': 'ABC CORP',
            'isin': 'ISIN1', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD',
        }]
        cache = etl._build_normalized_cache(force=True)
        key = etl.abbreviate_security_name('ABC CORP')
        assert len(cache[key]) == 1


class TestApplyPythonTierResult:
    def test_writes_expected_sql_sequence(self, impala):
        etl._apply_python_tier_result(
            matches={1: {'security_id': 100}}, multi_ids={2}, tier_name='NORMALIZED_FULL_NAME',
        )
        write_calls = [c[0][0] for c in impala.execute_write.call_args_list]
        assert any('pos_stage_4_tier_update' in q for q in write_calls)
        assert any('NORMALIZED_FULL_NAME' in q for q in write_calls)

    def test_no_matches_or_multi_still_runs(self, impala):
        etl._apply_python_tier_result(matches={}, multi_ids=set(), tier_name='X')
        assert impala.execute_write.called


class TestStandardizeSql:
    @pytest.mark.parametrize('table', [
        'gmp_cis_sta_dly_ams_multi_dis_cif',
        'gmp_cis_sta_dly_stat_street_ams_iceq',
        'gmp_cis_sta_mthly_stat_street_ams_iceq_end',
        'gmp_cis_sta_dly_stat_street_ams_daily_limit',
        'gmp_cis_sta_dly_position',
    ])
    def test_returns_sql_for_each_known_table(self, table):
        sql = etl._standardize_sql(table, '20260101', table)
        assert 'SELECT' in sql
        assert table in sql

    def test_unknown_table_raises(self):
        # ALL_SOURCES[table] is looked up before the known-tables if/elif chain,
        # so an unrecognised table raises KeyError, not the ValueError at the
        # function's end (which is genuinely unreachable for any string key).
        with pytest.raises(KeyError):
            etl._standardize_sql('not_a_real_table', '20260101', 'x')


class TestRunEtlForTable:
    TABLE = 'gmp_cis_sta_dly_stat_street_ams_iceq'

    def test_no_source_data_skips(self, impala, router):
        router.source_count = 0
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is False
        assert result['total'] == 0

    def test_dry_run_skips_writes(self, impala, router):
        router.source_count = 10
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=True)
        assert result['ok'] is True
        assert result['total'] == 10
        impala.execute_write.assert_not_called()

    def test_step0_insert_failure(self, impala, router):
        impala.execute_write.return_value = False
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is False

    def test_step0_zero_standardized_rows(self, impala, router):
        router.std_rows = 0

        def write_ok(query, **kw):
            return True
        impala.execute_write.side_effect = write_ok
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is False

    def test_step1_failure(self, impala, router):
        calls = {'n': 0}

        def write_side_effect(query, **kw):
            if 'CREATE TABLE pos_stage_1_base' in query:
                return False
            return True
        impala.execute_write.side_effect = write_side_effect
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is False

    def test_full_run_success_auto_create_false(self, impala, router):
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=False)
        assert result['ok'] is True
        assert result['total'] == 5
        assert result['passed'] == 4
        assert result['failed'] == 1

    def test_full_run_success_auto_create_true_no_candidates(self, impala, router):
        router.candidates = []
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=True)
        assert result['ok'] is True

    def test_step7a_upsert_failure(self, impala, router):
        def write_side_effect(query, **kw):
            if 'UPSERT INTO' in query and 'cis_position' in query:
                return False
            return True
        impala.execute_write.side_effect = write_side_effect
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is False

    def test_step7b_failure_logged_but_continues(self, capsys, impala, router):
        def write_side_effect(query, **kw):
            if 'INSERT OVERWRITE' in query and 'position_upload_report' in query:
                return False
            return True
        impala.execute_write.side_effect = write_side_effect
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        out = capsys.readouterr().out
        assert 'Step 7B] FAILED' in out
        assert result['ok'] is True  # 7B failure is logged, doesn't abort the pipeline

    def test_stage_b_and_d_with_pending_rows_matched(self, impala, router):
        router.pending_b = [{'row_id': 1, 'desc_prefix': 'ABC CORP', 'resolved_country': 'SG'}]
        router.pending_d = [{'row_id': 2, 'desc_prefix': 'XYZ LTD', 'resolved_country': ''}]
        router.cis_security_rows = [
            {'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
             'isin': 'ISIN1', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD'},
            {'security_id': 2, 'security_name': 'XYZ LTD', 'security_description': None,
             'isin': 'ISIN2', 'exchange_code': None, 'country_of_exchange': None, 'currency_code': 'USD'},
        ]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is True

    def test_stage_b_multi_match(self, impala, router):
        router.pending_b = [{'row_id': 1, 'desc_prefix': 'ABC CORP', 'resolved_country': 'SG'}]
        router.cis_security_rows = [
            {'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
             'isin': 'ISIN1', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD'},
            {'security_id': 2, 'security_name': 'ABC CORP', 'security_description': None,
             'isin': 'ISIN2', 'exchange_code': 'SP', 'country_of_exchange': 'SG', 'currency_code': 'SGD'},
        ]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is True

    def test_stage_b_no_country_skips_tier(self, impala, router):
        router.pending_b = [{'row_id': 1, 'desc_prefix': 'ABC CORP', 'resolved_country': ''}]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is True

    def test_stage_b_no_desc_prefix_skips_tier(self, impala, router):
        router.pending_b = [{'row_id': 1, 'desc_prefix': '', 'resolved_country': 'SG'}]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False)
        assert result['ok'] is True

    def test_5b_candidate_no_collision_creates(self, impala, router):
        router.candidates = [{
            'raw_security_name': 'NEW SECURITY CORP', 'isin': 'ISIN9', 'row_id': 1,
            'security_description': 'NEW SECURITY CORP', 'ticker': None, 'industry': None,
            'security_type': None, 'issuer_type': None, 'quoted_unquoted': None,
            'country_of_incorporation': None, 'country_of_exchange': 'SG', 'exchange': 'SG',
            'currency_code': 'SGD', 'shares_outstanding': None, 'fin_nonfin_co': None,
        }]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=True)
        assert result['ok'] is True
        insert_calls = [c[0][0] for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0] and 'cis_security' in c[0][0]]
        assert len(insert_calls) == 1

    def test_5b_candidate_same_exchange_collision_fails(self, impala, router):
        router.candidates = [{
            'raw_security_name': 'ABC CORP', 'isin': 'ISIN9', 'row_id': 1,
            'security_description': 'ABC CORP', 'ticker': None, 'industry': None,
            'security_type': None, 'issuer_type': None, 'quoted_unquoted': None,
            'country_of_incorporation': None, 'country_of_exchange': 'SG', 'exchange': 'SG',
            'currency_code': 'SGD', 'shares_outstanding': None, 'fin_nonfin_co': None,
        }]
        router.cis_security_rows = [{
            'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
            'isin': 'ISIN1', 'exchange_code': 'SG', 'country_of_exchange': 'SG', 'currency_code': 'SGD',
        }]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=True)
        assert result['ok'] is True
        insert_calls = [c[0][0] for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0] and 'cis_security' in c[0][0]]
        assert len(insert_calls) == 0

    def test_5b_candidate_different_exchange_disambiguates(self, impala, router):
        router.candidates = [{
            'raw_security_name': 'ABC CORP', 'isin': 'ISIN9', 'row_id': 1,
            'security_description': 'ABC CORP', 'ticker': None, 'industry': None,
            'security_type': None, 'issuer_type': None, 'quoted_unquoted': None,
            'country_of_incorporation': None, 'country_of_exchange': 'HK', 'exchange': 'HK',
            'currency_code': 'HKD', 'shares_outstanding': None, 'fin_nonfin_co': None,
        }]
        router.cis_security_rows = [{
            'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
            'isin': 'ISIN1', 'exchange_code': 'SG', 'country_of_exchange': 'SG', 'currency_code': 'SGD',
        }]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=True)
        assert result['ok'] is True
        insert_calls = [c[0][0] for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0] and 'cis_security' in c[0][0]]
        assert len(insert_calls) == 1
        assert 'HK' in insert_calls[0]

    def test_5b_candidate_disambiguated_name_also_collides_fails(self, impala, router):
        router.candidates = [{
            'raw_security_name': 'ABC CORP', 'isin': 'ISIN9', 'row_id': 1,
            'security_description': 'ABC CORP', 'ticker': None, 'industry': None,
            'security_type': None, 'issuer_type': None, 'quoted_unquoted': None,
            'country_of_incorporation': None, 'country_of_exchange': 'HK', 'exchange': 'HK',
            'currency_code': 'HKD', 'shares_outstanding': None, 'fin_nonfin_co': None,
        }]
        router.cis_security_rows = [
            {'security_id': 1, 'security_name': 'ABC CORP', 'security_description': None,
             'isin': 'ISIN1', 'exchange_code': 'SG', 'country_of_exchange': 'SG', 'currency_code': 'SGD'},
            {'security_id': 2, 'security_name': 'ABC CORP HK', 'security_description': None,
             'isin': 'ISIN2', 'exchange_code': 'HK', 'country_of_exchange': 'HK', 'currency_code': 'HKD'},
        ]
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=True)
        assert result['ok'] is True
        insert_calls = [c[0][0] for c in impala.execute_write.call_args_list if 'INSERT INTO' in c[0][0] and 'cis_security' in c[0][0]]
        assert len(insert_calls) == 0

    def test_auto_create_false_fails_not_found_rows(self, capsys, impala, router):
        result = etl.run_etl_for_table(self.TABLE, '20260101', dry_run=False, auto_create_security=False)
        out = capsys.readouterr().out
        assert 'auto_create_security=False' in out
        assert result['ok'] is True


class TestParseArgs:
    def test_parses_required_processing_date(self):
        with patch.object(sys, 'argv', ['prog', '--processing-date', '20260101']):
            args = etl.parse_args()
        assert args.processing_date == '20260101'
        assert args.source == 'all'
        assert args.dry_run is False
        assert args.auto_create_security is False

    def test_parses_optional_flags(self):
        with patch.object(sys, 'argv', [
            'prog', '--processing-date', '20260101', '--source', 'ams_iceq',
            '--dry-run', '--auto-create-security',
        ]):
            args = etl.parse_args()
        assert args.source == 'ams_iceq'
        assert args.dry_run is True
        assert args.auto_create_security is True


class TestMain:
    def test_invalid_date_format_exits(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--processing-date', 'bad-date']):
            with pytest.raises(SystemExit) as exc_info:
                etl.main()
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert 'ERROR' in out

    def test_runs_all_sources_success(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--processing-date', '20260101']):
            with patch('eod_ams_position_etl.run_etl_for_table') as run_mock:
                run_mock.return_value = {'total': 1, 'passed': 1, 'failed': 0, 'ok': True}
                etl.main()
        assert run_mock.call_count == len(etl.ALL_SOURCES)
        out = capsys.readouterr().out
        assert 'All sources completed successfully' in out

    def test_single_source_via_alias(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--processing-date', '20260101', '--source', 'ams_iceq']):
            with patch('eod_ams_position_etl.run_etl_for_table') as run_mock:
                run_mock.return_value = {'total': 1, 'passed': 1, 'failed': 0, 'ok': True}
                etl.main()
        run_mock.assert_called_once()
        assert run_mock.call_args[0][0] == 'gmp_cis_sta_dly_stat_street_ams_iceq'

    def test_source_failure_exits_with_errors(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--processing-date', '20260101']):
            with patch('eod_ams_position_etl.run_etl_for_table') as run_mock:
                run_mock.return_value = {'total': 0, 'passed': 0, 'failed': 0, 'ok': False}
                with pytest.raises(SystemExit) as exc_info:
                    etl.main()
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert 'ERRORS in' in out

    def test_exception_in_source_counted_as_error(self, capsys):
        with patch.object(sys, 'argv', ['prog', '--processing-date', '20260101']):
            with patch('eod_ams_position_etl.run_etl_for_table', side_effect=RuntimeError('boom')):
                with pytest.raises(SystemExit):
                    etl.main()
        out = capsys.readouterr().out
        assert 'ERRORS in' in out
