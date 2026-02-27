"""
Upload Service

Business logic layer for file upload operations.
Handles:
- File validation (format, size, encoding, structure)
- Schema detection from file contents
- File processing and preview generation
- Hive external table creation orchestration

Supports: CSV, Excel (xlsx/xls), JSON, Parquet, Text files
"""

import os
import csv
import json
import io
import logging
import chardet
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict, field
from datetime import datetime

from ..repositories.upload_kudu_repository import upload_kudu_repository, UploadKuduRepository
from ..repositories.datasource_repository import datasource_repository

logger = logging.getLogger('upload')


@dataclass
class FileValidationResult:
    """Result of file validation."""
    is_valid: bool = False
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    file_type: str = ''
    encoding: str = 'UTF-8'
    delimiter: str = ','
    has_header: bool = True
    row_count: int = 0
    column_count: int = 0
    columns: List[Dict[str, str]] = field(default_factory=list)
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    file_size: int = 0


@dataclass
class UploadDTO:
    """Data Transfer Object for Upload."""
    upload_id: str = ''
    file_name: str = ''
    original_file_name: str = ''
    file_path: str = ''
    file_size: int = 0
    file_type: str = ''
    mime_type: str = ''
    row_count: int = 0
    column_count: int = 0
    delimiter: str = ','
    has_header: bool = True
    encoding: str = 'UTF-8'
    description: str = ''
    target_table_name: str = ''
    target_database: str = 'gmp_cis'
    hdfs_path: str = ''
    schema: List[Dict[str, str]] = field(default_factory=list)
    sample_data: List[Dict[str, Any]] = field(default_factory=list)
    validation_errors: List[str] = field(default_factory=list)
    status: str = 'PENDING'

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FileValidationService:
    """Service for validating uploaded files."""

    # Supported file extensions and their MIME types
    SUPPORTED_EXTENSIONS = {
        'csv': ['text/csv', 'application/csv', 'text/plain'],
        'tsv': ['text/tab-separated-values', 'text/plain'],
        'txt': ['text/plain'],
        'json': ['application/json', 'text/json'],
        'parquet': ['application/octet-stream', 'application/parquet'],
        'xlsx': ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'],
        'xls': ['application/vnd.ms-excel'],
    }

    # Maximum file size (100 MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024

    # Maximum rows to preview
    MAX_PREVIEW_ROWS = 100

    # Common delimiters to detect
    DELIMITERS = [',', '\t', ';', '|', ':']

    def __init__(self):
        self.repository = upload_kudu_repository

    def validate_file(self, file_obj, file_name: str) -> FileValidationResult:
        """
        Validate uploaded file.

        Args:
            file_obj: File object (Django UploadedFile or file-like object)
            file_name: Original file name

        Returns:
            FileValidationResult with validation status and detected properties
        """
        result = FileValidationResult()
        result.file_size = 0

        try:
            # Get file extension
            ext = self._get_extension(file_name)
            result.file_type = ext

            # Validate extension
            if ext not in self.SUPPORTED_EXTENSIONS:
                result.errors.append(f"Unsupported file format: .{ext}. Supported formats: {', '.join(self.SUPPORTED_EXTENSIONS.keys())}")
                return result

            # Read file content
            file_obj.seek(0)
            content = file_obj.read()
            result.file_size = len(content)

            # Validate file size
            if result.file_size > self.MAX_FILE_SIZE:
                result.errors.append(f"File size ({self._format_size(result.file_size)}) exceeds maximum allowed ({self._format_size(self.MAX_FILE_SIZE)})")
                return result

            if result.file_size == 0:
                result.errors.append("File is empty")
                return result

            # Detect encoding
            result.encoding = self._detect_encoding(content)

            # Validate and parse based on file type
            if ext in ['csv', 'tsv', 'txt']:
                self._validate_csv(content, result, ext)
            elif ext == 'json':
                self._validate_json(content, result)
            elif ext in ['xlsx', 'xls']:
                self._validate_excel(file_obj, result)
            elif ext == 'parquet':
                self._validate_parquet(file_obj, result)

            # If no errors, mark as valid
            if not result.errors:
                result.is_valid = True

        except Exception as e:
            logger.error(f"File validation error: {str(e)}")
            result.errors.append(f"Validation error: {str(e)}")

        return result

    def _get_extension(self, file_name: str) -> str:
        """Get file extension in lowercase."""
        if '.' in file_name:
            return file_name.rsplit('.', 1)[-1].lower()
        return ''

    def _format_size(self, size_bytes: int) -> str:
        """Format file size for display."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def _detect_encoding(self, content: bytes) -> str:
        """Detect file encoding."""
        try:
            detected = chardet.detect(content[:10000])  # Check first 10KB
            encoding = detected.get('encoding', 'UTF-8')
            confidence = detected.get('confidence', 0)

            if confidence < 0.5:
                return 'UTF-8'  # Default to UTF-8 if low confidence

            # Normalize encoding names
            encoding_map = {
                'ascii': 'UTF-8',
                'iso-8859-1': 'ISO-8859-1',
                'windows-1252': 'Windows-1252',
            }
            return encoding_map.get(encoding.lower(), encoding) if encoding else 'UTF-8'

        except Exception:
            return 'UTF-8'

    def _detect_delimiter(self, sample_lines: List[str]) -> str:
        """Detect CSV delimiter from sample lines."""
        if not sample_lines:
            return ','

        delimiter_counts = {}
        for delim in self.DELIMITERS:
            counts = [line.count(delim) for line in sample_lines[:10]]
            if counts and min(counts) > 0 and max(counts) == min(counts):
                # Consistent count across lines suggests this is the delimiter
                delimiter_counts[delim] = sum(counts)

        if delimiter_counts:
            return max(delimiter_counts, key=delimiter_counts.get)

        return ','

    def _validate_csv(self, content: bytes, result: FileValidationResult, ext: str) -> None:
        """Validate CSV/TSV/TXT file."""
        try:
            # Decode content
            text_content = content.decode(result.encoding, errors='replace')
            lines = text_content.splitlines()

            if not lines:
                result.errors.append("File contains no data")
                return

            # Detect delimiter
            if ext == 'tsv':
                result.delimiter = '\t'
            else:
                result.delimiter = self._detect_delimiter(lines)

            # Parse CSV
            reader = csv.reader(io.StringIO(text_content), delimiter=result.delimiter)
            rows = list(reader)

            if not rows:
                result.errors.append("No data rows found")
                return

            # Detect header
            first_row = rows[0]
            result.has_header = self._detect_header(first_row, rows[1] if len(rows) > 1 else None)

            # Get column info
            header_row = rows[0] if result.has_header else [f'col_{i+1}' for i in range(len(rows[0]))]
            data_rows = rows[1:] if result.has_header else rows

            result.column_count = len(header_row)
            result.row_count = len(data_rows)

            # Infer column types
            result.columns = self._infer_column_types(header_row, data_rows[:100])

            # Generate sample data
            result.sample_data = []
            for row in data_rows[:self.MAX_PREVIEW_ROWS]:
                if len(row) == len(header_row):
                    result.sample_data.append(dict(zip(header_row, row)))
                elif len(row) < len(header_row):
                    # Pad short rows
                    padded = row + [''] * (len(header_row) - len(row))
                    result.sample_data.append(dict(zip(header_row, padded)))
                else:
                    # Truncate long rows (with warning)
                    result.sample_data.append(dict(zip(header_row, row[:len(header_row)])))
                    if "inconsistent column count" not in str(result.warnings):
                        result.warnings.append(f"Some rows have inconsistent column count")

            # Validate consistency
            if result.row_count == 0:
                result.warnings.append("File contains only header row, no data")

        except Exception as e:
            result.errors.append(f"CSV parsing error: {str(e)}")

    def _detect_header(self, first_row: List[str], second_row: Optional[List[str]]) -> bool:
        """Detect if first row is a header."""
        if not first_row:
            return False

        # Check if all values in first row look like column names
        name_like = 0
        for val in first_row:
            val = str(val).strip()
            # Column names are typically: short, no numbers only, no special chars
            if val and len(val) < 50 and not val.replace('.', '').replace('-', '').isdigit():
                name_like += 1

        # If most look like names, consider it a header
        return name_like >= len(first_row) * 0.7

    def _infer_column_types(self, headers: List[str], sample_rows: List[List[str]]) -> List[Dict[str, str]]:
        """Infer Hive column types from sample data."""
        columns = []

        for i, header in enumerate(headers):
            col_name = self._clean_column_name(header)
            col_type = 'STRING'  # Default type

            # Collect non-empty values from this column
            values = []
            for row in sample_rows:
                if i < len(row) and row[i].strip():
                    values.append(row[i].strip())

            if values:
                col_type = self._infer_type(values)

            columns.append({
                'name': col_name,
                'original_name': header,
                'type': col_type,
                'nullable': True
            })

        return columns

    def _clean_column_name(self, name: str) -> str:
        """Clean column name for Hive compatibility."""
        # Remove leading/trailing whitespace
        clean = name.strip()
        # Replace special chars with underscore
        clean = ''.join(c if c.isalnum() or c == '_' else '_' for c in clean)
        # Remove consecutive underscores
        while '__' in clean:
            clean = clean.replace('__', '_')
        # Remove leading underscores
        clean = clean.lstrip('_')
        # Ensure not empty
        if not clean:
            clean = 'column'
        # Ensure doesn't start with number
        if clean[0].isdigit():
            clean = 'col_' + clean
        return clean.lower()

    def _infer_type(self, values: List[str]) -> str:
        """Infer Hive type from sample values."""
        # Try to determine type from values
        int_count = 0
        float_count = 0
        bool_count = 0
        date_count = 0

        for val in values[:50]:  # Check first 50 values
            val_lower = val.lower()

            # Check boolean
            if val_lower in ['true', 'false', 'yes', 'no', '1', '0']:
                bool_count += 1
                continue

            # Check integer
            try:
                int(val.replace(',', ''))
                int_count += 1
                continue
            except ValueError:
                pass

            # Check float
            try:
                float(val.replace(',', ''))
                float_count += 1
                continue
            except ValueError:
                pass

            # Check date patterns
            if self._looks_like_date(val):
                date_count += 1

        total = len(values[:50])
        threshold = 0.8  # 80% of values must match type

        if bool_count / total >= threshold:
            return 'BOOLEAN'
        if int_count / total >= threshold:
            return 'BIGINT'
        if (int_count + float_count) / total >= threshold:
            return 'DECIMAL(20,6)'
        if date_count / total >= threshold:
            return 'STRING'  # Keep dates as STRING for flexibility

        return 'STRING'

    def _looks_like_date(self, val: str) -> bool:
        """Check if value looks like a date."""
        import re
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # 2024-01-15
            r'\d{2}/\d{2}/\d{4}',  # 01/15/2024
            r'\d{2}-\d{2}-\d{4}',  # 15-01-2024
            r'\d{4}/\d{2}/\d{2}',  # 2024/01/15
        ]
        for pattern in date_patterns:
            if re.match(pattern, val):
                return True
        return False

    def _validate_json(self, content: bytes, result: FileValidationResult) -> None:
        """Validate JSON file."""
        try:
            text_content = content.decode(result.encoding, errors='replace')
            data = json.loads(text_content)

            result.delimiter = ''
            result.has_header = False

            if isinstance(data, list):
                result.row_count = len(data)
                if data and isinstance(data[0], dict):
                    result.column_count = len(data[0].keys())
                    result.columns = [
                        {'name': self._clean_column_name(k), 'original_name': k, 'type': 'STRING', 'nullable': True}
                        for k in data[0].keys()
                    ]
                    result.sample_data = data[:self.MAX_PREVIEW_ROWS]
            elif isinstance(data, dict):
                # Single object or nested structure
                result.row_count = 1
                result.column_count = len(data.keys())
                result.columns = [
                    {'name': self._clean_column_name(k), 'original_name': k, 'type': 'STRING', 'nullable': True}
                    for k in data.keys()
                ]
                result.sample_data = [data]
            else:
                result.errors.append("JSON must be an array of objects or a single object")

        except json.JSONDecodeError as e:
            result.errors.append(f"Invalid JSON: {str(e)}")

    def _validate_excel(self, file_obj, result: FileValidationResult) -> None:
        """Validate Excel file (xlsx/xls)."""
        try:
            import openpyxl

            file_obj.seek(0)
            wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
            sheet = wb.active

            result.delimiter = ''

            # Read all rows
            rows = list(sheet.iter_rows(values_only=True))

            if not rows:
                result.errors.append("Excel file is empty")
                return

            # First row as header
            header_row = [str(cell) if cell is not None else f'col_{i+1}' for i, cell in enumerate(rows[0])]
            data_rows = rows[1:]

            result.has_header = True
            result.column_count = len(header_row)
            result.row_count = len(data_rows)

            # Infer column types
            str_rows = [[str(cell) if cell is not None else '' for cell in row] for row in data_rows[:100]]
            result.columns = self._infer_column_types(header_row, str_rows)

            # Generate sample data
            result.sample_data = []
            for row in data_rows[:self.MAX_PREVIEW_ROWS]:
                row_dict = {}
                for i, header in enumerate(header_row):
                    if i < len(row):
                        row_dict[header] = str(row[i]) if row[i] is not None else ''
                    else:
                        row_dict[header] = ''
                result.sample_data.append(row_dict)

            wb.close()

        except ImportError:
            result.errors.append("Excel support requires openpyxl library. Install with: pip install openpyxl")
        except Exception as e:
            result.errors.append(f"Excel parsing error: {str(e)}")

    def _validate_parquet(self, file_obj, result: FileValidationResult) -> None:
        """Validate Parquet file."""
        try:
            import pyarrow.parquet as pq

            file_obj.seek(0)
            table = pq.read_table(file_obj)

            result.delimiter = ''
            result.has_header = True
            result.row_count = table.num_rows
            result.column_count = table.num_columns

            # Get schema
            result.columns = []
            for field in table.schema:
                hive_type = self._arrow_to_hive_type(str(field.type))
                result.columns.append({
                    'name': self._clean_column_name(field.name),
                    'original_name': field.name,
                    'type': hive_type,
                    'nullable': field.nullable
                })

            # Sample data
            df = table.slice(0, min(self.MAX_PREVIEW_ROWS, table.num_rows)).to_pandas()
            result.sample_data = df.to_dict('records')

        except ImportError:
            result.errors.append("Parquet support requires pyarrow library. Install with: pip install pyarrow")
        except Exception as e:
            result.errors.append(f"Parquet parsing error: {str(e)}")

    def _arrow_to_hive_type(self, arrow_type: str) -> str:
        """Convert PyArrow type to Hive type."""
        type_map = {
            'int8': 'TINYINT',
            'int16': 'SMALLINT',
            'int32': 'INT',
            'int64': 'BIGINT',
            'float': 'FLOAT',
            'double': 'DOUBLE',
            'bool': 'BOOLEAN',
            'string': 'STRING',
            'date32': 'DATE',
            'timestamp': 'TIMESTAMP',
        }
        arrow_lower = arrow_type.lower()
        for key, val in type_map.items():
            if key in arrow_lower:
                return val
        return 'STRING'


class UploadService:
    """Service class for upload operations."""

    def __init__(self):
        self.repository = upload_kudu_repository
        self.validation_service = FileValidationService()

    def get_all_uploads(
        self,
        status: Optional[str] = None,
        file_type: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all uploads with optional filters."""
        return self.repository.get_all_uploads(
            status=status,
            file_type=file_type,
            search=search
        )

    def get_upload_by_id(self, upload_id: str) -> Optional[Dict[str, Any]]:
        """Get upload by ID."""
        return self.repository.get_upload_by_id(upload_id)

    def validate_and_create_upload(
        self,
        file_obj,
        file_name: str,
        description: str,
        created_by: str
    ) -> Tuple[Optional[str], FileValidationResult]:
        """
        Validate file and create upload record.

        Returns:
            Tuple of (upload_id or None, FileValidationResult)
        """
        # Validate file
        validation_result = self.validation_service.validate_file(file_obj, file_name)

        if not validation_result.is_valid:
            return None, validation_result

        # Create upload DTO
        upload_dto = UploadDTO(
            file_name=file_name,
            original_file_name=file_name,
            file_size=validation_result.file_size,
            file_type=validation_result.file_type,
            row_count=validation_result.row_count,
            column_count=validation_result.column_count,
            delimiter=validation_result.delimiter,
            has_header=validation_result.has_header,
            encoding=validation_result.encoding,
            description=description,
            schema=validation_result.columns,
            sample_data=validation_result.sample_data,
            validation_errors=validation_result.errors + validation_result.warnings,
            status=UploadKuduRepository.STATUS_VALIDATED
        )

        # Create upload record
        upload_id = self.repository.create_upload(upload_dto.to_dict(), created_by)

        return upload_id, validation_result

    def update_upload(
        self,
        upload_id: str,
        update_data: Dict[str, Any],
        updated_by: str
    ) -> bool:
        """Update upload record."""
        return self.repository.update_upload(upload_id, update_data, updated_by)

    def delete_upload(self, upload_id: str, deleted_by: str) -> bool:
        """Soft delete upload."""
        return self.repository.soft_delete(upload_id, deleted_by)

    def ingest_to_hive(
        self,
        upload_id: str,
        table_name: Optional[str],
        columns: List[Dict[str, str]],
        file_path: str,
        updated_by: str
    ) -> Tuple[bool, str]:
        """
        Ingest uploaded file to Hive external table.

        Args:
            upload_id: Upload record ID
            table_name: Custom table name (or None to auto-generate)
            columns: Column definitions
            file_path: HDFS path to file
            updated_by: User performing ingestion

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get upload record
            upload = self.repository.get_upload_by_id(upload_id)
            if not upload:
                return False, "Upload not found"

            # Update status to ingesting
            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_INGESTING, updated_by)

            # Generate table name if not provided
            if not table_name:
                table_name = upload.get('target_table_name') or self.repository.generate_table_name(upload.get('file_name', 'upload'))

            # Get file properties
            file_type = upload.get('file_type', 'csv')
            delimiter = upload.get('delimiter', ',')
            has_header = upload.get('has_header', True)
            hdfs_path = file_path or upload.get('hdfs_path', '')

            # Create external table
            success = self.repository.create_external_table(
                table_name=table_name,
                columns=columns,
                hdfs_path=hdfs_path,
                file_format=file_type,
                delimiter=delimiter,
                has_header=has_header
            )

            if success:
                # Update upload record
                self.repository.update_upload(upload_id, {
                    'status': UploadKuduRepository.STATUS_COMPLETED,
                    'target_table_name': table_name,
                    'hdfs_path': hdfs_path
                }, updated_by)

                # Get row count from new table
                row_count = self.repository.get_table_row_count(table_name)
                if row_count > 0:
                    self.repository.update_upload(upload_id, {'row_count': row_count}, updated_by)

                return True, f"Successfully created table {table_name} with {row_count} rows"
            else:
                self.repository.update_status(
                    upload_id,
                    UploadKuduRepository.STATUS_FAILED,
                    updated_by,
                    "Failed to create external table"
                )
                return False, "Failed to create external table"

        except Exception as e:
            logger.error(f"Ingestion error: {str(e)}")
            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, str(e))
            return False, f"Ingestion error: {str(e)}"

    def get_statistics(self) -> Dict[str, Any]:
        """Get upload statistics."""
        return self.repository.get_upload_statistics()

    def get_status_choices(self) -> List[Tuple[str, str]]:
        """Get status choices for dropdowns."""
        return [
            (UploadKuduRepository.STATUS_PENDING, 'Pending'),
            (UploadKuduRepository.STATUS_VALIDATING, 'Validating'),
            (UploadKuduRepository.STATUS_VALIDATED, 'Validated'),
            (UploadKuduRepository.STATUS_VALIDATION_FAILED, 'Validation Failed'),
            (UploadKuduRepository.STATUS_INGESTING, 'Ingesting'),
            (UploadKuduRepository.STATUS_COMPLETED, 'Completed'),
            (UploadKuduRepository.STATUS_FAILED, 'Failed'),
            (UploadKuduRepository.STATUS_CANCELLED, 'Cancelled'),
        ]

    def get_file_type_choices(self) -> List[Tuple[str, str]]:
        """Get file type choices for dropdowns."""
        return [
            ('csv', 'CSV'),
            ('tsv', 'TSV'),
            ('txt', 'Text'),
            ('json', 'JSON'),
            ('xlsx', 'Excel (xlsx)'),
            ('xls', 'Excel (xls)'),
            ('parquet', 'Parquet'),
        ]

    # =========================================================================
    # METADATA-DRIVEN INGESTION (using cis_datasource_mng)
    # =========================================================================

    def get_datasource_config(self, file_name: str) -> Optional[Dict[str, Any]]:
        """
        Get datasource configuration for a file from cis_datasource_mng.

        Args:
            file_name: Name of the uploaded file

        Returns:
            Datasource configuration dict or None if not found
        """
        return datasource_repository.get_datasource_by_name(file_name)

    def validate_with_datasource_config(
        self,
        file_obj,
        file_name: str,
        datasource_config: Dict[str, Any]
    ) -> FileValidationResult:
        """
        Validate file using datasource configuration from cis_datasource_mng.

        Uses predefined separator, columns, and skip lines from metadata.

        Args:
            file_obj: File object
            file_name: File name
            datasource_config: Configuration from cis_datasource_mng

        Returns:
            FileValidationResult with validation status
        """
        result = FileValidationResult()

        try:
            # Get file properties from datasource config
            separator = datasource_config.get('separator', ',')
            skip_lines = int(datasource_config.get('no_of_skip_line', 0) or 0)
            has_header = str(datasource_config.get('header', 'true')).lower() == 'true'

            # Get predefined columns
            intake_columns = datasource_repository.parse_intake_columns(datasource_config)

            # Read file content
            file_obj.seek(0)
            content = file_obj.read()
            result.file_size = len(content)

            if result.file_size == 0:
                result.errors.append("File is empty")
                return result

            if result.file_size > self.validation_service.MAX_FILE_SIZE:
                result.errors.append(f"File size exceeds maximum allowed")
                return result

            # Detect encoding
            result.encoding = self.validation_service._detect_encoding(content)

            # Decode and parse
            text_content = content.decode(result.encoding, errors='replace')
            lines = text_content.splitlines()

            # Skip initial lines if configured
            if skip_lines > 0:
                lines = lines[skip_lines:]

            if not lines:
                result.errors.append("File contains no data after skipping lines")
                return result

            # Parse CSV with configured separator
            import csv
            import io
            reader = csv.reader(io.StringIO('\n'.join(lines)), delimiter=separator)
            rows = list(reader)

            if not rows:
                result.errors.append("No data rows found")
                return result

            # Use intake_columns from datasource config
            if intake_columns:
                result.columns = intake_columns
                result.column_count = len(intake_columns)
            else:
                # Fall back to detection
                header_row = rows[0] if has_header else [f'col_{i+1}' for i in range(len(rows[0]))]
                data_rows = rows[1:] if has_header else rows
                result.columns = self.validation_service._infer_column_types(header_row, data_rows[:100])
                result.column_count = len(result.columns)

            # Count rows
            data_rows = rows[1:] if has_header else rows
            result.row_count = len(data_rows)

            # Set properties
            result.file_type = 'csv'
            result.delimiter = separator
            result.has_header = has_header

            # Generate sample data
            header_names = [col['name'] for col in result.columns]
            result.sample_data = []
            for row in data_rows[:self.validation_service.MAX_PREVIEW_ROWS]:
                if len(row) >= len(header_names):
                    result.sample_data.append(dict(zip(header_names, row[:len(header_names)])))

            result.is_valid = True

        except Exception as e:
            logger.error(f"Validation with datasource config error: {str(e)}")
            result.errors.append(f"Validation error: {str(e)}")

        return result

    def ingest_to_target_table(
        self,
        upload_id: str,
        datasource_config: Dict[str, Any],
        updated_by: str,
        processing_date: str = None
    ) -> Tuple[bool, str]:
        """
        Ingest uploaded file to pre-defined target table using datasource config.

        This method:
        1. Creates staging external table for uploaded file
        2. Reads processing_date from HDFS /mrw/cis/MRA_PC_DATE.txt
        3. Inserts data into target table with additional columns:
           - src_id (from datasource.source_id)
           - src_system = 'cis'
           - data_cat = 'sta'
           - data_frq = 'adhoc'
           - processing_date (from MRA_PC_DATE.txt)

        Args:
            upload_id: Upload record ID
            datasource_config: Configuration from cis_datasource_mng
            updated_by: User performing ingestion
            processing_date: Override processing date (optional)

        Returns:
            Tuple of (success, message)
        """
        try:
            # Get upload record
            upload = self.repository.get_upload_by_id(upload_id)
            if not upload:
                return False, "Upload not found"

            # Update status to ingesting
            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_INGESTING, updated_by)

            # Get target table from datasource config
            target_table = datasource_config.get('target_table')
            if not target_table:
                return False, "No target_table defined in datasource configuration"

            # Get processing date from HDFS if not provided
            if not processing_date:
                processing_date = datasource_repository.get_processing_date()

            # Get file properties
            separator = datasource_config.get('separator', ',')
            has_header = str(datasource_config.get('header', 'true')).lower() == 'true'
            skip_lines = int(datasource_config.get('no_of_skip_line', 0) or 0)

            # Create staging table name
            staging_table = f"stg_upload_{upload_id.replace('-', '_').lower()}"

            # Get columns from datasource config
            intake_columns = datasource_repository.parse_intake_columns(datasource_config)
            if not intake_columns:
                return False, "No columns defined in datasource configuration"

            # Create staging external table
            hdfs_path = upload.get('hdfs_path', '')
            column_defs = [{'name': col['name'], 'type': col.get('type', 'STRING')} for col in intake_columns]

            staging_success = self.repository.create_external_table(
                table_name=staging_table,
                columns=column_defs,
                hdfs_path=hdfs_path,
                file_format='csv',
                delimiter=separator,
                has_header=has_header
            )

            if not staging_success:
                self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, "Failed to create staging table")
                return False, "Failed to create staging table"

            # Build and execute insert query with additional columns
            source_id = datasource_config.get('source_id', '')
            source_cols = [col['name'] for col in intake_columns]

            # Build target columns (source columns + additional columns)
            target_cols = source_cols + ['src_id', 'src_system', 'data_cat', 'data_frq', 'processing_date']

            # Build SELECT part
            select_parts = [f"`{col}`" for col in source_cols]
            select_parts.append(f"'{source_id}' as src_id")
            select_parts.append("'cis' as src_system")
            select_parts.append("'sta' as data_cat")
            select_parts.append("'adhoc' as data_frq")
            select_parts.append(f"'{processing_date}' as processing_date")

            insert_query = f"""
            INSERT INTO {self.repository.DATABASE}.{target_table}
            ({', '.join([f'`{c}`' for c in target_cols])})
            SELECT
                {', '.join(select_parts)}
            FROM {self.repository.DATABASE}.{staging_table}
            """

            from core.repositories.impala_connection import impala_manager
            insert_success = impala_manager.execute_write(insert_query, database=self.repository.DATABASE)

            if insert_success:
                # Update upload record
                self.repository.update_upload(upload_id, {
                    'status': UploadKuduRepository.STATUS_COMPLETED,
                    'target_table_name': target_table,
                }, updated_by)

                # Get row count
                row_count = self.repository.get_table_row_count(target_table)

                # Clean up staging table
                self.repository.drop_external_table(staging_table)

                # Refresh target table metadata
                impala_manager.execute_write(f"INVALIDATE METADATA {self.repository.DATABASE}.{target_table}", database=self.repository.DATABASE)

                return True, f"Successfully ingested {row_count} rows to {target_table} with processing_date={processing_date}"
            else:
                self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, "Failed to insert data")
                # Clean up staging table
                self.repository.drop_external_table(staging_table)
                return False, "Failed to insert data to target table"

        except Exception as e:
            logger.error(f"Metadata-driven ingestion error: {str(e)}")
            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, str(e))
            return False, f"Ingestion error: {str(e)}"

    def get_all_datasource_configs(self) -> List[Dict[str, Any]]:
        """Get all datasource configurations for dropdown."""
        return datasource_repository.get_all_datasources()
