"""
System Date Repository

Reads system/settlement dates from the GMP reference table
gmp_cis_sta_dly_alldatesinfo, using the row with the latest
processing_date (src_system='gmp', sub_system='cis', data_frq='dly',
record_type='D').

Column mapping to service-layer dict keys:
  contextual_today  → system_date   (business date T, YYYYMMDD)
  prev_day          → report_date   (T-1, YYYYMMDD)
  processing_date   → processing_date
  settlement_t1     → settlement_t1
  settlement_t2     → settlement_t2 (default settle date for trades)
  reporting_date    → reporting_date
"""

import logging
from typing import Optional, Dict, Any

from core.repositories.impala_connection import impala_manager

logger = logging.getLogger(__name__)

DATABASE = 'gmp_cis'
ALLDATES_TABLE = 'gmp_cis_sta_dly_alldatesinfo'

_FILTER = (
    "src_system = 'gmp' "
    "AND sub_system = 'cis' "
    "AND data_frq = 'dly' "
    "AND record_type = 'D'"
)


class SystemDateRepository:
    """Read-only repository for system date from gmp_cis_sta_dly_alldatesinfo."""

    @staticmethod
    def get_current_system_date() -> Optional[Dict[str, Any]]:
        """
        Return the most recent date row from gmp_cis_sta_dly_alldatesinfo.

        Uses MAX(processing_date) to pick the latest loaded row.

        Returns dict with keys:
            system_date, report_date, processing_date,
            settlement_t1, settlement_t2, reporting_date,
            is_business_day, loaded_at
        """
        try:
            query = f"""
                SELECT
                    contextual_today  AS system_date,
                    prev_day          AS report_date,
                    processing_date,
                    settlement_t1,
                    settlement_t2,
                    reporting_date,
                    processing_date   AS loaded_at
                FROM {DATABASE}.{ALLDATES_TABLE}
                WHERE {_FILTER}
                  AND processing_date = (
                      SELECT MAX(processing_date)
                      FROM {DATABASE}.{ALLDATES_TABLE}
                      WHERE {_FILTER}
                  )
                LIMIT 1
            """

            results = impala_manager.execute_query(query, database=DATABASE)

            if results:
                row = results[0]
                row['is_business_day'] = True   # alldatesinfo only has business days
                row['source_file'] = ALLDATES_TABLE
                return row

            logger.warning("No date row found in %s.%s", DATABASE, ALLDATES_TABLE)
            return None

        except Exception as e:
            logger.error("Error reading system date from alldatesinfo: %s", e)
            return None


# Singleton instance
system_date_repository = SystemDateRepository()
