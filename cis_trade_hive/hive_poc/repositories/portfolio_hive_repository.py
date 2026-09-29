"""
Portfolio Repository for Hive Managed Tables

Handles CRUD operations for portfolio_hive table with ORC format.
"""

import logging
from typing import Optional, List, Dict, Any
from .hive_base_repository import HiveBaseRepository

logger = logging.getLogger('hive_poc')


class PortfolioHiveRepository(HiveBaseRepository):
    """
    Repository for portfolio_hive managed table.

    Table: gmp_cis.portfolio_hive
    Format: ORC with SNAPPY compression
    """

    @property
    def table_name(self) -> str:
        return "portfolio_hive"

    @property
    def primary_key(self) -> str:
        return "portfolio_id"

    @property
    def columns(self) -> List[str]:
        return [
            'portfolio_id',
            'portfolio_name',
            'portfolio_code',
            'portfolio_type',
            'currency',
            'manager_name',
            'description',
            'status',
            'created_at',
            'created_by',
            'updated_at',
            'updated_by',
            'deleted_at'
        ]

    def find_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Find portfolio by code.

        Args:
            code: Portfolio code (e.g., 'GEF')

        Returns:
            Portfolio record or None
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE portfolio_code = '{code}'
            AND deleted_at IS NULL
        """
        results = self.conn_manager.execute_query(query)
        return results[0] if results else None

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Find portfolios by status.

        Args:
            status: Status value (ACTIVE, INACTIVE, DRAFT)

        Returns:
            List of portfolios
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE status = '{status}'
            AND deleted_at IS NULL
            ORDER BY portfolio_name
        """
        return self.conn_manager.execute_query(query)

    def find_by_type(self, portfolio_type: str) -> List[Dict[str, Any]]:
        """
        Find portfolios by type.

        Args:
            portfolio_type: Type value (EQUITY, FIXED_INCOME, BALANCED)

        Returns:
            List of portfolios
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE portfolio_type = '{portfolio_type}'
            AND deleted_at IS NULL
            ORDER BY portfolio_name
        """
        return self.conn_manager.execute_query(query)

    def find_by_manager(self, manager_name: str) -> List[Dict[str, Any]]:
        """
        Find portfolios by manager name.

        Args:
            manager_name: Manager name (partial match)

        Returns:
            List of portfolios
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE LOWER(manager_name) LIKE LOWER('%{manager_name}%')
            AND deleted_at IS NULL
            ORDER BY portfolio_name
        """
        return self.conn_manager.execute_query(query)

    def search(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Search portfolios by name, code, or description.

        Args:
            search_term: Search term

        Returns:
            List of matching portfolios
        """
        term = search_term.lower()
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE (
                LOWER(portfolio_name) LIKE '%{term}%'
                OR LOWER(portfolio_code) LIKE '%{term}%'
                OR LOWER(description) LIKE '%{term}%'
            )
            AND deleted_at IS NULL
            ORDER BY portfolio_name
        """
        return self.conn_manager.execute_query(query)

    def get_portfolio_dropdown(self) -> List[Dict[str, str]]:
        """
        Get portfolios for dropdown selection.

        Returns:
            List of dicts with 'id' and 'name' keys
        """
        query = f"""
            SELECT portfolio_id, portfolio_name, portfolio_code
            FROM {self._get_full_table_name()}
            WHERE status = 'ACTIVE'
            AND deleted_at IS NULL
            ORDER BY portfolio_name
        """
        results = self.conn_manager.execute_query(query)
        return [
            {
                'id': r['portfolio_id'],
                'name': f"{r['portfolio_name']} ({r['portfolio_code']})"
            }
            for r in results
        ]

    def update_status(self, portfolio_id: str, status: str, updated_by: str = 'system') -> bool:
        """
        Update portfolio status.

        Args:
            portfolio_id: Portfolio ID
            status: New status (ACTIVE, INACTIVE, DRAFT)
            updated_by: Username

        Returns:
            True if successful
        """
        return self.update(portfolio_id, {
            'status': status,
            'updated_by': updated_by
        })
