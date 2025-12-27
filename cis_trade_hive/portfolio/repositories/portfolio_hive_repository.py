"""
Portfolio Repository
Fetches portfolio data from Kudu cis_portfolio table via Impala.
"""

from typing import List, Dict, Any, Optional
import logging
from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class PortfolioHiveRepository:
    """Repository for portfolio operations with Kudu via Impala."""

    DATABASE = 'gmp_cis'
    TABLE_NAME = 'cis_portfolio'

    @staticmethod
    def get_all_portfolios(
        limit: int = 1000,
        status: Optional[str] = None,
        currency: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve portfolios from Kudu with filters.

        Args:
            limit: Maximum number of records
            status: Filter by status
            currency: Filter by currency
            search: Search term for name/description

        Returns:
            List of portfolio records
        """
        try:
            # Build WHERE clause
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

            # Build query - use backticks for reserved keywords
            query = f"""
            SELECT `name`, `description`, `currency`, `manager`, `portfolio_client`,
                   `cash_balance`, `status`, `cost_centre_code`, `corp_code`,
                   `account_group`, `portfolio_group`, `report_group`, `entity_group`,
                   `revaluation_status`, `created_at`, `updated_at`
            FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            WHERE {where_clause}
            LIMIT {limit}
            """

            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)

            # Sort by name
            if results:
                results.sort(key=lambda x: x.get('name', ''))

            return results

        except Exception as e:
            logger.error(f"Error retrieving portfolios from Kudu: {str(e)}")
            return []

    @staticmethod
    def get_portfolio_statistics() -> Dict[str, Any]:
        """
        Get portfolio statistics from Kudu.

        Returns:
            Dictionary with portfolio statistics
        """
        try:
            # Fetch all portfolios
            all_query = f"SELECT `status`, `currency` FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}"
            all_result = impala_manager.execute_query(all_query, database=PortfolioHiveRepository.DATABASE)

            # Count total and active portfolios
            total_portfolios = len(all_result)
            active_portfolios = sum(1 for row in all_result if row.get('status') == 'Active')

            # Count currencies for active portfolios
            currency_counts = {}
            for row in all_result:
                if row.get('status') == 'Active':
                    curr = row.get('currency', 'Unknown')
                    currency_counts[curr] = currency_counts.get(curr, 0) + 1

            return {
                'total_portfolios': total_portfolios,
                'active_portfolios': active_portfolios,
                'currency_breakdown': [
                    {'currency': k, 'count': v}
                    for k, v in sorted(currency_counts.items())
                ]
            }

        except Exception as e:
            logger.error(f"Error getting portfolio statistics from Kudu: {str(e)}")
            return {
                'total_portfolios': 0,
                'active_portfolios': 0,
                'currency_breakdown': []
            }

    @staticmethod
    def get_currencies() -> List[str]:
        """
        Get list of unique currencies from portfolios.

        Returns:
            List of currency codes
        """
        try:
            # Fetch all currencies and deduplicate
            query = f"SELECT DISTINCT `currency` FROM {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}"
            results = impala_manager.execute_query(query, database=PortfolioHiveRepository.DATABASE)
            currencies = [row['currency'] for row in results if row.get('currency')]
            return sorted(currencies)
        except Exception as e:
            logger.error(f"Error getting currencies from Kudu: {str(e)}")
            return []

    @staticmethod
    def update_portfolio_status(
        portfolio_code: str,
        status: str,
        is_active: bool,
        updated_by: str
    ) -> bool:
        """
        Update portfolio status in Kudu.

        Args:
            portfolio_code: Portfolio code/name to update
            status: New status (CLOSED, ACTIVE, etc.)
            is_active: Active flag
            updated_by: Username of user making the update

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime
            updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Escape single quotes
            portfolio_code_escaped = portfolio_code.replace("'", "''")
            status_escaped = status.replace("'", "''")
            updated_by_escaped = updated_by.replace("'", "''")

            # Use UPDATE for Kudu - table uses 'name' as primary key
            query = f"""
            UPDATE {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            SET `status` = '{status_escaped}',
                `is_active` = {str(is_active).lower()},
                `updated_by` = '{updated_by_escaped}',
                `updated_at` = '{updated_at}'
            WHERE `name` = '{portfolio_code_escaped}'
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully updated portfolio {portfolio_code} status to {status} in Kudu")
            else:
                logger.error(f"Failed to update portfolio {portfolio_code} in Kudu")

            return success

        except Exception as e:
            logger.error(f"Error updating portfolio status in Kudu: {str(e)}")
            return False

    @staticmethod
    def insert_portfolio(portfolio_data: dict, created_by: str) -> bool:
        """
        Insert a new portfolio into Kudu.

        Args:
            portfolio_data: Dictionary with portfolio fields
            created_by: Username of user creating the portfolio

        Returns:
            True if successful, False otherwise
        """
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Escape single quotes in string fields
            def escape_value(val):
                if val is None:
                    return 'NULL'
                if isinstance(val, str):
                    return f"'{val.replace(chr(39), chr(39)+chr(39))}'"
                if isinstance(val, bool):
                    return str(val).lower()
                return str(val)

            # Build INSERT query
            query = f"""
            INSERT INTO {PortfolioHiveRepository.DATABASE}.{PortfolioHiveRepository.TABLE_NAME}
            (`name`, `description`, `currency`, `manager`, `portfolio_client`,
             `cash_balance`, `cost_centre_code`, `corp_code`, `account_group`,
             `portfolio_group`, `report_group`, `entity_group`, `status`,
             `is_active`, `revaluation_status`, `created_by`, `created_at`,
             `updated_by`, `updated_at`)
            VALUES (
                {escape_value(portfolio_data.get('name'))},
                {escape_value(portfolio_data.get('description', ''))},
                {escape_value(portfolio_data.get('currency'))},
                {escape_value(portfolio_data.get('manager'))},
                {escape_value(portfolio_data.get('portfolio_client', ''))},
                {portfolio_data.get('cash_balance', 0)},
                {escape_value(portfolio_data.get('cost_centre_code', ''))},
                {escape_value(portfolio_data.get('corp_code', ''))},
                {escape_value(portfolio_data.get('account_group', ''))},
                {escape_value(portfolio_data.get('portfolio_group', ''))},
                {escape_value(portfolio_data.get('report_group', ''))},
                {escape_value(portfolio_data.get('entity_group', ''))},
                'Active',
                true,
                {escape_value(portfolio_data.get('revaluation_status', ''))},
                {escape_value(created_by)},
                '{timestamp}',
                {escape_value(created_by)},
                '{timestamp}'
            )
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted portfolio {portfolio_data.get('name')} into Kudu")
            else:
                logger.error(f"Failed to insert portfolio {portfolio_data.get('name')} into Kudu")

            return success

        except Exception as e:
            logger.error(f"Error inserting portfolio into Kudu: {str(e)}")
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
        """
        Insert portfolio history record into Kudu.

        Args:
            portfolio_code: Portfolio code
            action: Action type (CLOSE, REACTIVATE, etc.)
            status: Portfolio status after action
            changes: Dictionary of changes
            comments: User comments
            performed_by: Username

        Returns:
            True if successful
        """
        try:
            from datetime import datetime
            import json
            import uuid

            # Generate unique ID
            history_id = int(datetime.now().timestamp() * 1000) + (uuid.uuid4().int % 1000)
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Escape values
            portfolio_code_escaped = portfolio_code.replace("'", "''")
            action_escaped = action.replace("'", "''")
            status_escaped = status.replace("'", "''")
            changes_json = json.dumps(changes).replace("'", "''")
            comments_escaped = comments.replace("'", "''") if comments else ''
            performed_by_escaped = performed_by.replace("'", "''")

            # Insert into portfolio history table (assuming it exists in Kudu)
            query = f"""
            UPSERT INTO {PortfolioHiveRepository.DATABASE}.cis_portfolio_history
            (`history_id`, `portfolio_code`, `action`, `status`, `changes`, `comments`, `performed_by`, `created_at`)
            VALUES (
                {history_id},
                '{portfolio_code_escaped}',
                '{action_escaped}',
                '{status_escaped}',
                '{changes_json}',
                '{comments_escaped}',
                '{performed_by_escaped}',
                '{created_at}'
            )
            """

            success = impala_manager.execute_write(query, database=PortfolioHiveRepository.DATABASE)

            if success:
                logger.info(f"Successfully inserted portfolio history for {portfolio_code} - {action}")
            else:
                logger.warning(f"Portfolio history insert may have failed for {portfolio_code}")

            return success

        except Exception as e:
            logger.error(f"Error inserting portfolio history: {str(e)}")
            return False

    @staticmethod
    def get_portfolio_by_code(portfolio_code: str) -> Optional[Dict[str, Any]]:
        """
        Get portfolio by code/name from Kudu.

        Args:
            portfolio_code: Portfolio code/name

        Returns:
            Portfolio dictionary or None
        """
        try:
            portfolio_code_escaped = portfolio_code.replace("'", "''")

            # Table uses 'name' as primary key
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


# Singleton instance
portfolio_hive_repository = PortfolioHiveRepository()
