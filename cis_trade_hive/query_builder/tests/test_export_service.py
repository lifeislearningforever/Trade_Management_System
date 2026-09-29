"""
Tests for ExportService — CSV, Excel, JSON, PDF corner cases and negative paths.
"""

import csv
import io
import json
import pytest

from query_builder.services.export_service import ExportService


@pytest.fixture
def svc():
    return ExportService()


ROWS = [
    {'trade_id': '001', 'trade_type': 'BUY',  'quantity': 100},
    {'trade_id': '002', 'trade_type': 'SELL', 'quantity': 50},
    {'trade_id': '003', 'trade_type': 'BUY',  'quantity': None},
]
COLS = ['trade_id', 'trade_type', 'quantity']


# ================================================================
# CSV
# ================================================================

class TestCsvStreaming:
    def _collect(self, gen):
        return ''.join(gen)

    def test_header_row_present(self, svc):
        out = self._collect(svc.to_csv_streaming(ROWS, COLS))
        lines = out.strip().splitlines()
        assert lines[0] == 'trade_id,trade_type,quantity'

    def test_correct_row_count(self, svc):
        out = self._collect(svc.to_csv_streaming(ROWS, COLS))
        lines = [l for l in out.strip().splitlines() if l]
        assert len(lines) == len(ROWS) + 1  # header + data

    def test_empty_rows_yields_only_header(self, svc):
        out = self._collect(svc.to_csv_streaming([], COLS))
        assert out.strip() == 'trade_id,trade_type,quantity'

    def test_none_value_rendered_as_empty(self, svc):
        out = self._collect(svc.to_csv_streaming(ROWS, COLS))
        lines = out.strip().splitlines()
        last = list(csv.reader([lines[-1]]))[0]
        assert last[2] == ''   # quantity=None → ''

    def test_columns_inferred_from_rows(self, svc):
        out = self._collect(svc.to_csv_streaming(ROWS))
        header = out.strip().splitlines()[0]
        assert 'trade_id' in header

    def test_special_chars_quoted(self, svc):
        rows = [{'col': 'value, with comma'}, {'col': 'normal'}]
        out = self._collect(svc.to_csv_streaming(rows, ['col']))
        assert '"value, with comma"' in out


# ================================================================
# Excel
# ================================================================

class TestExcelBytes:
    def test_returns_bytes(self, svc):
        result = svc.to_excel_bytes(ROWS, COLS)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_valid_xlsx_magic_bytes(self, svc):
        result = svc.to_excel_bytes(ROWS, COLS)
        # ZIP magic bytes (XLSX is a ZIP)
        assert result[:2] == b'PK'

    def test_empty_rows_still_returns_bytes(self, svc):
        result = svc.to_excel_bytes([], COLS)
        assert isinstance(result, bytes)

    def test_sheet_name_truncated_to_31_chars(self, svc):
        long_name = 'A' * 50
        result = svc.to_excel_bytes(ROWS, COLS, sheet_name=long_name)
        assert isinstance(result, bytes)

    def test_none_values_handled(self, svc):
        rows = [{'a': None, 'b': 0, 'c': ''}]
        result = svc.to_excel_bytes(rows, ['a', 'b', 'c'])
        assert isinstance(result, bytes)


# ================================================================
# JSON streaming
# ================================================================

class TestJsonStreaming:
    def _collect(self, gen):
        return ''.join(gen)

    def test_valid_json_array(self, svc):
        out = self._collect(svc.to_json_streaming(ROWS))
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) == len(ROWS)

    def test_empty_rows_valid_empty_array(self, svc):
        out = self._collect(svc.to_json_streaming([]))
        data = json.loads(out)
        assert data == []

    def test_none_values_serialised(self, svc):
        rows = [{'x': None}]
        out = self._collect(svc.to_json_streaming(rows))
        data = json.loads(out)
        assert data[0]['x'] is None

    def test_date_objects_serialised(self, svc):
        from datetime import date
        rows = [{'dt': date(2026, 1, 15)}]
        out = self._collect(svc.to_json_streaming(rows))
        data = json.loads(out)
        assert '2026-01-15' in data[0]['dt']

    def test_single_row_no_trailing_comma(self, svc):
        out = self._collect(svc.to_json_streaming([{'a': 1}]))
        assert out.count(',\n') == 0


# ================================================================
# PDF
# ================================================================

class TestPdfBytes:
    def test_returns_bytes(self, svc):
        result = svc.to_pdf_bytes(ROWS, COLS, title='Test Report')
        assert isinstance(result, bytes)
        assert len(result) > 100

    def test_pdf_magic_bytes(self, svc):
        result = svc.to_pdf_bytes(ROWS, COLS)
        assert result[:4] == b'%PDF'

    def test_empty_rows(self, svc):
        result = svc.to_pdf_bytes([], COLS, title='Empty')
        assert result[:4] == b'%PDF'

    def test_truncation_at_max_pdf_rows(self, svc):
        many = [{'id': str(i)} for i in range(svc.MAX_PDF_ROWS + 100)]
        result = svc.to_pdf_bytes(many, ['id'], title='Big')
        assert isinstance(result, bytes)

    def test_custom_title_and_subtitle(self, svc):
        result = svc.to_pdf_bytes(
            ROWS, COLS,
            title='Q1 Trade Report',
            subtitle='Filtered: BUY only',
            generated_by='admin',
        )
        assert isinstance(result, bytes)

    def test_none_values_in_rows(self, svc):
        rows = [{'a': None, 'b': 'ok', 'c': 0}]
        result = svc.to_pdf_bytes(rows, ['a', 'b', 'c'])
        assert result[:4] == b'%PDF'

    def test_many_columns(self, svc):
        cols = [f'col_{i}' for i in range(20)]
        rows = [{c: str(i) for c in cols} for i in range(5)]
        result = svc.to_pdf_bytes(rows, cols, title='Wide Table')
        assert isinstance(result, bytes)

    def test_unicode_values(self, svc):
        rows = [{'name': '日本語テスト', 'val': 'café'}]
        result = svc.to_pdf_bytes(rows, ['name', 'val'])
        assert isinstance(result, bytes)
