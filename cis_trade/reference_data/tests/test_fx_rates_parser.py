"""
Tests for FX Rates Parser
"""

import pytest
from decimal import Decimal
from pathlib import Path
from reference_data.services.fx_rates_parser import (
    FXRatesParser,
    FXRateHeader,
    FXRateDetail,
    parse_fx_rates_file
)


class TestFXRateHeader:
    """Tests for FXRateHeader dataclass"""

    def test_header_creation(self):
        """Test creating a header object"""
        header = FXRateHeader(
            record_type='H',
            source_system='GMP',
            start_date='19800101',
            system_timestamp='20251224111237'
        )
        assert header.record_type == 'H'
        assert header.source_system == 'GMP'
        assert header.start_date == '19800101'
        assert header.system_timestamp == '20251224111237'

    def test_header_str(self):
        """Test header string representation"""
        header = FXRateHeader('H', 'GMP', '19800101', '20251224111237')
        assert 'GMP' in str(header)
        assert '20251224111237' in str(header)

    def test_parsed_timestamp(self):
        """Test parsing timestamp"""
        header = FXRateHeader('H', 'GMP', '19800101', '20251224111237')
        parsed = header.parsed_timestamp
        assert parsed is not None
        assert parsed.year == 2025
        assert parsed.month == 12
        assert parsed.day == 24
        assert parsed.hour == 11
        assert parsed.minute == 12
        assert parsed.second == 37

    def test_invalid_timestamp(self):
        """Test invalid timestamp"""
        header = FXRateHeader('H', 'GMP', '19800101', 'INVALID')
        assert header.parsed_timestamp is None


class TestFXRateDetail:
    """Tests for FXRateDetail dataclass"""

    def test_detail_creation(self):
        """Test creating a detail object"""
        detail = FXRateDetail(
            record_type='D',
            ref_quot='1',
            spot_ff0='USD-AED',
            base='AED',
            trade_date='20251124',
            spot_rf_a=Decimal('3.6732'),
            underlng='USD',
            spot_rf_b=Decimal('3.6725'),
            alias='BOSET'
        )
        assert detail.record_type == 'D'
        assert detail.spot_ff0 == 'USD-AED'
        assert detail.base == 'AED'

    def test_mid_rate_calculation(self):
        """Test mid rate calculation"""
        detail = FXRateDetail(
            'D', '1', 'USD-AED', 'AED', '20251124',
            Decimal('3.6732'), 'USD', Decimal('3.6725'), 'BOSET'
        )
        expected_mid = (Decimal('3.6732') + Decimal('3.6725')) / Decimal('2')
        assert detail.mid_rate == expected_mid
        assert detail.mid_rate == Decimal('3.67285')

    def test_parsed_date(self):
        """Test parsing trade date"""
        detail = FXRateDetail(
            'D', '1', 'USD-AED', 'AED', '20251124',
            Decimal('3.6732'), 'USD', Decimal('3.6725'), 'BOSET'
        )
        parsed = detail.parsed_date
        assert parsed is not None
        assert parsed.year == 2025
        assert parsed.month == 11
        assert parsed.day == 24

    def test_invalid_date(self):
        """Test invalid date"""
        detail = FXRateDetail(
            'D', '1', 'USD-AED', 'AED', 'INVALID',
            Decimal('3.6732'), 'USD', Decimal('3.6725'), 'BOSET'
        )
        assert detail.parsed_date is None

    def test_to_dict(self):
        """Test converting detail to dictionary"""
        detail = FXRateDetail(
            'D', '1', 'USD-AED', 'AED', '20251124',
            Decimal('3.6732'), 'USD', Decimal('3.6725'), 'BOSET'
        )
        result = detail.to_dict()
        assert isinstance(result, dict)
        assert result['record_type'] == 'D'
        assert result['spot_ff0'] == 'USD-AED'
        assert result['base'] == 'AED'
        assert isinstance(result['spot_rf_a'], float)
        assert isinstance(result['mid_rate'], float)


