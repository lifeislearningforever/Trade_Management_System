"""
Portfolio Repository
Fetches portfolio data from Kudu cis_portfolio table via Impala.
Implements Maker-Checker workflow with statuses:
  - INITIAL: New portfolio created (Maker)
  - MODIFIED: Portfolio edited (Maker)
  - PENDING_VALIDATION: Submitted for validation (awaiting Checker)
  - VALIDATED: Approved by Checker (ready for settlement)
  - CANCELLED: Rejected/Cancelled
  - SETTLED: Final active state (settlement complete)

Audit Logging:
  All create, update, and status change operations are logged to cis_audit_log table.
"""

from typing import List, Dict, Any, Optional
import logging
import json
from datetime import datetime
from core.repositories.impala_connection import impala_manager
from core.audit.audit_kudu_repository import audit_log_kudu_repository

logger = logging.getLogger(__name__)


class PortfolioHiveRepository:
    """Repository for portfolio operations with Kudu via Impala."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_portfolio'

    # Workflow Status Constants
    STATUS_INITIAL = 'INITIAL'
    STATUS_MODIFIED = 'MODIFIED'
    STATUS_PENDING_VALIDATION = 'PENDING_VALIDATION'
    STATUS_VALIDATED = 'VALIDATED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_SETTLED = 'SETTLED'

    # Status groups for filtering
    # Allow edits during PENDING_VALIDATION (Maker can modify while awaiting approval)
    MAKER_EDITABLE_STATUSES = [STATUS_INITIAL, STATUS_MODIFIED, STATUS_PENDING_VALIDATION, STATUS_CANCELLED]
    CHECKER_ACTIONABLE_STATUSES = [STATUS_PENDING_VALIDATION, STATUS_VALIDATED]

    @staticmethod
    def escape_value(val):
        """Escape value for SQL query."""
        if val is None:
            return 'NULL'
        if isinstance(val, str):
            return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
        if isinstance(val, bool):
            return str(val).lower()
        return str(val)

    @staticmethod
    def get_all_portfolios(
        limit: int = 1000,
        status: Optional[str] = None,
        currency: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve portfolios from Kudu with filters.
        Orders by src_system='CIS' first, then by name.
        """
        try:
            where_clauses = []

            if status:
                status_escaped = status.replace("'", "''")
                where_clauses.append(f"`status` = '{status_escaped}'")

            if currency:
                currency_escaped = currency.replace("'", "''")
                where_clauses.append(f"`currency` = '{currency_escaped}'")

            if search:
                search_term = search.replace("'", "''")
                where_clauses.append(
                    f"(`name` LIKE '%{search_term}%' OR "
                    f"`description` LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            query = f"""
            SELECT `name`, `description`, `currency`, `manager`, `portfolio_client`,
                   `cash_balance`, `status`, `cost_centre_code`, `corp_code`,
                   `account_group`, `portfolio_group`, `report_group`, `entity_group`,
                   `revaluation_status`, `is_active`, `created_at`, `updated_at`, `updated_by`,
                   `src_system`, `submitted_by`, `submitted_at`, `validated_by`, `validated_at`,
                   `settled_by`, `settled_at`, `cancelled_by`, `cancelled_at`, `cancel_reason`
            FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, `name`
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)
            return results

        except Exception as e:
            logger.error(f"Error retrieving portfolios from Kudu: {str(e)}")
            return []

    @staticmethod
    def get_portfolios_by_status(statuses: List[str], limit: int = 1000) -> List[Dict[str, Any]]:
        """Get portfolios filtered by multiple statuses."""
        try:
            status_list = ", ".join([f"'{s}'" for s in statuses])
            query = f"""
            SELECT *
            FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            WHERE `status` IN ({status_list})
            ORDER BY CASE WHEN UPPER(src_system) = 'CIS' THEN 0 ELSE 1 END, `name`
            LIMIT {limit}
            """
            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)
            return results
        except Exception as e:
            logger.error(f"Error retrieving portfolios by status: {str(e)}")
            return []

    @staticmethod
    def get_pending_validation_portfolios(limit: int = 1000) -> List[Dict[str, Any]]:
        """Get portfolios pending validation (for Checker)."""
        return PortfolioHiveRepository.get_portfolios_by_status(
            [PortfolioHiveRepository.STATUS_PENDING_VALIDATION], limit
        )

    @staticmethod
    def get_validated_portfolios(limit: int = 1000) -> List[Dict[str, Any]]:
        """Get validated portfolios ready for settlement (for Checker)."""
        return PortfolioHiveRepository.get_portfolios_by_status(
            [PortfolioHiveRepository.STATUS_VALIDATED], limit
        )

    @staticmethod
    def get_portfolio_statistics() -> Dict[str, Any]:
        """Get portfolio statistics from Kudu."""
        try:
            all_query = f"SELECT `status`, `currency` FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}"
            all_result = impala_manager.execute_query(all_query, database=PortfolioHiveRepository.DATABASE)

            total_portfolios = len(all_result)

            # Count by status
            status_counts = {}
            currency_counts = {}
            for row in all_result:
                status = row.get('status', 'Unknown')
                status_counts[status] = status_counts.get(status, 0) + 1

                if row.get('status') == PortfolioHiveRepository.STATUS_SETTLED:
                    curr = row.get('currency', 'Unknown')
                    currency_counts[curr] = currency_counts.get(curr, 0) + 1

            return {
                'total_portfolios': total_portfolios,
                'settled_portfolios': status_counts.get(PortfolioHiveRepository.STATUS_SETTLED, 0),
                'pending_validation': status_counts.get(PortfolioHiveRepository.STATUS_PENDING_VALIDATION, 0),
                'validated': status_counts.get(PortfolioHiveRepository.STATUS_VALIDATED, 0),
                'status_breakdown': status_counts,
                'currency_breakdown': [
                    {'currency': k, 'count': v}
                    for k, v in sorted(currency_counts.items())
                ]
            }

        except Exception as e:
            logger.error(f"Error getting portfolio statistics from Kudu: {str(e)}")
            return {
                'total_portfolios': 0,
                'settled_portfolios': 0,
                'pending_validation': 0,
                'validated': 0,
                'status_breakdown': {},
                'currency_breakdown': []
            }

    @staticmethod
    def get_currencies() -> List[str]:
        """Get list of unique currencies from portfolios."""
        try:
            query = f"SELECT DISTINCT `currency` FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}"
            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)
            currencies = [row['currency'] for row in results if row.get('currency')]
            return sorted(currencies)
        except Exception as e:
            logger.error(f"Error getting currencies from Kudu: {str(e)}")
            return []

    @staticmethod
    def get_portfolio_by_code(portfolio_code: str) -> Optional[Dict[str, Any]]:
        """Get portfolio by code/name from Kudu."""
        try:
            portfolio_code_escaped = portfolio_code.replace("'", "''")
            query = f"""
            SELECT *
            FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            WHERE `name` = '{portfolio_code_escaped}'
            LIMIT 1
            """
            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error getting portfolio by code from Kudu: {str(e)}")
            return None

    @staticmethod
    def insert_portfolio(portfolio_data: dict, created_by: str) -> bool:
        """
        Insert a new portfolio into Kudu with INITIAL status.
        Maker action: Create Static/Book Trade -> INITIAL
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value
            cash_balance_str = str(portfolio_data.get('cash_balance', '0'))

            query = f"""
            INSERT INTO {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            (`name`, `description`, `currency`, `manager`, `portfolio_client`,
             `cash_balance`, `cost_centre_code`, `corp_code`, `account_group`,
             `portfolio_group`, `report_group`, `entity_group`, `status`,
             `is_active`, `revaluation_status`, `accounting_section`, `src_system`,
             `created_by`, `created_at`, `updated_by`, `updated_at`)
            VALUES (
                {escape(portfolio_data.get('name'))},
                {escape(portfolio_data.get('description', ''))},
                {escape(portfolio_data.get('currency'))},
                {escape(portfolio_data.get('manager'))},
                {escape(portfolio_data.get('portfolio_client', ''))},
                {escape(cash_balance_str)},
                {escape(portfolio_data.get('cost_centre_code', ''))},
                {escape(portfolio_data.get('corp_code', ''))},
                {escape(portfolio_data.get('account_group', ''))},
                {escape(portfolio_data.get('portfolio_group', ''))},
                {escape(portfolio_data.get('report_group', ''))},
                {escape(portfolio_data.get('entity_group', ''))},
                '{PortfolioHiveRepository.STATUS_INITIAL}',
                false,
                {escape(portfolio_data.get('revaluation_status', ''))},
                {escape(portfolio_data.get('accounting_section', ''))},
                'CIS',
                {escape(created_by)},
                '{timestamp}',
                {escape(created_by)},
                '{timestamp}'
            )
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Created portfolio {portfolio_data.get('name')} with INITIAL status")
                # Audit log for CREATE
                audit_log_kudu_repository.log_action(
                    user_id=created_by,
                    username=created_by,
                    action_type='CREATE',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_data.get('name'),
                    entity_name=portfolio_data.get('name'),
                    action_description=f"Created portfolio {portfolio_data.get('name')} with status INITIAL",
                    new_value=json.dumps(portfolio_data, default=str),
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='insert_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error inserting portfolio into Kudu: {str(e)}")
            # Log failed attempt
            audit_log_kudu_repository.log_action(
                user_id=created_by,
                username=created_by,
                action_type='CREATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_data.get('name'),
                entity_name=portfolio_data.get('name'),
                action_description=f"Failed to create portfolio {portfolio_data.get('name')}",
                error_message=str(e),
                request_method='POST',
                status='FAILURE',
                module_name='portfolio.repositories',
                function_name='insert_portfolio'
            )
            return False

    @staticmethod
    def update_portfolio(portfolio_name: str, portfolio_data: dict, updated_by: str) -> bool:
        """
        Update portfolio data. Sets status to MODIFIED.
        Maker action: Update Static/Trade -> MODIFIED
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value
            cash_balance_str = str(portfolio_data.get('cash_balance', '0'))

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `description` = {escape(portfolio_data.get('description', ''))},
                `currency` = {escape(portfolio_data.get('currency'))},
                `manager` = {escape(portfolio_data.get('manager'))},
                `portfolio_client` = {escape(portfolio_data.get('portfolio_client', ''))},
                `cash_balance` = {escape(cash_balance_str)},
                `cost_centre_code` = {escape(portfolio_data.get('cost_centre_code', ''))},
                `corp_code` = {escape(portfolio_data.get('corp_code', ''))},
                `account_group` = {escape(portfolio_data.get('account_group', ''))},
                `portfolio_group` = {escape(portfolio_data.get('portfolio_group', ''))},
                `report_group` = {escape(portfolio_data.get('report_group', ''))},
                `entity_group` = {escape(portfolio_data.get('entity_group', ''))},
                `revaluation_status` = {escape(portfolio_data.get('revaluation_status', ''))},
                `accounting_section` = {escape(portfolio_data.get('accounting_section', ''))},
                `status` = '{PortfolioHiveRepository.STATUS_MODIFIED}',
                `updated_by` = {escape(updated_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_name)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Updated portfolio {portfolio_name}, status set to MODIFIED")
                # Audit log for UPDATE
                audit_log_kudu_repository.log_action(
                    user_id=updated_by,
                    username=updated_by,
                    action_type='UPDATE',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_name,
                    entity_name=portfolio_name,
                    action_description=f"Updated portfolio {portfolio_name}, status set to MODIFIED",
                    new_value=json.dumps(portfolio_data, default=str),
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='update_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error updating portfolio: {str(e)}")
            audit_log_kudu_repository.log_action(
                user_id=updated_by,
                username=updated_by,
                action_type='UPDATE',
                entity_type='PORTFOLIO',
                entity_id=portfolio_name,
                entity_name=portfolio_name,
                action_description=f"Failed to update portfolio {portfolio_name}",
                error_message=str(e),
                request_method='POST',
                status='FAILURE',
                module_name='portfolio.repositories',
                function_name='update_portfolio'
            )
            return False

    @staticmethod
    def submit_for_validation(portfolio_code: str, submitted_by: str) -> bool:
        """
        Submit portfolio for validation.
        Maker action: Submit -> PENDING_VALIDATION
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{PortfolioHiveRepository.STATUS_PENDING_VALIDATION}',
                `submitted_by` = {escape(submitted_by)},
                `submitted_at` = '{timestamp}',
                `updated_by` = {escape(submitted_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Portfolio {portfolio_code} submitted for validation by {submitted_by}")
                audit_log_kudu_repository.log_action(
                    user_id=submitted_by,
                    username=submitted_by,
                    action_type='SUBMIT',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_code,
                    entity_name=portfolio_code,
                    action_description=f"Submitted portfolio {portfolio_code} for validation",
                    old_value='INITIAL/MODIFIED',
                    new_value='PENDING_VALIDATION',
                    field_name='status',
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='submit_for_validation'
                )
            return success

        except Exception as e:
            logger.error(f"Error submitting portfolio for validation: {str(e)}")
            return False

    @staticmethod
    def validate_portfolio(portfolio_code: str, validated_by: str, comments: str = '') -> bool:
        """
        Validate (approve) portfolio.
        Checker action: Validate -> VALIDATED
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{PortfolioHiveRepository.STATUS_VALIDATED}',
                `validated_by` = {escape(validated_by)},
                `validated_at` = '{timestamp}',
                `validation_comments` = {escape(comments)},
                `updated_by` = {escape(validated_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Portfolio {portfolio_code} validated by {validated_by}")
                audit_log_kudu_repository.log_action(
                    user_id=validated_by,
                    username=validated_by,
                    action_type='VALIDATE',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_code,
                    entity_name=portfolio_code,
                    action_description=f"Validated portfolio {portfolio_code}" + (f" - {comments}" if comments else ""),
                    old_value='PENDING_VALIDATION',
                    new_value='VALIDATED',
                    field_name='status',
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='validate_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error validating portfolio: {str(e)}")
            return False

    @staticmethod
    def settle_portfolio(portfolio_code: str, settled_by: str, comments: str = '') -> bool:
        """
        Settle (activate) portfolio.
        Checker action: Settle -> SETTLED (final active state)
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{PortfolioHiveRepository.STATUS_SETTLED}',
                `is_active` = true,
                `settled_by` = {escape(settled_by)},
                `settled_at` = '{timestamp}',
                `settlement_comments` = {escape(comments)},
                `updated_by` = {escape(settled_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Portfolio {portfolio_code} settled by {settled_by}")
                audit_log_kudu_repository.log_action(
                    user_id=settled_by,
                    username=settled_by,
                    action_type='SETTLE',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_code,
                    entity_name=portfolio_code,
                    action_description=f"Settled portfolio {portfolio_code}" + (f" - {comments}" if comments else ""),
                    old_value='VALIDATED',
                    new_value='SETTLED',
                    field_name='status',
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='settle_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error settling portfolio: {str(e)}")
            return False

    @staticmethod
    def cancel_portfolio(portfolio_code: str, cancelled_by: str, reason: str = '') -> bool:
        """
        Cancel portfolio.
        Maker action: Cancel Trade -> CANCELLED
        Checker action: Reject -> CANCELLED
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{PortfolioHiveRepository.STATUS_CANCELLED}',
                `is_active` = false,
                `cancelled_by` = {escape(cancelled_by)},
                `cancelled_at` = '{timestamp}',
                `cancel_reason` = {escape(reason)},
                `updated_by` = {escape(cancelled_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Portfolio {portfolio_code} cancelled by {cancelled_by}")
                audit_log_kudu_repository.log_action(
                    user_id=cancelled_by,
                    username=cancelled_by,
                    action_type='CANCEL',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_code,
                    entity_name=portfolio_code,
                    action_description=f"Cancelled portfolio {portfolio_code}" + (f" - Reason: {reason}" if reason else ""),
                    new_value='CANCELLED',
                    field_name='status',
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='cancel_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error cancelling portfolio: {str(e)}")
            return False

    @staticmethod
    def reactivate_portfolio(portfolio_code: str, reactivated_by: str, comments: str = '') -> bool:
        """
        Reactivate cancelled portfolio (sets back to INITIAL for re-submission).
        """
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{PortfolioHiveRepository.STATUS_INITIAL}',
                `is_active` = false,
                `cancelled_by` = NULL,
                `cancelled_at` = NULL,
                `cancel_reason` = NULL,
                `updated_by` = {escape(reactivated_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Portfolio {portfolio_code} reactivated by {reactivated_by}")
                audit_log_kudu_repository.log_action(
                    user_id=reactivated_by,
                    username=reactivated_by,
                    action_type='REACTIVATE',
                    entity_type='PORTFOLIO',
                    entity_id=portfolio_code,
                    entity_name=portfolio_code,
                    action_description=f"Reactivated portfolio {portfolio_code}" + (f" - {comments}" if comments else ""),
                    old_value='CANCELLED',
                    new_value='INITIAL',
                    field_name='status',
                    request_method='POST',
                    status='SUCCESS',
                    module_name='portfolio.repositories',
                    function_name='reactivate_portfolio'
                )
            return success

        except Exception as e:
            logger.error(f"Error reactivating portfolio: {str(e)}")
            return False

    @staticmethod
    def update_portfolio_status(
        portfolio_code: str,
        status: str,
        is_active: bool,
        updated_by: str
    ) -> bool:
        """Legacy method for backward compatibility."""
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = {escape(status)},
                `is_active` = {str(is_active).lower()},
                `updated_by` = {escape(updated_by)},
                `updated_at` = '{timestamp}'
            WHERE `name` = {escape(portfolio_code)}
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Updated portfolio {portfolio_code} status to {status}")
            return success

        except Exception as e:
            logger.error(f"Error updating portfolio status: {str(e)}")
            return False

    @staticmethod
    def insert_portfolio_history(
        portfolio_code: str,
        action: str,
        status: str,
        changes: Dict[str, Any],
        comments: str,
        performed_by: str
    ) -> bool:
        """Insert portfolio history record into Kudu."""
        try:
            import json
            import uuid

            history_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            escape = PortfolioHiveRepository.escape_value

            changes_json = json.dumps(changes).replace("'", "''")

            query = f"""
            UPSERT INTO {PortfolioHiveRepository.DATABASE}.cis_portfolio_history
            (`history_id`, `portfolio_code`, `action`, `status`, `changes`, `comments`, `performed_by`, `created_at`)
            VALUES (
                {history_id},
                {escape(portfolio_code)},
                {escape(action)},
                {escape(status)},
                '{changes_json}',
                {escape(comments)},
                {escape(performed_by)},
                '{created_at}'
            )
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)
            if success:
                logger.info(f"Inserted portfolio history for {portfolio_code} - {action}")
            return success

        except Exception as e:
            logger.error(f"Error inserting portfolio history: {str(e)}")
            return False


# Singleton instance
portfolio_hive_repository = PortfolioHiveRepository()
