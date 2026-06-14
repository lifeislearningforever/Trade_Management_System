"""
Position Repository

Read-only data access for cis_position (Kudu) table.
Supports filtering by portfolio, security, src_system, position_basis,
position_date range, and position_type.
"""

import logging
from typing import Dict, List, Optional, Any

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
TABLE = 'cis_position'


class PositionRepository:

    @staticmethod
    def _escape(value: str) -> str:
        if value is None:
            return ''
        return str(value).replace("\\", "\\\\").replace("'", "\\'")

    def get_positions(
        self,
        portfolios: Optional[list] = None,
        securities: Optional[list] = None,
        src_system: Optional[Any] = None,  # str or list[str]
        position_basis: Optional[str] = None,
        position_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 500,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch positions from cis_position with optional filters.

        Returns list of position dicts matching cis_position schema.
        """
        try:
            conditions = []

            if portfolios and len(portfolios) == 1:
                conditions.append(f"UPPER(pos.portfolio) LIKE '%{self._escape(portfolios[0].upper())}%'")
            elif portfolios and len(portfolios) > 1:
                vals = "', '".join(self._escape(p) for p in portfolios)
                conditions.append(f"pos.portfolio IN ('{vals}')")
            if securities and len(securities) == 1:
                conditions.append(f"UPPER(pos.security_label) LIKE '%{self._escape(securities[0].upper())}%'")
            elif securities and len(securities) > 1:
                vals = "', '".join(self._escape(s) for s in securities)
                conditions.append(f"pos.security_label IN ('{vals}')")
            if src_system:
                src_list = src_system if isinstance(src_system, list) else [src_system]
                src_list = [s for s in src_list if s]
                if len(src_list) == 1:
                    conditions.append(f"pos.src_system = '{self._escape(src_list[0])}'")
                elif len(src_list) > 1:
                    vals = "', '".join(self._escape(s) for s in src_list)
                    conditions.append(f"pos.src_system IN ('{vals}')")
            if position_basis:
                conditions.append(f"pos.position_basis = '{self._escape(position_basis)}'")
            if position_type:
                conditions.append(f"pos.position_type = '{self._escape(position_type)}'")
            if date_from:
                conditions.append(f"pos.position_date >= '{self._escape(date_from)}'")
            if date_to:
                conditions.append(f"pos.position_date <= '{self._escape(date_to)}'")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                SELECT
                    pos.position_id, pos.version_id,
                    pos.portfolio, pos.security_label,
                    pos.position_basis, pos.position_date,
                    pos.src_system, pos.processing_date,
                    pos.quantity,
                    pos.average_cost_fc, pos.average_cost_lc,
                    pos.cost_fc, pos.cost_lc,
                    pos.market_value_fc, pos.market_value_lc,
                    pos.net_book_value_fc, pos.net_book_value_lc,
                    pos.unrealized_pnl_fc, pos.unrealized_pnl_lc,
                    pos.realized_pnl_fc, pos.realized_pnl_lc,
                    pos.provision_fc, pos.provision_lc,
                    pos.dividend_fc, pos.dividend_lc,
                    pos.uncall_fc, pos.uncall_lc,
                    pos.pipeline_fc, pos.pipeline_lc,
                    pos.position_type,
                    pos.isin,
                    COALESCE(p.revaluation_status, '') AS revaluation_status,
                    s.security_id AS security_id
                FROM {DATABASE}.{TABLE} pos
                LEFT JOIN {DATABASE}.cis_portfolio p
                    ON pos.portfolio = p.name
                    AND (p.is_active = true OR p.is_active IS NULL)
                LEFT JOIN {DATABASE}.cis_security s
                    ON pos.security_label = s.security_name
                {where}
                ORDER BY pos.position_date DESC, pos.portfolio, pos.security_label
                LIMIT {limit}
                OFFSET {offset}
            """

            results = impala_manager.execute_query(query, database=DATABASE)
            return results if results else []

        except Exception as e:
            logger.error(f"Error fetching positions: {str(e)}")
            return []

    def get_position_count(
        self,
        portfolios: Optional[list] = None,
        securities: Optional[list] = None,
        src_system: Optional[Any] = None,  # str or list[str]
        position_basis: Optional[str] = None,
        position_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> int:
        """Return total count matching filters (for pagination)."""
        try:
            conditions = []

            if portfolios and len(portfolios) == 1:
                conditions.append(f"UPPER(portfolio) LIKE '%{self._escape(portfolios[0].upper())}%'")
            elif portfolios and len(portfolios) > 1:
                vals = "', '".join(self._escape(p) for p in portfolios)
                conditions.append(f"portfolio IN ('{vals}')")
            if securities and len(securities) == 1:
                conditions.append(f"UPPER(security_label) LIKE '%{self._escape(securities[0].upper())}%'")
            elif securities and len(securities) > 1:
                vals = "', '".join(self._escape(s) for s in securities)
                conditions.append(f"security_label IN ('{vals}')")
            if src_system:
                src_list = src_system if isinstance(src_system, list) else [src_system]
                src_list = [s for s in src_list if s]
                if len(src_list) == 1:
                    conditions.append(f"src_system = '{self._escape(src_list[0])}'")
                elif len(src_list) > 1:
                    vals = "', '".join(self._escape(s) for s in src_list)
                    conditions.append(f"src_system IN ('{vals}')")
            if position_basis:
                conditions.append(f"position_basis = '{self._escape(position_basis)}'")
            if position_type:
                conditions.append(f"position_type = '{self._escape(position_type)}'")
            if date_from:
                conditions.append(f"position_date >= '{self._escape(date_from)}'")
            if date_to:
                conditions.append(f"position_date <= '{self._escape(date_to)}'")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"SELECT COUNT(*) AS cnt FROM {DATABASE}.{TABLE} {where}"
            results = impala_manager.execute_query(query, database=DATABASE)
            return int(results[0].get('cnt', 0)) if results else 0

        except Exception as e:
            logger.error(f"Error counting positions: {str(e)}")
            return 0

    def get_summary_stats(
        self,
        portfolios: Optional[list] = None,
        securities: Optional[list] = None,
        src_system: Optional[Any] = None,  # str or list[str]
        position_basis: Optional[str] = None,
        position_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """Aggregate stats for summary cards matching current filters."""
        try:
            conditions = []

            if portfolios and len(portfolios) == 1:
                conditions.append(f"UPPER(portfolio) LIKE '%{self._escape(portfolios[0].upper())}%'")
            elif portfolios and len(portfolios) > 1:
                vals = "', '".join(self._escape(p) for p in portfolios)
                conditions.append(f"portfolio IN ('{vals}')")
            if securities and len(securities) == 1:
                conditions.append(f"UPPER(security_label) LIKE '%{self._escape(securities[0].upper())}%'")
            elif securities and len(securities) > 1:
                vals = "', '".join(self._escape(s) for s in securities)
                conditions.append(f"security_label IN ('{vals}')")
            if src_system:
                src_list = src_system if isinstance(src_system, list) else [src_system]
                src_list = [s for s in src_list if s]
                if len(src_list) == 1:
                    conditions.append(f"src_system = '{self._escape(src_list[0])}'")
                elif len(src_list) > 1:
                    vals = "', '".join(self._escape(s) for s in src_list)
                    conditions.append(f"src_system IN ('{vals}')")
            if position_basis:
                conditions.append(f"position_basis = '{self._escape(position_basis)}'")
            if position_type:
                conditions.append(f"position_type = '{self._escape(position_type)}'")
            if date_from:
                conditions.append(f"position_date >= '{self._escape(date_from)}'")
            if date_to:
                conditions.append(f"position_date <= '{self._escape(date_to)}'")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

            query = f"""
                SELECT
                    COUNT(*)                          AS total_positions,
                    SUM(market_value_fc)              AS total_market_value_fc,
                    SUM(market_value_lc)              AS total_market_value_lc,
                    SUM(cost_fc)                      AS total_cost_fc,
                    SUM(cost_lc)                      AS total_cost_lc,
                    SUM(unrealized_pnl_fc)            AS total_unrealized_pnl_fc,
                    SUM(unrealized_pnl_lc)            AS total_unrealized_pnl_lc,
                    SUM(realized_pnl_fc)              AS total_realized_pnl_fc,
                    SUM(COALESCE(uncall_fc, 0))       AS total_uncall_fc,
                    SUM(COALESCE(pipeline_fc, 0))     AS total_pipeline_fc
                FROM {DATABASE}.{TABLE}
                {where}
            """

            results = impala_manager.execute_query(query, database=DATABASE)
            return results[0] if results else {}

        except Exception as e:
            logger.error(f"Error computing position stats: {str(e)}")
            return {}

    def get_distinct_src_systems(self) -> List[str]:
        """Get distinct src_system values for filter dropdown."""
        try:
            query = f"""
                SELECT DISTINCT src_system
                FROM {DATABASE}.{TABLE}
                WHERE src_system IS NOT NULL
                ORDER BY src_system
            """
            results = impala_manager.execute_query(query, database=DATABASE)
            return [r.get('src_system') for r in results if r.get('src_system')]
        except Exception as e:
            logger.error(f"Error fetching src_systems: {str(e)}")
            return []

    def get_distinct_portfolios(self) -> List[str]:
        """Get distinct portfolio values for filter dropdown."""
        try:
            query = f"""
                SELECT DISTINCT portfolio
                FROM {DATABASE}.{TABLE}
                WHERE portfolio IS NOT NULL
                ORDER BY portfolio
                LIMIT 200
            """
            results = impala_manager.execute_query(query, database=DATABASE)
            return [r.get('portfolio') for r in results if r.get('portfolio')]
        except Exception as e:
            logger.error(f"Error fetching portfolios: {str(e)}")
            return []

    def get_max_position_date(self) -> Optional[str]:
        """Return the latest position_date in the table as YYYY-MM-DD, or None."""
        try:
            results = impala_manager.execute_query(
                f"SELECT MAX(position_date) AS max_date FROM {DATABASE}.{TABLE}",
                database=DATABASE,
            )
            if results:
                val = results[0].get('max_date')
                if val:
                    return str(val)[:10]
        except Exception as e:
            logger.error(f"Error fetching max position_date: {e}")
        return None


position_repository = PositionRepository()