class TestFXRatesParser:
    """Tests for FXRatesParser class"""

    @pytest.fixture
    def parser(self):
        """Create a parser instance"""
        return FXRatesParser()

    @pytest.fixture
    def sample_header_line(self):
        """Sample header line"""
        return "H|GMP|19800101|20251224111237"

    @pytest.fixture
    def sample_detail_line(self):
        """Sample detail line"""
        return "D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET"

    @pytest.fixture
    def sample_file_content(self):
        """Sample file content"""
        return """H|GMP|19800101|20251224111237
D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET
D|1|USD-EUR|EUR|20251124|0.86865|USD|0.86855|BOSET
D|1|USD-GBP|GBP|20251124|0.73075|USD|0.73065|BOSET
"""

    def test_parse_header(self, parser, sample_header_line):
        """Test parsing a header line"""
        header = parser.parse_header(sample_header_line)
        assert header is not None
        assert isinstance(header, FXRateHeader)
        assert header.record_type == 'H'
        assert header.source_system == 'GMP'
        assert header.start_date == '19800101'
        assert header.system_timestamp == '20251224111237'

    def test_parse_invalid_header(self, parser):
        """Test parsing invalid header"""
        invalid_line = "H|GMP"  # Missing fields
        header = parser.parse_header(invalid_line)
        assert header is None
        assert len(parser.errors) > 0

    def test_parse_detail(self, parser, sample_detail_line):
        """Test parsing a detail line"""
        detail = parser.parse_detail(sample_detail_line)
        assert detail is not None
        assert isinstance(detail, FXRateDetail)
        assert detail.record_type == 'D'
        assert detail.ref_quot == '1'
        assert detail.spot_ff0 == 'USD-AED'
        assert detail.base == 'AED'
        assert detail.trade_date == '20251124'
        assert detail.spot_rf_a == Decimal('3.6732')
        assert detail.underlng == 'USD'
        assert detail.spot_rf_b == Decimal('3.6725')
        assert detail.alias == 'BOSET'

    def test_parse_invalid_detail(self, parser):
        """Test parsing invalid detail"""
        invalid_line = "D|1|USD-AED"  # Missing fields
        detail = parser.parse_detail(invalid_line)
        assert detail is None
        assert len(parser.errors) > 0

    def test_parse_detail_invalid_decimal(self, parser):
        """Test parsing detail with invalid decimal"""
        invalid_line = "D|1|USD-AED|AED|20251124|INVALID|USD|3.6725|BOSET"
        detail = parser.parse_detail(invalid_line)
        assert detail is None
        assert len(parser.errors) > 0

    def test_parse_line_header(self, parser, sample_header_line):
        """Test parse_line with header"""
        result = parser.parse_line(sample_header_line)
        assert isinstance(result, FXRateHeader)
        assert len(parser.headers) == 1
        assert len(parser.details) == 0

    def test_parse_line_detail(self, parser, sample_detail_line):
        """Test parse_line with detail"""
        result = parser.parse_line(sample_detail_line)
        assert isinstance(result, FXRateDetail)
        assert len(parser.headers) == 0
        assert len(parser.details) == 1

    def test_parse_line_unknown_type(self, parser):
        """Test parse_line with unknown record type"""
        unknown_line = "X|some|data"
        result = parser.parse_line(unknown_line)
        assert result is None
        assert len(parser.errors) > 0

    def test_parse_text(self, parser, sample_file_content):
        """Test parsing text content"""
        result = parser.parse_text(sample_file_content)
        assert result['headers_count'] == 1
        assert result['details_count'] == 3
        assert result['errors_count'] == 0
        assert len(parser.headers) == 1
        assert len(parser.details) == 3

    def test_parse_text_skip_header(self, parser, sample_file_content):
        """Test parsing text with skip_header option"""
        result = parser.parse_text(sample_file_content, skip_header=True)
        # Headers are still parsed but not counted differently
        assert result['headers_count'] == 1
        assert result['details_count'] == 3

    def test_get_details_as_dicts(self, parser, sample_file_content):
        """Test getting details as dictionaries"""
        parser.parse_text(sample_file_content)
        dicts = parser.get_details_as_dicts()
        assert len(dicts) == 3
        assert all(isinstance(d, dict) for d in dicts)
        assert all('mid_rate' in d for d in dicts)

    def test_filter_by_currency_pair(self, parser, sample_file_content):
        """Test filtering by currency pair"""
        parser.parse_text(sample_file_content)
        filtered = parser.filter_by_currency_pair('USD-EUR')
        assert len(filtered) == 1
        assert filtered[0].spot_ff0 == 'USD-EUR'

    def test_filter_by_date(self, parser, sample_file_content):
        """Test filtering by date"""
        parser.parse_text(sample_file_content)
        filtered = parser.filter_by_date('20251124')
        assert len(filtered) == 3

    def test_filter_by_base_currency(self, parser, sample_file_content):
        """Test filtering by base currency"""
        parser.parse_text(sample_file_content)
        filtered = parser.filter_by_base_currency('EUR')
        assert len(filtered) == 1
        assert filtered[0].base == 'EUR'

    def test_get_summary(self, parser, sample_file_content):
        """Test getting summary statistics"""
        parser.parse_text(sample_file_content)
        summary = parser.get_summary()
        assert summary['total_records'] == 3
        assert summary['unique_currencies'] == 3
        assert summary['unique_currency_pairs'] == 3
        assert summary['unique_dates'] == 1
        assert 'AED' in summary['currencies']
        assert 'EUR' in summary['currencies']
        assert 'GBP' in summary['currencies']

    def test_empty_line_handling(self, parser):
        """Test handling of empty lines"""
        content = """H|GMP|19800101|20251224111237

D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET

"""
        result = parser.parse_text(content)
        assert result['headers_count'] == 1
        assert result['details_count'] == 1

    def test_parse_file(self, parser, tmp_path):
        """Test parsing an actual file"""
        # Create a temporary file
        test_file = tmp_path / "test_fx_rates.txt"
        test_file.write_text(
            "H|GMP|19800101|20251224111237\n"
            "D|1|USD-AED|AED|20251124|3.6732|USD|3.6725|BOSET\n"
            "D|1|USD-EUR|EUR|20251124|0.86865|USD|0.86855|BOSET\n"
        )

        result = parser.parse_file(str(test_file))
        assert result['headers_count'] == 1
        assert result['details_count'] == 2
        assert result['errors_count'] == 0

    def test_parse_file_not_found(self, parser):
        """Test parsing non-existent file"""
        with pytest.raises(FileNotFoundError):
            parser.parse_file('/nonexistent/file.txt')


class TestConvenienceFunction:
    """Tests for convenience function"""

    def test_parse_fx_rates_file(self, tmp_path):
        """Test convenience function"""
        test_file = tmp_path / "test_rates.txt"
        test_file.write_text(
            "H|GMP|19800101|20251224111237\n"
            "D|1|USD-SGD|SGD|20251124|1.3085|USD|1.3082|BOSET\n"
        )

        result = parse_fx_rates_file(str(test_file))
        assert result['headers_count'] == 1
        assert result['details_count'] == 1
        assert 'headers' in result
        assert 'details' in result
