#!/usr/bin/env python3
"""
CML (Cloudera Machine Learning) Application Entry Point

This script serves as the entry point for deploying the CIS Trade Hive
Django application as a CML Project Application.

Features:
- Multi-environment support (SIT, UAT, PROD, DR)
- Kerberos authentication with automatic ticket renewal
- Hybrid connection: Impala (reads) + Hive (writes)
- Gunicorn WSGI server with configurable workers/threads
- Trade Event Worker for async HISTORY and SETTLEMENT processing
- Position Queue Worker for async AVP processing

CML Application Configuration:
- Script: config/cml_app.py
- Subdomain: cis-trade-hive

Environment Variables (set in CML Project Settings):
- CIS_ENV: Environment name (SIT, UAT, PROD, DR) - REQUIRED
- KRB5_KTNAME: Override Kerberos keytab path (optional)
- KRB5_PRINCIPAL: Override Kerberos principal (optional)
- KRB5CCNAME: Kerberos credential cache
- TRADE_EVENT_WORKER_ENABLED: Set to '1' to enable trade event worker (default: enabled)
- TRADE_EVENT_WORKER_POLL_INTERVAL: Poll interval in seconds (default: 5)
- TRADE_EVENT_WORKER_BATCH_SIZE: Batch size for processing (default: 50)
- POSITION_WORKER_ENABLED: Set to '1' to enable position worker (default: enabled)
- POSITION_WORKER_POLL_INTERVAL: Poll interval in seconds (default: 10)
- POSITION_WORKER_BATCH_SIZE: Batch size for processing (default: 100)

Background Workers:
==================
Two background workers run alongside the main application:

1. Trade Event Worker (cis_trade_event_queue)
   - Processes HISTORY events: Insert trade history records for audit trail
   - Processes SETTLEMENT events: Trigger settlement and AVP calculations
   - Decouples trade save from post-trade processing for fast response
   - SLA: < 5 minutes from queue to completion
   - Retry: Max 3 attempts, then marked as FAILED

2. Position Queue Worker (cis_position_queue)
   - Processes position calculations for T+0 and backdated trades
   - Updates cis_trade_position table with AVP values
   - Handles chain recalculation for backdated trades
   - SLA: < 5 minutes from queue to position update

Trade Save Flow:
===============
1. User submits trade → insert_trade_fast() saves trade record (1-2s)
2. Events queued to cis_trade_event_queue (async, non-blocking)
3. Trade Event Worker picks up HISTORY event → inserts trade_history
4. Trade Event Worker picks up SETTLEMENT event → calls settlement_service
5. Settlement service queues to cis_position_queue (if T+0)
6. Position Worker picks up and calculates AVP

Queue Tables:
- cis_trade_event_queue: HISTORY, SETTLEMENT events from trade save
- cis_position_queue: Position calculations from settlement service
- cis_settlement_queue: Future-dated settlements (T+1, T+2)

Environments:
- SIT:  owntmrwsg@TST.UOBNET.COM (System Integration Testing)
- UAT:  ownumrwsg@SG.UOBNET.COM  (User Acceptance Testing)
- PROD: ownumrwsg@SG.UOBNET.COM  (Production)
- DR:   ownrmrwsg@SG.UOBNET.COM  (Disaster Recovery)

Impala/Hive are configured via IMPALA_CONFIG and HIVE_CONFIG in settings.py
"""

import os
import sys
import subprocess
import threading
import time
import signal

# === CML Application Launcher ===
WORKDIR = os.environ.get("WORKDIR", "/home/cdsw/CIS/")
DJANGO_SETTINGS = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings")
COLLECT_STATIC = os.environ.get("DJANGO_COLLECT_STATIC", "0") in ("1", "true", "True")
print(os.environ.get("USER_OWNER"))
print(os.environ.get("CDSW_USERNAME"))

# ============================================================================
# Environment Configuration
# ============================================================================
# Environment-specific Kerberos and connection settings

ENV_CONFIGS = {
    'SIT': {
        'name': 'System Integration Testing',
        'keytab': '/home/cdsw/CIS/secrets/owntmrwsg.keytab',
        'principal': 'owntmrwsg@TST.UOBNET.COM',
        'cache': 'FILE:/home/cdsw/CIS/krb5/krb5cc',
    },
    'UAT': {
        'name': 'User Acceptance Testing',
        'keytab': '/home/cdsw/CIS/secrets/ownumrwsg.keytab',
        'principal': 'ownumrwsg@SG.UOBNET.COM',
        'cache': 'FILE:/home/cdsw/CIS/krb5/krb5cc',
    },
    'PROD': {
        'name': 'Production',
        'keytab': '/home/cdsw/CIS/secrets/ownumrwsg.keytab',
        'principal': 'ownumrwsg@SG.UOBNET.COM',
        'cache': 'FILE:/home/cdsw/CIS/krb5/krb5cc',
    },
    'DR': {
        'name': 'Disaster Recovery',
        'keytab': '/home/cdsw/CIS/secrets/ownrmrwsg.keytab',
        'principal': 'ownrmrwsg@SG.UOBNET.COM',
        'cache': 'FILE:/home/cdsw/CIS/krb5/krb5cc',
    },
}


def get_environment_config():
    """
    Get configuration for current environment.

    Returns:
        Tuple of (env_name, keytab, principal, cache)
    """
    # Get environment from CIS_ENV (required for CML)
    cis_env = os.environ.get("CIS_ENV", "SIT").upper()

    # Handle legacy 'work' value
    if cis_env == "WORK":
        cis_env = "SIT"

    if cis_env not in ENV_CONFIGS:
        print(f"WARNING: Unknown CIS_ENV '{cis_env}', defaulting to SIT")
        cis_env = "SIT"

    config = ENV_CONFIGS[cis_env]

    # Allow environment variable overrides
    keytab = os.environ.get("KRB5_KTNAME") or config['keytab']
    principal = os.environ.get("KRB5_PRINCIPAL") or config['principal']
    cache = os.environ.get("KRB5CCNAME") or config['cache']

    return cis_env, keytab, principal, cache

