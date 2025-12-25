"""
Portfolio Hive Repository
Fetches portfolio data from Hive cis_portfolio table.
"""

from typing import List, Dict, Any, Optional
from pyhive import hive
import logging
import subprocess
import tempfile
import csv as csv_module

logger = logging.getLogger(__name__)


class HiveConnection:
    """Manages Hive database connections for portfolio data using beeline."""

    @staticmethod
    def execute_query(query: str) -> List[Dict[str, Any]]:
        """
        Execute Hive query using beeline and return results.
        Works around PyHive connection issues with Hive 4.x.

        Args:
            query: SQL query to execute

        Returns:
            List of dictionaries with query results
        """
        try:
            # Execute via beeline - output format flags are ignored, returns table format
            result = subprocess.run(
                [
                    '/usr/local/bin/beeline',
                    '-u', 'jdbc:hive2://localhost:10000/cis',
                    '-e', query,
                    '--silent=true'
                ],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.error(f"Beeline query error: {result.stderr}")
                return []

            # Parse table format output
            lines = result.stdout.strip().split('\n')
            if not lines:
                return []

            # Filter out non-data lines and find table rows
            table_lines = []
            for line in lines:
                # Skip log messages, separators, and metadata
                if (line.startswith('SLF4J') or line.startswith('2025-') or
                    line.startswith('WARN') or line.startswith('INFO') or
                    line.startswith('Connecting') or line.startswith('Connected') or
                    line.startswith('Driver') or line.startswith('Transaction') or
                    line.startswith('Beeline') or line.startswith('Closing') or
                    line.strip().startswith('Please remove') or
                    line.strip().startswith('See http') or
                    'rows selected' in line or
                    not line.strip()):
                    continue
                # Skip separator lines like +----+----+
                if line.strip().startswith('+') and line.strip().endswith('+'):
                    continue
                # Keep lines with | delimiters (header and data rows)
                if '|' in line:
                    table_lines.append(line)

            if len(table_lines) < 2:  # Need at least header and one data row
                return []

            # Parse header (first line with |)
            header_line = table_lines[0]
            headers = [col.strip() for col in header_line.split('|')[1:-1]]  # Skip first and last empty strings

            # Parse data rows
            results = []
            for data_line in table_lines[1:]:
                values = [val.strip() for val in data_line.split('|')[1:-1]]
                if len(values) == len(headers):
                    row_dict = {}
                    for i, header in enumerate(headers):
                        # Clean column names (remove table prefixes)
                        clean_key = header.split('.')[-1] if '.' in header else header
                        row_dict[clean_key] = values[i]
                    results.append(row_dict)

            logger.info(f"Portfolio query executed successfully: {len(results)} records")
            return results

        except subprocess.TimeoutExpired:
            logger.error(f"Beeline query timeout")
            return []
        except Exception as e:
            logger.error(f"Error executing portfolio query: {str(e)}")
            return []


class PortfolioHiveRepository:
    """Repository for portfolio operations with Hive."""

    @staticmethod
    def get_all_portfolios(
        limit: int = 100,
        status: Optional[str] = None,
        currency: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve portfolios from Hive with filters.

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
                where_clauses.append(f"status = '{status}'")

            if currency:
                where_clauses.append(f"currency = '{currency}'")

            if search:
                search_term = search.replace("'", "''")
                where_clauses.append(
                    f"(name LIKE '%{search_term}%' OR "
                    f"description LIKE '%{search_term}%')"
                )

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Build query
            query = f"""
            SELECT name, description, currency, manager, portfolio_client,
                   cash_balance, status, cost_centre_code, corp_code,
                   account_group, portfolio_group, report_group, entity_group,
                   revaluation_status, created_at, updated_at
            FROM cis_portfolio
            WHERE {where_clause}
            LIMIT {limit}
            """

            results = HiveConnection.execute_query(query)

            # Sort in Python (avoid ORDER BY due to Hive limitations)
            if results:
                results.sort(key=lambda x: x.get('name', ''))

            return results

        except Exception as e:
            logger.error(f"Error retrieving portfolios: {str(e)}")
            return []

    @staticmethod
    def get_portfolio_statistics() -> Dict[str, Any]:
        """
        Get portfolio statistics from Hive.

        Returns:
            Dictionary with portfolio statistics
        """
        try:
            # COUNT(*) not working in Hive 4.x - fetch all and count in Python
            all_query = "SELECT status, currency FROM cis_portfolio"
            all_result = HiveConnection.execute_query(all_query)

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
            logger.error(f"Error getting portfolio statistics: {str(e)}")
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
            # DISTINCT not working in Hive 4.x - fetch all and deduplicate in Python
            query = "SELECT currency FROM cis_portfolio"
            results = HiveConnection.execute_query(query)
            currencies = set([row['currency'] for row in results if row.get('currency')])
            return sorted(list(currencies))
        except Exception as e:
            logger.error(f"Error getting currencies: {str(e)}")
            return []


# Singleton instance
portfolio_hive_repository = PortfolioHiveRepository()
