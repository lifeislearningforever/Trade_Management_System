"""
Trade Repository for Hive Managed Tables

Handles CRUD operations for trade_hive table with ORC format.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import date
from .hive_base_repository import HiveBaseRepository

logger = logging.getLogger('hive_poc')


class TradeHiveRepository(HiveBaseRepository):
    """
    Repository for trade_hive managed table.

    Table: gmp_cis.trade_hive
    Format: ORC with SNAPPY compression
    """

    @property
    def table_name(self) -> str:
        return "trade_hive"

    @property
    def primary_key(self) -> str:
        return "trade_id"

    @property
    def columns(self) -> List[str]:
        return [
            'trade_id',
            'portfolio_id',
            'security_id',
            'security_name',
            'trade_type',
            'quantity',
            'price',
            'trade_amount',
            'currency',
            'trade_date',
            'settlement_date',
            'status',
            'broker',
            'notes',
            'created_at',
            'created_by',
            'updated_at',
            'updated_by',
            'deleted_at'
        ]

    def find_by_portfolio(self, portfolio_id: str) -> List[Dict[str, Any]]:
        """
        Find all trades for a portfolio.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            List of trades
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE portfolio_id = '{portfolio_id}'
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def find_by_status(self, status: str) -> List[Dict[str, Any]]:
        """
        Find trades by status.

        Args:
            status: Status value (PENDING, EXECUTED, SETTLED, CANCELLED)

        Returns:
            List of trades
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE status = '{status}'
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def find_by_date_range(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Find trades within a date range.

        Args:
            start_date: Start date
            end_date: End date

        Returns:
            List of trades
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE trade_date >= '{start_date}'
            AND trade_date <= '{end_date}'
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def find_by_security(self, security_id: str) -> List[Dict[str, Any]]:
        """
        Find trades by security ID.

        Args:
            security_id: Security identifier (ISIN, CUSIP)

        Returns:
            List of trades
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE security_id = '{security_id}'
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def find_by_broker(self, broker: str) -> List[Dict[str, Any]]:
        """
        Find trades by broker.

        Args:
            broker: Broker name (partial match)

        Returns:
            List of trades
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE LOWER(broker) LIKE LOWER('%{broker}%')
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def find_pending_settlement(self) -> List[Dict[str, Any]]:
        """
        Find trades pending settlement.

        Returns:
            List of trades with status EXECUTED
        """
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE status = 'EXECUTED'
            AND deleted_at IS NULL
            ORDER BY settlement_date ASC
        """
        return self.conn_manager.execute_query(query)

    def search(self, search_term: str) -> List[Dict[str, Any]]:
        """
        Search trades by security name, ID, or broker.

        Args:
            search_term: Search term

        Returns:
            List of matching trades
        """
        term = search_term.lower()
        query = f"""
            SELECT * FROM {self._get_full_table_name()}
            WHERE (
                LOWER(security_name) LIKE '%{term}%'
                OR LOWER(security_id) LIKE '%{term}%'
                OR LOWER(broker) LIKE '%{term}%'
                OR LOWER(notes) LIKE '%{term}%'
            )
            AND deleted_at IS NULL
            ORDER BY trade_date DESC
        """
        return self.conn_manager.execute_query(query)

    def update_status(self, trade_id: str, status: str, updated_by: str = 'system') -> bool:
        """
        Update trade status.

        Args:
            trade_id: Trade ID
            status: New status (PENDING, EXECUTED, SETTLED, CANCELLED)
            updated_by: Username

        Returns:
            True if successful
        """
        return self.update(trade_id, {
            'status': status,
            'updated_by': updated_by
        })

    def get_portfolio_summary(self, portfolio_id: str) -> Dict[str, Any]:
        """
        Get trade summary for a portfolio.

        Args:
            portfolio_id: Portfolio ID

        Returns:
            Summary with counts and totals
        """
        query = f"""
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN trade_type = 'BUY' THEN 1 ELSE 0 END) as buy_count,
                SUM(CASE WHEN trade_type = 'SELL' THEN 1 ELSE 0 END) as sell_count,
                SUM(CASE WHEN trade_type = 'BUY' THEN trade_amount ELSE 0 END) as total_buys,
                SUM(CASE WHEN trade_type = 'SELL' THEN trade_amount ELSE 0 END) as total_sells
            FROM {self._get_full_table_name()}
            WHERE portfolio_id = '{portfolio_id}'
            AND deleted_at IS NULL
        """
        results = self.conn_manager.execute_query(query)
        return results[0] if results else {
            'total_trades': 0,
            'buy_count': 0,
            'sell_count': 0,
            'total_buys': 0,
            'total_sells': 0
        }

    def get_trades_with_portfolio(self) -> List[Dict[str, Any]]:
        """
        Get all trades with portfolio details (JOIN).

        Returns:
            List of trades with portfolio info
        """
        query = f"""
            SELECT
                t.*,
                p.portfolio_name,
                p.portfolio_code
            FROM {self._get_full_table_name()} t
            LEFT JOIN {self.database}.portfolio_hive p
                ON t.portfolio_id = p.portfolio_id
            WHERE t.deleted_at IS NULL
            ORDER BY t.trade_date DESC
        """
        return self.conn_manager.execute_query(query)
