#!/usr/bin/env python
"""
Replay Fallback Audit Entries to Kudu

This script reads audit entries from the fallback JSONL files
and inserts them into the Kudu audit_log table.

Run this when the Kudu cluster is healthy to sync fallback entries.

Usage:
    source .venv/bin/activate
    python -m core.audit.replay_fallback

    # Or with options:
    python -m core.audit.replay_fallback --dry-run
    python -m core.audit.replay_fallback --batch-size 50
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from core.repositories.impala_connection import impala_manager
from core.audit.file_audit_logger import get_file_audit_logger

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def replay_fallback_entries(dry_run: bool = False, batch_size: int = 10) -> dict:
    """
    Replay fallback audit entries to Kudu.

    Args:
        dry_run: If True, only show what would be done
        batch_size: Number of entries per batch insert

    Returns:
        Dictionary with replay statistics
    """
    file_logger = get_file_audit_logger()
    pending_files = file_logger.get_pending_files()

    stats = {
        'files_processed': 0,
        'entries_replayed': 0,
        'entries_failed': 0,
        'files_archived': 0
    }

    if not pending_files:
        logger.info("No pending fallback files to replay")
        return stats

    logger.info(f"Found {len(pending_files)} pending fallback files")

    for file_path in pending_files:
        logger.info(f"Processing: {file_path}")
        entries = file_logger.read_entries(file_path)

        if not entries:
            logger.warning(f"No entries in {file_path}")
            continue

        logger.info(f"  Found {len(entries)} entries")

        if dry_run:
            for entry in entries:
                logger.info(f"    [DRY-RUN] Would replay: {entry.get('action_type')} {entry.get('entity_type')} {entry.get('entity_name')}")
            stats['entries_replayed'] += len(entries)
            stats['files_processed'] += 1
            continue

        # Process in batches
        success_count = 0
        fail_count = 0

        for i in range(0, len(entries), batch_size):
            batch = entries[i:i + batch_size]

            try:
                if insert_batch_to_kudu(batch):
                    success_count += len(batch)
                    logger.info(f"    Replayed batch {i // batch_size + 1}: {len(batch)} entries")
                else:
                    fail_count += len(batch)
                    logger.error(f"    Failed batch {i // batch_size + 1}")
            except Exception as e:
                fail_count += len(batch)
                logger.error(f"    Error in batch {i // batch_size + 1}: {e}")

        stats['entries_replayed'] += success_count
        stats['entries_failed'] += fail_count
        stats['files_processed'] += 1

        # Archive file if all entries were successful
        if fail_count == 0 and success_count > 0:
            if file_logger.archive_file(file_path):
                stats['files_archived'] += 1
                logger.info(f"  Archived: {file_path.name}")
            else:
                logger.warning(f"  Failed to archive: {file_path.name}")

    return stats


def insert_batch_to_kudu(batch: list) -> bool:
    """
    Insert a batch of audit entries to Kudu.

    Args:
        batch: List of audit entry dictionaries

    Returns:
        True if successful
    """
    if not batch:
        return True

    try:
        values_list = []

        for entry in batch:
            values = format_audit_values(entry)
            values_list.append(f"({values})")

        upsert_query = f"""
        UPSERT INTO gmp_cis.cis_audit_log
        (`audit_id`, `audit_timestamp`, `user_id`, `username`, `action_type`,
         `action_category`, `action_description`, `entity_type`, `entity_id`,
         `entity_name`, `old_value`, `new_value`, `status`, `status_code`,
         `duration_ms`, `audit_date`)
        VALUES {', '.join(values_list)}
        """

        return impala_manager.execute_write(upsert_query, database='gmp_cis')

    except Exception as e:
        logger.error(f"Kudu batch insert failed: {e}")
        return False


def format_audit_values(entry: dict) -> str:
    """Format audit entry as SQL VALUES string."""
    import uuid

    # Parse timestamp from fallback metadata or use current time
    fallback_ts = entry.get('_fallback_timestamp')
    if fallback_ts:
        try:
            ts = datetime.fromisoformat(fallback_ts)
        except:
            ts = datetime.now()
    else:
        ts = datetime.now()

    # Generate unique audit_id based on timestamp
    audit_id = int(ts.timestamp() * 1000) + (uuid.uuid4().int % 1000)

    def esc(val):
        if val is None:
            return 'NULL'
        val_str = str(val)
        val_str = val_str.replace("\\", "\\\\").replace("'", "\\'")
        if len(val_str) > 4000:
            val_str = val_str[:4000] + '...[truncated]'
        return f"'{val_str}'"

    return ', '.join([
        str(audit_id),
        f"'{ts.strftime('%Y-%m-%d %H:%M:%S')}'",
        esc(entry.get('user_id', '0')),
        esc(entry.get('username', 'SYSTEM')),
        esc(entry.get('action_type', 'UNKNOWN')),
        esc(entry.get('action_category', 'DATA')),
        esc(entry.get('action_description', '')),
        esc(entry.get('entity_type', '')),
        esc(entry.get('entity_id', '')),
        esc(entry.get('entity_name', '')),
        esc(entry.get('old_value')),
        esc(entry.get('new_value')),
        esc(entry.get('status', 'SUCCESS')),
        str(entry.get('status_code', 200)),
        str(entry.get('duration_ms', 0)),
        f"'{ts.strftime('%Y-%m-%d')}'"
    ])


def main():
    parser = argparse.ArgumentParser(description='Replay fallback audit entries to Kudu')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--batch-size', type=int, default=10, help='Number of entries per batch (default: 10)')

    args = parser.parse_args()

    print("\n" + "="*60)
    print("AUDIT FALLBACK REPLAY")
    print("="*60)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Dry run: {args.dry_run}")
    print(f"Batch size: {args.batch_size}")
    print()

    stats = replay_fallback_entries(
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )

    print("\n" + "="*60)
    print("REPLAY SUMMARY")
    print("="*60)
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Entries replayed: {stats['entries_replayed']}")
    print(f"  Entries failed: {stats['entries_failed']}")
    print(f"  Files archived: {stats['files_archived']}")
    print("="*60)

    if stats['entries_failed'] > 0:
        print("\nSome entries failed to replay. Check logs for details.")
        return 1

    print("\nReplay completed successfully!")
    return 0


if __name__ == '__main__':
    sys.exit(main())
