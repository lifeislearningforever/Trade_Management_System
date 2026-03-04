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
                result.warnings.append("File contains only header row, no data")

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

            # Get file header row for column names
            file_header = rows[0] if has_header else [f'col_{i+1}' for i in range(len(rows[0]))]
            data_rows = rows[1:] if has_header else rows

            # Use intake_columns from datasource config OR file header
            if intake_columns:
                # Ensure column count matches file
                if len(intake_columns) == len(file_header):
                    result.columns = intake_columns
                else:
                    # Column count mismatch - use file header with STRING type
                    logger.warning(
                        f"intake_columns count ({len(intake_columns)}) != file header count ({len(file_header)}). "
                        f"Using file header."
                    )
                    result.columns = [
                        {'name': self.validation_service._clean_column_name(h), 'type': 'STRING'}
                        for h in file_header
                    ]
                result.column_count = len(result.columns)
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

            # Generate sample data using actual column names from result.columns
            header_names = [col['name'] for col in result.columns]
            result.sample_data = []
            for row in data_rows[:self.validation_service.MAX_PREVIEW_ROWS]:
                row_dict = {}
                for idx, col_name in enumerate(header_names):
                    if idx < len(row):
                        row_dict[col_name] = row[idx]
                    else:
                        row_dict[col_name] = ''
                result.sample_data.append(row_dict)

            result.is_valid = True

        except Exception as e:
            logger.error(f"Validation with datasource config error: {str(e)}")
            result.errors.append(f"Validation error: {str(e)}")

        return result

    # HDFS temp location for staging files
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
            has_header = str(datasource_config.get('header', 'true')).lower() == 'true'
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

            # Use INSERT VALUES directly - more reliable than HDFS staging
            # Check for temp file first, then fall back to sample_data
            local_file = None
            if temp_file_path and os.path.exists(temp_file_path):
                local_file = temp_file_path
                logger.info(f"Using INSERT VALUES with local file: {local_file}")
            elif sample_data:
                logger.info(f"Using INSERT VALUES with sample_data ({len(sample_data)} rows)")
            else:
                # Try to get sample data from upload record
                upload_sample = upload.get('sample_data_json', []) if upload else []
                if upload_sample:
                    if isinstance(upload_sample, str):
                        import json as json_module
                        sample_data = json_module.loads(upload_sample)
                    else:
                        sample_data = upload_sample
                    logger.info(f"Using INSERT VALUES with upload sample_data ({len(sample_data)} rows)")

            # If we have either a local file or sample_data, use INSERT VALUES
            if local_file or sample_data:
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

            return False, "No file or sample data available for ingestion. Please re-upload the file."

        except Exception as e:
            logger.error(f"Metadata-driven ingestion error: {str(e)}")
            if not is_session_upload:
                self.repository.update_status(upload_id, UploadKuduRepository.STATUS_FAILED, updated_by, str(e))
            return False, f"Ingestion error: {str(e)}"

    def _upload_file_to_hdfs(self, local_path: str, hdfs_dir: str) -> bool:
        """
        Upload a local file to HDFS.

        Args:
            local_path: Path to local file
            hdfs_dir: HDFS directory to upload to

        Returns:
            True if successful, False otherwise
        """
        import subprocess

        try:
            # Create HDFS directory
            mkdir_cmd = ['hdfs', 'dfs', '-mkdir', '-p', hdfs_dir]
            result = subprocess.run(mkdir_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode != 0:
                logger.error(f"Failed to create HDFS directory: {result.stderr}")
                return False

            # Upload file to HDFS
            put_cmd = ['hdfs', 'dfs', '-put', '-f', local_path, hdfs_dir]
            result = subprocess.run(put_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                logger.error(f"Failed to upload file to HDFS: {result.stderr}")
                return False

            logger.info(f"Successfully uploaded {local_path} to {hdfs_dir}")
            return True

        except subprocess.TimeoutExpired:
            logger.error("HDFS upload timed out")
            return False
        except FileNotFoundError:
            logger.error("hdfs command not found - HDFS client not installed")
            return False
        except Exception as e:
            logger.error(f"HDFS upload error: {str(e)}")
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

        try:
            source_id = datasource_config.get('source_id', '')
            col_names = [col['name'] for col in intake_columns]
            separator = datasource_config.get('separator', ',')
            has_header = str(datasource_config.get('header', 'true')).lower() == 'true'

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

            logger.info(f"Using src_system={src_system}, sub_system={sub_system} for {target_table}")

            # Read data from file or use sample_data
            all_data = sample_data or []
            if temp_file_path and os.path.exists(temp_file_path):
                logger.info(f"Reading full file from {temp_file_path} for ingestion")
                try:
                    all_data = []
                    with open(temp_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        delim = separator if separator else ','
                        reader = csv.reader(f, delimiter=delim)
                        rows = list(reader)

                        if has_header and len(rows) > 0:
                            data_rows = rows[1:]
                        else:
                            data_rows = rows

                        # Convert to list of dicts using intake column names
                        for row in data_rows:
                            if len(row) > 0:
                                row_dict = {}
                                for idx, col in enumerate(col_names):
                                    if idx < len(row):
                                        row_dict[col] = row[idx]
                                    else:
                                        row_dict[col] = ''
                                all_data.append(row_dict)

                    logger.info(f"Read {len(all_data)} rows from file")
                except Exception as e:
                    logger.error(f"Failed to read file {temp_file_path}: {e}")
                    all_data = sample_data or []

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

            # Step 1: For Hive external Parquet tables, we use INSERT OVERWRITE
            # which automatically replaces data in the partition
            # No need to explicitly delete - INSERT OVERWRITE handles it
            logger.info(f"Will use INSERT OVERWRITE for partition processing_date='{processing_date}'")

            # Step 2: Insert data using INSERT OVERWRITE SELECT * FROM (UNION ALL)
            # Each SELECT must have column aliases to avoid "duplicated inline view column alias" error
            rows_inserted = 0
            batch_size = 50  # Smaller batches for stability

            for i in range(0, len(all_data), batch_size):
                batch = all_data[i:i + batch_size]
                select_statements = []

                for row_idx, row in enumerate(batch):
                    row_values = []
                    for col_idx, col in enumerate(non_partition_cols):
                        col_lower = col.lower()
                        if col_lower in additional_cols_map:
                            val = additional_cols_map[col_lower]
                        elif col_lower in [c.lower() for c in col_names]:
                            matching_col = next((c for c in col_names if c.lower() == col_lower), None)
                            val = row.get(matching_col, '') if matching_col else ''
                        else:
                            val = ''

                        # Escape single quotes and handle empty/null values
                        if val is None or val == '':
                            row_values.append(f"'' AS {col}")
                        else:
                            escaped_val = str(val).replace("'", "''")
                            row_values.append(f"'{escaped_val}' AS {col}")

                    # Build SELECT statement for this row with column aliases
                    select_statements.append(f"SELECT {', '.join(row_values)}")

                if select_statements:
                    # Build INSERT statement with PARTITION
                    # Mode determines whether to OVERWRITE or APPEND
                    union_query = '\nUNION ALL\n'.join(select_statements)

                    if ingestion_mode == 'append':
                        # APPEND mode: Always use INSERT INTO to add rows
                        insert_sql = f"""INSERT INTO {self.repository.DATABASE}.{target_table}
PARTITION (processing_date='{processing_date}')
SELECT * FROM (
{union_query}
) t"""
                        logger.info(f"Executing INSERT INTO (append) batch {i//batch_size + 1} with {len(batch)} rows")
                    elif i == 0:
                        # OVERWRITE mode - First batch: INSERT OVERWRITE to replace existing partition data
                        insert_sql = f"""INSERT OVERWRITE {self.repository.DATABASE}.{target_table}
PARTITION (processing_date='{processing_date}')
SELECT * FROM (
{union_query}
) t"""
                        logger.info(f"Executing INSERT OVERWRITE batch 1 with {len(batch)} rows")
                    else:
                        # OVERWRITE mode - Subsequent batches: INSERT INTO to append within same ingestion
                        insert_sql = f"""INSERT INTO {self.repository.DATABASE}.{target_table}
PARTITION (processing_date='{processing_date}')
SELECT * FROM (
{union_query}
) t"""
                        logger.info(f"Executing INSERT INTO batch {i//batch_size + 1} with {len(batch)} rows")

                    success = impala_manager.execute_write(insert_sql, database=self.repository.DATABASE)
                    if success:
                        rows_inserted += len(batch)
                        logger.info(f"Inserted batch {i//batch_size + 1}, total rows: {rows_inserted}")
                    else:
                        logger.error(f"Failed to insert batch at offset {i}")
                        return False, f"Failed to insert batch at offset {i}"

            if rows_inserted == 0:
                return False, "No rows were inserted"

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
