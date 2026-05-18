"""
Export Service

Single responsibility: convert result rows to download formats.
No network I/O, no DB calls, no business logic.
"""

import csv
import io
import json
import logging
from typing import List, Dict, Generator

logger = logging.getLogger(__name__)


class ExportService:
    """Converts query result rows into various download formats."""

    MAX_PDF_ROWS = 500  # PDF only practical for small result sets

    def to_csv_streaming(self, rows: List[Dict], columns: List[str] = None) -> Generator:
        """Generator suitable for Django StreamingHttpResponse."""
        if not rows:
            yield ''
            return
        cols = columns or list(rows[0].keys())
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(cols)
        yield buf.getvalue()
        for row in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow([row.get(c, '') for c in cols])
            yield buf.getvalue()

    def to_excel_bytes(
        self,
        rows: List[Dict],
        columns: List[str] = None,
        sheet_name: str = 'Results',
    ) -> bytes:
        """Return Excel workbook as bytes. Requires openpyxl."""
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment
        except ImportError:
            raise ImportError("openpyxl is required for Excel export: pip install openpyxl")

        cols = columns or (list(rows[0].keys()) if rows else [])
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet(title=sheet_name[:31])

        header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
        header_font = Font(bold=True, color='FFFFFF')
        header_row = []
        for col in cols:
            cell = openpyxl.cell.WriteOnlyCell(ws, value=str(col))
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
            header_row.append(cell)
        ws.append(header_row)

        for row in rows:
            ws.append([row.get(c, '') for c in cols])

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def to_json_streaming(self, rows: List[Dict]) -> Generator:
        """Generator that streams a JSON array."""
        yield '[\n'
        for i, row in enumerate(rows):
            suffix = ',\n' if i < len(rows) - 1 else '\n'
            yield json.dumps(row, default=str) + suffix
        yield ']\n'


export_service = ExportService()
