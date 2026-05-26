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
    # Full parsed data rows (all rows, not capped). Populated by
    # validate_with_datasource_config so upload_create can ingest
    # immediately without re-reading the file.
    all_data: List[Dict[str, Any]] = field(default_factory=list)


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

            # Generate sample data using cleaned column names from schema
            # IMPORTANT: Use the cleaned names from result.columns to match the template
            cleaned_col_names = [col['name'] for col in result.columns]
            result.sample_data = []
            for row in data_rows[:self.MAX_PREVIEW_ROWS]:
                row_dict = {}
                for idx, col_name in enumerate(cleaned_col_names):
                    if idx < len(row):
                        row_dict[col_name] = row[idx]
                    else:
                        row_dict[col_name] = ''
                result.sample_data.append(row_dict)

                # Track inconsistent column counts
                if len(row) > len(cleaned_col_names):
                    if "inconsistent column count" not in str(result.warnings):
                        result.warnings.append(f"Some rows have inconsistent column count")

            # Validate consistency
            if result.row_count == 0:
                result.errors.append("File contains only a header row with no data. Please add data rows before uploading.")

            # Check for duplicate rows in source file
            duplicate_count = self._count_duplicate_rows(data_rows)
            if duplicate_count > 0:
                result.warnings.append(f"Found {duplicate_count} duplicate row(s) in source file")

        except Exception as e:
            result.errors.append(f"CSV parsing error: {str(e)}")

    def _count_duplicate_rows(self, rows: List[List[str]]) -> int:
        """
        Count duplicate rows in the data.

        Args:
            rows: List of data rows (each row is a list of values)

        Returns:
            Number of duplicate rows found
        """
        try:
            # Convert rows to tuples for hashing
            row_tuples = [tuple(row) for row in rows]
            unique_rows = set(row_tuples)

            # If unique count differs from total, we have duplicates
            total_rows = len(row_tuples)
            unique_count = len(unique_rows)
            duplicate_count = total_rows - unique_count

            if duplicate_count > 0:
                logger.warning(f"Found {duplicate_count} duplicate rows in source file")

            return duplicate_count
        except Exception as e:
            logger.error(f"Error counting duplicates: {str(e)}")
            return 0

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

    def _infer_column_types(self, headers: List[str], sample_rows: List[List[str]],
                              force_string: bool = False) -> List[Dict[str, str]]:
        """
        Infer Hive column types from sample data.

        Args:
            headers: List of column header names
            sample_rows: Sample data rows for type inference
            force_string: If True, all columns will be STRING type (for external tables)

        Returns:
            List of column definitions with name, type, nullable
        """
        columns = []

        for i, header in enumerate(headers):
            col_name = self._clean_column_name(header)
            col_type = 'STRING'  # Default type

            # Only infer type if not forcing STRING
            if not force_string:
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

            if result.row_count == 0:
                result.errors.append("File contains only a header row with no data. Please add data rows before uploading.")
                return

            # Infer column types
            str_rows = [[str(cell) if cell is not None else '' for cell in row] for row in data_rows[:100]]
            result.columns = self._infer_column_types(header_row, str_rows)

            # Generate sample data using cleaned column names from schema
            cleaned_col_names = [col['name'] for col in result.columns]
            result.sample_data = []
            for row in data_rows[:self.MAX_PREVIEW_ROWS]:
                row_dict = {}
                for i, col_name in enumerate(cleaned_col_names):
                    if i < len(row):
                        row_dict[col_name] = str(row[i]) if row[i] is not None else ''
                    else:
                        row_dict[col_name] = ''
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
            col_name_map = {}  # Map original -> cleaned names
            for field in table.schema:
                hive_type = self._arrow_to_hive_type(str(field.type))
                cleaned_name = self._clean_column_name(field.name)
                col_name_map[field.name] = cleaned_name
                result.columns.append({
                    'name': cleaned_name,
                    'original_name': field.name,
                    'type': hive_type,
                    'nullable': field.nullable
                })

            # Sample data - rename columns to match cleaned schema names
            df = table.slice(0, min(self.MAX_PREVIEW_ROWS, table.num_rows)).to_pandas()
            df = df.rename(columns=col_name_map)
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
            safe_err = f"{type(e).__name__}: {str(e)[:200]}"
            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, safe_err)
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
            has_header = datasource_repository.parse_header_flag(datasource_config)

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

            # Get file header row for column names
            file_header = rows[0] if has_header else [f'col_{i+1}' for i in range(len(rows[0]))]
            data_rows = rows[1:] if has_header else rows

            # Columns that are injected at ingest time and are NOT present in the
            # uploaded file. These are excluded from file column validation and
            # their default values are injected into sample_data for preview.
            SERVER_INJECTED_COLS = {'position_basis'}

            # Determine position_basis default for this datasource's target table
            POSITION_TABLE_BASIS = {
                'cis_user_sta_adhoc_position_1': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_2': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_3': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_4': 'SETTLE_DATE',
                'cis_user_sta_adhoc_position_5': 'SETTLE_DATE',
            }
            target_table = datasource_config.get('target_table', '')
            target_table_key = target_table.lower().split('.')[-1]
            injected_defaults = {}
            if target_table_key in POSITION_TABLE_BASIS:
                injected_defaults['position_basis'] = POSITION_TABLE_BASIS[target_table_key]

            # Use intake_columns from datasource config OR file header
            if intake_columns:
                # Split intake_columns into file columns (present in file) and
                # server-injected columns (not in file, added at ingest time).
                file_intake_columns = [
                    col for col in intake_columns
                    if col['name'].lower().strip() not in SERVER_INJECTED_COLS
                ]
                injected_intake_columns = [
                    col for col in intake_columns
                    if col['name'].lower().strip() in SERVER_INJECTED_COLS
                ]

                # Strict column validation against FILE columns only
                expected_col_names = [col['name'].lower().strip() for col in file_intake_columns]
                actual_col_names = [self.validation_service._clean_column_name(h).lower().strip() for h in file_header]

                # Check column count (file columns only)
                if len(file_intake_columns) != len(file_header):
                    result.is_valid = False
                    result.errors.append(
                        f"Column count mismatch: File has {len(file_header)} columns, "
                        f"but datasource config expects {len(file_intake_columns)} columns. "
                        f"Expected columns: {', '.join(expected_col_names)}"
                    )
                    logger.error(
                        f"INVALID: Column count mismatch for {file_name}. "
                        f"Expected {len(file_intake_columns)}, got {len(file_header)}."
                    )
                    return result

                # Check column names match (order matters, file columns only)
                mismatched_columns = []
                for idx, (expected, actual) in enumerate(zip(expected_col_names, actual_col_names)):
                    if expected != actual:
                        mismatched_columns.append(f"Column {idx+1}: expected '{expected}', got '{actual}'")

                if mismatched_columns:
                    result.is_valid = False
                    result.errors.append(
                        f"Column name mismatch: {'; '.join(mismatched_columns)}. "
                        f"File columns must match datasource configuration exactly."
                    )
                    logger.error(
                        f"INVALID: Column name mismatch for {file_name}. "
                        f"Mismatches: {mismatched_columns}"
                    )
                    return result

                # All validations passed - use full intake_columns (including injected)
                result.columns = intake_columns
                result.column_count = len(result.columns)
                logger.info(
                    f"Column validation passed for {file_name}: "
                    f"{len(file_intake_columns)} file columns match"
                    + (f", {len(injected_intake_columns)} server-injected col(s) skipped from file check" if injected_intake_columns else "")
                )
            else:
                # Fall back to detection - but force STRING for external tables
                result.columns = self.validation_service._infer_column_types(
                    file_header, data_rows[:100], force_string=True
                )
                result.column_count = len(result.columns)

            # Count rows
            result.row_count = len(data_rows)

            # Set properties
            result.file_type = 'csv'
            result.delimiter = separator
            result.has_header = has_header

            # Generate sample data.
            # File columns are mapped by position; injected columns get their
            # default value so the preview table shows what will actually land
            # in the target table after ingest.
            file_col_names = [
                col['name'] for col in result.columns
                if col['name'].lower() not in SERVER_INJECTED_COLS
            ]
            result.sample_data = []
            result.all_data = []
            for row_idx, row in enumerate(data_rows):
                row_dict = {}
                # Map file columns by position
                for idx, col_name in enumerate(file_col_names):
                    row_dict[col_name] = row[idx] if idx < len(row) else ''
                # Inject server-side defaults (position_basis etc.)
                for col_name, default_val in injected_defaults.items():
                    row_dict[col_name] = default_val
                result.all_data.append(row_dict)
                # Sample data (preview only — bracketed defaults, capped at MAX_PREVIEW_ROWS)
                if row_idx < self.validation_service.MAX_PREVIEW_ROWS:
                    preview_dict = dict(row_dict)
                    for col_name, default_val in injected_defaults.items():
                        preview_dict[col_name] = f'[{default_val}]'
                    result.sample_data.append(preview_dict)

            logger.info(f"validate_with_datasource_config: {len(result.all_data)} total rows, {len(result.sample_data)} preview rows for {file_name}")

            if result.row_count == 0:
                result.errors.append("File contains only a header row with no data. Please add data rows before uploading.")
                return result

            result.is_valid = True

        except Exception as e:
            logger.error(f"Validation with datasource config error: {str(e)}")
            result.errors.append(f"Validation error: {str(e)}")

        return result

    # HDFS base path for uploaded files — must match upload_kudu_repository.HDFS_BASE_PATH
    HDFS_STAGING_PATH = '/mrw/cis/staging'

    def ingest_to_target_table(
        self,
        upload_id: str,
        datasource_config: Dict[str, Any],
        updated_by: str,
        processing_date: str = None,
        temp_file_path: str = None,
        sample_data: List[Dict[str, Any]] = None,
        ingestion_mode: str = 'overwrite'
    ) -> Tuple[bool, str]:
        """
        Ingest uploaded file to pre-defined target table using datasource config.

        This method:
        1. Uploads local file to HDFS /mrw/cis/staging/ if temp_file_path provided
        2. Creates staging external table for uploaded file
        3. Reads processing_date from HDFS /mrw/cis/MRA_PC_DATE.txt
        4. Inserts data into target table with additional columns:
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
            temp_file_path: Local file path for session-based uploads
            sample_data: Sample data from session (used if file not available)
            ingestion_mode: 'overwrite' to replace existing data, 'append' to add to existing

        Returns:
            Tuple of (success, message)
        """
        is_session_upload = False  # default; set properly after DB lookup
        try:
            # Get upload record (may be None for session uploads)
            upload = self.repository.get_upload_by_id(upload_id)

            # For session uploads, we won't have a database record
            is_session_upload = upload is None

            if not is_session_upload:
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
            has_header = datasource_repository.parse_header_flag(datasource_config)
            skip_lines = int(datasource_config.get('no_of_skip_line', 0) or 0)

            # Use Hybrid connection - Hive for external table operations
            from core.repositories.hybrid_connection import hybrid_manager

            # Create staging table name
            staging_table = f"stg_upload_{upload_id.replace('-', '_').lower()}"

            # Get columns from datasource config
            intake_columns = datasource_repository.parse_intake_columns(datasource_config)
            if not intake_columns:
                # Try to get columns from target table
                target_table_info = datasource_repository.get_table_info(target_table, self.repository.DATABASE)
                if target_table_info.get('columns'):
                    # Filter out the additional columns we add
                    additional_cols = {'src_id', 'src_system', 'data_cat', 'data_frq', 'processing_date'}
                    intake_columns = [
                        {'name': col['name'], 'type': 'STRING'}
                        for col in target_table_info['columns']
                        if col['name'].lower() not in additional_cols
                    ]

            if not intake_columns:
                return False, "No columns defined in datasource configuration or target table"

            # Resolve the best available data source, in priority order:
            #   P1. Local temp file (same-node upload or DB-persisted path)
            #   P2. Impala external table over HDFS path (Cloudera/MRW — no hdfs shell needed)
            #   P3. sample_data from session (session-based uploads only)
            #   P4. sample_data_json from DB record (last resort — capped at 20 rows)
            local_file = None
            _hdfs_tmp = None
            _hdfs_impala_done = False  # True if P2 Impala path handled ingest directly

            logger.info(f"[ingest:svc] ===== FILE RESOLUTION upload_id={upload_id} =====")
            logger.info(f"[ingest:svc] temp_file_path arg={temp_file_path!r}")
            logger.info(f"[ingest:svc] temp_file_path exists={os.path.exists(temp_file_path) if temp_file_path else 'N/A'}")
            logger.info(f"[ingest:svc] upload is None={upload is None}")
            if upload:
                logger.info(f"[ingest:svc] upload.hdfs_path={upload.get('hdfs_path')!r}")
                logger.info(f"[ingest:svc] upload.file_path={upload.get('file_path')!r}")
                logger.info(f"[ingest:svc] upload.row_count={upload.get('row_count')!r}")
            logger.info(f"[ingest:svc] sample_data arg count={len(sample_data) if sample_data else 0}")

            if temp_file_path and os.path.exists(temp_file_path):
                local_file = temp_file_path
                logger.info(f"[ingest:svc] P1 RESOLVED — local temp file: {local_file}")
            else:
                logger.info(f"[ingest:svc] P1 FAILED — local file not found, trying Impala/HDFS path")
                # ----------------------------------------------------------------
                # P2: HDFS file available — create a temporary Hive external table
                #     pointing at the HDFS staging directory and INSERT directly
                #     into the target raw table via Impala SELECT.
                #     No hdfs shell command needed — works on any Cloudera node.
                # ----------------------------------------------------------------
                hdfs_path_db = (upload.get('hdfs_path', '') or '').strip() if upload else ''
                logger.info(f"[ingest:svc] P2 hdfs_path_db={hdfs_path_db!r}")
                if hdfs_path_db and not is_session_upload:
                    logger.info(f"[ingest:svc] P2 attempting Impala external table over HDFS: {hdfs_path_db}")
                    p2_success, p2_msg = self._ingest_via_hdfs_impala(
                        hdfs_path=hdfs_path_db,
                        target_table=target_table,
                        datasource_config=datasource_config,
                        intake_columns=intake_columns,
                        processing_date=processing_date,
                        upload_id=upload_id,
                        updated_by=updated_by,
                        ingestion_mode=ingestion_mode,
                    )
                    if p2_success:
                        logger.info(f"[ingest:svc] P2 RESOLVED via Impala/HDFS: {p2_msg}")
                        if not is_session_upload:
                            self.repository.update_status(upload_id, UploadKuduRepository.STATUS_COMPLETED, updated_by)
                        return True, p2_msg
                    else:
                        logger.warning(f"[ingest:svc] P2 FAILED — Impala/HDFS path: {p2_msg} — falling through to P3/P4")
                else:
                    logger.warning(f"[ingest:svc] P2 SKIPPED — hdfs_path_db empty or session upload")

            if not local_file:
                logger.warning(f"[ingest:svc] P1+P2 FAILED — no local file, using row data")
                if sample_data:
                    logger.info(f"[ingest:svc] P3 RESOLVED — session sample_data ({len(sample_data)} rows)")
                else:
                    logger.warning(f"[ingest:svc] P3 FAILED — sample_data arg empty, trying DB sample_data_json")
                    upload_sample = upload.get('sample_data_json', []) if upload else []
                    logger.info(f"[ingest:svc] P4 sample_data_json type={type(upload_sample).__name__} len={len(upload_sample) if upload_sample else 0}")
                    if upload_sample:
                        if isinstance(upload_sample, str):
                            try:
                                import json as json_module
                                sample_data = json_module.loads(upload_sample)
                                logger.info(f"[ingest:svc] P4 parsed → {len(sample_data)} rows")
                            except Exception as _je:
                                logger.warning(f"[ingest:svc] P4 parse error: {_je}")
                                sample_data = []
                        else:
                            sample_data = upload_sample
                            logger.info(f"[ingest:svc] P4 already list → {len(sample_data)} rows")
                    if sample_data:
                        logger.warning(f"[ingest:svc] P4 FALLBACK — DB sample_data ({len(sample_data)} rows, CAPPED AT 20)")
                    else:
                        logger.error(f"[ingest:svc] ALL PRIORITIES FAILED — no data source available")

            logger.info(f"[ingest:svc] FINAL: local_file={local_file!r} sample_data_rows={len(sample_data) if sample_data else 0}")

            # If we have either a local file or sample_data, use INSERT VALUES
            if local_file or sample_data:
                try:
                    # ----------------------------------------------------------------
                    # Kudu UPSERT path: cis_equity_price is a Kudu table, not a
                    # Hive external/partitioned table — INSERT OVERWRITE won't work.
                    # Route to dedicated Kudu upsert method instead.
                    # ----------------------------------------------------------------
                    if target_table.lower() in ('cis_equity_price', 'gmp_cis.cis_equity_price'):
                        return self._ingest_kudu_equity_price(
                            datasource_config=datasource_config,
                            intake_columns=intake_columns,
                            sample_data=sample_data if sample_data else [],
                            updated_by=updated_by,
                            upload_id=upload_id,
                            is_session_upload=is_session_upload,
                            temp_file_path=local_file,
                        )

                    return self._ingest_using_insert_values(
                        target_table=target_table,
                        datasource_config=datasource_config,
                        intake_columns=intake_columns,
                        sample_data=sample_data if sample_data else [],
                        processing_date=processing_date,
                        updated_by=updated_by,
                        upload_id=upload_id,
                        is_session_upload=is_session_upload,
                        temp_file_path=local_file,
                        ingestion_mode=ingestion_mode
                    )
                finally:
                    # Clean up the HDFS-downloaded temp file (not the user's original temp)
                    if _hdfs_tmp and os.path.exists(_hdfs_tmp):
                        try:
                            os.unlink(_hdfs_tmp)
                            logger.info(f"[ingest] Cleaned up HDFS temp file: {_hdfs_tmp}")
                        except OSError:
                            pass

            return False, "No file or sample data available for ingestion. Please re-upload the file."

        except Exception as e:
            logger.error(f"Metadata-driven ingestion error: {str(e)}")
            if not is_session_upload:
                safe_err = f"{type(e).__name__}: {str(e)[:200]}"
                self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, safe_err)
            return False, f"Ingestion error: {str(e)}"

    def _ingest_kudu_equity_price(
        self,
        datasource_config: Dict[str, Any],
        intake_columns: List[Dict[str, str]],
        sample_data: List[Dict[str, Any]],
        updated_by: str,
        upload_id: str,
        is_session_upload: bool = False,
        temp_file_path: str = None,
    ) -> Tuple[bool, str]:
        """
        Ingest equity price CSV rows directly into cis_equity_price (Kudu) via UPSERT.

        cis_equity_price is a Kudu table — INSERT OVERWRITE / partitions don't apply.
        Each row is upserted using the existing EquityPriceHiveRepository so that
        currency_code + isin are looked up from cis_security and all audit fields
        are populated consistently.

        CSV columns used (case-insensitive via intake_columns):
            price_date, security_label, closing_price
            (shares_outstanding and market_value are ignored)

        Args:
            datasource_config: Datasource configuration from cis_datasource_mng
            intake_columns:    Parsed column list from datasource config
            sample_data:       Rows already parsed (used if temp_file_path not available)
            updated_by:        Username performing the ingestion
            upload_id:         Upload record ID for status tracking
            is_session_upload: True when upload record lives in session, not DB
            temp_file_path:    Path to local temp file (full data, preferred over sample_data)

        Returns:
            Tuple of (success, message)
        """
        from decimal import Decimal, InvalidOperation
        from market_data.repositories.equity_price_hive_repository import equity_price_hive_repository
        from security.repositories.security_hive_repository import SecurityHiveRepository
        import time as _time

        counters = {'inserted': 0, 'skipped': 0, 'errors': []}

        # ---- Build full data list from file or sample_data ----
        separator = datasource_config.get('separator', ',')
        has_header = str(datasource_config.get('header', 'true')).lower() == 'true'
        col_names = [col['name'] for col in intake_columns]

        all_data = list(sample_data) if sample_data else []

        if temp_file_path and os.path.exists(temp_file_path):
            logger.info(f"[equity_price] Reading full file from {temp_file_path}")
            try:
                all_data = []
                with open(temp_file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                    reader = csv.reader(f, delimiter=separator or ',')
                    rows = list(reader)
                if has_header and rows:
                    rows = rows[1:]
                for row in rows:
                    row_dict = {col: (row[i] if i < len(row) else '') for i, col in enumerate(col_names)}
                    all_data.append(row_dict)
                logger.info(f"[equity_price] Read {len(all_data)} rows from file")
            except Exception as e:
                logger.error(f"[equity_price] Failed to read file: {e}")
                all_data = list(sample_data) if sample_data else []

        if not all_data:
            return False, "No data to ingest"

        # ---- Column name map (normalise to lowercase for lookup) ----
        # intake_columns names are already cleaned by FileValidationService._clean_column_name
        # Expected cleaned names from CSV headers:
        #   "Price Date"       -> "price_date"
        #   "Security label"   -> "security_label"
        #   "Closing Price"    -> "closing_price"
        def _find_col(row_dict: dict, *candidates) -> str:
            """Return value for the first matching key (case-insensitive)."""
            lower_map = {k.lower(): v for k, v in row_dict.items()}
            for cand in candidates:
                v = lower_map.get(cand.lower(), '')
                if v:
                    return str(v).strip()
            return ''

        # Per-upload security lookup cache (avoids N Impala round-trips for same security)
        security_cache: Dict[str, Optional[Dict]] = {}

        for row_num, row in enumerate(all_data, start=2):
            price_date    = _find_col(row, 'price_date', 'price date')
            security_label = _find_col(row, 'security_label', 'security label', 'security_name')
            closing_price_str = _find_col(row, 'closing_price', 'closing price', 'main_closing_price')

            # Basic validation
            if not price_date or not security_label or not closing_price_str:
                counters['errors'].append({
                    'row': row_num,
                    'reason': 'Missing price_date, security_label, or closing_price'
                })
                counters['skipped'] += 1
                continue

            try:
                price_decimal = Decimal(closing_price_str)
                if price_decimal <= 0:
                    raise ValueError("non-positive")
            except (InvalidOperation, ValueError):
                counters['errors'].append({
                    'row': row_num,
                    'reason': f"Invalid closing price: '{closing_price_str}'"
                })
                counters['skipped'] += 1
                continue

            # Security lookup for currency_code + isin
            if security_label not in security_cache:
                try:
                    securities = SecurityHiveRepository.get_all_securities(
                        search=security_label, limit=5
                    )
                    match = next(
                        (s for s in securities
                         if s.get('security_name', '').strip() == security_label),
                        None
                    )
                    security_cache[security_label] = match
                except Exception as e:
                    security_cache[security_label] = None
                    logger.warning(f"[equity_price] Security lookup failed for '{security_label}': {e}")

            sec_rec = security_cache.get(security_label)
            currency_code = sec_rec.get('currency_code', '') if sec_rec else ''
            isin = sec_rec.get('isin', '') if sec_rec else ''

            if not currency_code:
                logger.warning(
                    f"[equity_price] Row {row_num}: no currency_code for '{security_label}', using empty"
                )

            equity_price_data = {
                'currency_code': currency_code,
                'security_label': security_label,
                'price_date': price_date,
                'main_closing_price': float(price_decimal),
                'isin': isin,
                'src_system': 'CIS',
                'created_by': updated_by,
                'price_timestamp': int(_time.time() * 1000),
            }

            try:
                success = equity_price_hive_repository.upsert_equity_price(
                    equity_price_data, username=updated_by
                )
                if success:
                    counters['inserted'] += 1
                else:
                    counters['errors'].append({'row': row_num, 'reason': 'Upsert returned False'})
                    counters['skipped'] += 1
            except Exception as e:
                counters['errors'].append({'row': row_num, 'reason': str(e)})
                counters['skipped'] += 1

        # ---- Update upload record status ----
        if not is_session_upload:
            if counters['inserted'] > 0:
                self.repository.update_upload(upload_id, {
                    'status': UploadKuduRepository.STATUS_COMPLETED,
                    'target_table_name': 'cis_equity_price',
                    'row_count': counters['inserted'],
                    'description': (
                        f"Kudu UPSERT: {counters['inserted']} inserted, "
                        f"{counters['skipped']} skipped"
                    ),
                }, updated_by)
            else:
                self.repository.update_status(
                    upload_id, UploadKuduRepository.STATUS_FAILED, updated_by,
                    f"0 rows inserted. Errors: {str(counters['errors'][:3])[:200]}"
                )

        # ---- Trigger position market value refresh ----
        if counters['inserted'] > 0:
            try:
                from trade.repositories.trade_kudu_repository import trade_kudu_repository
                trade_kudu_repository.refresh_market_values()
            except Exception:
                pass  # Non-blocking

        # ---- Clear equity price cache ----
        if counters['inserted'] > 0:
            try:
                from market_data.services.equity_price_service import EquityPriceService
                EquityPriceService.clear_cache()
            except Exception:
                pass

        logger.info(
            f"[equity_price] upload_id={upload_id} by {updated_by}: "
            f"inserted={counters['inserted']}, skipped={counters['skipped']}, "
            f"errors={len(counters['errors'])}"
        )

        if counters['inserted'] > 0:
            msg = (
                f"Successfully upserted {counters['inserted']} equity price"
                f"{'s' if counters['inserted'] != 1 else ''} into cis_equity_price"
            )
            if counters['skipped']:
                msg += f" ({counters['skipped']} skipped — see upload detail for errors)"
            return True, msg

        return False, (
            f"No rows inserted into cis_equity_price. "
            f"{counters['skipped']} skipped. "
            f"First error: {counters['errors'][0]['reason'] if counters['errors'] else 'unknown'}"
        )

    def _upload_file_to_hdfs(self, local_path: str, hdfs_dir: str) -> bool:
        """
        Upload a local file to HDFS using the hdfs CLI.
        Tries several common full paths for the hdfs binary on Cloudera CML.

        Args:
            local_path: Path to local file
            hdfs_dir: HDFS directory to upload to (LOCATION for external table)

        Returns:
            True if successful, False otherwise
        """
        import subprocess
        import shutil

        # Resolve hdfs binary — try PATH first, then common Cloudera install locations
        hdfs_bin = shutil.which('hdfs')
        if not hdfs_bin:
            for candidate in [
                '/usr/bin/hdfs',
                '/usr/local/bin/hdfs',
                '/opt/cloudera/parcels/CDH/bin/hdfs',
                '/opt/hadoop/bin/hdfs',
            ]:
                if os.path.isfile(candidate):
                    hdfs_bin = candidate
                    break

        if not hdfs_bin:
            logger.error("[hdfs:put] hdfs binary not found — cannot upload to HDFS")
            return False

        logger.info(f"[hdfs:put] using hdfs binary: {hdfs_bin}")
        try:
            # Create HDFS directory
            mkdir_cmd = [hdfs_bin, 'dfs', '-mkdir', '-p', hdfs_dir]
            logger.info(f"[hdfs:put] {' '.join(mkdir_cmd)}")
            result = subprocess.run(mkdir_cmd, capture_output=True, text=True, timeout=60)
            logger.info(f"[hdfs:put] mkdir rc={result.returncode} stderr={result.stderr[:200]}")
            if result.returncode != 0:
                logger.error(f"[hdfs:put] Failed to create HDFS directory: {result.stderr}")
                return False

            # Upload file to HDFS
            put_cmd = [hdfs_bin, 'dfs', '-put', '-f', local_path, hdfs_dir]
            logger.info(f"[hdfs:put] {' '.join(put_cmd)}")
            result = subprocess.run(put_cmd, capture_output=True, text=True, timeout=300)
            logger.info(f"[hdfs:put] put rc={result.returncode} stderr={result.stderr[:200]}")
            if result.returncode != 0:
                logger.error(f"[hdfs:put] Failed to upload file: {result.stderr}")
                return False

            logger.info(f"[hdfs:put] SUCCESS {local_path} → {hdfs_dir}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("[hdfs:put] timed out")
            return False
        except Exception as e:
            logger.error(f"[hdfs:put] error: {e}", exc_info=True)
            return False

    def _cleanup_hdfs_staging(self, hdfs_path: str) -> bool:
        """
        Clean up HDFS staging directory.

        Args:
            hdfs_path: HDFS path to clean up

        Returns:
            True if successful, False otherwise
        """
        import subprocess

        try:
            # Only clean up if path is under staging directory
            if self.HDFS_STAGING_PATH not in hdfs_path:
                return True

            rm_cmd = ['hdfs', 'dfs', '-rm', '-r', '-f', hdfs_path]
            result = subprocess.run(rm_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                logger.info(f"Cleaned up HDFS staging: {hdfs_path}")
                return True
            else:
                logger.warning(f"Could not clean up HDFS staging: {result.stderr}")
                return False

        except Exception as e:
            logger.warning(f"HDFS cleanup error: {e}")
            return False

    def _ingest_via_hdfs_impala(
        self,
        hdfs_path: str,
        target_table: str,
        datasource_config: Dict[str, Any],
        intake_columns: List[Dict[str, Any]],
        processing_date: str,
        upload_id: str,
        updated_by: str,
        ingestion_mode: str = 'overwrite',
    ) -> Tuple[bool, str]:
        """
        Ingest a CSV/pipe-delimited file on HDFS directly into the raw target table
        using Impala — no hdfs shell command required.

        Strategy:
          1. CREATE EXTERNAL TABLE stg_... STORED AS TEXTFILE LOCATION '<hdfs_path>'
          2. INSERT OVERWRITE/INTO <target_table> PARTITION(processing_date, src_id)
                SELECT col1, col2, ..., '<processing_date>' FROM stg_...
             skipping the header row via a WHERE clause on a ROW_NUMBER() window.
          3. DROP TABLE stg_... (external — does not delete HDFS data)
        """
        from core.repositories.impala_connection import impala_manager
        from ..repositories.datasource_repository import datasource_repository

        db = self.repository.DATABASE
        separator = datasource_config.get('separator', ',')
        has_header = datasource_repository.parse_header_flag(datasource_config)
        source_id = datasource_config.get('source_id', target_table)
        src_system = datasource_config.get('src_system', 'USER_UPLOAD')
        sub_system = datasource_config.get('sub_system', 'user')
        data_cat = datasource_config.get('data_cat', 'sta')
        data_frq = datasource_config.get('data_frq', 'adhoc')

        # Safe staging table name — unique per upload
        stg_table = f"stg_hdfs_{upload_id.replace('-', '_').lower()}"

        # Impala field terminator: pipe needs escaping
        field_term = separator if separator not in ('|',) else '\\|'

        col_names = [col['name'] for col in intake_columns]
        # Build SELECT col list: col1, col2, ... from the staging table
        # All staging columns are STRING (TEXTFILE external table)
        stg_col_select = ',\n                    '.join(col_names)

        # Additional columns appended to target
        POSITION_TABLE_BASIS = {
            'cis_user_sta_adhoc_position_1': 'TRADE_DATE',
            'cis_user_sta_adhoc_position_2': 'TRADE_DATE',
            'cis_user_sta_adhoc_position_3': 'TRADE_DATE',
            'cis_user_sta_adhoc_position_4': 'SETTLE_DATE',
            'cis_user_sta_adhoc_position_5': 'SETTLE_DATE',
        }
        table_lower = target_table.lower().split('.')[-1]
        position_basis = POSITION_TABLE_BASIS.get(table_lower, '')

        try:
            # Step 1: Drop any leftover staging table
            impala_manager.execute_write(f"DROP TABLE IF EXISTS {db}.{stg_table}", database=db)

            # Step 2: Create external table over the HDFS staging directory.
            # The LOCATION is a directory — Hive reads ALL files in it.
            # To prevent accumulation from re-runs, wipe the directory first
            # then re-upload. Since we only hold one file per upload_id dir,
            # this is safe.
            create_cols = ',\n    '.join(f"`{c}` STRING" for c in col_names)
            ok = impala_manager.execute_write(f"""
                CREATE EXTERNAL TABLE {db}.{stg_table} (
                    {create_cols}
                )
                ROW FORMAT DELIMITED
                FIELDS TERMINATED BY '{field_term}'
                STORED AS TEXTFILE
                LOCATION '{hdfs_path}'
                TBLPROPERTIES ('skip.header.line.count'='{"1" if has_header else "0"}')
            """, database=db)
            if not ok:
                return False, f"Could not CREATE EXTERNAL TABLE {stg_table} over {hdfs_path}"

            impala_manager.execute_write(f"INVALIDATE METADATA {db}.{stg_table}", database=db)

            # Step 3: Count rows to verify — also guards against multi-file accumulation
            cnt_rows = impala_manager.execute_query(
                f"SELECT COUNT(*) AS cnt FROM {db}.{stg_table}", database=db
            )
            row_count = cnt_rows[0].get('cnt', 0) if cnt_rows else 0
            logger.info(f"[hdfs:impala] staging table {stg_table} has {row_count} rows at {hdfs_path}")

            if row_count == 0:
                impala_manager.execute_write(f"DROP TABLE IF EXISTS {db}.{stg_table}", database=db)
                return False, f"HDFS staging table {stg_table} read 0 rows from {hdfs_path} — file may be empty or path wrong"

            # Build extra column expressions (only columns NOT already in the file).
            # position_basis defaulted here; src_id goes into PARTITION clause.
            extra_cols = [
                f"'{src_system}' AS src_system",
                f"'{sub_system}' AS sub_system",
                f"'{data_cat}'   AS data_cat",
                f"'{data_frq}'   AS data_frq",
            ]
            col_names_lower = [c.lower() for c in col_names]
            if position_basis and 'position_basis' not in col_names_lower:
                extra_cols.append(f"'{position_basis}' AS position_basis")

            # Step 4: Clear the target partition BEFORE inserting.
            # cis_user_sta_adhoc_position_* tables are partitioned by processing_date
            # only (no src_id partition). Always DROP the partition first so that
            # re-runs never double-insert.
            impala_manager.execute_write(
                f"ALTER TABLE {db}.{target_table} "
                f"DROP IF EXISTS PARTITION (processing_date='{processing_date}')",
                database=db
            )
            logger.info(f"[hdfs:impala] dropped partition processing_date={processing_date} in {target_table} before insert")

            # Step 5: INSERT from staging table into target (always INSERT INTO
            # after the partition drop — INSERT OVERWRITE on a single-partition-col
            # table would wipe all partitions if spec omitted, so be explicit).
            extra_cols_sql = ',\n                    '.join(extra_cols)
            ok = impala_manager.execute_write(f"""
                INSERT INTO {db}.{target_table}
                PARTITION (processing_date='{processing_date}')
                SELECT
                    {stg_col_select},
                    {extra_cols_sql}
                FROM {db}.{stg_table}
            """, database=db)

            if not ok:
                impala_manager.execute_write(f"DROP TABLE IF EXISTS {db}.{stg_table}", database=db)
                return False, f"INSERT from {stg_table} into {target_table} failed — check Impala logs"

            impala_manager.execute_write(f"INVALIDATE METADATA {db}.{target_table}", database=db)

            # Step 6: Confirm rows landed — filter by processing_date only
            # (src_id is a data column, not a partition key, on these tables)
            inserted = impala_manager.execute_query(f"""
                SELECT COUNT(*) AS cnt FROM {db}.{target_table}
                WHERE processing_date = '{processing_date}'
            """, database=db)
            inserted_count = inserted[0].get('cnt', 0) if inserted else 0
            logger.info(f"[hdfs:impala] inserted {inserted_count} rows into {target_table} partition processing_date={processing_date}")

            # Step 7: Drop staging table (external — HDFS data preserved for audit)
            impala_manager.execute_write(f"DROP TABLE IF EXISTS {db}.{stg_table}", database=db)

            return True, f"Ingested {inserted_count} rows from HDFS into {target_table} (processing_date={processing_date})"

        except Exception as e:
            logger.error(f"[hdfs:impala] error: {e}", exc_info=True)
            try:
                impala_manager.execute_write(f"DROP TABLE IF EXISTS {db}.{stg_table}", database=db)
            except Exception:
                pass
            return False, f"HDFS Impala ingest error: {e}"

    def _download_from_hdfs(self, hdfs_path: str) -> Optional[str]:
        """
        Download an HDFS file to a local temp file and return the local path.
        Returns None if hdfs command is unavailable or the download fails.
        """
        from django.conf import settings as django_settings
        import subprocess
        import tempfile

        logger.info(f"[hdfs:download] called with hdfs_path={hdfs_path!r}")
        try:
            suffix = os.path.basename(hdfs_path)
            tmp_dir = os.path.join(django_settings.BASE_DIR, 'temp_uploads')
            os.makedirs(tmp_dir, exist_ok=True)
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=f'_{suffix}', dir=tmp_dir
            )
            tmp.close()
            get_cmd = ['hdfs', 'dfs', '-get', '-f', hdfs_path, tmp.name]
            logger.info(f"[hdfs:download] running: {' '.join(get_cmd)}")
            result = subprocess.run(get_cmd, capture_output=True, text=True, timeout=300)
            logger.info(f"[hdfs:download] returncode={result.returncode}")
            if result.stdout:
                logger.info(f"[hdfs:download] stdout={result.stdout[:500]}")
            if result.stderr:
                logger.info(f"[hdfs:download] stderr={result.stderr[:500]}")
            if result.returncode == 0:
                file_size = os.path.getsize(tmp.name)
                logger.info(f"[hdfs:download] SUCCESS → {tmp.name} ({file_size} bytes)")
                return tmp.name
            logger.error(f"[hdfs:download] FAILED returncode={result.returncode} stderr={result.stderr[:500]}")
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
            return None
        except FileNotFoundError:
            logger.warning("[hdfs:download] 'hdfs' command not found — hdfs client not installed on this node")
            return None
        except subprocess.TimeoutExpired:
            logger.error("[hdfs:download] timed out after 300s")
            return None
        except Exception as e:
            logger.error(f"[hdfs:download] unexpected error: {e}", exc_info=True)
            return None

    # Columns whose values should be normalised to YYYYMMDD before ingest.
    # Matched case-insensitively against the target table column name.
    DATE_COLUMNS = {
        'trade_date', 'reporting_date', 'maturity_date', 'price_date',
        'settlement_date', 'settle_date', 'value_date', 'effective_date',
        'start_date', 'end_date', 'expiry_date',
    }

    @staticmethod
    def normalise_date(val: str) -> str:
        """
        Convert a date string from any common format to YYYYMMDD.

        Handles (examples):
            30/01/2026  -> 20260130   (DD/MM/YYYY)
            01-30-2026  -> 20260130   (MM-DD-YYYY)
            2026-01-30  -> 20260130   (YYYY-MM-DD  — already ISO)
            20260130    -> 20260130   (already YYYYMMDD)
            30-Jan-2026 -> 20260130   (DD-Mon-YYYY)
            Jan 30 2026 -> 20260130
            30 January 2026 -> 20260130

        Returns the original value unchanged if it cannot be parsed,
        so ingest never fails hard on a bad date — the raw value lands
        in the table and can be flagged by the ETL report.
        """
        if not val or not isinstance(val, str):
            return val or ''

        cleaned = val.strip()
        if not cleaned:
            return ''

        # Already YYYYMMDD — return immediately
        if len(cleaned) == 8 and cleaned.isdigit():
            return cleaned

        from datetime import datetime

        # Ordered list of format strings to try
        DATE_FORMATS = [
            '%d/%m/%Y',    # 30/01/2026
            '%d-%m-%Y',    # 30-01-2026
            '%m/%d/%Y',    # 01/30/2026  (US)
            '%m-%d-%Y',    # 01-30-2026  (US)
            '%Y-%m-%d',    # 2026-01-30  (ISO)
            '%Y/%m/%d',    # 2026/01/30
            '%d-%b-%Y',    # 30-Jan-2026
            '%d-%B-%Y',    # 30-January-2026
            '%d %b %Y',    # 30 Jan 2026
            '%d %B %Y',    # 30 January 2026
            '%b %d %Y',    # Jan 30 2026
            '%B %d %Y',    # January 30 2026
            '%b %d, %Y',   # Jan 30, 2026
            '%B %d, %Y',   # January 30, 2026
            '%Y%m%d',      # 20260130 (already caught above, safety fallback)
        ]

        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(cleaned, fmt)
                return dt.strftime('%Y%m%d')
            except ValueError:
                continue

        # Could not parse — return original so ingest doesn't break
        logger.warning(f"[date_normalise] Could not parse date value: '{cleaned}' — storing as-is")
        return cleaned

    def _ingest_using_insert_values(
        self,
        target_table: str,
        datasource_config: Dict[str, Any],
        intake_columns: List[Dict[str, str]],
        sample_data: List[Dict[str, Any]],
        processing_date: str,
        updated_by: str,
        upload_id: str,
        is_session_upload: bool = False,
        temp_file_path: str = None,
        ingestion_mode: str = 'overwrite'
    ) -> Tuple[bool, str]:
        """
        Ingest data to Hive external Parquet table using Impala INSERT.

        For external Parquet tables with partitions:
        1. Read data from file or sample_data
        2. Deduplicate rows
        3. Based on ingestion_mode:
           - 'overwrite': INSERT OVERWRITE to replace existing partition data
           - 'append': INSERT INTO to add to existing partition data
        4. Refresh table metadata

        Args:
            target_table: Target table name
            datasource_config: Datasource configuration
            intake_columns: Column definitions
            sample_data: Data rows to insert (used if temp_file_path not available)
            processing_date: Processing date (partition value)
            updated_by: User performing ingestion
            upload_id: Upload ID
            is_session_upload: Whether this is a session-based upload
            temp_file_path: Path to local temp file (if available, reads full file)
            ingestion_mode: 'overwrite' to replace data, 'append' to add to existing

        Returns:
            Tuple of (success, message)
        """
        from core.repositories.impala_connection import impala_manager
        from ..repositories.datasource_repository import datasource_repository
        import csv
        import re as _re

        try:
            # Validate processing_date before it touches any SQL
            if not processing_date or not _re.match(r'^\d{8}$', str(processing_date)):
                return False, f"Invalid processing_date '{processing_date}' — must be YYYYMMDD"

            source_id = datasource_config.get('source_id', '')
            col_names = [col['name'] for col in intake_columns]
            separator = datasource_config.get('separator', ',')
            has_header = datasource_repository.parse_header_flag(datasource_config)

            # Get target table columns to ensure we match exactly
            target_table_info = datasource_repository.get_table_info(target_table, self.repository.DATABASE)
            target_table_cols = [col['name'] for col in target_table_info.get('columns', [])]

            if not target_table_cols:
                return False, f"Could not get column info for target table {target_table}"

            # Determine src_system from datasource config or target table name
            # USER_UPLOAD tables: cis_user_sta_adhoc_position_* (contain 'user' in name)
            # AMS_STREET tables: gmp_cis_sta_*_ams_* (contain 'ams' in name)
            src_system = datasource_config.get('src_system', '')
            if not src_system:
                table_lower = target_table.lower()
                if 'ams' in table_lower:
                    src_system = 'AMS_STREET'
                elif 'user' in table_lower or 'cis_user' in table_lower:
                    src_system = 'USER_UPLOAD'
                else:
                    src_system = 'USER_UPLOAD'  # Default

            sub_system = datasource_config.get('sub_system', '')
            if not sub_system:
                sub_system = 'user' if src_system == 'USER_UPLOAD' else 'ams'

            # Additional columns map (excluding processing_date as it's a partition column)
            # Use target_table name as src_id for traceability
            additional_cols_map = {
                'src_id': target_table,  # Use table name as source identifier
                'src_system': src_system,
                'sub_system': sub_system,
                'data_cat': datasource_config.get('data_cat', 'sta'),
                'data_frq': datasource_config.get('data_frq', 'adhoc'),
            }

            # position_basis: defaulted at ingest time — not present in uploaded file.
            # Tables 1-3 (trade date based) → TRADE_DATE
            # Tables 4-5 (settled date based) → SETTLE_DATE
            POSITION_TABLE_BASIS = {
                'cis_user_sta_adhoc_position_1': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_2': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_3': 'TRADE_DATE',
                'cis_user_sta_adhoc_position_4': 'SETTLE_DATE',
                'cis_user_sta_adhoc_position_5': 'SETTLE_DATE',
            }
            table_lower = target_table.lower().split('.')[-1]  # strip db prefix if present
            if table_lower in POSITION_TABLE_BASIS and 'position_basis' in [c.lower() for c in target_table_cols]:
                additional_cols_map['position_basis'] = POSITION_TABLE_BASIS[table_lower]
                logger.info(f"Defaulting position_basis='{additional_cols_map['position_basis']}' for {target_table}")

            logger.info(f"Using src_system={src_system}, sub_system={sub_system} for {target_table}")

            # Read data from file or use sample_data
            all_data = sample_data or []
            logger.info(f"[insert_values] temp_file_path={temp_file_path!r} exists={os.path.exists(temp_file_path) if temp_file_path else 'N/A'}")
            logger.info(f"[insert_values] sample_data rows={len(sample_data) if sample_data else 0}")
            logger.info(f"[insert_values] separator={separator!r} has_header={has_header} col_names={col_names}")
            if temp_file_path and os.path.exists(temp_file_path):
                file_size = os.path.getsize(temp_file_path)
                logger.info(f"[insert_values] reading full file {temp_file_path} ({file_size} bytes)")
                try:
                    all_data = []
                    with open(temp_file_path, 'r', encoding='utf-8-sig', errors='replace') as f:
                        delim = separator if separator else ','
                        reader = csv.reader(f, delimiter=delim)
                        rows = list(reader)

                    logger.info(f"[insert_values] raw row count from file={len(rows)} has_header={has_header}")
                    if has_header and len(rows) > 0:
                        logger.info(f"[insert_values] header row={rows[0]}")
                        data_rows = rows[1:]
                    else:
                        data_rows = rows

                    logger.info(f"[insert_values] data_rows to process={len(data_rows)}")
                    # Convert to list of dicts using intake column names
                    for row in data_rows:
                        # Skip blank/whitespace-only rows (common in files with trailing newlines)
                        if not any(str(c).strip() for c in row):
                            continue
                        row_dict = {}
                        for idx, col in enumerate(col_names):
                            if idx < len(row):
                                row_dict[col] = row[idx]
                            else:
                                row_dict[col] = ''
                        all_data.append(row_dict)

                    logger.info(f"[insert_values] parsed {len(all_data)} rows from file")
                except Exception as e:
                    logger.error(f"[insert_values] FAILED to read file {temp_file_path}: {e}", exc_info=True)
                    all_data = sample_data or []
            else:
                logger.warning(f"[insert_values] temp_file_path not usable — using sample_data ({len(all_data)} rows)")

            if not all_data:
                return False, "No data to insert"

            # Deduplicate data before insertion
            original_count = len(all_data)
            all_data, duplicate_count = self._deduplicate_data(all_data, col_names)
            deduplicated_count = len(all_data)

            if duplicate_count > 0:
                logger.warning(f"Removed {duplicate_count} duplicate rows from {original_count} total rows")

            logger.info(f"Ingesting {deduplicated_count} unique rows to {target_table} partition={processing_date} (mode={ingestion_mode})")

            # Get non-partition columns (exclude processing_date)
            non_partition_cols = [col for col in target_table_cols if col.lower() != 'processing_date']

            # Step 1: For overwrite mode, delete the partition first using Impala
            # DROP PARTITION, which is the only safe way to clear a Hive partition
            # without relying on SELECT * column ordering.
            if ingestion_mode != 'append':
                try:
                    drop_sql = (
                        f"ALTER TABLE {self.repository.DATABASE}.{target_table} "
                        f"DROP IF EXISTS PARTITION (processing_date='{processing_date}')"
                    )
                    impala_manager.execute_write(drop_sql, database=self.repository.DATABASE)
                    logger.info(f"Dropped partition processing_date='{processing_date}' for overwrite")
                except Exception as _dp:
                    logger.warning(f"Could not drop partition (may not exist yet): {_dp}")

            # Step 2: One INSERT … SELECT per row.
            # Using a single-row SELECT with named aliases is the only form that
            # works across all Impala versions regardless of column count:
            #   INSERT INTO t PARTITION (p='v') SELECT lit AS col, ...
            # UNION ALL inside an inline view causes "duplicate alias" errors.
            # An explicit column list after PARTITION(…) is a ParseException.
            rows_inserted = 0

            def _sql_str(val) -> str:
                """Escape a value for Impala single-quoted string literals.
                Impala uses C-style escaping: \' for single-quote, not ''."""
                s = str(val)
                s = s.replace('\\', '\\\\')   # backslash first (must be first)
                s = s.replace("'", "\\'")      # single-quote → backslash-quote
                s = s.replace('\n', '\\n')     # newline
                s = s.replace('\r', '\\r')     # carriage return
                s = s.replace('\0', '')        # null byte — strip entirely
                return s

            def _build_row_sql(row):
                col_exprs = []
                for col in non_partition_cols:
                    col_lower = col.lower()
                    if col_lower in additional_cols_map:
                        val = additional_cols_map[col_lower]
                    elif col_lower in [c.lower() for c in col_names]:
                        matching_col = next((c for c in col_names if c.lower() == col_lower), None)
                        val = row.get(matching_col, '') if matching_col else ''
                    else:
                        val = ''
                    if col_lower in self.DATE_COLUMNS and val:
                        val = self.normalise_date(str(val))
                    if val is None or str(val).strip() == '':
                        lit = "''"
                    else:
                        lit = f"'{_sql_str(val)}'"
                    col_exprs.append(f"{lit} AS `{col}`")
                return (
                    f"INSERT INTO {self.repository.DATABASE}.{target_table} "
                    f"PARTITION (processing_date='{processing_date}') "
                    f"SELECT {', '.join(col_exprs)}"
                )

            rows_failed = 0
            for row_num, row in enumerate(all_data):
                insert_sql = _build_row_sql(row)
                success = impala_manager.execute_write(insert_sql, database=self.repository.DATABASE)
                if success:
                    rows_inserted += 1
                    if rows_inserted % 50 == 0:
                        logger.info(f"Inserted {rows_inserted}/{len(all_data)} rows into {target_table}")
                else:
                    rows_failed += 1
                    logger.error(f"[insert_values] row {row_num} failed — skipping. SQL was: {insert_sql[:300]}")
                    if rows_failed > 10:
                        return False, f"Too many row failures ({rows_failed}) — aborting at row {row_num}"

            if rows_inserted == 0:
                return False, f"No rows were inserted (all {rows_failed} rows failed)"

            # Step 3: Refresh metadata
            try:
                impala_manager.execute_write(
                    f"INVALIDATE METADATA {self.repository.DATABASE}.{target_table}",
                    database=self.repository.DATABASE
                )
                logger.info(f"Refreshed metadata for {target_table}")
            except Exception as e:
                logger.warning(f"Could not refresh metadata: {e}")

            # Success - update status
            if not is_session_upload:
                # Include duplicate info and mode in description for recon reference
                mode_label = 'APPEND' if ingestion_mode == 'append' else 'OVERWRITE'
                update_data = {
                    'status': UploadKuduRepository.STATUS_COMPLETED,
                    'target_table_name': target_table,
                    'row_count': rows_inserted,
                }
                desc_parts = [f"processing_date={processing_date}", f"mode={mode_label}"]
                if duplicate_count > 0:
                    desc_parts.append(f"{duplicate_count} duplicates removed")
                update_data['description'] = "; ".join(desc_parts)
                self.repository.update_upload(upload_id, update_data, updated_by)

            # Build success message
            mode_label = 'appended' if ingestion_mode == 'append' else 'ingested'
            success_msg = f"Successfully {mode_label} {rows_inserted} rows to {target_table} with processing_date={processing_date}"
            if duplicate_count > 0:
                success_msg += f" ({duplicate_count} duplicate rows removed from source)"

            return True, success_msg

        except Exception as e:
            logger.error(f"Ingestion error: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False, f"Ingestion error: {str(e)}"

    def _deduplicate_data(
        self,
        data: List[Dict[str, Any]],
        key_columns: List[str]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Remove duplicate rows from data.

        Duplicates are identified by comparing all values in key_columns.
        Only the first occurrence of each unique row is kept.

        Args:
            data: List of row dictionaries
            key_columns: List of column names to use for duplicate detection

        Returns:
            Tuple of (deduplicated_data, duplicate_count)
        """
        if not data:
            return data, 0

        seen = set()
        unique_data = []
        duplicate_count = 0

        for row in data:
            # Create a tuple of values for comparison
            # Use all key columns to identify duplicates
            key_values = tuple(str(row.get(col, '')).strip() for col in key_columns)

            if key_values not in seen:
                seen.add(key_values)
                unique_data.append(row)
            else:
                duplicate_count += 1
                logger.debug(f"Duplicate row found: {key_values[:3]}...")  # Log first 3 values

        if duplicate_count > 0:
            logger.info(f"Deduplication: {len(data)} -> {len(unique_data)} rows ({duplicate_count} duplicates removed)")

        return unique_data, duplicate_count

    def get_all_datasource_configs(self) -> List[Dict[str, Any]]:
        """Get all datasource configurations for dropdown."""
        return datasource_repository.get_all_datasources()

    # =========================================================================
    # POSITION UPLOAD ETL — Run transform pipeline & report download
    # =========================================================================

    # Position source tables that trigger the AVP transform pipeline
    POSITION_TARGET_TABLES = {
        'cis_user_sta_adhoc_position_1',
        'cis_user_sta_adhoc_position_2',
        'cis_user_sta_adhoc_position_3',
        'cis_user_sta_adhoc_position_4',
        'cis_user_sta_adhoc_position_5',
    }

    def is_position_upload(self, upload: Dict[str, Any]) -> bool:
        """Return True if this upload's target table is one of the 5 position sources."""
        target = (upload.get('target_table_name') or '').lower().split('.')[-1]
        return target in self.POSITION_TARGET_TABLES

    def run_position_etl(
        self,
        upload_id: str,
        src_id: str,
        processing_date: str,
        updated_by: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Execute the position upload transform pipeline for a given partition.

        Runs the Hive/Impala equivalent of position_upload_transform_optimized.sql:
          Step 1 — build pos_stage_1_base from position_upload_standardized
          Step 2 — portfolio validation
          Step 3 — security ISIN match
          Step 4 — security fallback match
          Step 5 — price lookup
          Step 6 — consolidated staging
          Step 7A — upsert into cis_position
          Step 7B — write position_upload_report

        Args:
            upload_id: Upload record ID (for status tracking)
            src_id:    Source partition value (e.g. 'cis_user_sta_adhoc_position_1')
            processing_date: YYYYMMDD partition value
            updated_by: Username triggering the ETL

        Returns:
            Tuple of (success, message, result_dict)
        """
        from core.repositories.impala_connection import impala_manager
        from core.notifications import notify_user, notify_admins
        from core.notifications.constants import (
            EVT_UPLOAD_STARTED, EVT_UPLOAD_STEP,
            EVT_UPLOAD_COMPLETED, EVT_UPLOAD_FAILED,
        )

        result = {'src_id': src_id, 'processing_date': processing_date}

        _notif_base = {
            'upload_id':       upload_id,
            'src_id':          src_id,
            'processing_date': processing_date,
        }

        try:
            logger.info(
                f"[position_etl] Starting ETL for src_id={src_id} "
                f"processing_date={processing_date} by {updated_by}"
            )
            notify_user(updated_by, EVT_UPLOAD_STARTED, {
                **_notif_base,
                'message': f'Position ETL started for {src_id} ({processing_date})',
            })

            db = 'gmp_cis'

            # ------------------------------------------------------------------
            # safe_decimal(col, dec_type): generates SQL that handles every
            # real-world dirty numeric format before CAST to DECIMAL:
            #   1. CAST source col to STRING (handles numeric source types)
            #   2. TRIM whitespace
            #   3. Strip commas (1,234.56 → 1234.56)
            #   4. Strip currency symbols and percent signs ($, £, %, etc.)
            #   5. Convert parentheses-negatives: (123.45) → -123.45
            #   6. Convert lone dash/en-dash meaning zero → '0'
            #   7. regexp_extract to pull only the leading -?digits.digits part
            #   8. NULLIF empty string → NULL
            #   9. Final CAST to target DECIMAL type
            # Any value that still can't parse becomes NULL (never throws UDF error).
            # ------------------------------------------------------------------
            def safe_decimal(col: str, dec_type: str) -> str:
                return (
                    f"CAST(NULLIF(regexp_extract("
                    f"regexp_replace("
                    f"regexp_replace("
                    f"regexp_replace("
                    f"regexp_replace("
                    f"TRIM(CAST({col} AS STRING)),"
                    f" ',', ''),"           # strip thousands separator
                    f" '[\\\\$£€¥%]', '')," # strip currency/percent symbols
                    f" '^\\\\(([0-9]+\\\\.?[0-9]*)\\\\)$', '-\\\\1')," # (123.45) → -123.45
                    f" '^[-–—]+$', '0'),"   # lone dash/en-dash → 0
                    f" '^-?[0-9]+(\\\\.?[0-9]*)?([eE][+-]?[0-9]+)?', 0),"
                    f" '') AS {dec_type})"
                )

            # ------------------------------------------------------------------
            # Step 0: Standardize — map raw source table columns into
            #         position_upload_standardized (equivalent of Position_insert.sql).
            #         This INSERT is partitioned by (src_id, processing_date).
            #         Each source table has a different column layout — we map
            #         them here to the common schema.
            # ------------------------------------------------------------------
            # Step 0 writes raw STRING values to position_upload_standardized (all columns are STRING).
            # Numeric CASTs are applied in Step 1 when building pos_stage_1_base (internal PARQUET).
            # exchange_code is the DDL column name; it is aliased to `exchange` in Step 1 for
            # use as a reserved-word-safe name throughout the internal pipeline.

            STANDARDIZE_SELECT = {
                # ------------------------------------------------------------------
                # position_1: pipe-separated file with 9 columns
                #   REPORTING_DATE|Portfolio|Client_Num|Exchange_Quoted|ISIN_Code|
                #   Counter|Quantity_Yesterday|Movement|Quantity_Today
                # column mapping per Position_insert.sql:
                #   counter → security_full_name
                #   isin_code → isin
                #   exchange_quoted → exchange_code
                #   quantity_today → quantity  (stored as STRING in standardized table)
                # ------------------------------------------------------------------
                # position_1: pipe-separated, 9 cols
                # REPORTING_DATE|Portfolio|Client_Num|Exchange_Quoted|ISIN_Code|Counter|Quantity_Yesterday|Movement|Quantity_Today
                'cis_user_sta_adhoc_position_1': f"""
                    SELECT
                        portfolio                                       AS portfolio,
                        counter                                         AS security_full_name,
                        NULL                                            AS security_short_name,
                        isin_code                                       AS isin,
                        NULL                                            AS ticker,
                        {safe_decimal('quantity_today', 'DECIMAL(18,4)')} AS quantity,
                        CAST(NULL AS DECIMAL(18,4))                     AS shares_outstanding,
                        CAST(NULL AS DECIMAL(18,4))                     AS shares_issued,
                        CAST(NULL AS DECIMAL(10,6))                     AS pct_holding,
                        CAST(NULL AS DECIMAL(18,6))                     AS market_price,
                        CAST(NULL AS DECIMAL(18,6))                     AS average_cost,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_lc,
                        NULL                                            AS product_type,
                        NULL                                            AS security_type,
                        NULL                                            AS quoted_unquoted,
                        NULL                                            AS industry,
                        NULL                                            AS fin_nonfin_co,
                        NULL                                            AS issuer_type,
                        NULL                                            AS reits_or_fund_y_n,
                        exchange_quoted                                 AS exchange,
                        NULL                                            AS country_code,
                        NULL                                            AS country_of_exchange,
                        NULL                                            AS country_of_incorporation,
                        NULL                                            AS country_of_risk,
                        NULL                                            AS country_of_operation,
                        NULL                                            AS security_currency,
                        NULL                                            AS corp_code,
                        NULL                                            AS branch_code,
                        NULL                                            AS cost_centre,
                        NULL                                            AS cels,
                        NULL                                            AS bwcif_sg,
                        NULL                                            AS bwcif_ovs,
                        NULL                                            AS mas_6d_code_sg,
                        NULL                                            AS mas_6d_code_ovs,
                        'TRADE_DATE'                                    AS position_basis,
                        reporting_date                                  AS reporting_date,
                        NULL                                            AS maturity_date,
                        'USER_UPLOAD'                                   AS src_system,
                        'user'                                          AS sub_system,
                        'sta'                                           AS data_cat,
                        'adhoc'                                         AS data_frq,
                        'cis_user_sta_adhoc_position_1'                 AS source_table,
                        CURRENT_TIMESTAMP()                             AS etl_insert_ts,
                        'python_etl'                                    AS etl_batch_id
                    FROM {db}.cis_user_sta_adhoc_position_1
                    WHERE processing_date = '{processing_date}'
                      AND src_id = '{src_id}'
                """,
                # position_2: portfolio_name, security_description, stock_name, isin_code, qty_held, shares_issued, pct_holding, country_id
                'cis_user_sta_adhoc_position_2': f"""
                    SELECT
                        portfolio_name                                  AS portfolio,
                        security_description                            AS security_full_name,
                        stock_name                                      AS security_short_name,
                        isin_code                                       AS isin,
                        NULL                                            AS ticker,
                        {safe_decimal('qty_held', 'DECIMAL(18,4)')} AS quantity,
                        {safe_decimal('shares_issued', 'DECIMAL(18,4)')} AS shares_outstanding,
                        CAST(NULL AS DECIMAL(18,4))                     AS shares_issued,
                        {safe_decimal('pct_holding', 'DECIMAL(10,6)')} AS pct_holding,
                        CAST(NULL AS DECIMAL(18,6))                     AS market_price,
                        CAST(NULL AS DECIMAL(18,6))                     AS average_cost,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_lc,
                        NULL                                            AS product_type,
                        NULL                                            AS security_type,
                        NULL                                            AS quoted_unquoted,
                        NULL                                            AS industry,
                        NULL                                            AS fin_nonfin_co,
                        NULL                                            AS issuer_type,
                        NULL                                            AS reits_or_fund_y_n,
                        country_id                                      AS exchange,
                        country_id                                      AS country_code,
                        country_id                                      AS country_of_exchange,
                        country_id                                      AS country_of_incorporation,
                        NULL                                            AS country_of_risk,
                        NULL                                            AS country_of_operation,
                        NULL                                            AS security_currency,
                        NULL                                            AS corp_code,
                        NULL                                            AS branch_code,
                        NULL                                            AS cost_centre,
                        NULL                                            AS cels,
                        NULL                                            AS bwcif_sg,
                        NULL                                            AS bwcif_ovs,
                        NULL                                            AS mas_6d_code_sg,
                        NULL                                            AS mas_6d_code_ovs,
                        'TRADE_DATE'                                    AS position_basis,
                        reporting_date                                  AS reporting_date,
                        NULL                                            AS maturity_date,
                        'USER_UPLOAD'                                   AS src_system,
                        'user'                                          AS sub_system,
                        'sta'                                           AS data_cat,
                        'adhoc'                                         AS data_frq,
                        'cis_user_sta_adhoc_position_2'                 AS source_table,
                        CURRENT_TIMESTAMP()                             AS etl_insert_ts,
                        'python_etl'                                    AS etl_batch_id
                    FROM {db}.cis_user_sta_adhoc_position_2
                    WHERE processing_date = '{processing_date}'
                      AND src_id = '{src_id}'
                """,
                # position_3: account_name, asset_description_short, isin, shares_par_value, shares_outstanding_total, country_of_listing_code, reporting_date, position_basis
                'cis_user_sta_adhoc_position_3': f"""
                    SELECT
                        account_name                                    AS portfolio,
                        asset_description_short                         AS security_full_name,
                        NULL                                            AS security_short_name,
                        isin                                            AS isin,
                        NULL                                            AS ticker,
                        {safe_decimal('shares_par_value', 'DECIMAL(18,4)')} AS quantity,
                        {safe_decimal('shares_outstanding_total', 'DECIMAL(18,4)')} AS shares_outstanding,
                        CAST(NULL AS DECIMAL(18,4))                     AS shares_issued,
                        CAST(NULL AS DECIMAL(10,6))                     AS pct_holding,
                        CAST(NULL AS DECIMAL(18,6))                     AS market_price,
                        CAST(NULL AS DECIMAL(18,6))                     AS average_cost,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_fc,
                        CAST(NULL AS DECIMAL(18,4))                     AS cost_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS market_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS net_book_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS unrealized_pnl_lc,
                        CAST(NULL AS DECIMAL(18,4))                     AS provision_lc,
                        NULL                                            AS product_type,
                        NULL                                            AS security_type,
                        NULL                                            AS quoted_unquoted,
                        NULL                                            AS industry,
                        NULL                                            AS fin_nonfin_co,
                        NULL                                            AS issuer_type,
                        NULL                                            AS reits_or_fund_y_n,
                        country_of_listing_code                         AS exchange,
                        NULL                                            AS country_code,
                        country_of_listing_code                         AS country_of_exchange,
                        NULL                                            AS country_of_incorporation,
                        NULL                                            AS country_of_risk,
                        NULL                                            AS country_of_operation,
                        NULL                                            AS security_currency,
                        NULL                                            AS corp_code,
                        NULL                                            AS branch_code,
                        NULL                                            AS cost_centre,
                        NULL                                            AS cels,
                        NULL                                            AS bwcif_sg,
                        NULL                                            AS bwcif_ovs,
                        NULL                                            AS mas_6d_code_sg,
                        NULL                                            AS mas_6d_code_ovs,
                        'TRADE_DATE'                                    AS position_basis,
                        reporting_date                                  AS reporting_date,
                        NULL                                            AS maturity_date,
                        'USER_UPLOAD'                                   AS src_system,
                        'user'                                          AS sub_system,
                        'sta'                                           AS data_cat,
                        'adhoc'                                         AS data_frq,
                        'cis_user_sta_adhoc_position_3'                 AS source_table,
                        CURRENT_TIMESTAMP()                             AS etl_insert_ts,
                        'python_etl'                                    AS etl_batch_id
                    FROM {db}.cis_user_sta_adhoc_position_3
                    WHERE processing_date = '{processing_date}'
                      AND src_id = '{src_id}'
                """,
                # position_4: portfolio, security_full_name, product_type, security_type, gl_fund_type,
                #   quoted_unquoted, security_currency, quantity, cost_fc, net_book_value_fc,
                #   net_book_value_lc, local_currency_home_ccy, cost_lc, pct_holdings,
                #   no_of_shares_issues_by_the_company, country_of_incorporation, country_of_exchange,
                #   isin_code, ticker_code, industry, financial_non_financial_co, position_basis
                'cis_user_sta_adhoc_position_4': f"""
                    SELECT
                        portfolio                                           AS portfolio,
                        security_full_name                                  AS security_full_name,
                        NULL                                                AS security_short_name,
                        isin_code                                           AS isin,
                        ticker_code                                         AS ticker,
                        {safe_decimal('quantity', 'DECIMAL(18,4)')} AS quantity,
                        {safe_decimal('no_of_shares_issues_by_the_company', 'DECIMAL(18,4)')} AS shares_outstanding,
                        {safe_decimal('no_of_shares_issues_by_the_company', 'DECIMAL(18,4)')} AS shares_issued,
                        {safe_decimal('pct_holdings', 'DECIMAL(10,6)')} AS pct_holding,
                        CAST(NULL AS DECIMAL(18,6))                         AS market_price,
                        CAST(NULL AS DECIMAL(18,6))                         AS average_cost,
                        {safe_decimal('cost_fc', 'DECIMAL(18,4)')} AS cost_fc,
                        CAST(NULL AS DECIMAL(18,4))                         AS market_value_fc,
                        {safe_decimal('net_book_value_fc', 'DECIMAL(18,4)')} AS net_book_value_fc,
                        CAST(NULL AS DECIMAL(18,4))                         AS unrealized_pnl_fc,
                        CAST(NULL AS DECIMAL(18,4))                         AS provision_fc,
                        {safe_decimal('cost_lc', 'DECIMAL(18,4)')} AS cost_lc,
                        CAST(NULL AS DECIMAL(18,4))                         AS market_value_lc,
                        {safe_decimal('net_book_value_lc', 'DECIMAL(18,4)')} AS net_book_value_lc,
                        CAST(NULL AS DECIMAL(18,4))                         AS unrealized_pnl_lc,
                        CAST(NULL AS DECIMAL(18,4))                         AS provision_lc,
                        product_type                                        AS product_type,
                        security_type                                       AS security_type,
                        quoted_unquoted                                     AS quoted_unquoted,
                        industry                                            AS industry,
                        financial_non_financial_co                          AS fin_nonfin_co,
                        NULL                                                AS issuer_type,
                        NULL                                                AS reits_or_fund_y_n,
                        country_of_exchange                                 AS exchange,
                        NULL                                                AS country_code,
                        country_of_exchange                                 AS country_of_exchange,
                        country_of_incorporation                            AS country_of_incorporation,
                        NULL                                                AS country_of_risk,
                        NULL                                                AS country_of_operation,
                        security_currency                                   AS security_currency,
                        NULL                                                AS corp_code,
                        NULL                                                AS branch_code,
                        NULL                                                AS cost_centre,
                        NULL                                                AS cels,
                        NULL                                                AS bwcif_sg,
                        NULL                                                AS bwcif_ovs,
                        NULL                                                AS mas_6d_code_sg,
                        NULL                                                AS mas_6d_code_ovs,
                        'SETTLE_DATE'                                       AS position_basis,
                        reporting_date                                      AS reporting_date,
                        NULL                                                AS maturity_date,
                        'USER_UPLOAD'                                       AS src_system,
                        'user'                                              AS sub_system,
                        'sta'                                               AS data_cat,
                        'adhoc'                                             AS data_frq,
                        'cis_user_sta_adhoc_position_4'                     AS source_table,
                        CURRENT_TIMESTAMP()                                 AS etl_insert_ts,
                        'python_etl'                                        AS etl_batch_id
                    FROM {db}.cis_user_sta_adhoc_position_4
                    WHERE processing_date = '{processing_date}'
                      AND src_id = '{src_id}'
                """,
                # position_5: full schema with all numeric and MAS codes
                'cis_user_sta_adhoc_position_5': f"""
                    SELECT
                        portfolio                                       AS portfolio,
                        security_full_name                              AS security_full_name,
                        NULL                                            AS security_short_name,
                        isin_code                                       AS isin,
                        ticker_code                                     AS ticker,
                        {safe_decimal('quantity', 'DECIMAL(18,4)')} AS quantity,
                        {safe_decimal('no_of_shares_issues_by_the_company', 'DECIMAL(18,4)')} AS shares_outstanding,
                        {safe_decimal('no_of_shares_issues_by_the_company', 'DECIMAL(18,4)')} AS shares_issued,
                        {safe_decimal('pct_holdings', 'DECIMAL(10,6)')} AS pct_holding,
                        {safe_decimal('market_price_unit_fc', 'DECIMAL(18,6)')} AS market_price,
                        {safe_decimal('unit_avg_cost_unit_fc', 'DECIMAL(18,6)')} AS average_cost,
                        {safe_decimal('cost_fc', 'DECIMAL(18,4)')} AS cost_fc,
                        {safe_decimal('market_value_fc', 'DECIMAL(18,4)')} AS market_value_fc,
                        {safe_decimal('net_book_value_fc', 'DECIMAL(18,4)')} AS net_book_value_fc,
                        {safe_decimal('unrealised_gain_loss_fc', 'DECIMAL(18,4)')} AS unrealized_pnl_fc,
                        {safe_decimal('provision_fc', 'DECIMAL(18,4)')} AS provision_fc,
                        {safe_decimal('cost_lc', 'DECIMAL(18,4)')} AS cost_lc,
                        {safe_decimal('market_value_lc', 'DECIMAL(18,4)')} AS market_value_lc,
                        {safe_decimal('net_book_value_lc', 'DECIMAL(18,4)')} AS net_book_value_lc,
                        {safe_decimal('unrealised_gain_loss_lc', 'DECIMAL(18,4)')} AS unrealized_pnl_lc,
                        {safe_decimal('provision_lc', 'DECIMAL(18,4)')} AS provision_lc,
                        product_type, security_type, quoted_unquoted, industry,
                        NULL                                            AS fin_nonfin_co,
                        issuer_type, reits_or_fund_y_n,
                        country_of_exchange                             AS exchange,
                        NULL                                            AS country_code,
                        country_of_exchange, country_of_incorporation,
                        country_of_risk, country_of_operation,
                        security_currency_fc                            AS security_currency,
                        corp_code, branch_code, cost_centre,
                        cels_code                                       AS cels,
                        bwcif_number_sg                                 AS bwcif_sg,
                        bwcif_number_overseas                           AS bwcif_ovs,
                        mas_6d_code_sg,
                        mas_6d_code_overseas                            AS mas_6d_code_ovs,
                        'SETTLE_DATE'                                   AS position_basis,
                        reporting_date, maturity_date,
                        'USER_UPLOAD'                                   AS src_system,
                        'user'                                          AS sub_system,
                        'sta'                                           AS data_cat,
                        'adhoc'                                         AS data_frq,
                        'cis_user_sta_adhoc_position_5'                 AS source_table,
                        CURRENT_TIMESTAMP()                             AS etl_insert_ts,
                        'python_etl'                                    AS etl_batch_id
                    FROM {db}.cis_user_sta_adhoc_position_5
                    WHERE processing_date = '{processing_date}'
                      AND src_id = '{src_id}'
                """,
            }

            std_select = STANDARDIZE_SELECT.get(src_id)
            if not std_select:
                return False, f"Unknown src_id '{src_id}' — no standardization mapping defined", result

            # Write this partition into position_upload_standardized (STRING columns, no casts).
            ok = impala_manager.execute_write(
                f"""
                INSERT OVERWRITE {db}.position_upload_standardized
                PARTITION (processing_date='{processing_date}', src_id='{src_id}')
                {std_select}
                """,
                database=db
            )
            if not ok:
                return False, f"Step 0 INSERT into position_upload_standardized failed — check Impala logs", result
            impala_manager.execute_write(
                f"INVALIDATE METADATA {db}.position_upload_standardized",
                database=db
            )

            # Verify rows landed
            std_count = impala_manager.execute_query(
                f"""
                SELECT COUNT(*) AS cnt
                FROM {db}.position_upload_standardized
                WHERE src_id = '{src_id}'
                  AND processing_date = '{processing_date}'
                """,
                database=db
            )
            std_rows = (std_count[0].get('cnt', 0) if std_count else 0)
            logger.info(f"[position_etl] Step 0 complete — {std_rows} rows standardized into position_upload_standardized")
            if std_rows == 0:
                return False, f"Standardization produced 0 rows — check src_id='{src_id}' processing_date='{processing_date}' in {src_id} table", result

            # ------------------------------------------------------------------
            # Step 1: Base staging table — read from position_upload_standardized
            #         (all STRING), apply DECIMAL casts, rename exchange_code →
            #         `exchange` for use as internal name throughout the pipeline.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_1_base", database=db
            )
            ok = impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_1_base
                STORED AS PARQUET AS
                SELECT
                    ROW_NUMBER() OVER (ORDER BY portfolio, security_full_name) AS row_id,
                    portfolio,
                    security_full_name,
                    security_short_name,
                    isin                                        AS isin,
                    ticker,
                    COALESCE(quantity,            CAST(0 AS DECIMAL(18,4))) AS quantity,
                    COALESCE(shares_outstanding,  CAST(0 AS DECIMAL(18,4))) AS shares_outstanding,
                    COALESCE(shares_issued,       CAST(0 AS DECIMAL(18,4))) AS shares_issued,
                    COALESCE(pct_holding,         CAST(0 AS DECIMAL(10,6))) AS pct_holding,
                    market_price,
                    average_cost,
                    COALESCE(cost_fc,             CAST(0 AS DECIMAL(18,4))) AS cost_fc,
                    COALESCE(market_value_fc,     CAST(0 AS DECIMAL(18,4))) AS market_value_fc,
                    COALESCE(net_book_value_fc,   CAST(0 AS DECIMAL(18,4))) AS net_book_value_fc,
                    COALESCE(unrealized_pnl_fc,   CAST(0 AS DECIMAL(18,4))) AS unrealized_pnl_fc,
                    COALESCE(cost_lc,             CAST(0 AS DECIMAL(18,4))) AS cost_lc,
                    COALESCE(market_value_lc,     CAST(0 AS DECIMAL(18,4))) AS market_value_lc,
                    COALESCE(net_book_value_lc,   CAST(0 AS DECIMAL(18,4))) AS net_book_value_lc,
                    COALESCE(unrealized_pnl_lc,   CAST(0 AS DECIMAL(18,4))) AS unrealized_pnl_lc,
                    COALESCE(provision_lc,        CAST(0 AS DECIMAL(18,4))) AS provision_lc,
                    COALESCE(provision_fc,        CAST(0 AS DECIMAL(18,4))) AS provision_fc,
                    product_type,
                    security_type,
                    quoted_unquoted,
                    industry,
                    fin_nonfin_co,
                    issuer_type,
                    reits_or_fund_y_n,
                    `exchange`                                  AS `exchange`,
                    country_code,
                    country_of_exchange,
                    country_of_incorporation,
                    country_of_risk,
                    country_of_operation,
                    security_currency,
                    corp_code,
                    branch_code,
                    cost_centre,
                    cels,
                    bwcif_sg,
                    bwcif_ovs,
                    mas_6d_code_sg,
                    mas_6d_code_ovs,
                    position_basis,
                    from_timestamp(
                        CASE
                            WHEN reporting_date LIKE '%/%/%' AND length(reporting_date) = 10 THEN
                                CAST(unix_timestamp(reporting_date, 'dd/MM/yyyy') AS TIMESTAMP)
                            WHEN reporting_date LIKE '__-__-____' THEN
                                CAST(unix_timestamp(reporting_date, 'dd-MM-yyyy') AS TIMESTAMP)
                            WHEN reporting_date LIKE '____-__-__' AND length(reporting_date) = 10 THEN
                                CAST(unix_timestamp(reporting_date, 'yyyy-MM-dd') AS TIMESTAMP)
                            WHEN length(reporting_date) = 8 THEN
                                CAST(unix_timestamp(reporting_date, 'yyyyMMdd') AS TIMESTAMP)
                            WHEN reporting_date LIKE '%-%-% %:%:%' THEN
                                CAST(regexp_replace(reporting_date, ' .*', '') AS TIMESTAMP)
                            ELSE
                                CAST(reporting_date AS TIMESTAMP)
                        END,
                        'yyyy-MM-dd'
                    ) AS reporting_date,
                    maturity_date,
                    src_system,
                    sub_system,
                    data_cat,
                    data_frq,
                    source_table,
                    etl_insert_ts,
                    etl_batch_id,
                    src_id,
                    processing_date
                FROM {db}.position_upload_standardized
                WHERE src_id = '{src_id}'
                  AND processing_date = '{processing_date}'
                """,
                database=db
            )
            if not ok:
                return False, "Step 1 CREATE TABLE pos_stage_1_base failed — check Impala logs (likely column mismatch in position_upload_standardized)", result
            logger.info("[position_etl] Step 1 complete")

            # ------------------------------------------------------------------
            # Step 2: Portfolio validation — join on pf.name (exact match)
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_2_portfolio", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_2_portfolio
                STORED AS PARQUET AS
                SELECT
                    b.row_id,
                    b.portfolio,
                    pf.name AS valid_portfolio,
                    pf.currency AS portfolio_currency,
                    CASE
                        WHEN pf.name IS NOT NULL THEN 'PASS'
                        ELSE 'FAIL: Portfolio not found in cis_portfolio'
                    END AS portfolio_status
                FROM pos_stage_1_base b
                LEFT JOIN {db}.cis_portfolio pf ON b.portfolio = pf.name
                """,
                database=db
            )
            logger.info("[position_etl] Step 2 complete")

            # ------------------------------------------------------------------
            # Step 3: Security validation — duplicate ISIN detection + ISIN match.
            #         Only for records that passed portfolio validation (INNER JOIN).
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_3_duplicate_isins", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_3_duplicate_isins
                STORED AS PARQUET AS
                SELECT isin, COUNT(*) AS isin_count
                FROM {db}.cis_security
                WHERE is_active = true
                  AND isin IS NOT NULL
                  AND TRIM(isin) != ''
                GROUP BY isin
                HAVING COUNT(*) > 1
                """,
                database=db
            )

            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_3_security", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_3_security
                STORED AS PARQUET AS
                SELECT
                    b.row_id,
                    b.isin AS upload_isin,
                    b.security_full_name,
                    b.security_short_name,
                    b.`exchange` AS upload_exchange,
                    p2.portfolio_status,
                    dup.isin_count AS duplicate_isin_count,
                    CASE WHEN dup.isin IS NULL THEN s.security_id  ELSE NULL END AS matched_security_id,
                    CASE WHEN dup.isin IS NULL THEN s.security_name ELSE NULL END AS matched_security_name,
                    CASE WHEN dup.isin IS NULL THEN s.isin          ELSE NULL END AS matched_isin,
                    CASE WHEN dup.isin IS NULL THEN s.exchange_code ELSE NULL END AS matched_exchange,
                    CASE WHEN dup.isin IS NULL THEN s.country_of_exchange ELSE NULL END AS matched_country,
                    CASE WHEN dup.isin IS NULL THEN s.currency_code ELSE NULL END AS matched_currency,
                    CASE
                        WHEN dup.isin IS NOT NULL              THEN 'FAIL: Multiple ISINs found in master'
                        WHEN s.security_id IS NOT NULL         THEN 'ISIN_MATCH'
                        WHEN b.isin IS NULL OR TRIM(b.isin) = '' THEN 'NO_ISIN'
                        ELSE 'ISIN_NO_MATCH'
                    END AS match_type
                FROM pos_stage_1_base b
                JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
                LEFT JOIN pos_stage_3_duplicate_isins dup ON b.isin = dup.isin
                LEFT JOIN {db}.cis_security s
                    ON b.isin = s.isin
                    AND s.is_active = true
                    AND b.isin IS NOT NULL
                    AND TRIM(b.isin) != ''
                WHERE p2.portfolio_status = 'PASS'
                """,
                database=db
            )
            logger.info("[position_etl] Step 3 complete")

            # ------------------------------------------------------------------
            # Step 4: Security fallback — full_name (security_description),
            #         then short_name, then 'NOT_FOUND: Create new security'.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_4_security_fallback", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_4_security_fallback
                STORED AS PARQUET AS
                SELECT
                    s3.row_id,
                    s3.upload_isin,
                    s3.security_full_name,
                    s3.security_short_name,
                    s3.upload_exchange,
                    s3.portfolio_status,
                    s3.match_type AS isin_match_type,
                    COALESCE(s3.matched_security_id, s_desc.security_id, s_name.security_id, s_ticker.security_id) AS final_security_id,
                    COALESCE(s3.matched_security_name, s_desc.security_name, s_name.security_name, s_ticker.security_name) AS final_security_name,
                    COALESCE(s3.matched_isin,     s_desc.isin,          s_name.isin,          s_ticker.isin)          AS final_isin,
                    COALESCE(s3.matched_exchange,  s_desc.exchange_code, s_name.exchange_code, s_ticker.exchange_code) AS final_exchange,
                    COALESCE(s3.matched_country,   s_desc.country_of_exchange, s_name.country_of_exchange, s_ticker.country_of_exchange) AS final_country,
                    COALESCE(s3.matched_currency,  s_desc.currency_code, s_name.currency_code, s_ticker.currency_code) AS final_currency,
                    CASE
                        WHEN s3.matched_security_id IS NOT NULL THEN 'ISIN_MATCH'
                        WHEN s_desc.security_id IS NOT NULL     THEN 'FULLNAME_MATCH'
                        WHEN s_name.security_id IS NOT NULL     THEN 'SHORTNAME_MATCH'
                        WHEN s_ticker.security_id IS NOT NULL   THEN 'TICKER_MATCH'
                        ELSE NULL
                    END AS match_method,
                    CASE
                        WHEN s3.match_type = 'FAIL: Multiple ISINs found in master'
                            THEN 'FAIL: Multiple ISINs found'
                        WHEN s3.matched_security_id IS NOT NULL THEN 'ISIN_MATCH'
                        WHEN s_desc.security_id IS NOT NULL     THEN 'FULLNAME_MATCH'
                        WHEN s_name.security_id IS NOT NULL     THEN 'SHORTNAME_MATCH'
                        WHEN s_ticker.security_id IS NOT NULL   THEN 'TICKER_MATCH'
                        WHEN (s3.upload_isin IS NULL OR TRIM(s3.upload_isin) = '')
                             AND (s3.security_full_name IS NULL OR TRIM(s3.security_full_name) = '')
                             AND (s3.security_short_name IS NULL OR TRIM(s3.security_short_name) = '')
                            THEN 'FAIL: No identifier (isin, security_full_name, security_short_name all null)'
                        ELSE 'NOT_FOUND: Create new security'
                    END AS security_status
                FROM pos_stage_3_security s3
                JOIN pos_stage_1_base b ON s3.row_id = b.row_id
                LEFT JOIN {db}.cis_security s_desc
                    ON s3.security_full_name = s_desc.security_description
                    AND s_desc.is_active = true
                    AND s3.matched_security_id IS NULL
                    AND s3.match_type != 'FAIL: Multiple ISINs found in master'
                    AND s3.security_full_name IS NOT NULL
                    AND TRIM(s3.security_full_name) != ''
                LEFT JOIN {db}.cis_security s_name
                    ON s3.security_short_name = s_name.security_name
                    AND s_name.is_active = true
                    AND s3.matched_security_id IS NULL
                    AND s_desc.security_id IS NULL
                    AND s3.match_type != 'FAIL: Multiple ISINs found in master'
                    AND s3.security_short_name IS NOT NULL
                    AND TRIM(s3.security_short_name) != ''
                LEFT JOIN {db}.cis_security s_ticker
                    ON UPPER(TRIM(b.ticker)) = UPPER(TRIM(s_ticker.ticker))
                    AND s_ticker.is_active = true
                    AND s3.matched_security_id IS NULL
                    AND s_desc.security_id IS NULL
                    AND s_name.security_id IS NULL
                    AND s3.match_type != 'FAIL: Multiple ISINs found in master'
                    AND b.ticker IS NOT NULL
                    AND TRIM(b.ticker) != ''
                """,
                database=db
            )
            logger.info("[position_etl] Step 4 complete")

            # ------------------------------------------------------------------
            # Step 5: Price lookup — latest price per ISIN from cis_equity_price.
            #         Skip records with FAIL security status.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS pos_stage_5_price", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE pos_stage_5_price
                STORED AS PARQUET AS
                SELECT
                    b.row_id,
                    b.isin,
                    b.reporting_date,
                    b.market_price AS upload_market_price,
                    ep.main_closing_price,
                    CASE
                        WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0
                            THEN ep.main_closing_price
                        WHEN b.market_price IS NOT NULL AND b.market_price != 0
                            THEN b.market_price
                        ELSE NULL
                    END AS final_market_price,
                    CASE
                        WHEN ep.main_closing_price IS NOT NULL AND ep.main_closing_price != 0
                            THEN 'PASS: Using cis_equity_price'
                        WHEN b.market_price IS NOT NULL AND b.market_price != 0
                            THEN 'PASS: Using uploaded'
                        WHEN ep.main_closing_price = 0 OR b.market_price = 0
                            THEN 'WARN: Price is zero (omitted)'
                        ELSE 'WARN: No price'
                    END AS price_status
                FROM pos_stage_1_base b
                JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
                LEFT JOIN (
                    SELECT isin, price_date, main_closing_price,
                           ROW_NUMBER() OVER (PARTITION BY isin, price_date ORDER BY price_timestamp DESC) AS rn
                    FROM {db}.cis_equity_price
                    WHERE is_active = true
                      AND main_closing_price IS NOT NULL
                      AND main_closing_price != 0
                ) ep ON b.isin = ep.isin AND b.reporting_date = ep.price_date AND ep.rn = 1
                WHERE p4.security_status NOT LIKE 'FAIL%'
                """,
                database=db
            )
            logger.info("[position_etl] Step 5 complete")

            # ------------------------------------------------------------------
            # Step 5B: Create new securities for NOT_FOUND rows that have exchange.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                f"""
                INSERT INTO {db}.cis_security (
                    security_id,
                    security_name,
                    isin,
                    security_description,
                    issuer,
                    ticker,
                    industry,
                    security_type,
                    investment_type,
                    issuer_type,
                    quoted_unquoted,
                    country_of_incorporation,
                    country_of_exchange,
                    exchange_code,
                    currency_code,
                    shares_outstanding,
                    fin_nonfin_ind,
                    status,
                    is_active,
                    created_by,
                    created_at,
                    updated_by,
                    updated_at
                )
                SELECT
                    (UNIX_TIMESTAMP() * 1000) + b.row_id AS security_id,
                    COALESCE(b.security_short_name, b.security_full_name) AS security_name,
                    b.isin,
                    b.security_full_name AS security_description,
                    NULL AS issuer,
                    b.ticker,
                    b.industry,
                    b.security_type,
                    NULL AS investment_type,
                    b.issuer_type,
                    b.quoted_unquoted,
                    b.country_of_incorporation,
                    b.country_of_exchange,
                    b.`exchange`,
                    b.security_currency AS currency_code,
                    CAST(b.shares_outstanding AS BIGINT) AS shares_outstanding,
                    b.fin_nonfin_co AS fin_nonfin_ind,
                    'ACTIVE' AS status,
                    TRUE AS is_active,
                    'POSITION_UPLOAD' AS created_by,
                    from_unixtime(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS created_at,
                    'POSITION_UPLOAD' AS updated_by,
                    from_unixtime(UNIX_TIMESTAMP(), 'yyyy-MM-dd HH:mm:ss') AS updated_at
                FROM pos_stage_1_base b
                JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
                WHERE p4.security_status = 'NOT_FOUND: Create new security'
                  AND b.`exchange` IS NOT NULL
                  AND TRIM(b.`exchange`) != ''
                  AND (b.quantity IS NOT NULL OR b.cost_fc IS NOT NULL)
                """,
                database=db
            )
            logger.info("[position_etl] Step 5B complete (new securities created)")

            # ------------------------------------------------------------------
            # Step 6: Final staging — INNER JOIN on portfolio PASS; compute
            #         final_quantity, final_market_value_fc, overall_status.
            #         Also create position_upload_failed for reporting.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS position_upload_staging", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE position_upload_staging
                STORED AS PARQUET AS
                SELECT
                    b.*,
                    p2.valid_portfolio,
                    p2.portfolio_currency,
                    p2.portfolio_status,
                    p4.final_security_id,
                    p4.final_security_name AS matched_security_name,
                    p4.final_isin,
                    p4.final_country AS country_resolved,
                    p4.final_currency AS security_currency_resolved,
                    p4.security_status,
                    p5.final_market_price,
                    p5.price_status,
                    CASE
                        WHEN b.quantity IS NOT NULL THEN b.quantity
                        WHEN b.cost_fc IS NOT NULL  THEN b.cost_fc
                        ELSE NULL
                    END AS final_quantity,
                    CASE
                        WHEN b.quantity IS NOT NULL THEN 'PASS'
                        WHEN b.cost_fc IS NOT NULL  THEN 'PASS: Using cost_fc'
                        ELSE 'FAIL: Both quantity and cost_fc null'
                    END AS quantity_status,
                    CASE
                        WHEN b.shares_issued IS NOT NULL THEN b.shares_issued
                        WHEN b.pct_holding IS NOT NULL AND b.quantity IS NOT NULL AND b.pct_holding > 0
                            THEN b.quantity / b.pct_holding
                        ELSE NULL
                    END AS final_shares_issued,
                    CASE
                        WHEN b.`exchange` IS NULL OR TRIM(b.`exchange`) = ''
                            THEN 'FAIL: Exchange is null'
                        ELSE 'PASS'
                    END AS exchange_status,
                    CASE
                        WHEN b.market_value_fc IS NOT NULL AND b.market_value_fc != 0
                            THEN b.market_value_fc
                        WHEN b.quantity IS NOT NULL AND p5.final_market_price IS NOT NULL
                            THEN b.quantity * p5.final_market_price
                        ELSE NULL
                    END AS final_market_value_fc,
                    CASE
                        WHEN b.net_book_value_fc IS NOT NULL THEN b.net_book_value_fc
                        WHEN b.cost_fc IS NOT NULL           THEN b.cost_fc - COALESCE(b.provision_fc, 0)
                        ELSE NULL
                    END AS final_net_book_value_fc,
                    CASE
                        WHEN p4.security_status LIKE 'FAIL: No identifier%'
                            THEN 'INVALID: No security identifier'
                        WHEN b.`exchange` IS NULL OR TRIM(b.`exchange`) = ''
                            THEN 'INVALID: Exchange is null'
                        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
                            THEN 'INVALID: No quantity'
                        WHEN p4.security_status = 'NOT_FOUND: Create new security'
                            THEN 'VALID: New security created'
                        WHEN p4.security_status IN ('ISIN_MATCH', 'FULLNAME_MATCH', 'SHORTNAME_MATCH',
                                                     'TICKER_MATCH', 'DESC_MATCH', 'NAME_MATCH')
                            THEN 'VALID'
                        WHEN p4.security_status LIKE 'FAIL%'
                            THEN CONCAT('INVALID: ', p4.security_status)
                        ELSE 'VALID'
                    END AS overall_status
                FROM pos_stage_1_base b
                JOIN pos_stage_2_portfolio p2
                    ON b.row_id = p2.row_id AND p2.portfolio_status = 'PASS'
                JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
                LEFT JOIN pos_stage_5_price p5 ON b.row_id = p5.row_id
                """,
                database=db
            )
            logger.info("[position_etl] Step 6 complete")

            # Failed records table (for reporting — records that never made it to staging)
            impala_manager.execute_write(
                "DROP TABLE IF EXISTS position_upload_failed", database=db
            )
            impala_manager.execute_write(
                f"""
                CREATE TABLE position_upload_failed
                STORED AS PARQUET AS
                SELECT
                    b.*,
                    CASE
                        WHEN p2.portfolio_status LIKE 'FAIL%' THEN p2.portfolio_status
                        ELSE NULL
                    END AS portfolio_fail_reason,
                    CASE
                        WHEN (b.isin IS NULL OR TRIM(b.isin) = '')
                             AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
                             AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = '')
                            THEN 'FAIL: No security identifier'
                        ELSE NULL
                    END AS security_fail_reason,
                    CASE
                        WHEN b.`exchange` IS NULL OR TRIM(b.`exchange`) = ''
                            THEN 'FAIL: Exchange is null'
                        ELSE NULL
                    END AS exchange_fail_reason,
                    CASE
                        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
                            THEN 'FAIL: No quantity'
                        ELSE NULL
                    END AS quantity_fail_reason,
                    CASE
                        WHEN p2.portfolio_status LIKE 'FAIL%' THEN 'PORTFOLIO_NOT_FOUND'
                        WHEN (b.isin IS NULL OR TRIM(b.isin) = '')
                             AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
                             AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = '')
                            THEN 'NO_SECURITY_IDENTIFIER'
                        WHEN b.`exchange` IS NULL OR TRIM(b.`exchange`) = ''
                            THEN 'EXCHANGE_NULL'
                        WHEN b.quantity IS NULL AND b.cost_fc IS NULL
                            THEN 'NO_QUANTITY'
                        ELSE 'OTHER'
                    END AS fail_category
                FROM pos_stage_1_base b
                LEFT JOIN pos_stage_2_portfolio p2 ON b.row_id = p2.row_id
                WHERE p2.portfolio_status LIKE 'FAIL%'
                   OR ((b.isin IS NULL OR TRIM(b.isin) = '')
                       AND (b.security_full_name IS NULL OR TRIM(b.security_full_name) = '')
                       AND (b.security_short_name IS NULL OR TRIM(b.security_short_name) = ''))
                   OR (b.`exchange` IS NULL OR TRIM(b.`exchange`) = '')
                   OR (b.quantity IS NULL AND b.cost_fc IS NULL)
                """,
                database=db
            )
            logger.info("[position_etl] Step 6B complete (failed table created)")

            # ------------------------------------------------------------------
            # Step 7A: UPSERT valid records into cis_position (Kudu).
            #
            # position_id is a deterministic hash of the natural key:
            #   (portfolio, security_label, position_basis, position_date, src_system)
            # Using FNV-style: abs(hash(concat(...))) cast to BIGINT.
            # This guarantees that re-running ETL for the same batch replaces
            # existing rows rather than inserting duplicates.
            # ------------------------------------------------------------------
            ok = impala_manager.execute_write(
                f"""
                UPSERT INTO {db}.cis_position (
                    position_id,
                    version_id,
                    portfolio,
                    security_label,
                    position_basis,
                    position_date,
                    src_system,
                    processing_date,
                    quantity,
                    average_cost_fc,
                    cost_fc,
                    market_value_fc,
                    net_book_value_fc,
                    unrealized_pnl_fc,
                    cost_lc,
                    market_value_lc,
                    net_book_value_lc,
                    unrealized_pnl_lc,
                    provision_lc,
                    provision_fc,
                    dividend_fc,
                    dividend_lc,
                    realized_pnl_fc,
                    realized_pnl_lc,
                    isin,
                    average_cost_lc,
                    source_table,
                    placeholder_4,
                    uncall_fc,
                    uncall_lc,
                    pipeline_fc,
                    pipeline_lc,
                    position_type
                )
                SELECT
                    ABS(CAST(fnv_hash(CONCAT_WS('|',
                        COALESCE(portfolio, ''),
                        COALESCE(COALESCE(matched_security_name, security_full_name, security_short_name), ''),
                        COALESCE(position_basis, ''),
                        COALESCE(CAST(reporting_date AS STRING), ''),
                        COALESCE(src_system, '')
                    )) AS BIGINT))                          AS position_id,
                    CAST(UNIX_TIMESTAMP() * 1000 AS BIGINT) AS version_id,
                    portfolio,
                    COALESCE(matched_security_name, security_full_name, security_short_name) AS security_label,
                    position_basis,
                    reporting_date AS position_date,
                    src_system,
                    processing_date,
                    CAST(final_quantity          AS DECIMAL(18,4)) AS quantity,
                    CAST(average_cost            AS DECIMAL(18,6)) AS average_cost_fc,
                    CAST(cost_fc                 AS DECIMAL(18,4)) AS cost_fc,
                    CAST(final_market_value_fc   AS DECIMAL(18,4)) AS market_value_fc,
                    CAST(final_net_book_value_fc AS DECIMAL(18,4)) AS net_book_value_fc,
                    CAST(unrealized_pnl_fc       AS DECIMAL(18,4)) AS unrealized_pnl_fc,
                    CAST(cost_lc                 AS DECIMAL(18,4)) AS cost_lc,
                    CAST(market_value_lc         AS DECIMAL(18,4)) AS market_value_lc,
                    CAST(net_book_value_lc       AS DECIMAL(18,4)) AS net_book_value_lc,
                    CAST(unrealized_pnl_lc       AS DECIMAL(18,4)) AS unrealized_pnl_lc,
                    CAST(provision_lc            AS DECIMAL(18,4)) AS provision_lc,
                    CAST(provision_fc            AS DECIMAL(18,4)) AS provision_fc,
                    CAST(0                       AS DECIMAL(18,4)) AS dividend_fc,
                    CAST(0                       AS DECIMAL(18,4)) AS dividend_lc,
                    CAST(0                       AS DECIMAL(18,4)) AS realized_pnl_fc,
                    CAST(0                       AS DECIMAL(18,4)) AS realized_pnl_lc,
                    COALESCE(final_isin, isin)                     AS isin,
                    CAST(0                       AS DECIMAL(18,4)) AS average_cost_lc,
                    source_table                                   AS source_table,
                    ''                                             AS placeholder_4,
                    CAST(0                       AS DECIMAL(18,4)) AS uncall_fc,
                    CAST(0                       AS DECIMAL(18,4)) AS uncall_lc,
                    CAST(0                       AS DECIMAL(18,4)) AS pipeline_fc,
                    CAST(0                       AS DECIMAL(18,4)) AS pipeline_lc,
                    'EOD'                                          AS position_type
                FROM position_upload_staging
                WHERE overall_status LIKE 'VALID%'
                """,
                database=db
            )
            if not ok:
                return False, "Step 7A UPSERT INTO cis_position failed — check Impala logs for column/type mismatch", result
            logger.info("[position_etl] Step 7A complete (cis_position upsert)")

            # ------------------------------------------------------------------
            # Step 7B: INSERT OVERWRITE into the existing external partitioned
            #          table gmp_cis.position_upload_report.
            #          Columns match the DDL in 25_position_upload_standardized.sql.
            #          Only the (processing_date, src_id) partition is overwritten;
            #          all other partitions (other runs) are preserved.
            # ------------------------------------------------------------------
            impala_manager.execute_write(
                f"""
                INSERT OVERWRITE {db}.position_upload_report
                PARTITION (processing_date='{processing_date}', src_id='{src_id}')

                -- One row per source row — LEFT JOIN all staging tables, pick status by priority:
                -- portfolio fail > security fail > staging INVALID > staging VALID
                SELECT
                    b.portfolio,
                    COALESCE(b.security_full_name, b.security_short_name, b.isin) AS security_full_name,
                    b.security_short_name,
                    b.isin,
                    b.ticker,
                    b.quantity,
                    b.shares_outstanding,
                    b.shares_issued,
                    b.pct_holding,
                    b.market_price,
                    b.average_cost,
                    b.cost_fc,
                    b.market_value_fc,
                    b.net_book_value_fc,
                    b.unrealized_pnl_fc,
                    b.provision_fc,
                    b.cost_lc,
                    b.market_value_lc,
                    b.net_book_value_lc,
                    b.unrealized_pnl_lc,
                    b.provision_lc,
                    b.product_type,
                    b.security_type,
                    b.quoted_unquoted,
                    b.industry,
                    b.fin_nonfin_co,
                    b.issuer_type,
                    b.reits_or_fund_y_n,
                    b.`exchange`                                        AS `exchange`,
                    b.country_of_exchange,
                    b.country_of_incorporation,
                    b.country_of_risk,
                    b.country_of_operation,
                    b.security_currency,
                    b.corp_code,
                    b.branch_code,
                    b.cost_centre,
                    b.cels,
                    b.bwcif_sg,
                    b.bwcif_ovs,
                    b.mas_6d_code_sg,
                    b.mas_6d_code_ovs,
                    b.position_basis,
                    b.reporting_date,
                    b.maturity_date,
                    b.src_system,
                    b.source_table,
                    CASE
                        WHEN p2.portfolio_status LIKE 'FAIL%'  THEN 'FAIL'
                        WHEN p4.security_status  LIKE 'FAIL%'  THEN 'FAIL'
                        WHEN s.overall_status    LIKE 'INVALID%' THEN 'FAIL'
                        WHEN s.overall_status    LIKE 'VALID%'   THEN 'PASS'
                        ELSE 'FAIL'
                    END AS row_status,
                    CASE
                        WHEN p2.portfolio_status LIKE 'FAIL%'    THEN 'Portfolio not found in cis_portfolio'
                        WHEN p4.security_status  LIKE 'FAIL%'    THEN p4.security_status
                        WHEN s.overall_status    LIKE 'INVALID%' THEN s.overall_status
                        ELSE NULL
                    END AS fail_reason,
                    COALESCE(p2.portfolio_status, s.portfolio_status) AS portfolio_status,
                    COALESCE(p4.security_status,  s.security_status)  AS security_status,
                    s.price_status,
                    s.quantity_status,
                    s.exchange_status,
                    CAST(s.final_security_id AS STRING) AS matched_security_id,
                    s.matched_security_name
                FROM pos_stage_1_base b
                LEFT JOIN pos_stage_2_portfolio       p2 ON b.row_id = p2.row_id
                LEFT JOIN pos_stage_4_security_fallback p4 ON b.row_id = p4.row_id
                LEFT JOIN position_upload_staging      s  ON b.row_id = s.row_id
                """,
                database=db
            )
            impala_manager.execute_write(
                f"INVALIDATE METADATA {db}.position_upload_report",
                database=db
            )
            logger.info("[position_etl] Step 7B complete — INSERT OVERWRITE into partitioned position_upload_report")

            # ------------------------------------------------------------------
            # Count totals from report
            # ------------------------------------------------------------------
            rows = impala_manager.execute_query(
                f"""
                SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN row_status = 'PASS' THEN 1 ELSE 0 END) AS passed,
                    SUM(CASE WHEN row_status = 'FAIL' THEN 1 ELSE 0 END) AS failed
                FROM {db}.position_upload_report
                WHERE src_id = '{src_id}'
                  AND processing_date = '{processing_date}'
                """,
                database=db
            )
            if rows:
                result.update({
                    'total':  rows[0].get('total', 0),
                    'passed': rows[0].get('passed', 0),
                    'failed': rows[0].get('failed', 0),
                })
            else:
                result.update({'total': 0, 'passed': 0, 'failed': 0})

            # Clean up intermediate staging tables (keep report + failed for UI)
            for tbl in [
                'pos_stage_1_base', 'pos_stage_2_portfolio',
                'pos_stage_3_duplicate_isins', 'pos_stage_3_security',
                'pos_stage_4_security_fallback', 'pos_stage_5_price',
                'position_upload_staging',
            ]:
                try:
                    impala_manager.execute_write(
                        f"DROP TABLE IF EXISTS {tbl}", database=db
                    )
                except Exception:
                    pass

            msg = (
                f"Position ETL complete for {src_id} / {processing_date}: "
                f"{result.get('total', 0)} rows — "
                f"{result.get('passed', 0)} PASS, {result.get('failed', 0)} FAIL"
            )
            logger.info(f"[position_etl] {msg}")
            notify_user(updated_by, EVT_UPLOAD_COMPLETED, {
                **_notif_base,
                'total':  result.get('total', 0),
                'passed': result.get('passed', 0),
                'failed': result.get('failed', 0),
                'message': msg,
            })
            return True, msg, result

        except Exception as e:
            logger.error(f"[position_etl] Error: {e}", exc_info=True)
            err_msg = f"Position ETL error: {e}"
            notify_user(updated_by, EVT_UPLOAD_FAILED, {
                **_notif_base,
                'error':   str(e)[:500],
                'message': f'Position ETL failed for {src_id}: {str(e)[:200]}',
            })
            notify_admins(EVT_UPLOAD_FAILED, {
                **_notif_base,
                'triggered_by': updated_by,
                'error':        str(e)[:500],
                'message':      f'Upload ETL failure: src_id={src_id} user={updated_by} — {str(e)[:200]}',
            })
            return False, err_msg, result

    def get_position_report(
        self,
        src_id: str,
        processing_date: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows from position_upload_report for a given partition.

        Args:
            src_id: Source partition value
            processing_date: YYYYMMDD partition value

        Returns:
            List of row dicts
        """
        from core.repositories.impala_connection import impala_manager

        try:
            rows = impala_manager.execute_query(
                f"""
                SELECT
                    portfolio                   AS portfolio_name,
                    security_full_name,
                    security_short_name,
                    isin,
                    ticker,
                    quantity,
                    shares_outstanding,
                    shares_issued,
                    pct_holding,
                    market_price,
                    average_cost,
                    cost_fc,
                    market_value_fc,
                    net_book_value_fc,
                    unrealized_pnl_fc,
                    provision_fc,
                    cost_lc,
                    market_value_lc,
                    net_book_value_lc,
                    unrealized_pnl_lc,
                    provision_lc,
                    product_type,
                    security_type,
                    quoted_unquoted,
                    industry,
                    fin_nonfin_co,
                    issuer_type,
                    reits_or_fund_y_n,
                    `exchange`,
                    country_of_exchange,
                    country_of_incorporation,
                    country_of_risk,
                    country_of_operation,
                    security_currency,
                    corp_code,
                    branch_code,
                    cost_centre,
                    cels,
                    bwcif_sg,
                    bwcif_ovs,
                    mas_6d_code_sg,
                    mas_6d_code_ovs,
                    position_basis,
                    reporting_date,
                    maturity_date,
                    src_system,
                    source_table,
                    row_status,
                    fail_reason,
                    portfolio_status,
                    security_status,
                    price_status,
                    quantity_status,
                    exchange_status,
                    matched_security_id,
                    matched_security_name
                FROM gmp_cis.position_upload_report
                WHERE src_id = '{src_id}'
                  AND processing_date = '{processing_date}'
                ORDER BY row_status, portfolio, security_full_name
                """,
                database='gmp_cis'
            )
            return rows or []
        except Exception as e:
            logger.error(f"[position_report] Query error: {e}")
            return []

    def build_position_report_csv(
        self,
        src_id: str,
        processing_date: str
    ) -> Tuple[bool, str, str]:
        """
        Build CSV content from position_upload_report for a given partition.

        Returns:
            Tuple of (success, message, csv_string)
        """
        rows = self.get_position_report(src_id, processing_date)
        if not rows:
            return False, "No report data found for this upload partition", ""

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return True, f"{len(rows)} rows", output.getvalue()
