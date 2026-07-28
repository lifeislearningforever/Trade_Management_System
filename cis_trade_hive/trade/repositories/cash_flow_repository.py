"""
Cash Flow Repository

Data access layer for cash flow operations using Kudu via Impala.
Implements:
- CRUD operations for cash flows
- Four-Eyes (Maker-Checker) workflow
- Audit trail with field-level change tracking
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class CashFlowRepository:
    """Repository for cash flow operations with Kudu via Impala"""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_cash_flow'
    HISTORY_TABLE = 'cis_cash_flow_history'

    # Workflow Status Constants (same as Portfolio)
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_PENDING_APPROVAL = 'PENDING_APPROVAL'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'

    # Status groups
    MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_REJECTED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED]

    @staticmethod
    def escape_value(val: Any) -> str:
        """Escape value for SQL query. Impala uses C-style \\' escaping, not doubled quotes."""
        if val is None or val == '':
            return 'NULL'
        if isinstance(val, str):
            s = val.replace('\\', '\\\\').replace(chr(39), '\\' + chr(39))
            return f"'{s}'"
        if isinstance(val, bool):
            return 'true' if val else 'false'
        return str(val)

    @staticmethod
    def to_decimal(val: Any, default: float = 0) -> str:
        """Convert value to decimal string for SQL (no quotes)."""
        if val is None or val == '':
            return str(default)
        try:
            if isinstance(val, str):
                val = val.strip()
                if val == '':
                    return str(default)
                return str(float(val))
            return str(float(val))
        except (ValueError, TypeError):
            return str(default)

    # =========================================================================
    # READ OPERATIONS
    # =========================================================================

    @staticmethod
    def get_all(
        limit: int = 1000,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
        portfolio_short_name: Optional[str] = None,
        portfolios: Optional[List[str]] = None,
        cash_flow_type: Optional[str] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Fetch all cash flows with optional filters.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            status: Filter by workflow status
            search: Search term for cash_flow_number or security_label
            portfolio_short_name: Filter by portfolio
            cash_flow_type: Filter by cash flow type
            include_deleted: Include soft-deleted records

        Returns:
            List of cash flow dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE 1=1
            """

            # Exclude deleted unless requested
            if not include_deleted:
                query += " AND (is_deleted = false OR is_deleted IS NULL)"

            # Apply filters
            if status:
                query += f" AND status = {CashFlowRepository.escape_value(status)}"

            if search:
                search_term = f"%{search}%"
                query += f" AND (LOWER(cash_flow_number) LIKE LOWER({CashFlowRepository.escape_value(search_term)}) "
                query += f"OR LOWER(security_label) LIKE LOWER({CashFlowRepository.escape_value(search_term)}) "
                query += f"OR LOWER(portfolio_short_name) LIKE LOWER({CashFlowRepository.escape_value(search_term)}))"

            if portfolio_short_name:
                query += f" AND portfolio_short_name = {CashFlowRepository.escape_value(portfolio_short_name)}"

            if portfolios:
                escaped = ', '.join(CashFlowRepository.escape_value(p) for p in portfolios)
                query += f" AND portfolio_short_name IN ({escaped})"

            if cash_flow_type:
                # Case-insensitive match to handle 'Cash Dividend' vs 'CASH_DIVIDEND' etc. (item 10)
                query += f" AND LOWER(cash_flow_type) = LOWER({CashFlowRepository.escape_value(cash_flow_type)})"

            # Order by most recent first
            query += " ORDER BY created_at DESC"

            # Apply limit and offset
            if offset > 0:
                query += f" OFFSET {offset}"
            query += f" LIMIT {limit}"

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching cash flows: {str(e)}")
            return []

    @staticmethod
    def get_by_id(cash_flow_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetch a single cash flow by ID.

        Args:
            cash_flow_id: Cash Flow ID

        Returns:
            Cash flow dictionary or None
        """
        try:
            query = f"""
            SELECT cash_flow_id, cash_flow_number,
                   security_label, portfolio_short_name,
                   cash_flow_type, send_receive,
                   cf_processed,
                   foreign_ccy, local_ccy,
                   local_ccy_amt, foreign_ccy_amt,
                   flow_amount_local, dividend_price, quantity, fx_rate,
                   tax_deducted_fc, tax_deducted_lc, other_charges_fc,
                   gl_acc_no, src_system,
                   ca_id, ca_number,
                   payment_date, trade_date, value_date,
                   dividend_date, ex_date, record_date,
                   is_deleted, is_active,
                   created_by, created_at, updated_by, updated_at,
                   status,
                   validated_by, validated_at, validation_comments,
                   settled_by, settled_at, settlement_comments,
                   cancelled_by, cancelled_at, cancel_reason,
                   remarks
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE cash_flow_id = {cash_flow_id}
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching cash flow {cash_flow_id}: {str(e)}")
            return None

    @staticmethod
    def get_by_cash_flow_number(cash_flow_number: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single cash flow by Cash Flow Number.

        Args:
            cash_flow_number: Cash Flow Number

        Returns:
            Cash flow dictionary or None
        """
        try:
            query = f"""
            SELECT *
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE cash_flow_number = {CashFlowRepository.escape_value(cash_flow_number)}
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result[0] if result and len(result) > 0 else None

        except Exception as e:
            logger.error(f"Error fetching cash flow by number {cash_flow_number}: {str(e)}")
            return None

    @staticmethod
    def get_pending_approvals(limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch cash flows pending approval (INITIAL or MODIFIED status).

        Args:
            limit: Maximum number of records

        Returns:
            List of cash flow dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE status IN ('INITIAL', 'MODIFIED')
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching pending approvals: {str(e)}")
            return []

    @staticmethod
    def get_by_portfolio(portfolio_short_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Fetch cash flows for a specific portfolio.

        Args:
            portfolio_short_name: Portfolio short name
            limit: Maximum number of records

        Returns:
            List of cash flow dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE portfolio_short_name = {CashFlowRepository.escape_value(portfolio_short_name)}
              AND (is_deleted = false OR is_deleted IS NULL)
            ORDER BY created_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching cash flows for portfolio {portfolio_short_name}: {str(e)}")
            return []

    # =========================================================================
    # WRITE OPERATIONS
    # =========================================================================

    @staticmethod
    def insert(cf_data: Dict[str, Any], created_by: str) -> tuple[bool, Optional[int]]:
        """
        Insert a new cash flow record into Kudu.

        Args:
            cf_data: Dictionary of cash flow fields
            created_by: Username creating the record

        Returns:
            Tuple of (success, cash_flow_id)
        """
        try:
            # Generate cash_flow_id (BIGINT ms PK — intentional)
            timestamp_ms = int(datetime.now().timestamp() * 1000)
            cash_flow_id = timestamp_ms
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build column and value lists
            columns = ['cash_flow_id']
            values = [str(cash_flow_id)]

            # Add all business fields from cf_data
            # Field mapping matches actual cis_cash_flow table in production
            field_mapping = {
                'cash_flow_number': str,
                'portfolio_short_name': str,
                'security_label': str,
                'cash_flow_type': str,
                'send_receive': str,
                'cf_processed': bool,
                'foreign_ccy': str,
                'local_ccy': str,
                'local_ccy_amt': float,
                'foreign_ccy_amt': float,
                'flow_amount_local': float,
                'dividend_price': float,
                'quantity': float,      # Quantity held at ex-date (for CA cash flows)
                'fx_rate': float,
                'tax_deducted_fc': float,
                'tax_deducted_lc': float,
                'gl_acc_no': str,
                'src_system': str,
                'payment_date': str,
                'trade_date': str,
                'value_date': str,
                'dividend_date': str,
                'ex_date': str,
                'record_date': str,
                # CA reference fields
                'ca_id': int,
                'ca_number': str,
                # Optional notes
                'remarks': str,
            }

            for field, field_type in field_mapping.items():
                if field in cf_data and cf_data[field] is not None and cf_data[field] != '':
                    columns.append(field)
                    if field_type == float:
                        values.append(CashFlowRepository.to_decimal(cf_data[field]))
                    elif field_type == int:
                        # Cast to int to avoid string-quoted values being rejected by BIGINT columns
                        try:
                            values.append(str(int(float(str(cf_data[field])))))
                        except (ValueError, TypeError):
                            values.append('NULL')
                    elif field_type == bool:
                        values.append('true' if cf_data[field] else 'false')
                    else:
                        values.append(CashFlowRepository.escape_value(cf_data[field]))

            # Add status
            status = cf_data.get('status', 'INITIAL')
            columns.append('status')
            values.append(CashFlowRepository.escape_value(status))

            # Add src_system - 'CIS' for records created via UI, 'CA' for corporate action generated
            src_system = cf_data.get('src_system', 'CIS')
            if 'src_system' not in cf_data:
                columns.append('src_system')
                values.append("'CIS'")

            # Add audit fields
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            columns.extend(['is_active', 'is_deleted', 'created_by', 'created_at', 'updated_by', 'updated_at'])
            values.extend([
                'true',
                'false',
                CashFlowRepository.escape_value(created_by),
                f"'{timestamp_str}'",
                CashFlowRepository.escape_value(created_by),
                f"'{timestamp_str}'"
            ])

            # For CA-generated cash flows (status=VALIDATED, src_system=CA), auto-populate validation fields
            if status == 'VALIDATED' and src_system == 'CA':
                columns.extend(['validated_by', 'validated_at', 'validation_comments'])
                values.extend([
                    "'SYSTEM_CA'",
                    f"'{timestamp_str}'",
                    "'Auto-validated: Generated from Corporate Action'"
                ])

            # Build UPSERT statement
            upsert_sql = f"""
            UPSERT INTO {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            ({', '.join(columns)})
            VALUES ({', '.join(values)})
            """

            # Debug logging - log the SQL being executed
            logger.info(f"[CF_INSERT] Executing cash flow insert SQL:")
            logger.info(f"[CF_INSERT] Columns: {columns}")
            logger.info(f"[CF_INSERT] Values: {values}")
            logger.info(f"[CF_INSERT] SQL: {upsert_sql.strip()}")

            success = impala_manager.execute_write(upsert_sql, database=CashFlowRepository.DATABASE)
            logger.info(f"[CF_INSERT] execute_write returned: {success}")

            if success:
                logger.info(f"[CF_INSERT] SUCCESS - Inserted cash flow {cash_flow_id}")
                # Verify the insert by reading it back
                verify_query = f"""
                SELECT cash_flow_id, cash_flow_number, status
                FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
                WHERE cash_flow_id = {cash_flow_id}
                """
                try:
                    verify_result = impala_manager.execute_query(verify_query, database=CashFlowRepository.DATABASE)
                    if verify_result and len(verify_result) > 0:
                        logger.info(f"[CF_INSERT] VERIFIED - Cash flow {cash_flow_id} found in table: {verify_result[0]}")
                    else:
                        logger.warning(f"[CF_INSERT] VERIFY FAILED - Cash flow {cash_flow_id} NOT found in table after insert!")
                except Exception as ve:
                    logger.warning(f"[CF_INSERT] Could not verify insert: {ve}")
                return True, cash_flow_id
            else:
                logger.error(f"[CF_INSERT] FAILED - execute_write returned False for cash flow {cash_flow_id}")

            return False, None

        except Exception as e:
            logger.error(f"[CF_INSERT] EXCEPTION - Error inserting cash flow: {str(e)}")
            import traceback
            logger.error(f"[CF_INSERT] Traceback: {traceback.format_exc()}")
            return False, None

    @staticmethod
    def update(cash_flow_id: int, cf_data: Dict[str, Any], updated_by: str) -> bool:
        """
        Update an existing cash flow record in Kudu.

        Args:
            cash_flow_id: Cash Flow ID to update
            cf_data: Dictionary of fields to update
            updated_by: Username updating the record

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Build SET clause
            set_clauses = []

            # Update business fields if provided
            updatable_fields = [
                'cash_flow_number', 'portfolio_short_name', 'security_label',
                'cash_flow_type', 'send_receive', 'cf_processed',
                'foreign_ccy', 'local_ccy', 'local_ccy_amt', 'foreign_ccy_amt',
                'flow_amount_local', 'dividend_price', 'gl_acc_no', 'src_system',
                'payment_date', 'trade_date', 'value_date', 'dividend_date',
                'ex_date', 'record_date', 'status',
                'tax_deducted_fc', 'tax_deducted_lc',
                'remarks',
            ]

            decimal_fields = ['local_ccy_amt', 'foreign_ccy_amt', 'flow_amount_local', 'dividend_price',
                              'tax_deducted_fc', 'tax_deducted_lc']
            boolean_fields = ['cf_processed']

            for field in updatable_fields:
                if field in cf_data:
                    if field in decimal_fields:
                        set_clauses.append(f"{field} = {CashFlowRepository.to_decimal(cf_data[field])}")
                    elif field in boolean_fields:
                        set_clauses.append(f"{field} = {'true' if cf_data[field] else 'false'}")
                    else:
                        set_clauses.append(f"{field} = {CashFlowRepository.escape_value(cf_data[field])}")

            # Always update audit fields
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            set_clauses.append(f"updated_by = {CashFlowRepository.escape_value(updated_by)}")
            set_clauses.append(f"updated_at = '{timestamp_str}'")

            if not set_clauses:
                logger.warning(f"No fields to update for cash flow {cash_flow_id}")
                return False

            # Build UPDATE statement
            update_sql = f"""
            UPDATE {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE cash_flow_id = {cash_flow_id}
            """

            success = impala_manager.execute_write(update_sql, database=CashFlowRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated cash flow {cash_flow_id}")

            return success

        except Exception as e:
            logger.error(f"Error updating cash flow {cash_flow_id}: {str(e)}")
            return False

    @staticmethod
    def update_status(
        cash_flow_id: int,
        status: str,
        updated_by: str,
        comments: str = None
    ) -> bool:
        """
        Update cash flow status (for maker-checker workflow).

        Args:
            cash_flow_id: Cash Flow ID
            status: New status
            updated_by: Username updating
            comments: Reviewer/settlement comments

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_now = datetime.now()
            timestamp_str = timestamp_now.strftime('%Y-%m-%d %H:%M:%S')

            set_clauses = [
                f"status = {CashFlowRepository.escape_value(status)}",
                f"updated_by = {CashFlowRepository.escape_value(updated_by)}",
                f"updated_at = '{timestamp_str}'",
            ]

            # Set appropriate workflow fields based on status
            if status == 'VALIDATED':
                set_clauses.append(f"validated_by = {CashFlowRepository.escape_value(updated_by)}")
                set_clauses.append(f"validated_at = '{timestamp_str}'")
                if comments:
                    set_clauses.append(f"validation_comments = {CashFlowRepository.escape_value(comments)}")
                set_clauses.append("is_active = true")
            elif status == 'APPROVED':
                set_clauses.append(f"validated_by = {CashFlowRepository.escape_value(updated_by)}")
                set_clauses.append(f"validated_at = '{timestamp_str}'")
                if comments:
                    set_clauses.append(f"validation_comments = {CashFlowRepository.escape_value(comments)}")
                set_clauses.append("is_active = true")
            elif status == 'SETTLED':
                set_clauses.append(f"settled_by = {CashFlowRepository.escape_value(updated_by)}")
                set_clauses.append(f"settled_at = '{timestamp_str}'")
                if comments:
                    set_clauses.append(f"settlement_comments = {CashFlowRepository.escape_value(comments)}")
            elif status == 'CANCELLED':
                set_clauses.append(f"cancelled_by = {CashFlowRepository.escape_value(updated_by)}")
                set_clauses.append(f"cancelled_at = '{timestamp_str}'")
                if comments:
                    set_clauses.append(f"cancel_reason = {CashFlowRepository.escape_value(comments)}")
                set_clauses.append("is_active = false")

            update_sql = f"""
            UPDATE {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            SET {', '.join(set_clauses)}
            WHERE cash_flow_id = {cash_flow_id}
            """

            success = impala_manager.execute_write(update_sql, database=CashFlowRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated cash flow {cash_flow_id} status to {status}")

            return success

        except Exception as e:
            logger.error(f"Error updating cash flow status {cash_flow_id}: {str(e)}")
            return False

    @staticmethod
    def soft_delete(cash_flow_id: int, deleted_by: str) -> bool:
        """
        Soft delete a cash flow.

        Args:
            cash_flow_id: Cash Flow ID
            deleted_by: Username deleting

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            update_sql = f"""
            UPDATE {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            SET is_deleted = true,
                is_active = false,
                updated_by = {CashFlowRepository.escape_value(deleted_by)},
                updated_at = '{timestamp_str}'
            WHERE cash_flow_id = {cash_flow_id}
            """

            success = impala_manager.execute_write(update_sql, database=CashFlowRepository.DATABASE)

            if success:
                logger.info(f"Successfully soft deleted cash flow {cash_flow_id}")

            return success

        except Exception as e:
            logger.error(f"Error soft deleting cash flow {cash_flow_id}: {str(e)}")
            return False

    @staticmethod
    def restore(cash_flow_id: int, restored_by: str) -> bool:
        """
        Restore a soft-deleted cash flow.

        Args:
            cash_flow_id: Cash Flow ID
            restored_by: Username restoring

        Returns:
            True if successful, False otherwise
        """
        try:
            timestamp_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            update_sql = f"""
            UPDATE {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            SET is_deleted = false,
                is_active = true,
                status = 'MODIFIED',
                updated_by = {CashFlowRepository.escape_value(restored_by)},
                updated_at = '{timestamp_str}'
            WHERE cash_flow_id = {cash_flow_id}
            """

            success = impala_manager.execute_write(update_sql, database=CashFlowRepository.DATABASE)

            if success:
                logger.info(f"Successfully restored cash flow {cash_flow_id}")

            return success

        except Exception as e:
            logger.error(f"Error restoring cash flow {cash_flow_id}: {str(e)}")
            return False

    # =========================================================================
    # HISTORY OPERATIONS
    # =========================================================================

    @staticmethod
    def insert_history(
        cash_flow_id: int,
        cash_flow_number: str,
        portfolio_short_name: str,
        action: str,
        status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """
        Insert a cash flow history record.

        Args:
            cash_flow_id: Cash Flow ID
            cash_flow_number: Cash Flow Number (denormalized)
            portfolio_short_name: Portfolio name (denormalized)
            action: Action type (CREATE, UPDATE, APPROVE, REJECT, DELETE)
            status: Status after action
            changes: Dictionary of changes
            comments: User comments
            performed_by: Username who performed action

        Returns:
            True if successful, False otherwise
        """
        try:
            import random
            now = datetime.now()
            timestamp_ms = int(now.timestamp() * 1000)
            # Embed cash_flow_id in upper bits + random salt to avoid PK collisions
            # when two history rows are written within the same millisecond.
            history_id = (cash_flow_id % 10**6) * 10**10 + timestamp_ms * 10**3 + random.randint(0, 999)
            # performed_at column is STRING in Kudu (not BIGINT) — store as ISO datetime
            performed_at_str = now.strftime('%Y-%m-%d %H:%M:%S')

            # Convert changes dict to JSON string; Decimal/date values from Kudu must be cast to str
            import decimal
            def _safe_default(obj):
                if isinstance(obj, decimal.Decimal):
                    return float(obj)
                return str(obj)
            changes_json = json.dumps(changes, default=_safe_default) if changes else '{}'

            insert_sql = f"""
            UPSERT INTO {CashFlowRepository.DATABASE}.{CashFlowRepository.HISTORY_TABLE}
            (history_id, cash_flow_id, cash_flow_number, portfolio_short_name, action, status, changes, comments, performed_by, performed_at)
            VALUES (
                {history_id},
                {cash_flow_id},
                {CashFlowRepository.escape_value(cash_flow_number)},
                {CashFlowRepository.escape_value(portfolio_short_name)},
                {CashFlowRepository.escape_value(action)},
                {CashFlowRepository.escape_value(status)},
                {CashFlowRepository.escape_value(changes_json)},
                {CashFlowRepository.escape_value(comments)},
                {CashFlowRepository.escape_value(performed_by)},
                {CashFlowRepository.escape_value(performed_at_str)}
            )
            """

            success = impala_manager.execute_write(insert_sql, database=CashFlowRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted history for cash flow {cash_flow_id}, action {action}")
            else:
                logger.error(
                    f"insert_history returned False for cash_flow_id={cash_flow_id} action={action}. "
                    f"SQL: {insert_sql.strip()}"
                )

            return success

        except Exception as e:
            logger.error(f"Error inserting cash flow history: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def get_history(cash_flow_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get history records for a cash flow.

        Args:
            cash_flow_id: Cash Flow ID
            limit: Maximum number of records

        Returns:
            List of history dictionaries
        """
        try:
            query = f"""
            SELECT *
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.HISTORY_TABLE}
            WHERE cash_flow_id = {cash_flow_id}
            ORDER BY performed_at DESC
            LIMIT {limit}
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)
            return result if result else []

        except Exception as e:
            logger.error(f"Error fetching cash flow history {cash_flow_id}: {str(e)}")
            return []

    # =========================================================================
    # UTILITY OPERATIONS
    # =========================================================================

    @staticmethod
    def generate_cash_flow_number() -> str:
        """
        Generate a unique Cash Flow number.

        Returns:
            Generated CF number (format: CF-YYYYMMDD-XXXXX)
        """
        try:
            today = datetime.now().strftime('%Y%m%d')
            prefix = f"CF-{today}-"

            # Get the latest CF number for today
            query = f"""
            SELECT cash_flow_number
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE cash_flow_number LIKE '{prefix}%'
            ORDER BY cash_flow_number DESC
            LIMIT 1
            """

            result = impala_manager.execute_query(query, database=CashFlowRepository.DATABASE)

            if result and len(result) > 0:
                last_number = result[0].get('cash_flow_number', '')
                if last_number:
                    try:
                        seq = int(last_number.split('-')[-1])
                        new_seq = seq + 1
                    except (ValueError, IndexError):
                        new_seq = 1
                else:
                    new_seq = 1
            else:
                new_seq = 1

            return f"{prefix}{new_seq:05d}"

        except Exception as e:
            logger.error(f"Error generating CF number: {str(e)}")
            # Fallback to timestamp-based number
            timestamp = int(datetime.now().timestamp() * 1000)
            return f"CF-{timestamp}"

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get cash flow statistics for dashboard.

        Returns:
            Dictionary of statistics
        """
        try:
            today_str = datetime.now().strftime('%Y-%m-%d')

            # Count by status
            status_query = f"""
            SELECT status, COUNT(*) as count
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE (is_deleted = false OR is_deleted IS NULL)
            GROUP BY status
            """
            status_results = impala_manager.execute_query(status_query, database=CashFlowRepository.DATABASE)

            status_counts = {}
            total = 0
            approved = 0
            pending = 0
            modified = 0

            if status_results:
                for row in status_results:
                    status = row.get('status', 'Unknown')
                    count = row.get('count', 0)
                    status_counts[status] = count
                    total += count

                    if status == 'APPROVED':
                        approved += count
                    elif status in ['INITIAL', 'MODIFIED']:
                        pending += count
                    if status == 'MODIFIED':
                        modified += count

            # Count approved today using validated_at date prefix
            approved_today_query = f"""
            SELECT COUNT(*) as count
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE status = 'APPROVED'
              AND (is_deleted = false OR is_deleted IS NULL)
              AND validated_at LIKE '{today_str}%'
            """
            approved_today_results = impala_manager.execute_query(
                approved_today_query, database=CashFlowRepository.DATABASE
            )
            approved_today = approved_today_results[0].get('count', 0) if approved_today_results else 0

            # Count by cash flow type
            type_query = f"""
            SELECT cash_flow_type, COUNT(*) as count
            FROM {CashFlowRepository.DATABASE}.{CashFlowRepository.TABLE_NAME}
            WHERE (is_deleted = false OR is_deleted IS NULL)
            GROUP BY cash_flow_type
            ORDER BY count DESC
            LIMIT 10
            """
            type_results = impala_manager.execute_query(type_query, database=CashFlowRepository.DATABASE)

            cf_types = []
            if type_results:
                cf_types = [{'cash_flow_type': row.get('cash_flow_type', 'Unknown'), 'count': row.get('count', 0)}
                           for row in type_results]

            return {
                'total': total,
                'approved': approved,
                'approved_today': approved_today,
                'pending_approval': pending,
                'modified': modified,
                'status_breakdown': status_counts,
                'by_type': cf_types,
            }

        except Exception as e:
            logger.error(f"Error getting statistics: {str(e)}")
            return {
                'total': 0,
                'approved': 0,
                'approved_today': 0,
                'pending_approval': 0,
                'modified': 0,
                'status_breakdown': {},
                'by_type': [],
            }


# Create singleton instance
cash_flow_repository = CashFlowRepository()
