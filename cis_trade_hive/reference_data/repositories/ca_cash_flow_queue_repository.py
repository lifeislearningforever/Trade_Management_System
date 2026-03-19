"""
Corporate Action Cash Flow Queue Repository

Data access layer for CA cash flow queue operations in Kudu tables.
Manages the queue of corporate actions pending cash flow generation.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from decimal import Decimal

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class CACashFlowQueueRepository:
    """Repository for CA cash flow queue operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_ca_cash_flow_queue'
    LOG_TABLE_NAME = 'cis_ca_cash_flow_log'

    # Queue status constants
    STATUS_PENDING = 'PENDING'
    STATUS_PROCESSING = 'PROCESSING'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'

    # Maximum retry attempts
    MAX_RETRIES = 3

    @staticmethod
    def escape_value(value: Any) -> str:
        """
        Escape value for SQL query.
        Uses backslash escaping for Impala compatibility.
        """
        if value is None or value == '':
            return 'NULL'
        if isinstance(value, bool):
            return 'true' if value else 'false'
        if isinstance(value, (int, float, Decimal)):
            return str(value)
        # String - escape backslashes and single quotes
        escaped = str(value).replace('\\', '\\\\').replace("'", "\\'")
        return f"'{escaped}'"

    @staticmethod
    def insert(queue_data: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
        """
        Insert a new CA into the processing queue.

        Args:
            queue_data: Dictionary with queue entry data

        Returns:
            Tuple of (success, queue_id)
        """
        try:
            queue_id = int(datetime.now().timestamp() * 1000)
            timestamp_ms = queue_id

            insert_sql = f"""
            UPSERT INTO {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME} (
                queue_id, ca_id, ca_number, ca_type,
                security_name, portfolio_name,
                ex_date, record_date, payment_date,
                price, currency,
                status, retry_count, error_message,
                cash_flows_created, total_amount, processed_at,
                created_at, created_by
            ) VALUES (
                {queue_id},
                {CACashFlowQueueRepository.escape_value(queue_data.get('ca_id'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('ca_number'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('ca_type'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('security_name'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('portfolio_name'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('ex_date'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('record_date'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('payment_date'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('price'))},
                {CACashFlowQueueRepository.escape_value(queue_data.get('currency'))},
                '{CACashFlowQueueRepository.STATUS_PENDING}',
                CAST(0 AS BIGINT),
                NULL,
                CAST(0 AS BIGINT),
                NULL,
                NULL,
                {timestamp_ms},
                {CACashFlowQueueRepository.escape_value(queue_data.get('created_by', 'system'))}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=CACashFlowQueueRepository.DATABASE)

            if success:
                logger.info(f"Queued CA {queue_data.get('ca_number')} for cash flow processing (queue_id: {queue_id})")
                return True, queue_id
            else:
                logger.error(f"Failed to queue CA {queue_data.get('ca_number')}")
                return False, None

        except Exception as e:
            logger.error(f"Error inserting CA queue entry: {str(e)}")
            return False, None

    @staticmethod
    def get_pending(limit: int = 100, payment_date: str = None) -> List[Dict[str, Any]]:
        """
        Get pending queue entries for processing.

        Args:
            limit: Maximum entries to return
            payment_date: Optional filter by payment date (YYYY-MM-DD)

        Returns:
            List of pending queue entries
        """
        try:
            query = f"""
            SELECT *
            FROM {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            WHERE status = '{CACashFlowQueueRepository.STATUS_PENDING}'
              AND retry_count < {CACashFlowQueueRepository.MAX_RETRIES}
            """

            if payment_date:
                query += f" AND payment_date = {CACashFlowQueueRepository.escape_value(payment_date)}"

            query += f" ORDER BY created_at ASC LIMIT {limit}"

            result = impala_manager.execute_query(query, database=CACashFlowQueueRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching pending CA queue entries: {str(e)}")
            return []

    @staticmethod
    def get_by_id(queue_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific queue entry by ID.

        Args:
            queue_id: Queue entry ID

        Returns:
            Queue entry dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            WHERE queue_id = {queue_id}
            """

            result = impala_manager.execute_query(query, database=CACashFlowQueueRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching queue entry {queue_id}: {str(e)}")
            return None

    @staticmethod
    def get_by_ca_id(ca_id: int) -> List[Dict[str, Any]]:
        """
        Get queue entries for a specific corporate action.

        Args:
            ca_id: Corporate Action ID

        Returns:
            List of queue entries
        """
        try:
            query = f"""
            SELECT *
            FROM {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            WHERE ca_id = {ca_id}
            ORDER BY created_at DESC
            """

            result = impala_manager.execute_query(query, database=CACashFlowQueueRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching queue entries for CA {ca_id}: {str(e)}")
            return []

    @staticmethod
    def update_status(
        queue_id: int,
        status: str,
        error_message: str = None,
        cash_flows_created: int = None,
        total_amount: Decimal = None
    ) -> bool:
        """
        Update queue entry status.

        Args:
            queue_id: Queue entry ID
            status: New status (PENDING, PROCESSING, COMPLETED, FAILED)
            error_message: Error details if failed
            cash_flows_created: Number of cash flows created
            total_amount: Total amount of cash flows

        Returns:
            True if successful
        """
        try:
            set_clauses = [f"status = {CACashFlowQueueRepository.escape_value(status)}"]

            if error_message is not None:
                set_clauses.append(f"error_message = {CACashFlowQueueRepository.escape_value(error_message)}")

            if cash_flows_created is not None:
                set_clauses.append(f"cash_flows_created = {cash_flows_created}")

            if total_amount is not None:
                set_clauses.append(f"total_amount = {total_amount}")

            if status in [CACashFlowQueueRepository.STATUS_COMPLETED, CACashFlowQueueRepository.STATUS_FAILED]:
                set_clauses.append(f"processed_at = {int(datetime.now().timestamp() * 1000)}")

            update_sql = f"""
            UPDATE {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE queue_id = {queue_id}
            """

            success = impala_manager.execute_write(update_sql, database=CACashFlowQueueRepository.DATABASE)

            if success:
                logger.info(f"Updated queue entry {queue_id} status to {status}")

            return success

        except Exception as e:
            logger.error(f"Error updating queue entry {queue_id}: {str(e)}")
            return False

    @staticmethod
    def mark_processing(queue_id: int) -> bool:
        """
        Mark queue entry as processing.

        Args:
            queue_id: Queue entry ID

        Returns:
            True if successful
        """
        return CACashFlowQueueRepository.update_status(
            queue_id,
            CACashFlowQueueRepository.STATUS_PROCESSING
        )

    @staticmethod
    def mark_completed(
        queue_id: int,
        cash_flows_created: int = 0,
        total_amount: Decimal = Decimal('0')
    ) -> bool:
        """
        Mark queue entry as completed.

        Args:
            queue_id: Queue entry ID
            cash_flows_created: Number of cash flows created
            total_amount: Total amount of cash flows

        Returns:
            True if successful
        """
        return CACashFlowQueueRepository.update_status(
            queue_id,
            CACashFlowQueueRepository.STATUS_COMPLETED,
            cash_flows_created=cash_flows_created,
            total_amount=total_amount
        )

    @staticmethod
    def mark_failed(queue_id: int, error_message: str) -> bool:
        """
        Mark queue entry as failed and increment retry count.

        Args:
            queue_id: Queue entry ID
            error_message: Error details

        Returns:
            True if successful
        """
        try:
            update_sql = f"""
            UPDATE {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            SET status = '{CACashFlowQueueRepository.STATUS_FAILED}',
                error_message = {CACashFlowQueueRepository.escape_value(error_message)},
                retry_count = retry_count + 1,
                processed_at = {int(datetime.now().timestamp() * 1000)}
            WHERE queue_id = {queue_id}
            """

            success = impala_manager.execute_write(update_sql, database=CACashFlowQueueRepository.DATABASE)

            if success:
                logger.warning(f"Marked queue entry {queue_id} as failed: {error_message}")

            return success

        except Exception as e:
            logger.error(f"Error marking queue entry {queue_id} as failed: {str(e)}")
            return False

    @staticmethod
    def reset_for_retry(queue_id: int) -> bool:
        """
        Reset a failed queue entry for retry.

        Args:
            queue_id: Queue entry ID

        Returns:
            True if successful
        """
        try:
            update_sql = f"""
            UPDATE {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            SET status = '{CACashFlowQueueRepository.STATUS_PENDING}',
                error_message = NULL
            WHERE queue_id = {queue_id}
              AND retry_count < {CACashFlowQueueRepository.MAX_RETRIES}
            """

            success = impala_manager.execute_write(update_sql, database=CACashFlowQueueRepository.DATABASE)

            if success:
                logger.info(f"Reset queue entry {queue_id} for retry")

            return success

        except Exception as e:
            logger.error(f"Error resetting queue entry {queue_id}: {str(e)}")
            return False

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Dictionary with queue statistics
        """
        try:
            query = f"""
            SELECT
                status,
                COUNT(*) as count,
                SUM(cash_flows_created) as total_cash_flows,
                SUM(total_amount) as total_amount
            FROM {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.TABLE_NAME}
            GROUP BY status
            """

            result = impala_manager.execute_query(query, database=CACashFlowQueueRepository.DATABASE)

            stats = {
                'pending': 0,
                'processing': 0,
                'completed': 0,
                'failed': 0,
                'total_cash_flows': 0,
                'total_amount': Decimal('0')
            }

            if result:
                for row in result:
                    status = row.get('status', '').lower()
                    if status in stats:
                        stats[status] = row.get('count', 0)
                    if status == 'completed':
                        stats['total_cash_flows'] = row.get('total_cash_flows', 0) or 0
                        stats['total_amount'] = Decimal(str(row.get('total_amount', 0) or 0))

            return stats

        except Exception as e:
            logger.error(f"Error fetching queue statistics: {str(e)}")
            return {}

    # =========================================================================
    # Log Table Operations
    # =========================================================================

    @staticmethod
    def insert_log(log_data: Dict[str, Any]) -> Tuple[bool, Optional[int]]:
        """
        Insert a processing log entry.

        Args:
            log_data: Dictionary with log entry data

        Returns:
            Tuple of (success, log_id)
        """
        try:
            log_id = int(datetime.now().timestamp() * 1000)
            timestamp_ms = log_id

            insert_sql = f"""
            UPSERT INTO {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.LOG_TABLE_NAME} (
                log_id, queue_id, ca_id, cash_flow_id,
                portfolio_short_name, security_label,
                quantity, amount, currency,
                status, error_message,
                created_at
            ) VALUES (
                {log_id},
                {CACashFlowQueueRepository.escape_value(log_data.get('queue_id'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('ca_id'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('cash_flow_id'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('portfolio_short_name'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('security_name'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('quantity'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('amount'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('currency'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('status', 'SUCCESS'))},
                {CACashFlowQueueRepository.escape_value(log_data.get('error_message'))},
                {timestamp_ms}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=CACashFlowQueueRepository.DATABASE)

            if success:
                return True, log_id
            else:
                return False, None

        except Exception as e:
            logger.error(f"Error inserting CA cash flow log: {str(e)}")
            return False, None

    @staticmethod
    def get_logs_by_queue_id(queue_id: int) -> List[Dict[str, Any]]:
        """
        Get processing logs for a queue entry.

        Args:
            queue_id: Queue entry ID

        Returns:
            List of log entries
        """
        try:
            query = f"""
            SELECT *
            FROM {CACashFlowQueueRepository.DATABASE}.{CACashFlowQueueRepository.LOG_TABLE_NAME}
            WHERE queue_id = {queue_id}
            ORDER BY created_at ASC
            """

            result = impala_manager.execute_query(query, database=CACashFlowQueueRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching logs for queue {queue_id}: {str(e)}")
            return []


# Create singleton instance
ca_cash_flow_queue_repository = CACashFlowQueueRepository()