# Trade Event Worker Configuration (HISTORY, SETTLEMENT events)
TRADE_EVENT_WORKER_ENABLED = os.environ.get("TRADE_EVENT_WORKER_ENABLED", "1") in ("1", "true", "True")
TRADE_EVENT_WORKER_POLL_INTERVAL = int(os.environ.get("TRADE_EVENT_WORKER_POLL_INTERVAL", "5"))
TRADE_EVENT_WORKER_BATCH_SIZE = int(os.environ.get("TRADE_EVENT_WORKER_BATCH_SIZE", "50"))

# Position Worker Configuration (AVP calculations)
POSITION_WORKER_ENABLED = os.environ.get("POSITION_WORKER_ENABLED", "1") in ("1", "true", "True")
POSITION_WORKER_POLL_INTERVAL = int(os.environ.get("POSITION_WORKER_POLL_INTERVAL", "10"))
POSITION_WORKER_BATCH_SIZE = int(os.environ.get("POSITION_WORKER_BATCH_SIZE", "100"))

# Global flag for graceful shutdown
_shutdown_requested = False
_trade_event_worker_thread = None
_position_worker_thread = None


def run(cmd, env=None, check=True):
    """Run a command and optionally check return code."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, env=env)
    if check and result.returncode != 0:
        sys.exit(result.returncode)
    return result.returncode


def kinit_with_keytab(keytab, principal, cache=None):
    """Initialize Kerberos ticket using keytab."""
    env = os.environ.copy()
    if cache:
        env["KRB5CCNAME"] = cache
    print(f"==> kinit -kt {keytab} {principal}")
    rc = subprocess.run(["kinit", "-kt", keytab, principal], env=env).returncode
    if rc != 0:
        print("ERROR: kinit failed. Verify keytab, principal, and krb5.conf.")
        sys.exit(rc)
    subprocess.run(["klist"], env=env)
    return rc


def start_kerberos_renewal_loop(keytab, principal, interval_sec=3600, cache=None):
    """Start a background thread to renew Kerberos ticket periodically."""
    def _renew():
        env = os.environ.copy()
        if cache:
            env["KRB5CCNAME"] = cache
        while True:
            r = subprocess.run(["kinit", "-R"], env=env)
            if r.returncode != 0:
                print("Renewal failed; re-acquiring ticket via keytab...")
                subprocess.run(["kinit", "-kt", keytab, principal], env=env)
            time.sleep(interval_sec)

    t = threading.Thread(target=_renew, daemon=True)
    t.start()


_worker_lock_fd = None  # File descriptor held for the lifetime of the process


def start_trade_event_worker():
    """
    Start the Trade Event Worker in a background thread.

    Only ONE gunicorn worker process runs the thread at a time.  A process-level
    file lock (/tmp/cis_trade_event_worker.lock) ensures that when gunicorn spawns
    multiple worker processes only the first one to acquire the lock actually starts
    the background thread.  All others print a skip message and return — they still
    serve HTTP requests normally.

    Queue Table: cis_trade_event_queue
    Event Types:
    - HISTORY: Insert trade history record for audit trail
    - SETTLEMENT: Trigger settlement and AVP calculation

    Features:
    - Processes events from cis_trade_event_queue
    - SLA: < 5 minutes from queue to completion
    - Auto-retry with max 3 attempts
    - Stale PROCESSING recovery (events stuck > 5 min re-queued)
    - Graceful shutdown on SIGTERM/SIGINT
    """
    global _trade_event_worker_thread, _shutdown_requested, _worker_lock_fd

    if not TRADE_EVENT_WORKER_ENABLED:
        print("==> Trade Event Worker: DISABLED (TRADE_EVENT_WORKER_ENABLED=0)")
        return

    # --- Process-level lock: only ONE gunicorn worker runs the background thread ---
    import fcntl as _fcntl
    _lock_path = '/tmp/cis_trade_event_worker.lock'
    try:
        _worker_lock_fd = open(_lock_path, 'w')
        _fcntl.flock(_worker_lock_fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        _worker_lock_fd.write(str(os.getpid()))
        _worker_lock_fd.flush()
        print(f"==> Trade Event Worker: Acquired process lock (pid={os.getpid()})")
    except BlockingIOError:
        print(f"==> Trade Event Worker: Another gunicorn worker already holds the lock — skipping thread start (pid={os.getpid()})")
        return
    # ---------------------------------------------------------------------------

    print("==> Starting Trade Event Worker...")
    print(f"    Poll Interval: {TRADE_EVENT_WORKER_POLL_INTERVAL}s")
    print(f"    Batch Size: {TRADE_EVENT_WORKER_BATCH_SIZE}")

    def _worker_loop():
        """Main worker loop - runs in background thread."""
        global _shutdown_requested
        import json
        from datetime import datetime
        from decimal import Decimal

        # Import Django and services inside thread to ensure proper initialization
        import django
        django.setup()

        from core.repositories.impala_connection import impala_manager
        from core.notifications import notify_user
        from core.notifications.constants import EVT_AVP_COMPLETED, EVT_AVP_FAILED

        DATABASE = 'gmp_cis'
        EVENT_QUEUE_TABLE = 'cis_trade_event_queue'
        HISTORY_TABLE = 'cis_trade_history'

        print("==> Trade Event Worker: Started")

        def process_history_event(event, event_data):
            """Process a HISTORY event - insert trade history record."""
            trade_id = event['trade_id']
            deal_number = event['deal_number']
            created_by = event['created_by']
            action = event_data.get('action', 'CREATE')
            old_status = event_data.get('old_status')
            new_status = event_data.get('new_status', 'INITIAL')

            timestamp = datetime.now()
            history_id = int(timestamp.timestamp() * 1000)

            query = f"""
            UPSERT INTO {DATABASE}.{HISTORY_TABLE}
            (history_id, trade_id, deal_number, action, old_status, new_status,
             changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {trade_id},
                '{deal_number}',
                '{action}',
                {f"'{old_status}'" if old_status else 'NULL'},
                '{new_status}',
                '{{}}',
                'Trade created',
                '{created_by}',
                '{timestamp.strftime('%Y-%m-%d %H:%M:%S')}'
            )
            """
            impala_manager.execute_write(query, database=DATABASE)
            print(f"==> Trade Event Worker: Inserted HISTORY for trade {trade_id}")

        def process_settlement_event(event, event_data):
            """Process a SETTLEMENT event - trigger settlement/AVP calculation."""
            from trade.services.settlement_service import settlement_service

            trade_id = event_data.get('trade_id')
            created_by = event['created_by']

            # Calculate total charges (manual + auto-calculated)
            manual_charges = (
                Decimal(str(event_data.get('commission', 0) or 0)) +
                Decimal(str(event_data.get('sec_fee', 0) or 0)) +
                Decimal(str(event_data.get('other_charges', 0) or 0))
            )
            auto_charges = (
                Decimal(str(event_data.get('calculated_commission', 0) or 0)) +
                Decimal(str(event_data.get('calculated_clearing_fee', 0) or 0)) +
                Decimal(str(event_data.get('calculated_trading_fee', 0) or 0)) +
                Decimal(str(event_data.get('calculated_gst', 0) or 0)) +
                Decimal(str(event_data.get('calculated_other_fees', 0) or 0))
            )
            charges = manual_charges + auto_charges

            # Process settlement (this calculates AVP)
            success, msg, result = settlement_service.process_trade_settlement(
                trade_id=trade_id,
                portfolio_id=event_data.get('portfolio_short_name', ''),
                security_id=event_data.get('security_label', ''),
                trade_type=event_data.get('trade_type', ''),
                quantity=Decimal(str(event_data.get('quantity', 0) or 0)),
                price=Decimal(str(event_data.get('price', 0) or 0)),
                charges=charges,
                trade_date=event_data.get('trade_date', ''),
                settle_date=event_data.get('settle_date', ''),
                updated_by=created_by,
                security_currency=event_data.get('security_currency'),
                portfolio_currency=event_data.get('portfolio_currency'),
                isin=event_data.get('isin'),
                security_name=event_data.get('security_name'),
                custodian=event_data.get('custodian', ''),
                sub_custodian=event_data.get('sub_custodian', ''),
                async_mode=False  # Process synchronously in worker
            )

            if success:
                print(f"==> Trade Event Worker: SETTLEMENT processed for trade {trade_id}: {msg}")
                notify_user(created_by, EVT_AVP_COMPLETED, {
                    'trade_id': trade_id,
                    'portfolio_id': event_data.get('portfolio_short_name', ''),
                    'security_id': event_data.get('security_label', ''),
                    'message': f'AVP calculation complete for trade {trade_id}',
                })
            else:
                print(f"==> Trade Event Worker: SETTLEMENT warning for trade {trade_id}: {msg}")
                if 'queued' in msg.lower() or 'future' in msg.lower():
                    notify_user(created_by, EVT_AVP_COMPLETED, {
                        'trade_id': trade_id,
                        'message': f'Trade {trade_id} queued for settlement date',
                    })
                else:
                    notify_user(created_by, EVT_AVP_FAILED, {
                        'trade_id': trade_id,
                        'message': f'AVP failed for trade {trade_id}: {msg}',
                    })

        def process_position_modify_event(event, event_data):
            """Process a POSITION_MODIFY event - update position when trade is modified.

            For trade modifications:
            1. Reverse the old position effect (treat old BUY as SELL, vice versa)
            2. Apply the new position effect

            This ensures the position correctly reflects the new trade values.

            Event data structure:
            {
                'old_trade': { ... original trade data ... },
                'new_trade': { ... updated trade data ... }
            }
            """
            from trade.services.position_service import position_service

            # Extract old and new trade data from nested structure
            old_trade = event_data.get('old_trade', {})
            new_trade = event_data.get('new_trade', {})

            trade_id = event['trade_id']
            created_by = event['created_by']

            # Get new trade values
            portfolio_id = new_trade.get('portfolio_short_name', '')
            security_id = new_trade.get('security_label', '')
            trade_type = new_trade.get('trade_type', '')
            quantity = Decimal(str(new_trade.get('quantity', 0) or 0))
            price = Decimal(str(new_trade.get('price', 0) or 0))
            trade_date = new_trade.get('trade_date', '')
            settle_date = new_trade.get('settle_date', '')
            position_date = settle_date or trade_date

            # Calculate total charges for new trade (manual + auto-calculated)
            manual_charges = (
                Decimal(str(new_trade.get('commission', 0) or 0)) +
                Decimal(str(new_trade.get('sec_fee', 0) or 0)) +
                Decimal(str(new_trade.get('other_charges', 0) or 0))
            )
            auto_charges = (
                Decimal(str(new_trade.get('calculated_commission', 0) or 0)) +
                Decimal(str(new_trade.get('calculated_clearing_fee', 0) or 0)) +
                Decimal(str(new_trade.get('calculated_trading_fee', 0) or 0)) +
                Decimal(str(new_trade.get('calculated_gst', 0) or 0)) +
                Decimal(str(new_trade.get('calculated_other_fees', 0) or 0))
            )
            charges = manual_charges + auto_charges

            # Get old values from old_trade
            old_quantity = Decimal(str(old_trade.get('quantity', 0) or 0))
            old_price = Decimal(str(old_trade.get('price', 0) or 0))
            old_manual_charges = (
                Decimal(str(old_trade.get('commission', 0) or 0)) +
                Decimal(str(old_trade.get('sec_fee', 0) or 0)) +
                Decimal(str(old_trade.get('other_charges', 0) or 0))
            )
            old_charges = old_manual_charges

            print(f"==> Trade Event Worker: POSITION_MODIFY processing trade {trade_id}")
            print(f"    Portfolio: {portfolio_id}, Security: {security_id}")
            print(f"    Old: qty={old_quantity}, price={old_price}, type={trade_type}")
            print(f"    New: qty={quantity}, price={price}, type={trade_type}")

            # Step 1: Reverse the old trade effect
            # If original was BUY, reverse with SELL. If original was SELL, reverse with BUY.
            reverse_type = 'SELL' if trade_type == 'BUY' else 'BUY'

            if old_quantity > 0 and old_price > 0:
                print(f"==> Trade Event Worker: Reversing old position ({reverse_type} {old_quantity}@{old_price})")
                success1, msg1, _ = position_service.calculate_position(
                    portfolio_id=portfolio_id,
                    security_id=security_id,
                    trade_type=reverse_type,
                    quantity=old_quantity,
                    price=old_price,
                    charges=old_charges,
                    position_date=position_date,
                    trade_id=trade_id,
                    updated_by=created_by,
                    security_currency=new_trade.get('security_currency'),
                    portfolio_currency=new_trade.get('portfolio_currency'),
                    isin=new_trade.get('isin'),
                    security_name=new_trade.get('security_name'),
                    custodian=new_trade.get('custodian', ''),
                    sub_custodian=new_trade.get('sub_custodian', ''),
                )
                if not success1:
                    print(f"==> Trade Event Worker: Reversal warning: {msg1}")

            # Step 2: Apply the new trade effect
            print(f"==> Trade Event Worker: Applying new position ({trade_type} {quantity}@{price})")
            success, msg, result = position_service.calculate_position(
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=trade_type,
                quantity=quantity,
                price=price,
                charges=charges,
                position_date=position_date,
                trade_id=trade_id,
                updated_by=created_by,
                security_currency=new_trade.get('security_currency'),
                portfolio_currency=new_trade.get('portfolio_currency'),
                isin=new_trade.get('isin'),
                security_name=new_trade.get('security_name'),
                custodian=new_trade.get('custodian', ''),
                sub_custodian=new_trade.get('sub_custodian', ''),
            )

            if success:
                print(f"==> Trade Event Worker: POSITION_MODIFY completed for trade {trade_id}: {msg}")
                notify_user(created_by, EVT_AVP_COMPLETED, {
                    'trade_id': trade_id,
                    'message': f'Position updated for modified trade {trade_id}',
                })
            else:
                print(f"==> Trade Event Worker: POSITION_MODIFY warning for trade {trade_id}: {msg}")
                notify_user(created_by, EVT_AVP_FAILED, {
                    'trade_id': trade_id,
                    'message': f'Position update failed for trade {trade_id}: {msg}',
                })

        def process_position_cancel_event(event, event_data):
            """Process a POSITION_CANCEL event - reverse position when trade is cancelled.

            Steps:
            1. Get the original trade details
            2. Apply opposite trade (BUY -> SELL, SELL -> BUY) to reverse
            """
            from trade.services.position_service import position_service

            trade_id = event['trade_id']
            created_by = event['created_by']

            # Get trade data (POSITION_CANCEL passes trade data directly, not nested)
            portfolio_id = event_data.get('portfolio_short_name', '')
            security_id = event_data.get('security_label', '')
            original_trade_type = event_data.get('trade_type', '')
            quantity = Decimal(str(event_data.get('quantity', 0) or 0))
            price = Decimal(str(event_data.get('price', 0) or 0))
            trade_date = event_data.get('trade_date', '')
            settle_date = event_data.get('settle_date', '')
            position_date = settle_date or trade_date

            # Determine reversal type
            reverse_type = 'SELL' if original_trade_type == 'BUY' else 'BUY'

            print(f"==> Trade Event Worker: POSITION_CANCEL processing trade {trade_id}")
            print(f"    Reversing {original_trade_type} with {reverse_type} ({quantity}@{price})")

            # Process reversal (no charges on cancellation reversal)
            success, msg, result = position_service.calculate_position(
                portfolio_id=portfolio_id,
                security_id=security_id,
                trade_type=reverse_type,
                quantity=quantity,
                price=price,
                charges=Decimal('0'),  # No charges on reversal
                position_date=position_date,
                trade_id=trade_id,
                updated_by=created_by,
                security_currency=event_data.get('security_currency'),
                portfolio_currency=event_data.get('portfolio_currency'),
                isin=event_data.get('isin'),
                security_name=event_data.get('security_name'),
                custodian=event_data.get('custodian', ''),
                sub_custodian=event_data.get('sub_custodian', ''),
            )

            if success:
                print(f"==> Trade Event Worker: POSITION_CANCEL completed for trade {trade_id}: {msg}")
                notify_user(created_by, EVT_AVP_COMPLETED, {
                    'trade_id': trade_id,
                    'message': f'Position reversed for cancelled trade {trade_id}',
                })
            else:
                print(f"==> Trade Event Worker: POSITION_CANCEL warning for trade {trade_id}: {msg}")
                notify_user(created_by, EVT_AVP_FAILED, {
                    'trade_id': trade_id,
                    'message': f'Position reversal failed for trade {trade_id}: {msg}',
                })

        def mark_processing(event_id, event):
            """Mark event as PROCESSING before starting work (prevents double-processing)."""
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            upsert_query = f"""
            UPSERT INTO {DATABASE}.{EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status,
             retry_count, error_message, created_by, created_at, processing_started_at, processed_at)
            VALUES (
                {event_id},
                {event['trade_id']},
                '{event['deal_number']}',
                '{event['event_type']}',
                '{event['event_data'].replace("'", "''")}',
                'PROCESSING',
                {event.get('retry_count', 0)},
                NULL,
                '{event['created_by']}',
                '{event['created_at']}',
                '{timestamp}',
                NULL
            )
            """
            impala_manager.execute_write(upsert_query, database=DATABASE)

        def mark_completed(event_id, event):
            """Mark event as completed."""
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processing_started_at = event.get('processing_started_at') or timestamp
            upsert_query = f"""
            UPSERT INTO {DATABASE}.{EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status,
             retry_count, error_message, created_by, created_at, processing_started_at, processed_at)
            VALUES (
                {event_id},
                {event['trade_id']},
                '{event['deal_number']}',
                '{event['event_type']}',
                '{event['event_data'].replace("'", "''")}',
                'COMPLETED',
                {event.get('retry_count', 0)},
                NULL,
                '{event['created_by']}',
                '{event['created_at']}',
                '{processing_started_at}',
                '{timestamp}'
            )
            """
            impala_manager.execute_write(upsert_query, database=DATABASE)

        def mark_failed(event_id, event, error_message, retry_count):
            """Mark event as failed with error message."""
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_retry_count = retry_count + 1
            status = 'FAILED' if new_retry_count >= 3 else 'PENDING'
            error_escaped = error_message.replace("'", "''")[:500]
            processing_started_at = event.get('processing_started_at') or timestamp

            upsert_query = f"""
            UPSERT INTO {DATABASE}.{EVENT_QUEUE_TABLE}
            (event_id, trade_id, deal_number, event_type, event_data, status,
             retry_count, error_message, created_by, created_at, processing_started_at, processed_at)
            VALUES (
                {event_id},
                {event['trade_id']},
                '{event['deal_number']}',
                '{event['event_type']}',
                '{event['event_data'].replace("'", "''")}',
                '{status}',
                {new_retry_count},
                '{error_escaped}',
                '{event['created_by']}',
                '{event['created_at']}',
                '{processing_started_at}',
                '{timestamp}'
            )
            """
            impala_manager.execute_write(upsert_query, database=DATABASE)

        STALE_PROCESSING_TIMEOUT_SECONDS = 300  # 5 minutes
        from datetime import timedelta as _timedelta

        while not _shutdown_requested:
            try:
                # Compute stale-PROCESSING threshold (events running > 5 min are re-fetched)
                stale_threshold = (
                    datetime.now() - _timedelta(seconds=STALE_PROCESSING_TIMEOUT_SECONDS)
                ).strftime('%Y-%m-%d %H:%M:%S')

                # Fetch PENDING events AND stale PROCESSING events (stuck > 5 min)
                query = f"""
                SELECT event_id, trade_id, deal_number, event_type, event_data,
                       retry_count, created_by, created_at, processing_started_at
                FROM {DATABASE}.{EVENT_QUEUE_TABLE}
                WHERE status = 'PENDING'
                   OR (status = 'PROCESSING'
                       AND processing_started_at IS NOT NULL
                       AND processing_started_at < '{stale_threshold}')
                ORDER BY created_at
                LIMIT {TRADE_EVENT_WORKER_BATCH_SIZE}
                """
                events = impala_manager.execute_query(query, database=DATABASE)

                if events:
                    print(f"==> Trade Event Worker: Processing {len(events)} events...")
                    for event in events:
                        if _shutdown_requested:
                            break
                        event_id = event['event_id']
                        try:
                            # Mark as PROCESSING first — prevents other workers/threads picking same event
                            mark_processing(event_id, event)
                            # Store processing_started_at on event dict for mark_completed/mark_failed
                            event['processing_started_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                            event_type = event.get('event_type')
                            event_data = json.loads(event.get('event_data', '{}'))

                            if event_type == 'HISTORY':
                                process_history_event(event, event_data)
                            elif event_type == 'SETTLEMENT':
                                process_settlement_event(event, event_data)
                            elif event_type == 'POSITION_MODIFY':
                                process_position_modify_event(event, event_data)
                            elif event_type == 'POSITION_CANCEL':
                                process_position_cancel_event(event, event_data)
                            else:
                                print(f"==> Trade Event Worker: Unknown event type: {event_type}")

                            mark_completed(event_id, event)

                        except Exception as e:
                            print(f"==> Trade Event Worker: Error processing event {event_id}: {e}")
                            mark_failed(event_id, event, str(e), event.get('retry_count', 0))
                else:
                    # No events, sleep
                    time.sleep(TRADE_EVENT_WORKER_POLL_INTERVAL)

            except Exception as e:
                print(f"==> Trade Event Worker: Error in loop: {e}")
                time.sleep(TRADE_EVENT_WORKER_POLL_INTERVAL)

        print("==> Trade Event Worker: Stopped")

    _trade_event_worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="TradeEventWorker")
    _trade_event_worker_thread.start()
    print("==> Trade Event Worker: Thread started")


def start_position_worker():
    """
    Start the Position Queue Worker in a background thread.

    This worker processes position calculations asynchronously,
    decoupling them from trade save for faster response times.

    Queue Table: cis_position_queue

    Features:
    - Processes T+0, backdated settlements from cis_position_queue
    - SLA: < 5 minutes from queue to position update
    - Auto-retry with max 3 attempts
    - Chain recalculation for backdated trades
    """
    global _position_worker_thread, _shutdown_requested

    if not POSITION_WORKER_ENABLED:
        print("==> Position Worker: DISABLED (POSITION_WORKER_ENABLED=0)")
        return

    print("==> Starting Position Queue Worker...")
    print(f"    Poll Interval: {POSITION_WORKER_POLL_INTERVAL}s")
    print(f"    Batch Size: {POSITION_WORKER_BATCH_SIZE}")

    def _worker_loop():
        """Main worker loop - runs in background thread."""
        global _shutdown_requested

        # Import Django and services inside thread to ensure proper initialization
        import django
        django.setup()

        from trade.services.position_queue_service import position_queue_service

        print("==> Position Worker: Started")

        while not _shutdown_requested:
            try:
                # Get pending items from queue
                pending = position_queue_service.get_pending_items(
                    limit=POSITION_WORKER_BATCH_SIZE
                )

                if pending:
                    print(f"==> Position Worker: Processing {len(pending)} items...")
                    for item in pending:
                        if _shutdown_requested:
                            break
                        try:
                            position_queue_service._process_item(item)
                        except Exception as e:
                            print(f"==> Position Worker: Error processing item {item.get('queue_id')}: {e}")

                    # Log stats after batch
                    stats = position_queue_service.get_queue_statistics()
                    print(f"==> Position Worker: Queue stats - "
                          f"pending={stats.get('pending', 0)}, "
                          f"completed={stats.get('completed', 0)}, "
                          f"failed={stats.get('failed', 0)}")
                else:
                    # No items, sleep
                    time.sleep(POSITION_WORKER_POLL_INTERVAL)

            except Exception as e:
                print(f"==> Position Worker: Error in loop: {e}")
                time.sleep(POSITION_WORKER_POLL_INTERVAL)

        print("==> Position Worker: Stopped")

    _position_worker_thread = threading.Thread(target=_worker_loop, daemon=True, name="PositionQueueWorker")
    _position_worker_thread.start()
    print("==> Position Worker: Thread started")


def start_worker_health_monitor():
    """
    Start a background thread to monitor worker health and restart if needed.

    Every 60 s:
    - Checks thread liveness for TradeEventWorker and PositionQueueWorker
    - Restarts any dead worker thread
    - Polls /trade/api/worker-health/ HTTP endpoint and logs the response
    - Prints queue stats (pending / completed / failed counts)
    """
    if not TRADE_EVENT_WORKER_ENABLED and not POSITION_WORKER_ENABLED:
        return

    import sys as _sys
    _this_module = _sys.modules[__name__]

    # Resolve the app port once — used for HTTP health check
    _app_port = os.environ.get("CDSW_APP_PORT") or os.environ.get("PORT", "8080")

    def _monitor():
        while not getattr(_this_module, '_shutdown_requested', False):
            time.sleep(60)

            try:
                # ── Thread liveness checks ──────────────────────────────────
                if TRADE_EVENT_WORKER_ENABLED:
                    t = getattr(_this_module, '_trade_event_worker_thread', None)
                    if t and not t.is_alive():
                        print("==> WorkerHealthMonitor: TradeEventWorker thread died — restarting...")
                        start_trade_event_worker()
                    else:
                        print("==> WorkerHealthMonitor: TradeEventWorker OK")

                if POSITION_WORKER_ENABLED:
                    p = getattr(_this_module, '_position_worker_thread', None)
                    if p and not p.is_alive():
                        print("==> WorkerHealthMonitor: PositionWorker thread died — restarting...")
                        start_position_worker()
                    else:
                        print("==> WorkerHealthMonitor: PositionWorker OK")

                # ── HTTP health endpoint ────────────────────────────────────
                try:
                    result = subprocess.run(
                        ["curl", "-s", "--max-time", "5",
                         f"http://127.0.0.1:{_app_port}/trade/api/worker-health/"],
                        capture_output=True, text=True
                    )
                    health_out = (result.stdout or "").strip()[:200]
                    if health_out:
                        print(f"==> WorkerHealthMonitor: HTTP health: {health_out}")
                except Exception as he:
                    print(f"==> WorkerHealthMonitor: HTTP health check failed: {he}")

                # ── Kerberos ticket status ──────────────────────────────────
                try:
                    klist = subprocess.run(["klist", "-s"], capture_output=True)
                    if klist.returncode != 0:
                        print("==> WorkerHealthMonitor: Kerberos ticket EXPIRED — attempting renewal...")
                        subprocess.run(["kinit", "-R"], capture_output=True)
                except Exception as ke:
                    print(f"==> WorkerHealthMonitor: klist check failed: {ke}")

            except Exception as e:
                print(f"==> WorkerHealthMonitor: Error - {e}")

    monitor_thread = threading.Thread(target=_monitor, daemon=True, name="WorkerHealthMonitor")
    monitor_thread.start()
    print("==> WorkerHealthMonitor: Started (60s interval)")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown_requested
    print(f"\n==> Received signal {signum}, initiating graceful shutdown...")
    _shutdown_requested = True


def main():
    """Main entry point for CML application deployment."""
    global _shutdown_requested

    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if WORKDIR:
        os.chdir(WORKDIR)
        # Add project root to sys.path so 'core', 'trade', etc. are importable
        # by uvicorn/daphne worker processes that inherit this environment.
        if WORKDIR not in sys.path:
            sys.path.insert(0, WORKDIR)

    # ==================== Environment Detection ====================
    # Get environment-specific configuration (SIT, UAT, PROD, DR)
    cis_env, keytab, principal, cache = get_environment_config()
    env_config = ENV_CONFIGS.get(cis_env, {})

    print("=" * 60)
    print(f"  CIS Trade Hive - {env_config.get('name', cis_env)} Environment")
    print("=" * 60)

    # Set Django environment
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", DJANGO_SETTINGS)
    os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "*")

    # Set CIS_ENV for settings.py to pick up
    os.environ["CIS_ENV"] = cis_env

    # Debug mode off for UAT, PROD, DR — only True for SIT/local
    if cis_env in ("SIT",):
        os.environ.setdefault("DJANGO_DEBUG", "True")
    else:
        os.environ.setdefault("DJANGO_DEBUG", "False")

    # ==================== REST Proxy Configuration ====================
    # Enable REST proxy mode for Hive operations (bypasses direct Hive connections)
    # This is required in CML where glibc/SASL issues prevent direct connections
    os.environ.setdefault("USE_REST_PROXY", "true")

    # REST Proxy URL - Flask app running on edge node
    # Change this to your edge node IP/hostname where app_v2.py is running
    os.environ.setdefault("HIVE_PROXY_URL", "http://172.29.22.185:5000")

    # Database name for Hive operations
    os.environ.setdefault("HIVE_DATABASE", "mrw_ima")

    # Optional: API key for proxy authentication (if configured on proxy)
    # os.environ.setdefault("HIVE_PROXY_API_KEY", "your-api-key")

    # Timeout for proxy requests (seconds)
    os.environ.setdefault("HIVE_TIMEOUT", "300")

    # ==================== Kerberos Authentication ====================
    # Kerberos config from environment detection
    print(f"==> Environment: {cis_env} ({env_config.get('name', 'Unknown')})")
    print(f"==> Keytab: {keytab}")
    print(f"==> Principal: {principal}")

    # Obtain Kerberos TGT up-front (before commands that hit Impala/Hive)
    kinit_with_keytab(keytab, principal, cache=cache)
    start_kerberos_renewal_loop(keytab, principal, interval_sec=3600, cache=cache)

    python_exec = sys.executable

    # Run Django management commands
    run([python_exec, "manage.py", "migrate"])
    try:
        run([python_exec, "manage.py", "verify_rbac"], check=False)
    except Exception:
        print("verify_rbac command not found; continuing...")

    try:
        run([python_exec, "manage.py", "create_hive_db"], check=False)
    except Exception:
        print("create_hive_db failed or not available; continuing...")

    if COLLECT_STATIC:
        os.environ.setdefault("DJANGO_COLLECTSTATIC", "1")
        run([python_exec, "manage.py", "collectstatic", "--noinput"], check=True)

    # ==================== Background Workers ====================
    # Workers are started via gunicorn post_fork hook (see gunicorn_conf below)
    # so they run INSIDE the worker process and share its InMemoryChannelLayer.
    # Starting them here in the parent would give them a separate channel layer
    # instance that WebSocket consumers (in the forked worker) cannot see.
    # 3. Health Monitor only — watches thread liveness from the parent process
    start_worker_health_monitor()

    # Server configuration
    # Uses gunicorn + uvicorn worker (ASGI) so WebSocket notifications work.
    # Falls back to daphne if uvicorn is not installed.
    port = os.environ.get("CDSW_APP_PORT") or os.environ.get("PORT", "8080")
    bind = f"127.0.0.1:{os.environ.get('CDSW_APP_PORT', port)}"
    # InMemoryChannelLayer is NOT shared across gunicorn worker processes.
    # When REDIS_URL is set the channel layer is Redis-backed and workers > 1 is safe.
    # Without Redis, force workers=1 so the Trade Event Worker thread and the
    # WebSocket consumer are in the same process and share the same channel layer.
    _redis_url = os.environ.get('REDIS_URL', '')
    if os.environ.get("WORKERS"):
        workers = os.environ.get("WORKERS")
    elif _redis_url:
        workers = str(8)
    else:
        workers = str(1)
        print("==> WARNING: REDIS_URL not set — forcing workers=1 so InMemoryChannelLayer")
        print("==>          is shared between Trade Event Worker and WebSocket consumers.")
        print("==>          Set REDIS_URL to enable multi-worker mode with real-time notifications.")
    timeout = os.environ.get("TIMEOUT", "120")
    keepalive = os.environ.get("KEEPALIVE", "5")
    asgi_app = f"{DJANGO_SETTINGS.rsplit('.', 1)[0]}.asgi:application"

    print("=" * 60)
    print("  Runtime Configuration")
    print("=" * 60)
    print(f"  Environment:         {cis_env} ({env_config.get('name', 'Unknown')})")
    print(f"  Django Settings:     {os.environ['DJANGO_SETTINGS_MODULE']}")
    print(f"  Debug Mode:          {os.environ.get('DJANGO_DEBUG')}")
    print(f"  Allowed Hosts:       {os.environ.get('DJANGO_ALLOWED_HOSTS')}")
    print(f"  Collect Static:      {COLLECT_STATIC}")
    print("")
    print("  ASGI Server (WebSocket-capable):")
    print(f"    Bind:              {bind}")
    print(f"    Workers:           {workers}")
    print(f"    Worker Class:      uvicorn.workers.UvicornWorker (ASGI)")
    print(f"    Timeout:           {timeout}")
    print(f"    Keep-alive:        {keepalive}")
    print(f"    App:               {asgi_app}")
    print("")
    print("  Kerberos:")
    print(f"    Keytab:            {keytab}")
    print(f"    Principal:         {principal}")
    print(f"    Cache:             {cache}")
    print("")
    print("  REST Proxy:")
    print(f"    Enabled:           {os.environ.get('USE_REST_PROXY')}")
    print(f"    URL:               {os.environ.get('HIVE_PROXY_URL')}")
    print(f"    Database:          {os.environ.get('HIVE_DATABASE')}")
    print(f"    Timeout:           {os.environ.get('HIVE_TIMEOUT')}")
    print("")
    print("  Trade Event Worker:")
    print(f"    Enabled:           {TRADE_EVENT_WORKER_ENABLED}")
    print(f"    Poll Interval:     {TRADE_EVENT_WORKER_POLL_INTERVAL}s")
    print(f"    Batch Size:        {TRADE_EVENT_WORKER_BATCH_SIZE}")
    print(f"    Queue Table:       cis_trade_event_queue")
    print(f"    Events:            HISTORY, SETTLEMENT")
    print("")
    print("  Position Worker:")
    print(f"    Enabled:           {POSITION_WORKER_ENABLED}")
    print(f"    Poll Interval:     {POSITION_WORKER_POLL_INTERVAL}s")
    print(f"    Batch Size:        {POSITION_WORKER_BATCH_SIZE}")
    print(f"    Queue Table:       cis_position_queue")
    print("=" * 60)

    # Write a gunicorn config file so worker processes don't re-run this
    # startup script on fork (workers import the ASGI app, not cml_app.py).
    gunicorn_conf = "/tmp/cis_gunicorn.conf.py"
    gunicorn_conf_lines = [
        "# Auto-generated by cml_app.py — do not edit manually",
        f"bind = '{bind}'",
        f"workers = {workers}",
        "worker_class = 'uvicorn.workers.UvicornWorker'",
        f"timeout = {timeout}",
        f"keepalive = {keepalive}",
        "accesslog = '-'",
        "errorlog  = '-'",
        "loglevel  = 'info'",
        "import sys, os",
        f"_root = {repr(WORKDIR)}",
        "if _root not in sys.path: sys.path.insert(0, _root)",
        f"os.environ.setdefault('PYTHONPATH', {repr(WORKDIR)})",
        # post_fork runs inside the worker process after gunicorn forks it.
        # Starting the Trade Event Worker here ensures the worker thread and
        # the WebSocket consumer share the SAME InMemoryChannelLayer instance
        # (same process), so notify_user() actually reaches connected clients.
        "",
        "def post_fork(server, worker):",
        "    import sys as _sys",
        f"    _root2 = {repr(WORKDIR)}",
        "    if _root2 not in _sys.path: _sys.path.insert(0, _root2)",
        "    try:",
        "        import config.cml_app as _cml",
        "        _cml.start_trade_event_worker()",
        "        _cml.start_position_worker()",
        "        print(f'==> post_fork: workers started in gunicorn worker pid={worker.pid}')",
        "    except Exception as _e:",
        "        print(f'==> post_fork: worker start failed: {_e}')",
    ]
    with open(gunicorn_conf, "w") as _f:
        _f.write("\n".join(gunicorn_conf_lines) + "\n")
    print(f"==> Wrote gunicorn config: {gunicorn_conf}")

    import shutil

    # Prefer venv-relative binaries (same dir as sys.executable) so CML's venv
    # is found even when its bin/ directory is not on the system PATH.
    _bin_dir = os.path.dirname(sys.executable)

    def _find_exe(name):
        """Return full path to name in venv bin dir, falling back to PATH search."""
        venv_path = os.path.join(_bin_dir, name)
        if os.path.isfile(venv_path) and os.access(venv_path, os.X_OK):
            return venv_path
        return shutil.which(name)  # fallback to PATH

    _gunicorn = _find_exe("gunicorn")
    _daphne   = _find_exe("daphne")
    print(f"==> ASGI server detection: python={sys.executable}")
    print(f"==> ASGI server detection: gunicorn={_gunicorn or 'NOT FOUND'}")
    print(f"==> ASGI server detection: daphne={_daphne or 'NOT FOUND'}")

    if _gunicorn:
        try:
            import uvicorn  # noqa: F401 — verify importable before passing worker-class
            # gunicorn forks worker processes — start_trade_event_worker() is called
            # inside the worker via the post_fork hook in gunicorn_conf, NOT here.
            print(f"==> Starting gunicorn (UvicornWorker/ASGI) → {bind}")
            run([_gunicorn, "--config", gunicorn_conf, asgi_app])
        except ImportError:
            print("==> uvicorn not installed — falling back to daphne (ASGI)")
            if _daphne:
                # daphne is a single-process server — start workers here directly.
                start_trade_event_worker()
                start_position_worker()
                run([_daphne, "-b", "127.0.0.1", "-p", port, asgi_app])
            else:
                print("==> WARNING: No ASGI server found. WebSocket notifications will NOT work!")
                print("==>          Install: pip install uvicorn  OR  pip install daphne")
                run([sys.executable, "manage.py", "runserver", bind])
    elif _daphne:
        # daphne is a single-process server — start workers here directly.
        start_trade_event_worker()
        start_position_worker()
        print(f"==> Starting daphne (ASGI) → {bind}")
        run([_daphne, "-b", "127.0.0.1", "-p", port, asgi_app])
    else:
        print("==> WARNING: No ASGI server found. WebSocket notifications will NOT work!")
        print("==>          Install: pip install uvicorn  OR  pip install daphne")
        run([sys.executable, "manage.py", "runserver", bind])


if __name__ == "__main__":
    main()
