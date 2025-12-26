"""
FX Rate Hive Repository
Fetches FX rate data from Hive fx_rates table.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import subprocess

logger = logging.getLogger(__name__)


class HiveConnection:
    """Manages Hive database connections for FX rate data using beeline."""

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

            logger.info(f"FX Rate query executed successfully: {len(results)} records")
            return results

        except subprocess.TimeoutExpired:
            logger.error(f"Beeline query timeout")
            return []
        except Exception as e:
            logger.error(f"Error executing FX rate query: {str(e)}")
            return []


class FXRateHiveRepository:
    """Repository for FX rate operations with Hive."""

    @staticmethod
    def get_all_fx_rates(
        limit: int = 1000,
        currency_pair: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve FX rates from Hive with filters.

        Args:
            limit: Maximum number of records
            currency_pair: Filter by currency pair (e.g., "USD/EUR")
            date_from: Filter by start date (YYYY-MM-DD)
            date_to: Filter by end date (YYYY-MM-DD)
            source: Filter by source

        Returns:
            List of FX rate records
        """
        try:
            # Build WHERE clause
            where_clauses = []

            if currency_pair:
                where_clauses.append(f"currency_pair = '{currency_pair}'")

            if date_from:
                where_clauses.append(f"rate_date >= '{date_from}'")

            if date_to:
                where_clauses.append(f"rate_date <= '{date_to}'")

            if source:
                where_clauses.append(f"source = '{source}'")

            where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"

            # Build query
            query = f"""
            SELECT currency_pair, base_currency, quote_currency,
                   rate, bid_rate, ask_rate, mid_rate,
                   rate_date, rate_time, source, is_active,
                   created_at, updated_at
            FROM fx_rates
            WHERE {where_clause}
            LIMIT {limit}
            """

            results = HiveConnection.execute_query(query)

            # Sort in Python (avoid ORDER BY due to Hive limitations)
            if results:
                results.sort(key=lambda x: (x.get('rate_date', ''), x.get('rate_time', '')), reverse=True)

            return results

        except Exception as e:
            logger.error(f"Error retrieving FX rates: {str(e)}")
            return []

    @staticmethod
    def get_latest_rates() -> List[Dict[str, Any]]:
        """
        Get the most recent rate for each currency pair.

        Returns:
            List of latest FX rate records by currency pair
        """
        try:
            # Get all rates and deduplicate in Python
            query = """
            SELECT currency_pair, base_currency, quote_currency,
                   rate, bid_rate, ask_rate, mid_rate,
                   rate_date, rate_time, source, is_active,
                   created_at, updated_at
            FROM fx_rates
            WHERE is_active = 'true'
            """

            all_results = HiveConnection.execute_query(query)

            # Group by currency_pair and keep only latest
            latest_rates = {}
            for row in all_results:
                pair = row.get('currency_pair')
                rate_datetime = f"{row.get('rate_date', '')} {row.get('rate_time', '')}"

                if pair not in latest_rates:
                    latest_rates[pair] = row
                else:
                    existing_datetime = f"{latest_rates[pair].get('rate_date', '')} {latest_rates[pair].get('rate_time', '')}"
                    if rate_datetime > existing_datetime:
                        latest_rates[pair] = row

            results = list(latest_rates.values())
            results.sort(key=lambda x: x.get('currency_pair', ''))

            logger.info(f"Retrieved {len(results)} latest FX rates")
            return results

        except Exception as e:
            logger.error(f"Error getting latest FX rates: {str(e)}")
            return []

    @staticmethod
    def get_rate_history(currency_pair: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get rate history for a specific currency pair.

        Args:
            currency_pair: Currency pair (e.g., "USD/EUR")
            days: Number of days of history to retrieve

        Returns:
            List of historical FX rates
        """
        try:
            # Calculate date range
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)

            query = f"""
            SELECT currency_pair, base_currency, quote_currency,
                   rate, bid_rate, ask_rate, mid_rate,
                   rate_date, rate_time, source, is_active,
                   created_at, updated_at
            FROM fx_rates
            WHERE currency_pair = '{currency_pair}'
              AND rate_date >= '{start_date}'
              AND rate_date <= '{end_date}'
            """

            results = HiveConnection.execute_query(query)

            # Sort by date ascending
            if results:
                results.sort(key=lambda x: (x.get('rate_date', ''), x.get('rate_time', '')))

            logger.info(f"Retrieved {len(results)} historical rates for {currency_pair}")
            return results

        except Exception as e:
            logger.error(f"Error getting rate history for {currency_pair}: {str(e)}")
            return []

    @staticmethod
    def get_currencies() -> List[str]:
        """
        Get list of unique currencies from FX rates.

        Returns:
            List of unique currency codes
        """
        try:
            # Get all base and quote currencies
            query = """
            SELECT base_currency, quote_currency
            FROM fx_rates
            """

            results = HiveConnection.execute_query(query)

            # Collect unique currencies
            currencies = set()
            for row in results:
                if row.get('base_currency'):
                    currencies.add(row['base_currency'])
                if row.get('quote_currency'):
                    currencies.add(row['quote_currency'])

            return sorted(list(currencies))

        except Exception as e:
            logger.error(f"Error getting currencies: {str(e)}")
            return []

    @staticmethod
    def get_currency_pairs() -> List[str]:
        """
        Get list of unique currency pairs.

        Returns:
            List of unique currency pairs
        """
        try:
            query = "SELECT currency_pair FROM fx_rates"
            results = HiveConnection.execute_query(query)

            pairs = set([row['currency_pair'] for row in results if row.get('currency_pair')])
            return sorted(list(pairs))

        except Exception as e:
            logger.error(f"Error getting currency pairs: {str(e)}")
            return []

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get FX rate statistics from Hive.

        Returns:
            Dictionary with FX rate statistics
        """
        try:
            # Fetch all rates and calculate statistics in Python
            all_query = "SELECT currency_pair, source, rate_date FROM fx_rates"
            all_results = HiveConnection.execute_query(all_query)

            # Calculate statistics
            total_rates = len(all_results)
            unique_pairs = len(set([r.get('currency_pair') for r in all_results if r.get('currency_pair')]))
            unique_sources = len(set([r.get('source') for r in all_results if r.get('source')]))

            # Latest update
            dates = [r.get('rate_date', '') for r in all_results if r.get('rate_date')]
            latest_update = max(dates) if dates else 'N/A'

            # Source breakdown
            source_counts = {}
            for row in all_results:
                src = row.get('source', 'Unknown')
                source_counts[src] = source_counts.get(src, 0) + 1

            return {
                'total_rates': total_rates,
                'unique_pairs': unique_pairs,
                'data_sources': unique_sources,
                'latest_update': latest_update,
                'source_breakdown': [
                    {'source': k, 'count': v}
                    for k, v in sorted(source_counts.items())
                ]
            }

        except Exception as e:
            logger.error(f"Error getting FX rate statistics: {str(e)}")
            return {
                'total_rates': 0,
                'unique_pairs': 0,
                'data_sources': 0,
                'latest_update': 'N/A',
                'source_breakdown': []
            }


# Singleton instance
fx_rate_hive_repository = FXRateHiveRepository()
