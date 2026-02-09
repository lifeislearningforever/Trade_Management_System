"""
FX Rate Repository for Market Data Module

Fetches daily FX spot rates from gmp_cis.gmp_cis_sta_dly_fx_rates external table.
Data source: BOSET and other market data providers.
Update frequency: Daily

Table Structure (from screenshots):
- SRC_SYSTEM: Source system (e.g., 'gmp')
- SUB_SYSTEM: Sub-system (e.g., 'cis')
- DATA_CAT: Data category (e.g., 'sta')
- DATA_FRQ: Data frequency (e.g., 'dly')
- RECORD_TYPE: Record type (e.g., 'D' for detail)
- SPOT_FLAG: Spot flag (e.g., '1')
- REF_QUOT_CCY: Currency pair reference (e.g., 'USD-AED')
- BASE_CUR: Base currency (e.g., 'AED')
- DATE: Trade date (YYYYMMDD format)
- ASK_RATE: Ask rate
- UNDERLYING_CUR: Quote/underlying currency (e.g., 'USD')
- BID_RATE: Bid rate
- MKTDATA_SET: Market data set (e.g., 'BOSET')
- SPOT_RATE_D: Spot rate / mid rate
- SRC_ID: Source identifier
- PROCESSING_DATE: Processing date partition (YYYYMMDD)

Author: CisTrade Team
Last Updated: 2026-02-08
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from decimal import Decimal

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)


class FXRateHiveRepository:
    """Repository for FX rate operations with Impala/Kudu."""

    TABLE_NAME = "gmp_cis.gmp_cis_sta_dly_fx_rates"

    @staticmethod
    def get_all_fx_rates(
        limit: int = 1000,
        currency_pair: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        base_currency: Optional[str] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve FX rates from external table with filters.

        Args:
            limit: Maximum number of records
            currency_pair: Filter by currency pair (e.g., "USD-AED")
            date_from: Filter by start date (YYYYMMDD format)
            date_to: Filter by end date (YYYYMMDD format)
            base_currency: Filter by base currency (e.g., "USD")
            source: Filter by source/alias (e.g., "BOSET")

        Returns:
            List of FX rate records
        """
        try:
            # Build WHERE clause
            where_clauses = ["record_type = 'D'"]  # Only detail records

            if currency_pair:
                where_clauses.append(f"ref_quot_ccy = '{currency_pair}'")

            if base_currency:
                where_clauses.append(f"underlying_cur = '{base_currency}'")

            if date_from:
                where_clauses.append(f"`date` >= '{date_from}'")

            if date_to:
                where_clauses.append(f"`date` <= '{date_to}'")

            if source:
                where_clauses.append(f"mktdata_set = '{source}'")

            where_clause = " AND ".join(where_clauses)

            # Build query with new column names
            query = f"""
            SELECT
                ref_quot_ccy as currency_pair,
                underlying_cur as base_currency,
                base_cur as quote_currency,
                `date` as trade_date,
                bid_rate,
                ask_rate,
                spot_rate_d as mid_rate,
                mktdata_set as source,
                src_id as reference_id,
                processing_date,
                src_system,
                sub_system,
                data_cat,
                data_frq,
                spot_flag
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY processing_date DESC, `date` DESC, ref_quot_ccy
            LIMIT {limit}
            """

            logger.info(f"Executing FX rate query with filters: {where_clause}")
            results = impala_manager.execute_query(query)

            # Transform trade_date from YYYYMMDD to YYYY-MM-DD for display
            for row in results:
                if row.get('trade_date'):
                    trade_date = str(row['trade_date'])
                    if len(trade_date) == 8:
                        row['trade_date_display'] = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                    else:
                        row['trade_date_display'] = trade_date

                # Calculate spread (ask - bid)
                if row.get('bid_rate') and row.get('ask_rate'):
                    try:
                        bid = Decimal(str(row['bid_rate']))
                        ask = Decimal(str(row['ask_rate']))
                        row['spread'] = float(ask - bid)
                        row['spread_bps'] = float((ask - bid) / bid * 10000) if bid > 0 else 0
                    except (ValueError, TypeError):
                        row['spread'] = None
                        row['spread_bps'] = None

            logger.info(f"Retrieved {len(results)} FX rates")
            return results

        except Exception as e:
            logger.error(f"Error retrieving FX rates: {str(e)}")
            return []

    @staticmethod
    def get_latest_rates(limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get the most recent rate for each currency pair.

        Args:
            limit: Maximum number of currency pairs to return

        Returns:
            List of latest FX rate records by currency pair
        """
        try:
            # Get the most recent trade date first
            date_query = f"""
            SELECT MAX(`date`) as max_date
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
            """

            date_results = impala_manager.execute_query(date_query)
            if not date_results or not date_results[0].get('max_date'):
                logger.warning("No trade dates found in FX rates table")
                return []

            latest_date = date_results[0]['max_date']

            # Get all rates for the latest date
            query = f"""
            SELECT
                ref_quot_ccy as currency_pair,
                underlying_cur as base_currency,
                base_cur as quote_currency,
                `date` as trade_date,
                bid_rate,
                ask_rate,
                spot_rate_d as mid_rate,
                mktdata_set as source,
                src_id as reference_id,
                processing_date,
                src_system,
                sub_system
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND `date` = '{latest_date}'
            ORDER BY ref_quot_ccy
            LIMIT {limit}
            """

            logger.info(f"Retrieving latest FX rates for date: {latest_date}")
            results = impala_manager.execute_query(query)

            # Add formatted date and spread calculations
            for row in results:
                if row.get('trade_date'):
                    trade_date = str(row['trade_date'])
                    if len(trade_date) == 8:
                        row['trade_date_display'] = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                    else:
                        row['trade_date_display'] = trade_date

                # Calculate spread
                if row.get('bid_rate') and row.get('ask_rate'):
                    try:
                        bid = Decimal(str(row['bid_rate']))
                        ask = Decimal(str(row['ask_rate']))
                        row['spread'] = float(ask - bid)
                        row['spread_bps'] = float((ask - bid) / bid * 10000) if bid > 0 else 0
                    except (ValueError, TypeError):
                        row['spread'] = None
                        row['spread_bps'] = None

            logger.info(f"Retrieved {len(results)} latest FX rates for {latest_date}")
            return results

        except Exception as e:
            logger.error(f"Error getting latest FX rates: {str(e)}")
            return []

    @staticmethod
    def get_rate_history(currency_pair: str, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get rate history for a specific currency pair.

        Args:
            currency_pair: Currency pair (e.g., "USD-AED")
            days: Number of days of history to retrieve (limits result count, not date range)

        Returns:
            List of historical FX rates sorted by date descending (most recent first)
        """
        try:
            # Get latest records for the currency pair
            # Note: 'days' parameter limits the number of records, not the date range
            # This allows viewing historical data regardless of when it was loaded
            query = f"""
            SELECT
                ref_quot_ccy as currency_pair,
                underlying_cur as base_currency,
                base_cur as quote_currency,
                `date` as trade_date,
                bid_rate,
                ask_rate,
                spot_rate_d as mid_rate,
                mktdata_set as source,
                src_id as reference_id,
                processing_date,
                src_system,
                sub_system
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND ref_quot_ccy = '{currency_pair}'
            ORDER BY processing_date DESC, `date` DESC
            LIMIT {days}
            """

            logger.info(f"Retrieving latest {days} records for {currency_pair}")
            results = impala_manager.execute_query(query)

            # Add formatted date and spread calculations
            for row in results:
                if row.get('trade_date'):
                    trade_date = str(row['trade_date'])
                    if len(trade_date) == 8:
                        row['trade_date_display'] = f"{trade_date[0:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
                    else:
                        row['trade_date_display'] = trade_date

                # Calculate spread
                if row.get('bid_rate') and row.get('ask_rate'):
                    try:
                        bid = Decimal(str(row['bid_rate']))
                        ask = Decimal(str(row['ask_rate']))
                        row['spread'] = float(ask - bid)
                        row['spread_bps'] = float((ask - bid) / bid * 10000) if bid > 0 else 0
                    except (ValueError, TypeError):
                        row['spread'] = None
                        row['spread_bps'] = None

            logger.info(f"Retrieved {len(results)} historical rates for {currency_pair}")
            return results

        except Exception as e:
            logger.error(f"Error getting rate history for {currency_pair}: {str(e)}")
            return []

    @staticmethod
    def get_currency_pairs() -> List[str]:
        """
        Get list of unique currency pairs.

        Returns:
            List of unique currency pairs sorted alphabetically
        """
        try:
            query = f"""
            SELECT DISTINCT ref_quot_ccy as currency_pair
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND ref_quot_ccy IS NOT NULL
            ORDER BY ref_quot_ccy
            """

            logger.info("Retrieving unique currency pairs")
            results = impala_manager.execute_query(query)

            pairs = [row['currency_pair'] for row in results if row.get('currency_pair')]

            logger.info(f"Found {len(pairs)} unique currency pairs")
            return pairs

        except Exception as e:
            logger.error(f"Error getting currency pairs: {str(e)}")
            return []

    @staticmethod
    def get_base_currencies() -> List[str]:
        """
        Get list of unique base currencies.

        Returns:
            List of unique base currency codes sorted alphabetically
        """
        try:
            query = f"""
            SELECT DISTINCT underlying_cur as base_currency
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND underlying_cur IS NOT NULL
            ORDER BY underlying_cur
            """

            logger.info("Retrieving unique base currencies")
            results = impala_manager.execute_query(query)

            currencies = [row['base_currency'] for row in results if row.get('base_currency')]

            logger.info(f"Found {len(currencies)} unique base currencies")
            return currencies

        except Exception as e:
            logger.error(f"Error getting base currencies: {str(e)}")
            return []

    @staticmethod
    def get_sources() -> List[str]:
        """
        Get list of unique data sources.

        Returns:
            List of unique source/alias values
        """
        try:
            query = f"""
            SELECT DISTINCT mktdata_set as source
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND mktdata_set IS NOT NULL
            ORDER BY mktdata_set
            """

            logger.info("Retrieving unique data sources")
            results = impala_manager.execute_query(query)

            sources = [row['source'] for row in results if row.get('source')]

            logger.info(f"Found {len(sources)} unique data sources")
            return sources

        except Exception as e:
            logger.error(f"Error getting data sources: {str(e)}")
            return []

    @staticmethod
    def get_statistics() -> Dict[str, Any]:
        """
        Get FX rate statistics from external table.

        Returns:
            Dictionary with FX rate statistics
        """
        try:
            # Get overall statistics
            stats_query = f"""
            SELECT
                COUNT(*) as total_records,
                COUNT(DISTINCT ref_quot_ccy) as unique_pairs,
                COUNT(DISTINCT mktdata_set) as unique_sources,
                MAX(`date`) as latest_date,
                MIN(`date`) as earliest_date,
                MAX(processing_date) as latest_processing_date,
                MIN(processing_date) as earliest_processing_date,
                COUNT(DISTINCT processing_date) as processing_date_count
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
            """

            logger.info("Retrieving FX rate statistics")
            stats_results = impala_manager.execute_query(stats_query)

            if not stats_results:
                return {
                    'total_records': 0,
                    'unique_pairs': 0,
                    'unique_sources': 0,
                    'latest_date': 'N/A',
                    'earliest_date': 'N/A',
                    'source_breakdown': []
                }

            stats = stats_results[0]

            # Format dates
            latest_date = str(stats.get('latest_date', 'N/A'))
            if len(latest_date) == 8:
                latest_date = f"{latest_date[0:4]}-{latest_date[4:6]}-{latest_date[6:8]}"

            earliest_date = str(stats.get('earliest_date', 'N/A'))
            if len(earliest_date) == 8:
                earliest_date = f"{earliest_date[0:4]}-{earliest_date[4:6]}-{earliest_date[6:8]}"

            # Format processing dates
            latest_proc_date = str(stats.get('latest_processing_date', 'N/A'))
            if len(latest_proc_date) == 8:
                latest_proc_date = f"{latest_proc_date[0:4]}-{latest_proc_date[4:6]}-{latest_proc_date[6:8]}"

            earliest_proc_date = str(stats.get('earliest_processing_date', 'N/A'))
            if len(earliest_proc_date) == 8:
                earliest_proc_date = f"{earliest_proc_date[0:4]}-{earliest_proc_date[4:6]}-{earliest_proc_date[6:8]}"

            # Get source breakdown
            source_query = f"""
            SELECT
                mktdata_set as source,
                COUNT(*) as record_count
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
            GROUP BY mktdata_set
            ORDER BY record_count DESC
            """

            source_results = impala_manager.execute_query(source_query)

            # Get processing date breakdown
            proc_date_query = f"""
            SELECT
                processing_date,
                COUNT(*) as record_count,
                COUNT(DISTINCT ref_quot_ccy) as pair_count
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
            GROUP BY processing_date
            ORDER BY processing_date DESC
            """

            proc_date_results = impala_manager.execute_query(proc_date_query)

            return {
                'total_records': stats.get('total_records', 0),
                'unique_pairs': stats.get('unique_pairs', 0),
                'unique_sources': stats.get('unique_sources', 0),
                'latest_date': latest_date,
                'earliest_date': earliest_date,
                'latest_processing_date': latest_proc_date,
                'earliest_processing_date': earliest_proc_date,
                'processing_date_count': stats.get('processing_date_count', 0),
                'source_breakdown': source_results if source_results else [],
                'processing_date_breakdown': proc_date_results if proc_date_results else []
            }

        except Exception as e:
            logger.error(f"Error getting FX rate statistics: {str(e)}")
            return {
                'total_records': 0,
                'unique_pairs': 0,
                'unique_sources': 0,
                'latest_date': 'N/A',
                'earliest_date': 'N/A',
                'source_breakdown': []
            }

    @staticmethod
    def get_rate_by_date_and_pair(trade_date: str, currency_pair: str) -> Optional[Dict[str, Any]]:
        """
        Get specific FX rate for a date and currency pair.

        Args:
            trade_date: Trade date in YYYYMMDD format
            currency_pair: Currency pair (e.g., "USD-AED")

        Returns:
            FX rate record or None if not found
        """
        try:
            query = f"""
            SELECT
                ref_quot_ccy as currency_pair,
                underlying_cur as base_currency,
                base_cur as quote_currency,
                `date` as trade_date,
                bid_rate,
                ask_rate,
                spot_rate_d as mid_rate,
                mktdata_set as source,
                src_id as reference_id,
                processing_date,
                src_system,
                sub_system
            FROM {FXRateHiveRepository.TABLE_NAME}
            WHERE record_type = 'D'
              AND `date` = '{trade_date}'
              AND ref_quot_ccy = '{currency_pair}'
            ORDER BY processing_date DESC
            LIMIT 1
            """

            logger.info(f"Retrieving FX rate for {currency_pair} on {trade_date}")
            results = impala_manager.execute_query(query)

            if not results:
                logger.warning(f"No FX rate found for {currency_pair} on {trade_date}")
                return None

            row = results[0]

            # Add formatted date
            if row.get('trade_date'):
                trade_date_val = str(row['trade_date'])
                if len(trade_date_val) == 8:
                    row['trade_date_display'] = f"{trade_date_val[0:4]}-{trade_date_val[4:6]}-{trade_date_val[6:8]}"
                else:
                    row['trade_date_display'] = trade_date_val

            # Calculate spread
            if row.get('bid_rate') and row.get('ask_rate'):
                try:
                    bid = Decimal(str(row['bid_rate']))
                    ask = Decimal(str(row['ask_rate']))
                    row['spread'] = float(ask - bid)
                    row['spread_bps'] = float((ask - bid) / bid * 10000) if bid > 0 else 0
                except (ValueError, TypeError):
                    row['spread'] = None
                    row['spread_bps'] = None

            return row

        except Exception as e:
            logger.error(f"Error getting FX rate for {currency_pair} on {trade_date}: {str(e)}")
            return None


# Singleton instance
fx_rate_hive_repository = FXRateHiveRepository()
