"""
File-Based Audit Logger (Fallback)

Writes audit entries to rotating JSON Lines files when Kudu is unavailable.
These files can be replayed to Kudu when the service recovers.

Author: CisTrade Team
Last Updated: 2026-01-25
"""

import json
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class FileAuditLogger:
    """
    Fallback audit logger that writes to rotating JSONL files.

    Features:
    - Thread-safe file writing
    - Automatic file rotation by date and size
    - JSON Lines format for easy replay
    - Configurable file size limits

    Usage:
        file_logger = FileAuditLogger(log_dir='logs/audit_fallback')
        file_logger.log({'action_type': 'CREATE', 'entity_type': 'EQUITY_PRICE', ...})
    """

    def __init__(
        self,
        log_dir: str = 'logs/audit_fallback',
        max_file_size: int = 10 * 1024 * 1024,  # 10MB
        file_prefix: str = 'audit_fallback'
    ):
        """
        Initialize file audit logger.

        Args:
            log_dir: Directory to store fallback log files
            max_file_size: Maximum file size before rotation (bytes)
            file_prefix: Prefix for log file names
        """
        self.log_dir = Path(log_dir)
        self.max_file_size = max_file_size
        self.file_prefix = file_prefix
        self._lock = threading.Lock()

        # Statistics
        self._entries_written = 0
        self._files_created = 0
        self._bytes_written = 0

        # Create directory if not exists
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"FileAuditLogger initialized: {self.log_dir}")
        except Exception as e:
            logger.error(f"Failed to create audit fallback directory: {e}")

    def log(self, audit_entry: Dict[str, Any]) -> bool:
        """
        Write audit entry to file as JSON line.

        Args:
            audit_entry: Dictionary containing audit data

        Returns:
            True if successfully written, False otherwise
        """
        with self._lock:
            try:
                # Add fallback metadata
                entry_with_meta = {
                    **audit_entry,
                    '_fallback_timestamp': datetime.now().isoformat(),
                    '_fallback_source': 'file_audit_logger'
                }

                # Get current file path (with rotation)
                file_path = self._get_current_file()

                # Write JSON line
                json_line = json.dumps(entry_with_meta, default=str) + '\n'
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(json_line)

                self._entries_written += 1
                self._bytes_written += len(json_line.encode('utf-8'))

                logger.debug(
                    f"Audit entry written to fallback: {audit_entry.get('action_type')} "
                    f"{audit_entry.get('entity_type')}"
                )
                return True

            except Exception as e:
                logger.error(f"Failed to write audit fallback: {e}")
                return False

    def _get_current_file(self) -> Path:
        """
        Get current log file path, creating new file if rotation needed.

        Returns:
            Path to current log file
        """
        date_str = datetime.now().strftime('%Y%m%d')
        base_name = f'{self.file_prefix}_{date_str}.jsonl'
        base_path = self.log_dir / base_name

        # Check if file exists and needs rotation
        if base_path.exists():
            file_size = base_path.stat().st_size
            if file_size >= self.max_file_size:
                # Find next available rotated filename
                i = 1
                while True:
                    rotated_name = f'{self.file_prefix}_{date_str}_{i:03d}.jsonl'
                    rotated_path = self.log_dir / rotated_name
                    if not rotated_path.exists():
                        self._files_created += 1
                        logger.info(f"Created new audit fallback file: {rotated_path}")
                        return rotated_path
                    # Check if this rotated file still has space
                    if rotated_path.stat().st_size < self.max_file_size:
                        return rotated_path
                    i += 1
        else:
            self._files_created += 1
            logger.info(f"Created new audit fallback file: {base_path}")

        return base_path

    def get_pending_files(self) -> list:
        """
        Get list of fallback files that need to be replayed.

        Returns:
            List of file paths sorted by modification time
        """
        try:
            files = list(self.log_dir.glob(f'{self.file_prefix}_*.jsonl'))
            # Sort by modification time (oldest first)
            files.sort(key=lambda f: f.stat().st_mtime)
            return files
        except Exception as e:
            logger.error(f"Failed to list fallback files: {e}")
            return []

    def get_pending_count(self) -> int:
        """
        Get approximate count of pending audit entries.

        Returns:
            Estimated number of entries in fallback files
        """
        try:
            total_lines = 0
            for file_path in self.get_pending_files():
                with open(file_path, 'r', encoding='utf-8') as f:
                    total_lines += sum(1 for _ in f)
            return total_lines
        except Exception as e:
            logger.error(f"Failed to count pending entries: {e}")
            return 0

    def read_entries(self, file_path: Path) -> list:
        """
        Read all entries from a fallback file.

        Args:
            file_path: Path to fallback file

        Returns:
            List of audit entry dictionaries
        """
        entries = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            entries.append(entry)
                        except json.JSONDecodeError as e:
                            logger.warning(f"Invalid JSON line in {file_path}: {e}")
        except Exception as e:
            logger.error(f"Failed to read fallback file {file_path}: {e}")
        return entries

    def archive_file(self, file_path: Path) -> bool:
        """
        Archive a processed fallback file.

        Args:
            file_path: Path to file to archive

        Returns:
            True if successfully archived
        """
        try:
            archive_dir = self.log_dir / 'archived'
            archive_dir.mkdir(exist_ok=True)

            archive_path = archive_dir / file_path.name
            file_path.rename(archive_path)
            logger.info(f"Archived fallback file: {file_path} -> {archive_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to archive fallback file: {e}")
            return False

    def get_stats(self) -> dict:
        """
        Get file logger statistics.

        Returns:
            Dictionary with stats
        """
        pending_files = self.get_pending_files()
        return {
            'entries_written': self._entries_written,
            'files_created': self._files_created,
            'bytes_written': self._bytes_written,
            'pending_files': len(pending_files),
            'pending_entries': self.get_pending_count() if pending_files else 0,
            'log_dir': str(self.log_dir)
        }


# Singleton instance
_file_logger_instance: Optional[FileAuditLogger] = None


def get_file_audit_logger() -> FileAuditLogger:
    """
    Get singleton file audit logger instance.

    Returns:
        FileAuditLogger instance
    """
    global _file_logger_instance

    if _file_logger_instance is None:
        from django.conf import settings
        log_dir = getattr(settings, 'AUDIT_FALLBACK_DIR', 'logs/audit_fallback')
        max_size = getattr(settings, 'AUDIT_FALLBACK_MAX_FILE_SIZE', 10 * 1024 * 1024)
        _file_logger_instance = FileAuditLogger(log_dir=log_dir, max_file_size=max_size)

    return _file_logger_instance
